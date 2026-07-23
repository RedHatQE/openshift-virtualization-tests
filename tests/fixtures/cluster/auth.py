"""Cluster authentication and identity-provider fixtures."""

import logging
import os
import shutil
import tempfile

import bcrypt
import pytest
import yaml
from ocp_resources.daemonset import DaemonSet
from ocp_resources.oauth import OAuth
from ocp_resources.resource import ResourceEditor, get_client
from ocp_resources.secret import Secret
from pytest_testconfig import config as py_config
from timeout_sampler import TimeoutSampler

from utilities.cluster import cache_admin_client, get_oc_whoami_username
from utilities.constants.cluster import KUBECONFIG, UTILITY
from utilities.constants.components import CLUSTER
from utilities.constants.namespaces import NamespacesNames
from utilities.constants.pytest import UNPRIVILEGED_PASSWORD, UNPRIVILEGED_USER
from utilities.constants.timeouts import TIMEOUT_4MIN
from utilities.data_utils import base64_encode_str
from utilities.infra import get_deployment_by_name, login_with_user_password

LOGGER = logging.getLogger(__name__)

HTTP_SECRET_NAME = "htpass-secret-for-cnv-tests"
HTPASSWD_PROVIDER_DICT = {
    "name": "htpasswd_provider",
    "mappingMethod": "claim",
    "type": "HTPasswd",
    "htpasswd": {"fileData": {"name": HTTP_SECRET_NAME}},
}
ACCESS_TOKEN = {
    "accessTokenMaxAgeSeconds": 604800,
    "accessTokenInactivityTimeout": None,
}


@pytest.fixture(scope="session")
def kubeconfig_export_path():
    return os.environ.get(KUBECONFIG)


@pytest.fixture(scope="session")
def admin_client():
    """Get DynamicClient"""
    return cache_admin_client()


@pytest.fixture(scope="session")
def skip_unprivileged_client():
    # To disable unprivileged_client pass --tc=no_unprivileged_client:True to pytest commandline.
    return py_config.get("no_unprivileged_client")


@pytest.fixture(scope="session")
def identity_provider_config(skip_unprivileged_client, admin_client):
    if skip_unprivileged_client:
        return

    return OAuth(client=admin_client, name=CLUSTER)


@pytest.fixture(scope="session")
def exported_kubeconfig(unprivileged_secret, kubeconfig_export_path):
    if not unprivileged_secret:
        yield

    else:
        kube_config_path = os.path.join(os.path.expanduser("~"), ".kube/config")

        if os.path.isfile(kube_config_path) and kubeconfig_export_path:
            LOGGER.warning(
                f"Both {KUBECONFIG} {kubeconfig_export_path} and {kube_config_path} exist. "
                f"{kubeconfig_export_path} is used as kubeconfig source for this run."
            )

        orig_kubeconfig_file_path = kubeconfig_export_path or kube_config_path

        tests_kubeconfig_dir_path = tempfile.mkdtemp(suffix="-cnv-tests-kubeconfig")
        LOGGER.info(f"Setting {KUBECONFIG} dir for this run to point to: {tests_kubeconfig_dir_path}")

        kubeconfig_file_dest_path = os.path.join(tests_kubeconfig_dir_path, KUBECONFIG.lower())

        LOGGER.info(f"Copy {KUBECONFIG} to {kubeconfig_file_dest_path}")
        shutil.copyfile(src=orig_kubeconfig_file_path, dst=kubeconfig_file_dest_path)

        LOGGER.info(f"Set: {KUBECONFIG}={kubeconfig_file_dest_path}")
        os.environ[KUBECONFIG] = kubeconfig_file_dest_path

        yield kubeconfig_file_dest_path

        LOGGER.info(f"Remove: {kubeconfig_file_dest_path}")
        shutil.rmtree(tests_kubeconfig_dir_path, ignore_errors=True)

        if kubeconfig_export_path:
            LOGGER.info(f"Set: {KUBECONFIG}={kubeconfig_export_path}")
            os.environ[KUBECONFIG] = kubeconfig_export_path

        else:
            del os.environ[KUBECONFIG]


@pytest.fixture(scope="session")
def unprivileged_secret(admin_client, skip_unprivileged_client):
    if skip_unprivileged_client:
        yield

    else:
        password = UNPRIVILEGED_PASSWORD.encode()
        enc_password = bcrypt.hashpw(password, bcrypt.gensalt(5, prefix=b"2a")).decode()
        crypto_credentials = f"{UNPRIVILEGED_USER}:{enc_password}"
        with Secret(
            name=HTTP_SECRET_NAME,
            namespace=NamespacesNames.OPENSHIFT_CONFIG,
            htpasswd=base64_encode_str(text=crypto_credentials),
            client=admin_client,
        ) as secret:
            yield secret

        #  Wait for oauth-openshift deployment to update after removing htpass-secret
        _wait_for_oauth_openshift_deployment(admin_client=admin_client)


@pytest.fixture(scope="session")
def identity_provider_with_htpasswd(skip_unprivileged_client, admin_client, identity_provider_config):
    if skip_unprivileged_client:
        yield
    else:
        identity_provider_config_editor = ResourceEditor(
            patches={
                identity_provider_config: {
                    "metadata": {"name": identity_provider_config.name},
                    "spec": {
                        "identityProviders": [HTPASSWD_PROVIDER_DICT],
                        "tokenConfig": ACCESS_TOKEN,
                    },
                }
            }
        )
        identity_provider_config_editor.update(backup_resources=True)
        _wait_for_oauth_openshift_deployment(admin_client=admin_client)
        yield
        identity_provider_config_editor.restore()


@pytest.fixture(scope="session")
def unprivileged_client(
    skip_unprivileged_client,
    admin_client,
    unprivileged_secret,
    identity_provider_with_htpasswd,
    exported_kubeconfig,
):
    """Provides none privilege API client"""
    if skip_unprivileged_client:
        LOGGER.info("no_unprivileged_client was set, using admin_client")
        yield admin_client

    else:
        current_user = get_oc_whoami_username()
        if login_with_user_password(
            api_address=admin_client.configuration.host,
            user=UNPRIVILEGED_USER,
            password=UNPRIVILEGED_PASSWORD,
        ):  # Login to an unprivileged account
            with open(exported_kubeconfig) as fd:
                kubeconfig_content = yaml.safe_load(fd)
            unprivileged_context = kubeconfig_content["current-context"]

            # Get back to an admin account
            login_with_user_password(
                api_address=admin_client.configuration.host,
                user=current_user.strip(),
            )
            yield get_client(config_file=exported_kubeconfig, context=unprivileged_context)

        else:
            yield admin_client


@pytest.fixture(scope="session")
def leftovers_cleanup(admin_client, cnv_tests_utilities_namespace, identity_provider_config):
    LOGGER.info("Checking for leftover resources")
    secret = Secret(
        client=admin_client,
        name=HTTP_SECRET_NAME,
        namespace=NamespacesNames.OPENSHIFT_CONFIG,
    )
    ds = None
    if cnv_tests_utilities_namespace:
        ds = DaemonSet(
            client=admin_client,
            name=UTILITY,
            namespace=cnv_tests_utilities_namespace.name,
        )
    #  Delete Secret and DaemonSet created by us.
    for resource_ in (secret, ds):
        if resource_ and resource_.exists:
            resource_.delete(wait=True)

    #  Remove leftovers from OAuth
    if not identity_provider_config:
        # When running CI (k8s) OAuth is not exists on the cluster.
        LOGGER.warning("OAuth does not exist on the cluster")
        return

    identity_providers_spec = identity_provider_config.instance.to_dict()["spec"]
    identity_providers_token = identity_providers_spec.get("tokenConfig")
    identity_providers = identity_providers_spec.get("identityProviders", [])

    if ACCESS_TOKEN == identity_providers_token:
        identity_providers_spec["tokenConfig"] = None

    if HTPASSWD_PROVIDER_DICT in identity_providers:
        identity_providers.pop(identity_providers.index(HTPASSWD_PROVIDER_DICT))
        identity_providers_spec["identityProviders"] = identity_providers or None

    r_editor = ResourceEditor(
        patches={
            identity_provider_config: {
                "metadata": {"name": identity_provider_config.name},
                "spec": identity_providers_spec,
            }
        }
    )
    r_editor.update()


def _wait_for_oauth_openshift_deployment(admin_client):
    dp = get_deployment_by_name(
        deployment_name="oauth-openshift",
        namespace_name="openshift-authentication",
        admin_client=admin_client,
    )

    _log = f"Wait for {dp.name} -> Type: Progressing -> Reason:"

    def _wait_sampler(_reason):
        sampler = TimeoutSampler(
            wait_timeout=TIMEOUT_4MIN,
            sleep=1,
            func=lambda: dp.instance.status.conditions,
        )
        for sample in sampler:
            for _spl in sample:
                if _spl.type == "Progressing" and _spl.reason == _reason:
                    return

    for reason in ("ReplicaSetUpdated", "NewReplicaSetAvailable"):
        LOGGER.info(f"{_log} {reason}")
        _wait_sampler(_reason=reason)

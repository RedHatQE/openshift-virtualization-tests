"""Cluster utility daemonset and service-account fixtures."""

import logging

import pytest
from ocp_resources.daemonset import DaemonSet
from ocp_resources.resource import ResourceEditor
from ocp_resources.secret import Secret
from ocp_resources.service_account import ServiceAccount

from tests.fixtures.cluster.auth import ACCESS_TOKEN, HTPASSWD_PROVIDER_DICT, HTTP_SECRET_NAME
from utilities.constants.cluster import CNV_TEST_SERVICE_ACCOUNT, UTILITY
from utilities.constants.namespaces import NamespacesNames
from utilities.infra import (
    add_scc_to_service_account,
    generate_openshift_pull_secret_file,
    get_daemonset_yaml_file_with_image_hash,
    get_utility_pods_from_nodes,
)

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def generated_pulled_secret(
    is_production_source,
    installing_cnv,
    admin_client,
):
    if is_production_source and installing_cnv:
        return
    return generate_openshift_pull_secret_file()


@pytest.fixture(scope="session")
def cnv_tests_utilities_service_account(admin_client, cnv_tests_utilities_namespace, installing_cnv):
    if installing_cnv:
        yield
    else:
        with ServiceAccount(
            client=admin_client,
            name=CNV_TEST_SERVICE_ACCOUNT,
            namespace=cnv_tests_utilities_namespace.name,
        ) as service_account:
            add_scc_to_service_account(
                namespace=cnv_tests_utilities_namespace.name,
                scc_name="privileged",
                sa_name=service_account.name,
            )
            yield service_account


@pytest.fixture(scope="session")
def utility_daemonset(
    admin_client,
    installing_cnv,
    generated_pulled_secret,
    cnv_tests_utilities_namespace,
    cnv_tests_utilities_service_account,
):
    """
    Deploy utility daemonset into the cnv-tests-utilities namespace.

    This daemonset deploys a pod on every node with hostNetwork and the main usage is to run commands on the hosts.
    For example to create linux bridge and other components related to the host configuration.
    """
    if installing_cnv:
        yield
    else:
        modified_ds_yaml_file = get_daemonset_yaml_file_with_image_hash(
            generated_pulled_secret=generated_pulled_secret,
            service_account=cnv_tests_utilities_service_account,
        )
        with DaemonSet(client=admin_client, yaml_file=modified_ds_yaml_file) as ds:
            ds.wait_until_deployed()
            yield ds


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


@pytest.fixture(scope="session")
def workers_utility_pods(admin_client, workers, utility_daemonset, installing_cnv):
    """
    Get utility pods from worker nodes.
    When the tests start we deploy a pod on every worker node in the cluster using a daemonset.
    These pods have a label of cnv-test=utility and they are privileged pods with hostnetwork=true
    """
    if installing_cnv:
        return None
    return get_utility_pods_from_nodes(
        nodes=workers,
        admin_client=admin_client,
        label_selector="cnv-test=utility",
    )


@pytest.fixture(scope="session")
def control_plane_utility_pods(admin_client, installing_cnv, control_plane_nodes, utility_daemonset):
    """
    Get utility pods from control plane nodes.
    When the tests start we deploy a pod on every control plane node in the cluster using a daemonset.
    These pods have a label of cnv-test=utility and they are privileged pods with hostnetwork=true
    """
    if installing_cnv:
        return None
    return get_utility_pods_from_nodes(
        nodes=control_plane_nodes,
        admin_client=admin_client,
        label_selector="cnv-test=utility",
    )

import logging
import os
import ssl
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass

import requests
from kubernetes.dynamic import DynamicClient
from ocp_resources.config_map import ConfigMap
from ocp_resources.secret import Secret
from pytest_testconfig import config as py_config
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from utilities.constants.timeouts import (
    TIMEOUT_1MIN,
    TIMEOUT_5SEC,
)
from utilities.data_utils import base64_encode_str

LOGGER = logging.getLogger(__name__)

ARTIFACTORY_SECRET_NAME = "cnv-tests-artifactory-secret"
ARTIFACTORY_CONFIG_MAP_NAME = "artifactory-configmap"
BASE_ARTIFACTORY_LOCATION = "artifactory/cnv-qe-server-local"


@dataclass(frozen=True)
class ArtifactoryCredentials:
    """Namespace-scoped Artifactory Secret and/or TLS ConfigMap.

    Attributes:
        secret: Artifactory Secret when created; None if ``create_secret=False``.
        config_map: Artifactory ConfigMap when created; None if ``create_config_map=False``.
    """

    secret: Secret | None = None
    config_map: ConfigMap | None = None

    @property
    def secret_name(self) -> str:
        """Return the Artifactory Secret name.

        Returns:
            str: Name of the created Secret.

        Raises:
            ValueError: If the Secret was not created (``create_secret=False``).
        """
        if self.secret is None:
            raise ValueError("Artifactory secret was not created")
        return self.secret.name

    @property
    def cert_configmap_name(self) -> str:
        """Return the Artifactory ConfigMap name.

        Returns:
            str: Name of the created ConfigMap.

        Raises:
            ValueError: If the ConfigMap was not created (``create_config_map=False``).
        """
        if self.config_map is None:
            raise ValueError("Artifactory ConfigMap was not created")
        return self.config_map.name


def get_test_artifact_server_url(schema: str = "https") -> str:  # type: ignore[return]
    """
    Verify https server server connectivity (regardless of schema).
    Return the requested "registry" or "https" server url.

    Args:
        schema (str): registry or https.

    Returns:
        str: Server URL.

    Raises:
        TimeoutExpiredError: If server is not accessible within timeout.
        KeyError: If the specified schema is not found in server configuration.
    """
    artifactory_connection_url: str = py_config["servers"]["https_server"]
    LOGGER.info(f"Testing connectivity to {artifactory_connection_url} {schema.upper()} server")
    sample = None
    try:
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_1MIN,
            sleep=TIMEOUT_5SEC,
            func=lambda: requests.get(artifactory_connection_url, headers=get_artifactory_header(), verify=False),
        ):
            if sample.status_code == requests.codes.ok:
                return py_config["servers"][f"{schema}_server"]
    except TimeoutExpiredError:
        error_msg = f"Unable to connect to test image server: {artifactory_connection_url} {schema.upper()}"
        if sample:
            error_msg += f", with error code: {sample.status_code}, error: {sample.text}"
        LOGGER.error(error_msg)
        raise


def get_http_image_url(image_directory: str, image_name: str) -> str:
    """
    Construct the full HTTP URL for a test image on the artifact server.

    Args:
        image_directory (str): Directory path where the image is located on the artifact server.
        image_name (str): Name of the image file.

    Returns:
        str: Complete HTTP URL to the image on the artifact server.

    Raises:
        TimeoutExpiredError: If artifact server connectivity check fails.
        KeyError: If server configuration is missing required keys.
    """
    return f"{get_test_artifact_server_url()}{image_directory}/{image_name}"


def get_artifactory_header() -> dict[str, str]:
    """
    Get the authorization header for Artifactory API requests.

    Returns:
        dict[str, str]: Dictionary containing the Bearer token authorization header.

    Raises:
        KeyError: If ARTIFACTORY_TOKEN environment variable is not set.
    """
    return {"Authorization": f"Bearer {os.environ['ARTIFACTORY_TOKEN']}"}


def get_artifactory_secret(
    namespace: str,
    client: DynamicClient | None = None,
) -> Secret:
    """
    Create or retrieve an Artifactory authentication secret in the specified namespace.

    Creates a Kubernetes Secret containing Artifactory credentials (user and token) encoded in base64.
    If the secret already exists in the namespace, it returns the existing secret.
    Otherwise, it creates and deploys a new secret.

    Args:
        namespace (str): The Kubernetes namespace where the secret should be created or retrieved.
        client (DynamicClient | None): Optional Kubernetes client. If None, uses the default client.

    Returns:
        Secret: The Artifactory Secret resource object.

    Raises:
        KeyError: If ARTIFACTORY_USER or ARTIFACTORY_TOKEN environment variables are not set.
    """
    artifactory_secret = Secret(
        name=ARTIFACTORY_SECRET_NAME,
        namespace=namespace,
        accesskeyid=base64_encode_str(os.environ["ARTIFACTORY_USER"]),
        secretkey=base64_encode_str(os.environ["ARTIFACTORY_TOKEN"]),
        client=client,
    )
    if not artifactory_secret.exists:
        artifactory_secret.deploy()
    return artifactory_secret


def get_artifactory_config_map(
    namespace: str,
    client: DynamicClient | None = None,
) -> ConfigMap:
    """
    Create or retrieve an Artifactory TLS certificate ConfigMap in the specified namespace.

    Creates a Kubernetes ConfigMap containing the TLS certificate for the Artifactory server.
    The certificate is retrieved from the server specified in py_config["server_url"].
    If the ConfigMap already exists in the namespace, it returns the existing ConfigMap.
    Otherwise, it creates and deploys a new ConfigMap.

    Args:
        namespace (str): The Kubernetes namespace where the ConfigMap should be created or retrieved.
        client (DynamicClient | None): Optional Kubernetes client. If None, uses the default client.

    Returns:
        ConfigMap: The Artifactory ConfigMap resource object containing the TLS certificate.

    Raises:
        KeyError: If server_url is not found in py_config.
        OSError: If SSL connection to the server fails.
    """
    artifactory_cm = ConfigMap(
        name=ARTIFACTORY_CONFIG_MAP_NAME,
        namespace=namespace,
        data={"tlsregistry.crt": ssl.get_server_certificate(addr=(py_config["server_url"], 443))},
        client=client,
    )
    if not artifactory_cm.exists:
        artifactory_cm.deploy()
    return artifactory_cm


def cleanup_artifactory_secret_and_config_map(
    artifactory_secret: Secret | None = None,
    artifactory_config_map: ConfigMap | None = None,
) -> None:
    """
    Clean up Artifactory Secret and ConfigMap resources from the cluster.

    Deletes the provided Artifactory Secret and/or ConfigMap resources if they exist.
    Prefer ``artifactory_credentials`` for new code; this remains for low-level cleanup.

    Args:
        artifactory_secret (Secret | None): The Artifactory Secret resource to delete.
            If None, no secret cleanup is performed.
        artifactory_config_map (ConfigMap | None): The Artifactory ConfigMap resource to delete.
            If None, no ConfigMap cleanup is performed.
    """
    if artifactory_secret:
        artifactory_secret.clean_up()
    if artifactory_config_map:
        artifactory_config_map.clean_up()


@contextmanager
def artifactory_credentials(
    namespace: str,
    client: DynamicClient,
    *,
    create_secret: bool = True,
    create_config_map: bool = True,
) -> Generator[ArtifactoryCredentials]:
    """
    Create Artifactory Secret and/or ConfigMap and guarantee cleanup on exit.

    Args:
        namespace: Kubernetes namespace for the credentials resources.
        client: Kubernetes dynamic client used to create and delete the resources.
        create_secret: Whether to create/retrieve the Artifactory Secret. Defaults to True.
        create_config_map: Whether to create/retrieve the Artifactory ConfigMap. Defaults to True.

    Yields:
        ArtifactoryCredentials: Created Secret and/or ConfigMap for DV/source auth.

    Raises:
        ValueError: If both ``create_secret`` and ``create_config_map`` are False.
    """
    if not create_secret and not create_config_map:
        raise ValueError("At least one of create_secret or create_config_map must be True")

    secret: Secret | None = None
    config_map: ConfigMap | None = None
    try:
        if create_secret:
            secret = get_artifactory_secret(namespace=namespace, client=client)
        if create_config_map:
            config_map = get_artifactory_config_map(namespace=namespace, client=client)
        yield ArtifactoryCredentials(secret=secret, config_map=config_map)
    finally:
        cleanup_artifactory_secret_and_config_map(
            artifactory_secret=secret,
            artifactory_config_map=config_map,
        )

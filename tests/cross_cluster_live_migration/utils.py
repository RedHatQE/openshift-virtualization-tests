import logging

from kubernetes.dynamic.exceptions import NotFoundError
from ocp_resources.secret import Secret
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from utilities.constants import TIMEOUT_1MIN, TIMEOUT_5SEC

LOGGER = logging.getLogger(__name__)


def get_token_from_secret(secret):
    if secret_instance := secret.exists:
        if token := secret_instance.get("data", {}).get("token"):
            return token
    raise NotFoundError(f"Secret {secret.name} does not exist")


def wait_for_service_account_token(secret: Secret) -> str | None:
    """
    Wait for a service account token to be populated in a secret.

    Args:
        secret: The Secret resource object

    Returns:
        str: The token value

    Raises:
        TimeoutExpiredError: If token is not populated within timeout
    """
    LOGGER.info(f"Waiting for service account token to be populated in secret {secret.name}")

    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_1MIN,
        sleep=TIMEOUT_5SEC,
        func=get_token_from_secret,
        secret=secret,
        exceptions_dict={NotFoundError: []},
    )
    try:
        for sample in samples:
            if sample:
                LOGGER.info(f"Service account token populated successfully in secret {secret.name}")
                return sample
    except TimeoutExpiredError:
        raise TimeoutExpiredError(
            f"Timed out waiting for service account token to be populated in secret {secret.name}"
        )
    return None

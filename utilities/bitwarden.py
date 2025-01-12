import json
import logging
import os
from functools import lru_cache

from bitwarden_sdk import BitwardenClient

from utilities.exceptions import MissingEnvironmentVariableError

LOGGER = logging.getLogger(__name__)
# Bitwarden SDK: https://github.com/bitwarden/sdk/blob/main/languages/python/bitwarden_sdk/bitwarden_client.py


def get_bitwarden_secrets_client():
    """
    Creates a BitwardenClient instance, logs in using ACCESS_TOKEN environment variable and bitwarden AuthClient
    instance, and returns SecretsClient. To use bitwarden secret manager ACCESS_TOKEN and ORGANIZATION_ID environment
    variables must be set

    Returns:
        SecretsClient: Returns SecretsClient instance to be used for secret manager calls
    """
    if not (os.getenv("ACCESS_TOKEN") and os.getenv("ORGANIZATION_ID")):
        raise MissingEnvironmentVariableError(
            "Bitwarden client needs ORGANIZATION_ID and ACCESS_TOKEN environment variable set up"
        )
    bitwarden_client = BitwardenClient()
    bitwarden_client.auth().login_access_token(access_token=os.getenv("ACCESS_TOKEN"))
    return bitwarden_client.secrets()


@lru_cache
def get_all_cnv_tests_secrets(bitwarden_secrets_client):
    """
    Using Bitwarden SecretsClient, gets a list of all cnv-secrets saved in bitwarden secret manager (associated with
    a specific organization id). ORGANIZATION_ID is expected to set via environment variable.

    Args:
        bitwarden_secrets_client (SecretsClient): Bitwarden SecretsClient instance

    Returns:
        dict: dictionary of secret name and secret uuid associated with the organization
    """
    secrets = bitwarden_secrets_client.list(organization_id=os.getenv("ORGANIZATION_ID")).data.data
    LOGGER.info(f"Cache info stats for pulling secrets: {get_all_cnv_tests_secrets.cache_info()}")
    return {secret.key: secret.id for secret in secrets}


@lru_cache
def get_cnv_tests_secret_by_name(secret_name):
    """
    Pull a specific secret from bitwarden secret manager by name

    Args:
        secret_name (str): Bitwarden secret manager secret name

    Returns:
        dict: value of the saved secret
    """
    bitwarden_secrets_client = get_bitwarden_secrets_client()
    secrets = get_all_cnv_tests_secrets(bitwarden_secrets_client=bitwarden_secrets_client)
    secret_dict = None
    for secret_key, secret_value in secrets.items():
        if secret_key == secret_name:
            secret_dict = json.loads(bitwarden_secrets_client.get(id=secret_value).data.value)
            break
    LOGGER.info(f"Cache info stats for getting specific secret: {get_cnv_tests_secret_by_name.cache_info()}")
    assert secret_dict, f"secret {secret_name} is either not found or does not have valid values."
    return secret_dict

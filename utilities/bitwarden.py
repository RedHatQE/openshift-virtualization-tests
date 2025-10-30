import json
import logging
import os
from functools import cache
from typing import Any

from pyhelper_utils.shell import run_command

from utilities.exceptions import MissingEnvironmentVariableError

LOGGER = logging.getLogger(__name__)


def _run_bws_command(args: list[str]) -> Any:
    """Run bws CLI command and return parsed JSON output.

    Args:
        args: Command arguments to pass to bws (e.g., ['secret', 'list'])

    Returns:
        Any: Parsed JSON response from bws CLI (can be list or dict depending on command)

    Raises:
        MissingEnvironmentVariableError: If ACCESS_TOKEN not set
    """
    access_token = os.getenv("ACCESS_TOKEN")

    if not access_token:
        raise MissingEnvironmentVariableError("Bitwarden client needs ACCESS_TOKEN environment variable set up")

    _, stdout, _ = run_command(
        command=["bws", "--access-token", access_token] + args,
        capture_output=True,
        check=True,
        hide_log_command=True,
    )

    return json.loads(stdout)


@cache
def get_all_cnv_tests_secrets() -> dict[str, str]:
    """Gets a list of all cnv-secrets saved in Bitwarden Secret Manager.

    Uses bws CLI to list all secrets associated with the organization.
    ACCESS_TOKEN environment variable must be set.

    Returns:
        dict[str, str]: Dictionary mapping secret name to secret UUID
    """
    data = _run_bws_command(args=["secret", "list"])

    LOGGER.info(f"Cache info stats for pulling secrets: {get_all_cnv_tests_secrets.cache_info()}")

    return {secret["key"]: secret["id"] for secret in data}


@cache
def get_cnv_tests_secret_by_name(secret_name: str) -> dict[str, Any]:
    """Pull a specific secret from Bitwarden Secret Manager by name.

    Args:
        secret_name: Bitwarden Secret Manager secret name

    Returns:
        dict[str, Any]: Value of the saved secret (parsed from JSON)

    Raises:
        ValueError: If secret is not found
    """
    secrets = get_all_cnv_tests_secrets()

    secret_id = secrets.get(secret_name)
    if not secret_id:
        raise ValueError(f"Secret '{secret_name}' not found in Bitwarden")

    secret_data = _run_bws_command(args=["secret", "get", secret_id])
    secret_value = secret_data.get("value", "")

    secret_dict = json.loads(secret_value)
    LOGGER.info(f"Cache info stats for getting specific secret: {get_cnv_tests_secret_by_name.cache_info()}")
    return secret_dict

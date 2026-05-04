import logging
import os

from jira import JIRA
from pytest_testconfig import config as py_config

from utilities.exceptions import MissingEnvironmentVariableError

LOGGER = logging.getLogger(__name__)


def get_jira_status(jira: str) -> str:
    """
    Get jira status.

    Args:
        jira (str): jira card ID

    Returns:
        str: jira status. For conformance tests without JIRA credentials, assume the JIRA is open.

    Raises:
        MissingEnvironmentVariableError: if PYTEST_JIRA_TOKEN or PYTEST_JIRA_URL or
            PYTEST_JIRA_USERNAME environment variables are not set

    """
    url = os.getenv("PYTEST_JIRA_URL")
    token = os.getenv("PYTEST_JIRA_TOKEN")
    email = os.getenv("PYTEST_JIRA_USERNAME")

    if not (token and url and email):
        # For conformance tests without JIRA credentials, assume the JIRA is open
        if py_config.get("conformance_tests"):
            LOGGER.info(f"Conformance tests without JIRA credentials: assuming {jira} is open")
            return "open"

        raise MissingEnvironmentVariableError(
            "Please set PYTEST_JIRA_TOKEN, PYTEST_JIRA_URL and PYTEST_JIRA_USERNAME environment variables"
        )

    jira_connection = JIRA(
        server=url,
        basic_auth=(email, token),
    )

    status = jira_connection.issue(id=jira).fields.status.name.lower()
    LOGGER.info(f"Jira {jira}: status is {status}")

    return status


def is_jira_open(jira_id: str) -> bool:
    """
    Check if jira status is open.

    Args:
        jira_id (str): Jira card ID in format: "CNV-<jira_id>"

    Returns:
        bool: True: if jira is open, False: if jira is closed
    """
    return get_jira_status(jira=jira_id) not in ("on_qa", "verified", "release pending", "closed")

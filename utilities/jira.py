"""Jira status helpers.

Service account: PYTEST_JIRA_OAUTH_CLIENT_ID, PYTEST_JIRA_OAUTH_CLIENT_SECRET,
PYTEST_JIRA_CLOUD_ID. Fallback: PYTEST_JIRA_URL, PYTEST_JIRA_USERNAME,
PYTEST_JIRA_TOKEN. See docs/RUNNING_TESTS.md.
"""

import logging
import os
from math import isfinite
from time import monotonic
from typing import Any

import requests
from jira import JIRA, JIRAError
from pytest_testconfig import config as py_config

from utilities.exceptions import JiraServiceAccountError, MissingEnvironmentVariableError

LOGGER = logging.getLogger(__name__)

# Named after the pytest-jira family, which reads the same three variables from 0.5.0
# on, so one environment configures both this module and the @pytest.mark.jira plugin.
SERVICE_ACCOUNT_CLIENT_ID_ENV = "PYTEST_JIRA_OAUTH_CLIENT_ID"
SERVICE_ACCOUNT_CLIENT_SECRET_ENV = "PYTEST_JIRA_OAUTH_CLIENT_SECRET"
SERVICE_ACCOUNT_CLOUD_ID_ENV = "PYTEST_JIRA_CLOUD_ID"
SERVICE_ACCOUNT_VARIABLES = (
    SERVICE_ACCOUNT_CLIENT_ID_ENV,
    SERVICE_ACCOUNT_CLIENT_SECRET_ENV,
    SERVICE_ACCOUNT_CLOUD_ID_ENV,
)
ATLASSIAN_TOKEN_URL = "https://auth.atlassian.com/oauth/token"
JIRA_CLOUD_GATEWAY_URL = "https://api.atlassian.com/ex/jira/{cloud_id}"
# Local rather than utilities.constants.timeouts: importing that package runs
# utilities/constants/__init__.py, which resolves Images through a live cluster, and a Jira
# helper must stay importable without one.
JIRA_REQUEST_TIMEOUT_SECONDS = 15
# An access token lives an hour. A call that still lands on an expired one is
# recovered by the single remint in _read_service_account_issue.
TOKEN_REFRESH_MARGIN_SECONDS = 120
# OAuth 2.0 error codes worth echoing back from a rejected token request.
OAUTH_ERROR_CODES = (
    "access_denied",
    "invalid_client",
    "invalid_grant",
    "invalid_request",
    "invalid_scope",
    "server_error",
    "temporarily_unavailable",
    "unauthorized_client",
    "unsupported_grant_type",
)

_SERVICE_ACCOUNT_CLIENTS: dict[tuple[str, str], tuple[JIRA, float]] = {}


def _missing_service_account_variables() -> list[str]:
    """Return the service-account variables that are not set.

    Returns:
        list[str]: Names of the unset variables, empty when the triple is complete.
    """
    return [name for name in SERVICE_ACCOUNT_VARIABLES if not os.getenv(name)]


def _token_failure_details(response: requests.Response) -> str:
    """Return the OAuth error code of a rejected token request, if it is a known one.

    Only the standardised code is echoed: the request body carries the client secret, so
    a proxy that reflects the request in an ``error_description`` must not reach a message.

    Args:
        response: Response of the token request.

    Returns:
        str: ": <code>" when the body carries a known OAuth error code, else "".
    """
    try:
        payload = response.json()
    except ValueError:
        return ""

    if not isinstance(payload, dict):
        return ""

    error_code = payload.get("error")

    return f": {error_code}" if error_code in OAUTH_ERROR_CODES else ""


def _token_response_object(response: requests.Response) -> dict[str, Any]:
    """Return the JSON object of a token response.

    Args:
        response: Response of the token request.

    Returns:
        dict: The parsed body.

    Raises:
        JiraServiceAccountError: if the body is not a JSON object.
    """
    payload: Any = None
    is_json = True
    try:
        payload = response.json()
    except ValueError:
        is_json = False

    # Raised outside the handler: the chained decode error can carry the whole body.
    if not is_json:
        raise JiraServiceAccountError(
            f"{ATLASSIAN_TOKEN_URL} returned a body that is not JSON (HTTP {response.status_code})"
        )

    if not isinstance(payload, dict):
        raise JiraServiceAccountError(
            f"{ATLASSIAN_TOKEN_URL} returned a body that is not a JSON object (HTTP {response.status_code})"
        )

    return payload


def _mint_service_account_access_token(client_id: str, client_secret: str) -> tuple[str, float]:
    """Exchange the Jira Cloud service-account credential for an access token.

    Args:
        client_id: OAuth 2.0 client id of the service account.
        client_secret: OAuth 2.0 client secret of the service account.

    Returns:
        tuple[str, float]: The access token, and the ``monotonic`` time it expires at.

    Raises:
        JiraServiceAccountError: if Atlassian cannot be reached, rejects the credential, or
            answers without a usable token and expiry.
    """
    transport_error: requests.RequestException | None = None
    try:
        response = requests.post(
            url=ATLASSIAN_TOKEN_URL,
            json={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
            },
            timeout=JIRA_REQUEST_TIMEOUT_SECONDS,
            allow_redirects=False,
        )
    except requests.RequestException as error:
        transport_error = error

    if transport_error is not None:
        # Raised outside the handler: a chained requests error exposes its prepared
        # request, whose body carries the client secret.
        raise JiraServiceAccountError(f"Could not reach {ATLASSIAN_TOKEN_URL} ({type(transport_error).__name__})")

    if response.status_code != 200:
        details = _token_failure_details(response=response)
        hint = (
            f": check {SERVICE_ACCOUNT_CLIENT_ID_ENV} and {SERVICE_ACCOUNT_CLIENT_SECRET_ENV}"
            if response.status_code in (400, 401, 403)
            else ""
        )
        raise JiraServiceAccountError(
            f"Could not mint a Jira Cloud access token for the service account "
            f"(HTTP {response.status_code}{details}){hint}"
        )

    payload = _token_response_object(response=response)
    access_token = payload.get("access_token")
    expires_in = payload.get("expires_in")
    if not isinstance(access_token, str) or not access_token:
        raise JiraServiceAccountError(
            f"{ATLASSIAN_TOKEN_URL} returned no usable access token (HTTP {response.status_code})"
        )
    if expires_in is None:
        raise JiraServiceAccountError(f"{ATLASSIAN_TOKEN_URL} returned no expiry (HTTP {response.status_code})")

    lifetime: float | None = None
    try:
        lifetime = float(expires_in)
    except TypeError, ValueError, OverflowError:
        lifetime = None

    # Raised outside the handler, and only the type is reported: a proxy reflecting the
    # request would otherwise put the client secret in this message.
    if lifetime is None:
        raise JiraServiceAccountError(
            f"{ATLASSIAN_TOKEN_URL} returned an unusable expires_in ({type(expires_in).__name__})"
        )

    if not (isfinite(lifetime) and lifetime > 0):
        # nan compares False against every deadline and would remint on each call; inf
        # would keep the client cached forever.
        raise JiraServiceAccountError(
            f"{ATLASSIAN_TOKEN_URL} returned a non-finite or non-positive expires_in ({type(expires_in).__name__})"
        )

    if lifetime < 2 * TOKEN_REFRESH_MARGIN_SECONDS:
        # Atlassian issues an hour. Anything much shorter means a misconfigured or hostile
        # endpoint, and caching it would remint and rebuild a client on almost every read;
        # refusing it is deliberate policy rather than a silent slowdown.
        raise JiraServiceAccountError(
            f"{ATLASSIAN_TOKEN_URL} returned an expires_in of {lifetime}s, less than twice "
            f"the {TOKEN_REFRESH_MARGIN_SECONDS}s refresh margin"
        )

    return access_token, monotonic() + lifetime


def _service_account_settings() -> tuple[str, str, str] | None:
    """Return the configured Jira Cloud service-account settings.

    Returns:
        tuple[str, str, str] | None: client id, client secret and cloud id, or None when the
            triple is incomplete. The caller then uses the user + API token pair when that
            pair is configured, otherwise it fails, or assumes an open issue in conformance
            runs.
    """
    client_id, client_secret, cloud_id = (os.getenv(name) for name in SERVICE_ACCOUNT_VARIABLES)
    if not (client_id and client_secret and cloud_id):
        return None

    return client_id, client_secret, cloud_id


def _service_account_client(settings: tuple[str, str, str]) -> tuple[JIRA, bool]:
    """Return the Jira client for the service account, reusing it until its token expires.

    Constructing the client sets python-jira's shared ``jira`` logger to CRITICAL, which is
    process-wide and is the reason the gateway address cannot be logged from inside the
    library. It is not a guarantee: transport-level loggers are separate, and a later
    JIRA(...) with logging enabled would reset that level.

    Args:
        settings: client id, client secret and cloud id of the service account.

    Returns:
        tuple[JIRA, bool]: The client, and whether it was reused from the cache.

    Raises:
        JiraServiceAccountError: if the credential cannot be exchanged for an access token.
    """
    client_id, client_secret, cloud_id = settings
    cache_key = (client_id, cloud_id)
    cached_client, token_expiry = _SERVICE_ACCOUNT_CLIENTS.get(cache_key, (None, 0.0))
    if cached_client is not None and token_expiry - TOKEN_REFRESH_MARGIN_SECONDS > monotonic():
        # Another JIRA(...) may have reset the shared logger since this client was built.
        logging.getLogger("jira").setLevel(logging.CRITICAL)
        return cached_client, True
    access_token, token_expiry = _mint_service_account_access_token(
        client_id=client_id,
        client_secret=client_secret,
    )
    jira_connection = JIRA(
        server=JIRA_CLOUD_GATEWAY_URL.format(cloud_id=cloud_id),
        token_auth=access_token,
        timeout=JIRA_REQUEST_TIMEOUT_SECONDS,
        get_server_info=False,
        logging=False,
    )

    superseded = _SERVICE_ACCOUNT_CLIENTS.pop(cache_key, None)
    if superseded is not None:
        superseded_client, _ = superseded
        superseded_client.close()

    _SERVICE_ACCOUNT_CLIENTS[cache_key] = (jira_connection, token_expiry)

    return jira_connection, False


def _forget_service_account_client(settings: tuple[str, str, str]) -> None:
    """Drop and close the cached client for these settings.

    Args:
        settings: client id, client secret and cloud id of the service account.
    """
    client_id, _, cloud_id = settings
    cached = _SERVICE_ACCOUNT_CLIENTS.pop((client_id, cloud_id), None)
    if cached is not None:
        cached_client, _ = cached
        cached_client.close()


def _issue_status(jira_connection: JIRA, jira: str) -> str:
    """Return the lower-cased status of one issue.

    Args:
        jira_connection: Connected Jira client.
        jira: Jira card ID in format: "CNV-<jira_id>".

    Returns:
        str: Lower-cased issue status.
    """
    return jira_connection.issue(id=jira).fields.status.name.lower()


def _read_failure_reason(
    error: JIRAError | requests.RequestException | NotImplementedError | AttributeError,
) -> str:
    """Return a reason for a failed read that cannot carry the gateway address.

    Args:
        error: What the read raised.

    Returns:
        str: "HTTP <status>" (or "Jira returned no HTTP status"), the transport exception
            class name, "empty response" for an empty issue body, or "response without a
            status" when the payload has no status field.
    """
    if isinstance(error, JIRAError):
        return f"HTTP {error.status_code}" if error.status_code else "Jira returned no HTTP status"

    if isinstance(error, requests.RequestException):
        return type(error).__name__

    if isinstance(error, NotImplementedError):
        # jira/resources.py Resource._parse_raw rejects an empty resource with it.
        return "empty response"

    return "response without a status"


def _read_service_account_issue(settings: tuple[str, str, str], jira: str) -> tuple[str | None, str]:
    """Read the issue status as the service account, retrying once with a fresh token.

    A 401 on a reused token is recoverable, so that client is retired and the read is
    repeated once. A 401 on a token minted for this very call is not: it would just spend
    another exchange and another request on every Jira-gated fixture.

    Args:
        settings: client id, client secret and cloud id of the service account.
        jira: Jira card ID in format: "CNV-<jira_id>".

    Returns:
        tuple[str | None, str]: The status, or None and the reason the read failed.

    Raises:
        JiraServiceAccountError: if the credential cannot be exchanged for an access token.
    """
    attempt = 1
    while True:
        jira_connection, reused = _service_account_client(settings=settings)
        try:
            return _issue_status(jira_connection=jira_connection, jira=jira), ""
        # NotImplementedError: jira/resources.py Resource._parse_raw rejects an empty
        # ("{}") issue body with it.
        except (JIRAError, requests.RequestException, NotImplementedError, AttributeError) as error:
            if isinstance(error, JIRAError) and error.status_code == 401:
                # A rejected token is useless for later calls too: retire it either way.
                _forget_service_account_client(settings=settings)
                if attempt == 1 and reused:
                    LOGGER.warning(
                        f"Jira service account token rejected for {jira} (HTTP 401); "
                        "dropping the cached client and retrying once"
                    )
                    attempt = 2
                    continue

            return None, _read_failure_reason(error=error)


def _service_account_status(settings: tuple[str, str, str], jira: str) -> str:
    """Read one issue status as the Jira Cloud service account.

    The cloud id identifies the tenant in the API gateway address, so it is kept out of
    every log line and error message: a failure names the issue key plus a reason that
    cannot carry the gateway address - the HTTP status, the transport error class, or a
    fixed note for an empty response.

    Args:
        settings: client id, client secret and cloud id of the service account.
        jira: Jira card ID in format: "CNV-<jira_id>".

    Returns:
        str: Lower-cased issue status.

    Raises:
        JiraServiceAccountError: if the credential is rejected, Atlassian cannot be reached,
            or the issue cannot be read.
    """
    status, failure = _read_service_account_issue(settings=settings, jira=jira)
    if status is None:
        # Raised outside the read handler: no exception is being handled here, so no
        # chained context can carry the gateway address into a traceback.
        raise JiraServiceAccountError(f"Could not read {jira} with the Jira Cloud service account ({failure})")

    return status


# TODO: drop the user + API token path once CI exports the three service-account
#  variables; pytest-jira 0.5.0 already reads them for @pytest.mark.jira.
def _user_jira_connection() -> JIRA | None:
    """Build a Jira client from the user + API token pair.

    This retiring path builds a client per call and keeps python-jira's serverInfo probe
    and its request logging, so it is slower and noisier than the cached service-account
    client; its site URL carries no cloud id, and the two paths are never both in use.

    Returns:
        JIRA | None: A client, or None when PYTEST_JIRA_URL, PYTEST_JIRA_TOKEN or
            PYTEST_JIRA_USERNAME is not set.
    """
    url = os.getenv("PYTEST_JIRA_URL")
    token = os.getenv("PYTEST_JIRA_TOKEN")
    email = os.getenv("PYTEST_JIRA_USERNAME")
    if not (token and url and email):
        return None

    return JIRA(
        server=url,
        basic_auth=(email, token),
        timeout=JIRA_REQUEST_TIMEOUT_SECONDS,
    )


def get_jira_status(jira: str) -> str:
    """Return the status of a Jira issue, lower-cased.

    The service account is used when all three of its variables are set, otherwise the
    PYTEST_JIRA_URL / PYTEST_JIRA_USERNAME / PYTEST_JIRA_TOKEN pair. Precedence differs
    from pytest-jira, which prefers the username + token pair - see the module docstring.

    Args:
        jira: Jira card ID in format: "CNV-<jira_id>".

    Returns:
        str: Lower-cased status such as "new" or "closed". Conformance runs without Jira
            credentials get "open" so they keep running.

    Raises:
        MissingEnvironmentVariableError: if no usable Jira credentials are configured
            outside conformance runs.
        JiraServiceAccountError: if Atlassian cannot be reached, rejects the credential,
            answers with a token response without a usable token and expiry, or if the issue
            cannot be read with it.
        JIRAError: if the issue cannot be read with the user + API token pair.
        requests.RequestException: if that read fails at the transport level.
    """
    settings = _service_account_settings()
    if settings is not None:
        LOGGER.info("Reading the Jira status with the service account credential")
        status = _service_account_status(settings=settings, jira=jira)
    else:
        jira_connection = _user_jira_connection()
        if jira_connection is None:
            # For conformance tests without JIRA credentials, assume the JIRA is open
            if py_config.get("conformance_tests"):
                LOGGER.info(f"Conformance tests without JIRA credentials: assuming {jira} is open")
                return "open"

            # A partial service account is the confusing case: say which part is missing.
            missing = _missing_service_account_variables()
            partial_note = f" (not set: {', '.join(missing)})" if len(missing) < len(SERVICE_ACCOUNT_VARIABLES) else ""
            raise MissingEnvironmentVariableError(
                f"Please set {SERVICE_ACCOUNT_CLIENT_ID_ENV}, {SERVICE_ACCOUNT_CLIENT_SECRET_ENV} and "
                f"{SERVICE_ACCOUNT_CLOUD_ID_ENV}{partial_note}, or PYTEST_JIRA_TOKEN, "
                "PYTEST_JIRA_URL and PYTEST_JIRA_USERNAME environment variables"
            )
        status = _issue_status(jira_connection=jira_connection, jira=jira)

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

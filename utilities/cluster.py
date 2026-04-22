from functools import cache
from subprocess import TimeoutExpired

from kubernetes.dynamic import DynamicClient
from ocp_resources.resource import get_client
from pyhelper_utils.shell import run_command
from timeout_sampler import TimeoutSampler


@cache
def cache_admin_client() -> DynamicClient:
    """Get admin_client once and reuse it

    This usage of this function is limited ONLY in places where `client` cannot be passed as an argument.
    For example: in pytest native fixtures in conftest.py.

    Returns:
        DynamicClient: admin_client

    """

    return get_client()


def get_oc_whoami_username(*, wait_timeout: int = 30, sleep: int = 3):
    """Return the current OpenShift CLI user by running ``oc whoami``.

    Each attempt runs ``oc whoami`` in a subprocess with a time limit, then retries
    on error or hang until a non-empty username is returned or ``wait_timeout`` is
    reached.

    Args:
        wait_timeout: Maximum time in seconds to keep retrying ``oc whoami``.
        sleep: Seconds to wait between attempts.

    Returns:
        The authenticated user name (stdout from ``oc whoami``, stripped of whitespace).

    Raises:
        TimeoutExpiredError: If no successful non-empty result is obtained before
            ``wait_timeout`` elapses.
    """

    def _whoami() -> str:
        did_succeed, stdout, _ = run_command(
            command=["oc", "whoami"],
            capture_output=True,
            check=False,
            timeout=sleep,
        )
        return stdout.strip() if did_succeed else ""

    for result in TimeoutSampler(
        wait_timeout=wait_timeout,
        sleep=sleep,
        func=_whoami,
        exceptions_dict={TimeoutExpired: []},
    ):
        if result:
            return result

from functools import cache

from kubernetes.dynamic import DynamicClient
from ocp_resources.resource import get_client


@cache
def cache_admin_client() -> DynamicClient:
    """Get admin_client once and reuse it

    This usage of this function is limited ONLY in places where `client` cannot be passed as an argument.
    For example: in pytest native fixtures in conftest.py.

    Returns:
        DynamicClient: admin_client

    """

    return get_client()

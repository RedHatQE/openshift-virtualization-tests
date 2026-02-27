import ipaddress
import logging
from functools import cache

from pytest_testconfig import py_config

LOGGER = logging.getLogger(__name__)


@cache
def is_ipv6_single_stack_cluster() -> bool:
    ipv4_supported = cluster_ip_family_supported(ip_family=4)
    ipv6_supported = cluster_ip_family_supported(ip_family=6)

    is_ipv6_only = ipv6_supported and not ipv4_supported
    LOGGER.info(f"Cluster network detection: IPv4={ipv4_supported}, IPv6={ipv6_supported}, IPv6-only={is_ipv6_only}")
    return is_ipv6_only


def cluster_ip_family_supported(ip_family: int) -> bool:
    return any(ipaddress.ip_network(ip).version == ip_family for ip in py_config.get("cluster_service_network"))

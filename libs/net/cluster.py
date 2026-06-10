import ipaddress
import logging
from functools import cache

from pytest_testconfig import py_config

LOGGER = logging.getLogger(__name__)


@cache
def is_ipv6_single_stack_cluster() -> bool:
    ipv4_supported = ipv4_supported_cluster()
    ipv6_supported = ipv6_supported_cluster()

    is_ipv6_only = ipv6_supported and not ipv4_supported
    LOGGER.info(f"Cluster network detection: IPv4={ipv4_supported}, IPv6={ipv6_supported}, IPv6-only={is_ipv6_only}")
    return is_ipv6_only


@cache
def ipv4_supported_cluster() -> bool:
    return _cluster_ip_family_supported(ip_family=4)


@cache
def ipv6_supported_cluster() -> bool:
    return _cluster_ip_family_supported(ip_family=6)


def _cluster_ip_family_supported(ip_family: int) -> bool:
    return any(ipaddress.ip_network(ip).version == ip_family for ip in py_config.get("cluster_service_network"))

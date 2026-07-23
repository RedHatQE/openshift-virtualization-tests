import ipaddress
from functools import cache

from pytest_testconfig import py_config


@cache
def ipv4_supported_cluster() -> bool:
    return _cluster_ip_family_supported(ip_family=4)


@cache
def ipv6_supported_cluster() -> bool:
    return _cluster_ip_family_supported(ip_family=6)


def _cluster_ip_family_supported(ip_family: int) -> bool:
    return any(ipaddress.ip_network(ip).version == ip_family for ip in py_config.get("cluster_service_network"))

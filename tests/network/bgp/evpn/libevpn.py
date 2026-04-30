from libs.net.cluster import ipv4_supported_cluster, ipv6_supported_cluster
from libs.net.ip import random_ipv4_address, random_ipv6_address

CUDN_EVPN_SUBNET_IPV4: str = f"{random_ipv4_address(net_seed=5, host_address=0)}/24"
CUDN_EVPN_SUBNET_IPV6: str = f"{random_ipv6_address(net_seed=5, host_address=0)}/64"


def cudn_evpn_subnets() -> list[str]:
    """Returns CUDN EVPN subnets based on cluster IP family support.

    Returns:
        List of subnet CIDRs (IPv4 and/or IPv6) supported by the cluster.
    """
    subnets = []
    if ipv4_supported_cluster():
        subnets.append(CUDN_EVPN_SUBNET_IPV4)
    if ipv6_supported_cluster():
        subnets.append(CUDN_EVPN_SUBNET_IPV6)
    return subnets

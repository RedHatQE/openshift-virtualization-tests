from dataclasses import asdict, dataclass, field
from typing import Any, Final

import yaml

from libs.net.cluster import ipv4_supported_cluster, ipv6_supported_cluster
from tests.network.libs.apimachinery import dict_normalization_for_dataclass

NETWORK_DATA: Final[str] = "networkData"


@dataclass
class MatchSelector:
    macaddress: str


@dataclass
class EthernetDevice:
    """
    Ethernet Device

    Example:
        addresses:
        - 1.1.1.1/24
        - d10:0:2::2
        gateway6: d10:0:2::1
    """

    dhcp4: bool | None = None
    dhcp6: bool | None = None
    addresses: list[str] | None = None
    gateway4: str | None = None
    gateway6: str | None = None

    match: MatchSelector | None = None
    set_name: str | None = None


@dataclass
class NetworkData:
    """
    Cloud init network data.
    https://cloudinit.readthedocs.io/en/latest/topics/network-config-format-v2.html

    Example:
        version: 2
        ethernets:
          eth0:
            addresses:
            - 1.1.1.1/24
            - d10:0:2::2
            gateway6: d10:0:2::1
    """

    version: int = field(default=2, init=False)
    ethernets: dict[str, EthernetDevice]


@dataclass
class UserData:
    """Represents user configuration for cloud-init."""

    users: list[Any]
    """
    Part of cloud-init's 'users and groups' module:
    https://cloudinit.readthedocs.io/en/latest/reference/modules.html#users-and-groups
    """


def todict(no_cloud: NetworkData | UserData) -> dict[str, Any]:
    return asdict(obj=no_cloud, dict_factory=dict_normalization_for_dataclass)


def asyaml(no_cloud: NetworkData | UserData) -> str:
    return yaml.safe_dump(todict(no_cloud=no_cloud), sort_keys=False)


def format_cloud_config(userdata: UserData) -> str:
    """
    Formats UserData as a cloud-init '#cloud-config' file.
    See: https://cloudinit.readthedocs.io/en/latest/explanation/format.html#headers-and-content-types
    """
    body = yaml.safe_dump(todict(no_cloud=userdata), sort_keys=False)
    return f"#cloud-config\n{body}"


def cloudinit(netdata: NetworkData) -> dict[str, Any]:
    return {NETWORK_DATA: todict(no_cloud=netdata)}


def primary_iface_cloud_init() -> EthernetDevice | None:
    """Return cloud-init ethernet config for the masquerade primary interface.

    Configures a static IPv6 address on eth0 when the cluster supports IPv6,
    enabling per-family connectivity verification. Returns None on IPv4-only clusters.

    Returns:
        EthernetDevice with static IPv6 and optional DHCP4, or None if IPv6 is not supported.
    """
    if ipv6_supported_cluster():
        return EthernetDevice(
            addresses=["fd10:0:2::2/120"],
            gateway6="fd10:0:2::1",
            dhcp4=ipv4_supported_cluster(),
            dhcp6=False,
        )
    return None

from dataclasses import asdict, dataclass, field
from typing import Any, Final

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
    addresses: list[str] | None = None
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


def cloudinit(netdata: NetworkData) -> dict[str, Any]:
    return {NETWORK_DATA: todict(netdata)}


def todict(netdata: NetworkData) -> dict[str, Any]:
    return asdict(obj=netdata, dict_factory=dict_normalization_for_dataclass)

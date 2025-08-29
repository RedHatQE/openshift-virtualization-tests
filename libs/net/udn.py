from collections.abc import Generator
from typing import Final

from ocp_resources.namespace import Namespace

from libs.vm.spec import Interface, NetBinding, Network
from utilities.infra import cache_admin_client, create_ns

UDN_BINDING_PLUGIN_NAME: Final[str] = "l2bridge"


def udn_primary_network(name: str) -> tuple[Interface, Network]:
    return Interface(name=name, binding=NetBinding(name=UDN_BINDING_PLUGIN_NAME)), Network(name=name, pod={})


def create_udn_namespace(name: str, labels: dict[str, str] | None = None) -> Generator[Namespace]:
    return create_ns(
        name=name,
        labels={"k8s.ovn.org/primary-user-defined-network": "", **(labels or {})},
        admin_client=cache_admin_client(),
    )

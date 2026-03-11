from collections.abc import Generator
from typing import Final

from kubernetes.dynamic import DynamicClient
from ocp_resources.namespace import Namespace

from libs.vm.spec import Interface, NetBinding, Network
from utilities.infra import create_ns

UDN_BINDING_DEFAULT_PLUGIN_NAME: Final[str] = "l2bridge"
UDN_PASST_CORE_BINDING_NAME: Final[str] = "passtBinding"


def udn_primary_network(name: str, binding: str) -> tuple[Interface, Network]:
    if binding == UDN_PASST_CORE_BINDING_NAME:
        interface = Interface(name=name, passtBinding={})
    else:
        interface = Interface(name=name, binding=NetBinding(name=binding))
    return interface, Network(name=name, pod={})


def create_udn_namespace(
    name: str,
    client: DynamicClient,
    labels: dict[str, str] | None = None,
) -> Generator[Namespace]:
    return create_ns(
        name=name,
        labels={"k8s.ovn.org/primary-user-defined-network": "", **(labels or {})},
        admin_client=client,
    )

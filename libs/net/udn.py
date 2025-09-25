from collections.abc import Generator
from typing import Final

from kubernetes.dynamic import DynamicClient
from ocp_resources.namespace import Namespace

from libs.vm.spec import Interface, NetBinding, Network
from utilities.infra import create_ns

UDN_BINDING_PLUGIN_NAME: Final[str] = "l2bridge"


def udn_primary_network(name: str) -> tuple[Interface, Network]:
    return Interface(name=name, binding=NetBinding(name=UDN_BINDING_PLUGIN_NAME)), Network(name=name, pod={})


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

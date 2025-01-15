from typing import Final

from libs.vm.spec import Interface, NetBinding, Network

UDN_BINDING_PLUGIN_NAME: Final[str] = "l2bridge"


def udn_primary_network(name: str) -> tuple[Interface, Network]:
    return Interface(name=name, binding=NetBinding(name=UDN_BINDING_PLUGIN_NAME)), Network(name=name, pod={})

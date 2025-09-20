from collections.abc import Generator
from typing import Final

from kubernetes.dynamic import DynamicClient
from ocp_resources.namespace import Namespace

from libs.vm.affinity import new_pod_anti_affinity
from libs.vm.factory import base_vmspec, fedora_vm
from libs.vm.spec import Interface, NetBinding, Network
from libs.vm.vm import BaseVirtualMachine
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


def udn_vm(namespace_name: str, name: str, template_labels: dict | None = None) -> BaseVirtualMachine:
    spec = base_vmspec()
    iface, network = udn_primary_network(name="udn-primary")
    spec.template.spec.domain.devices.interfaces = [iface]  # type: ignore
    spec.template.spec.networks = [network]
    if template_labels:
        spec.template.metadata.labels = spec.template.metadata.labels or {}  # type: ignore
        spec.template.metadata.labels.update(template_labels)  # type: ignore
        # Use the first label key and first value as the anti-affinity label to use:
        label, *_ = template_labels.items()
        spec.template.spec.affinity = new_pod_anti_affinity(label=label)

    return fedora_vm(namespace=namespace_name, name=name, spec=spec)

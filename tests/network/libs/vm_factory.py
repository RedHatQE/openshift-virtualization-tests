"""This module provides various virtual machine configurations with a focus on network setups."""

from libs.net.udn import udn_primary_network
from libs.vm.affinity import new_pod_anti_affinity
from libs.vm.factory import base_vmspec, fedora_vm
from libs.vm.vm import BaseVirtualMachine


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

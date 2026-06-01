"""This module provides various virtual machine configurations with a focus on network setups."""

from kubernetes.dynamic import DynamicClient

from libs.net.udn import udn_primary_network
from libs.vm.affinity import new_pod_anti_affinity
from libs.vm.factory import base_vmspec, fedora_vm
from libs.vm.spec import Affinity
from libs.vm.vm import BaseVirtualMachine


def udn_vm(
    namespace_name: str,
    name: str,
    client: DynamicClient,
    binding: str,
    template_labels: dict | None = None,
    anti_affinity_namespaces: list[str] | None = None,
    affinity: Affinity | None = None,
) -> BaseVirtualMachine:
    """Create a Fedora VM connected to a primary UDN using the specified binding.

    Args:
        namespace_name: Namespace in which the VM will be created.
        name: Name of the VM.
        client: Kubernetes dynamic client.
        binding: UDN binding plugin name (e.g. UDN_BINDING_DEFAULT_PLUGIN_NAME).
        template_labels: Optional labels to add to the VM pod template, also used as anti-affinity key.
        anti_affinity_namespaces: Optional namespaces to scope the pod anti-affinity rule.
        affinity: Optional explicit affinity rules. When set, takes precedence over auto-generated anti-affinity from template_labels.

    Returns:
        Configured BaseVirtualMachine object (not yet started).
    """
    spec = base_vmspec()
    iface, network = udn_primary_network(name="udn-primary", binding=binding)
    spec.template.spec.domain.devices.interfaces = [iface]  # type: ignore
    spec.template.spec.networks = [network]
    if affinity is not None:
        spec.template.spec.affinity = affinity
    if template_labels:
        spec.template.metadata.labels = spec.template.metadata.labels or {}  # type: ignore
        spec.template.metadata.labels.update(template_labels)  # type: ignore
        if affinity is None:
            # Use the first label key and first value as the anti-affinity label to use:
            label, *_ = template_labels.items()
            spec.template.spec.affinity = new_pod_anti_affinity(label=label, namespaces=anti_affinity_namespaces)

    return fedora_vm(namespace=namespace_name, name=name, client=client, spec=spec)

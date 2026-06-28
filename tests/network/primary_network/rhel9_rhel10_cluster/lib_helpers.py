from kubernetes.dynamic import DynamicClient

from libs.vm.factory import base_vmspec, fedora_vm
from libs.vm.spec import Affinity, CloudInitNoCloud, Devices, Interface, Network
from libs.vm.vm import BaseVirtualMachine, add_volume_disk, cloudinitdisk_storage
from tests.network.libs import cloudinit
from tests.network.libs.cloudinit import primary_iface_cloud_init


def primary_network_vm(
    namespace: str,
    name: str,
    client: DynamicClient,
    affinity: Affinity | None = None,
) -> BaseVirtualMachine:
    """Create a Fedora VM connected to the primary (masquerade) network only.

    Configures a static IPv6 address on the primary interface when the cluster supports IPv6.

    Args:
        namespace: Namespace in which the VM will be created.
        name: Name of the VM.
        client: Kubernetes dynamic client.
        affinity: Optional affinity rules for scheduling.

    Returns:
        Configured BaseVirtualMachine object (not yet started).
    """
    spec = base_vmspec()
    spec.template.spec.domain.devices = Devices(interfaces=[Interface(name="default", masquerade={})])
    spec.template.spec.networks = [Network(name="default", pod={})]
    spec.template.spec.affinity = affinity

    primary = primary_iface_cloud_init()
    if primary is not None:
        userdata = cloudinit.UserData(users=[])
        disk, volume = cloudinitdisk_storage(
            data=CloudInitNoCloud(
                networkData=cloudinit.asyaml(no_cloud=cloudinit.NetworkData(ethernets={"eth0": primary})),
                userData=cloudinit.format_cloud_config(userdata=userdata),
            )
        )
        spec.template.spec = add_volume_disk(vmi_spec=spec.template.spec, volume=volume, disk=disk)

    return fedora_vm(namespace=namespace, name=name, client=client, spec=spec)

from typing import Final

from kubernetes.dynamic import DynamicClient

from libs.net.vmspec import lookup_iface_status
from libs.vm.factory import base_vmspec, fedora_vm
from libs.vm.spec import (
    CloudInitNoCloud,
    DataVolumeRef,
    Devices,
    Disk,
    Interface,
    Multus,
    Network,
    SpecDisk,
    Volume,
)
from libs.vm.vm import BaseVirtualMachine, add_volume_disk, cloudinitdisk_storage
from tests.network.libs import cloudinit
from tests.network.libs.cloudinit import primary_iface_cloud_init

NET_SEED: Final[int] = 0

VM_IFACE_1: Final[str] = "iface-1"
VM_IFACE_2: Final[str] = "iface-2"

GUEST_IFACE_1: Final[str] = "eth1"
GUEST_IFACE_2: Final[str] = "eth2"


def iface_info(vm: BaseVirtualMachine, iface_name: str) -> dict:
    iface = lookup_iface_status(vm=vm, iface_name=iface_name)
    return {
        "name": iface.name,
        "macAddress": iface.macAddress,
        "ipAddresses": sorted(iface.ipAddresses or []),
    }


def bridge_vm(
    namespace: str,
    name: str,
    client: DynamicClient,
    nad_names: list[str],
    ip_addresses: list[list[str]],
    iface_names: list[str],
    runcmd: list[str] | None = None,
    rwo_dv_name: str | None = None,
    data_volume_template: dict | None = None,
) -> BaseVirtualMachine:
    """Create a Fedora VM with a masquerade primary interface and bridge-bound secondary interfaces.

    Interface layout in guest OS:
        eth0 = masquerade (pod network, primary — handles default route and IPv6)
        eth1 = first secondary bridge interface
        eth2 = second secondary bridge interface (if present)

    Args:
        namespace: Namespace to deploy the VM in.
        name: VM name.
        client: Kubernetes dynamic client.
        nad_names: NAD names (multus networkName) for the secondary interfaces, in spec order.
        ip_addresses: Per-interface CIDR address lists, aligned with nad_names.
            Each inner list contains one address per supported IP family.
        iface_names: Logical interface names for the VM spec, aligned with nad_names.
        rwo_dv_name: When set, boots from an existing RWO DataVolume instead of a container disk.
            The DataVolume's RWO access mode causes KubeVirt to set LiveMigratable: False.
        data_volume_template: When set, added to VM spec.dataVolumeTemplates so the VM
            owns and manages the DataVolume lifecycle.
    """
    spec = base_vmspec()
    spec.template.spec.domain.devices = Devices(
        interfaces=[
            Interface(name="default", masquerade={}),
            *[Interface(name=iface_name, bridge={}) for iface_name in iface_names],
        ]
    )
    spec.template.spec.networks = [
        Network(name="default", pod={}),
        *[
            Network(name=iface_name, multus=Multus(networkName=nad_name))
            for iface_name, nad_name in zip(iface_names, nad_names)
        ],
    ]
    ethernets = {}
    primary = primary_iface_cloud_init()
    if primary:
        ethernets["eth0"] = primary
    for i, addresses in enumerate(ip_addresses):
        ethernets[f"eth{i + 1}"] = cloudinit.EthernetDevice(addresses=addresses)
    userdata = cloudinit.UserData(users=[], runcmd=runcmd)
    disk, volume = cloudinitdisk_storage(
        data=CloudInitNoCloud(
            networkData=cloudinit.asyaml(no_cloud=cloudinit.NetworkData(ethernets=ethernets)) if ethernets else "",
            userData=cloudinit.format_cloud_config(userdata=userdata),
        )
    )
    if rwo_dv_name:
        dv_disk = SpecDisk(name=rwo_dv_name, disk=Disk(bus="virtio"))
        dv_volume = Volume(name=rwo_dv_name, dataVolume=DataVolumeRef(name=rwo_dv_name))
        spec.template.spec = add_volume_disk(vmi_spec=spec.template.spec, volume=dv_volume, disk=dv_disk)
    spec.template.spec = add_volume_disk(vmi_spec=spec.template.spec, volume=volume, disk=disk)
    vm = fedora_vm(namespace=namespace, name=name, client=client, spec=spec)
    if data_volume_template:
        vm.body["spec"].setdefault("dataVolumeTemplates", []).append(data_volume_template)
    return vm

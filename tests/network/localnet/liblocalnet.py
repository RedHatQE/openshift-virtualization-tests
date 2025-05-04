from libs.net import netattachdef
from libs.net.vmspec import add_network_interface, add_volume_disk
from libs.vm.affinity import new_pod_anti_affinity
from libs.vm.factory import base_vmspec, fedora_vm
from libs.vm.spec import CloudInitNoCloud, Interface, Metadata, Multus, Network
from libs.vm.vm import BaseVirtualMachine, cloudinitdisk_storage
from tests.network.libs import cloudinit

NETWORK_NAME = "localnet-network"


def localnet_vm(namespace: str, name: str, network: str, cidr: str) -> BaseVirtualMachine:
    """
    Create a Fedora-based Virtual Machine connected to a given localnet network with a static IP configuration.

    The VM will:
    - Attach to a Multus network using a bridge interface.
    - Apply a specific label for anti-affinity scheduling.
    - Use cloud-init to configure a static IP address.
    - Based on a standard Fedora VM template.

    Args:
        namespace (str): The namespace where the VM should be created.
        name (str): The name of the VM.
        network (str): The name of the Multus network to attach.
        cidr (str): The CIDR address to assign to the VM's interface.

    Returns:
        BaseVirtualMachine: The configured VM object ready for creation.
    """
    spec = base_vmspec()
    spec.template.metadata = spec.template.metadata or Metadata()
    spec.template.metadata.labels = spec.template.metadata.labels or {}
    localnet_test_label = {"test": "localnet"}
    spec.template.metadata.labels.update(localnet_test_label)
    vmi_spec = spec.template.spec

    vmi_spec = add_network_interface(
        vmi_spec=vmi_spec,
        network=Network(name=NETWORK_NAME, multus=Multus(networkName=network)),
        interface=Interface(name=NETWORK_NAME, bridge={}),
    )

    netdata = cloudinit.NetworkData(ethernets={"eth0": cloudinit.EthernetDevice(addresses=[cidr])})
    # Prevents cloud-init from overriding the default OS user credentials
    userdata = cloudinit.UserData(users=[])
    disk, volume = cloudinitdisk_storage(
        data=CloudInitNoCloud(
            networkData=cloudinit.asyaml(no_cloud=netdata), userData=cloudinit.format_cloud_config(userdata=userdata)
        )
    )
    vmi_spec = add_volume_disk(vmi_spec=vmi_spec, volume=volume, disk=disk)

    vmi_spec.affinity = new_pod_anti_affinity(label=next(iter(localnet_test_label.items())))
    vmi_spec.affinity.podAntiAffinity.requiredDuringSchedulingIgnoredDuringExecution[0].namespaceSelector = {}

    return fedora_vm(namespace=namespace, name=name, spec=spec)


def localnet_nad(namespace: str, name: str, vlan_id: int) -> netattachdef.NetworkAttachmentDefinition:
    return netattachdef.NetworkAttachmentDefinition(
        namespace=namespace,
        name=name,
        config=netattachdef.NetConfig(
            NETWORK_NAME,
            [
                netattachdef.CNIPluginOvnK8sConfig(
                    topology=netattachdef.CNIPluginOvnK8sConfig.Topology.LOCALNET.value,
                    netAttachDefName=f"{namespace}/{name}",
                    vlanID=vlan_id,
                )
            ],
        ),
    )

from libs.net import netattachdef
from libs.net.traffic_generator import Client, Server
from libs.net.vmspec import IP_ADDRESS, add_network_interface, add_volume_disk, lookup_iface_status
from libs.vm.affinity import new_pod_anti_affinity
from libs.vm.factory import base_vmspec, fedora_vm
from libs.vm.spec import CloudInitNoCloud, Interface, Metadata, Multus, Network
from libs.vm.vm import BaseVirtualMachine, cloudinitdisk_storage
from tests.network.libs import cloudinit

_IPERF_SERVER_PORT = 5201


def run_vms(vms: tuple[BaseVirtualMachine, ...]) -> tuple[BaseVirtualMachine, ...]:
    for vm in vms:
        vm.start()
    for vm in vms:
        vm.wait_for_ready_status(status=True)
        vm.vmi.wait_for_condition(condition=vm.Condition.Type.AGENT_CONNECTED, status=vm.Condition.Status.TRUE)
    return vms


def create_traffic_server(vm: BaseVirtualMachine) -> Server:
    return Server(vm=vm, port=_IPERF_SERVER_PORT)


def create_traffic_client(server_vm: BaseVirtualMachine, client_vm: BaseVirtualMachine, network_name: str) -> Client:
    return Client(
        vm=client_vm,
        server_ip=lookup_iface_status(vm=server_vm, iface_name=network_name)[IP_ADDRESS],
        server_port=_IPERF_SERVER_PORT,
    )


def localnet_vm(namespace: str, name: str, nad_name: str, cidr: str, spec_logical_network: str) -> BaseVirtualMachine:
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
        nad_name (str): The name of the Multus network to attach.
        cidr (str): The CIDR address to assign to the VM's interface.
        spec_logical_network (str): The name of the localnet network to attach.

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
        network=Network(name=spec_logical_network, multus=Multus(networkName=nad_name)),
        interface=Interface(name=spec_logical_network, bridge={}),
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


def localnet_nad(
    namespace: str, name: str, vlan_id: int, network_name: str
) -> netattachdef.NetworkAttachmentDefinition:
    """
    Create a Network Attachment Definition for a localnet network.

    Args:
        namespace (str): The namespace for the NetworkAttachmentDefinition.
        name (str): The name of the NetworkAttachmentDefinition.
        vlan_id (int): The VLAN ID for the network.
        network_name (str): The name to use for the network.

    Returns:
        NetworkAttachmentDefinition: The configured NetworkAttachmentDefinition object.
    """
    return netattachdef.NetworkAttachmentDefinition(
        namespace=namespace,
        name=name,
        config=netattachdef.NetConfig(
            network_name,
            [
                netattachdef.CNIPluginOvnK8sConfig(
                    topology=netattachdef.CNIPluginOvnK8sConfig.Topology.LOCALNET.value,
                    netAttachDefName=f"{namespace}/{name}",
                    vlanID=vlan_id,
                )
            ],
        ),
    )

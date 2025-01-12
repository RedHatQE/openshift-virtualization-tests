import ipaddress

import pytest
from ocp_resources.resource import Resource
from ocp_resources.user_defined_network import Layer2UserDefinedNetwork
from ocp_resources.utils.constants import TIMEOUT_1MINUTE, TIMEOUT_30SEC
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from libs.vm import affinity
from libs.vm.affinity import new_pod_anti_affinity
from libs.vm.factory import base_vmspec, fedora_vm
from libs.vm.spec import Interface, NetBinding, Network
from utilities.constants import PUBLIC_DNS_SERVER_IP, TIMEOUT_1MIN
from utilities.virt import migrate_vm_and_verify

# For version 4.18, this module can only run on clusters where FeatureGate is configured with
# featureSet TechPreviewNoUpgrade.
pytestmark = pytest.mark.udn

IP_ADDRESS = "ipAddress"


def udn_vm(namespace_name, name, template_labels=None):
    spec = base_vmspec()
    iface, network = udn_primary_network(name="udn-primary")
    spec.template.spec.domain.devices.interfaces = [iface]
    spec.template.spec.networks = [network]
    if template_labels:
        spec.template.metadata.labels = spec.template.metadata.labels or {}
        spec.template.metadata.labels.update(template_labels)
        # Use the first label key and first value as the anti-affinity label to use:
        label, *_ = template_labels.items()
        spec.template.spec.affinity = new_pod_anti_affinity(label=label)

    return fedora_vm(namespace=namespace_name, name=name, spec=spec)


def udn_primary_network(name):
    return Interface(name=name, binding=NetBinding(name="l2bridge")), Network(name=name, pod={})


class VMInterfaceNotFoundError(Exception):
    pass


def vm_primary_network_name(vm):
    vm_primary_network_type = "pod"
    for network in vm.instance.spec.template.spec.networks:
        if vm_primary_network_type in network.keys():
            return network.name
    raise VMInterfaceNotFoundError(f"No interface connected to the primary network was found in VM {vm.name}.")


def iface_lookup(vm, iface_name, predicate):
    """
    Returns the interface requested if found and the predicate function (to which the interface is
    sent) returns True. Else, raise VMInterfaceNotFound.

    Args:
        vm (BaseVirtualMachine): VM in which to search for the network interface.
        iface_name (str): The name of the requested interface.
        predicate (function): A function that takes a network interface as an argument
            and returns a boolean value. This function should define the condition that
            the interface needs to meet.

    Returns:
        iface (dict): The requested interface.

    Raises:
        VMInterfaceNotFound: If the requested interface was not found in the VM.
    """
    for iface in vm.vmi.interfaces:
        if iface.name == iface_name and predicate(iface):
            return iface
    raise VMInterfaceNotFoundError(f"Network interface named {iface_name} was not found in VM {vm.name}.")


def wait_for_vm_iface(vm, iface_name, timeout, sleep, predicate=lambda iface: True):
    samples = TimeoutSampler(
        wait_timeout=timeout,
        sleep=sleep,
        func=iface_lookup,
        vm=vm,
        iface_name=iface_name,
        predicate=predicate,
        exceptions_dict={VMInterfaceNotFoundError: []},
    )
    for sample in samples:
        if sample:
            return sample


def get_iface(vm, iface_name):
    try:
        return wait_for_vm_iface(
            vm=vm,
            iface_name=iface_name,
            timeout=30,
            sleep=5,
            predicate=lambda interface: "guest-agent" in interface["infoSource"] and interface[IP_ADDRESS],
        )
    except TimeoutExpiredError:
        raise VMInterfaceNotFoundError(f"Network interface named {iface_name} was not found in VM {vm.name}.")


@pytest.fixture(scope="module")
def namespaced_layer2_user_defined_network(namespace):
    with Layer2UserDefinedNetwork(
        name="layer2-udn",
        namespace=namespace.name,
        role="Primary",
        subnets=["10.10.0.0/24"],
        ipam_lifecycle="Persistent",
    ) as udn:
        udn.wait_for_condition(
            condition="NetworkReady",
            status=Resource.Condition.Status.TRUE,
            timeout=TIMEOUT_30SEC,
        )
        yield udn


@pytest.fixture(scope="class")
def udn_affinity_label():
    return affinity.new_label(key_prefix="udn")


@pytest.fixture(scope="class")
def vma_udn(namespace, namespaced_layer2_user_defined_network, udn_affinity_label):
    with udn_vm(namespace_name=namespace.name, name="vma-udn", template_labels=dict((udn_affinity_label,))) as vm:
        vm.start(wait=True)
        vm.vmi.wait_for_condition(condition="AgentConnected", status=Resource.Condition.Status.TRUE)
        yield vm


@pytest.fixture(scope="class")
def vmb_udn_non_migratable(namespace, namespaced_layer2_user_defined_network, udn_affinity_label):
    with udn_vm(namespace_name=namespace.name, name="vmb-udn", template_labels=dict((udn_affinity_label,))) as vm:
        vm.start(wait=True)
        vm.vmi.wait_for_condition(condition="AgentConnected", status=Resource.Condition.Status.TRUE)
        yield vm


@pytest.mark.ipv4
class TestPrimaryUdn:
    @pytest.mark.polarion("CNV-11624")
    def test_ip_address_in_running_vm_matches_udn_subnet(self, namespaced_layer2_user_defined_network, vma_udn):
        ip = get_iface(vm=vma_udn, iface_name=vm_primary_network_name(vm=vma_udn))[IP_ADDRESS]
        (subnet,) = namespaced_layer2_user_defined_network.subnets
        assert ipaddress.ip_address(ip) in ipaddress.ip_network(subnet), (
            f"The VM's primary network IP address ({ip}) is not in the UDN defined subnet ({subnet})"
        )

    @pytest.mark.polarion("CNV-11674")
    def test_ip_address_is_preserved_during_live_migration(self, namespaced_layer2_user_defined_network, vma_udn):
        ip_before_migration = get_iface(vm=vma_udn, iface_name=vm_primary_network_name(vm=vma_udn))[IP_ADDRESS]
        assert ip_before_migration
        migrate_vm_and_verify(vm=vma_udn)
        ip_after_migration = get_iface(vm=vma_udn, iface_name=vm_primary_network_name(vm=vma_udn))[IP_ADDRESS]
        assert ip_before_migration == ip_after_migration, (
            f"The IP address {ip_before_migration} was not preserved during live migration. "
            f"IP after migration: {ip_after_migration}."
        )

    @pytest.mark.polarion("CNV-11434")
    def test_vm_egress_connectivity(self, namespaced_layer2_user_defined_network, vmb_udn_non_migratable):
        assert get_iface(vm=vmb_udn_non_migratable, iface_name=vm_primary_network_name(vm=vmb_udn_non_migratable))[
            IP_ADDRESS
        ]
        vmb_udn_non_migratable.console(commands=[f"ping -c 3 {PUBLIC_DNS_SERVER_IP}"], timeout=TIMEOUT_1MINUTE)

    @pytest.mark.polarion("CNV-11418")
    def test_basic_connectivity_between_udn_vms(self, vma_udn, vmb_udn_non_migratable):
        target_vm_ip = get_iface(
            vm=vmb_udn_non_migratable, iface_name=vm_primary_network_name(vm=vmb_udn_non_migratable)
        )[IP_ADDRESS]
        vma_udn.console(commands=[f"ping -c 3 {target_vm_ip}"], timeout=TIMEOUT_1MIN)

import time

import pytest

from libs.net import netattachdef
from tests.network.constants import IPV4_ADDRESS_SUBNET_PREFIX
from tests.network.l2_bridge.utils import (
    check_mac_released,
    create_bridge_interface_for_hot_plug,
    create_vm_for_hot_plug,
    create_vm_with_hot_plugged_sriov_interface,
    create_vm_with_secondary_interface_on_setup,
    get_kubemacpool_controller_log,
    get_primary_and_hot_plugged_mac_addresses,
    hot_plug_interface,
    hot_plug_interface_and_set_address,
    hot_unplug_interface,
    search_hot_plugged_interface_in_vmi,
    set_secondary_static_ip_address,
    wait_for_interface_hot_plug_completion,
)
from utilities.constants import FLAT_OVERLAY_STR, SRIOV
from utilities.network import (
    IfaceNotFound,
    assert_ping_successful,
    get_vmi_ip_v4_by_name,
    network_nad,
)
from utilities.virt import migrate_vm_and_verify, running_vm

pytestmark = [
    pytest.mark.special_infra,
    pytest.mark.usefixtures(
        "label_schedulable_nodes",
    ),
]

HOT_PLUG_STR = "hot-plug"
TEST_BASIC_HOT_PLUGGED_INTERFACE_CONNECTIVITY = "test_basic_connectivity_of_hot_plugged_interface"
SECONDARY_SETUP_INTERFACE_NAME = "eth1"


@pytest.fixture(scope="class")
def running_vm_for_nic_hot_plug(namespace, unprivileged_client):
    vm_name = f"{HOT_PLUG_STR}-test-vm"
    with create_vm_for_hot_plug(
        namespace_name=namespace.name,
        vm_name=vm_name,
        client=unprivileged_client,
    ) as vm:
        yield vm


@pytest.fixture(scope="module")
def bridge_interface_for_hot_plug(hosts_common_available_ports):
    yield from create_bridge_interface_for_hot_plug(
        bridge_name=f"{HOT_PLUG_STR}-br",
        bridge_port=hosts_common_available_ports[-1],
    )


@pytest.fixture(scope="module")
def network_attachment_definition_for_hot_plug(
    namespace,
    bridge_interface_for_hot_plug,
):
    bridge_name = bridge_interface_for_hot_plug.bridge_name
    with netattachdef.NetworkAttachmentDefinition(
        namespace=namespace.name,
        name=f"{bridge_name}-nad",
        config=netattachdef.NetConfig(bridge_name, [netattachdef.CNIPluginBridgeConfig(bridge=bridge_name)]),
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def hot_plugged_interface_name(
    running_vm_for_nic_hot_plug,
    network_attachment_definition_for_hot_plug,
):
    hot_plugged_interface_name = f"{HOT_PLUG_STR}-iface"
    hot_plug_interface(
        vm=running_vm_for_nic_hot_plug,
        hot_plugged_interface_name=hot_plugged_interface_name,
        net_attach_def_name=network_attachment_definition_for_hot_plug.name,
    )

    return hot_plugged_interface_name


@pytest.fixture()
def multiple_hot_plugged_interfaces(running_vm_for_nic_hot_plug, network_attachment_definition_for_hot_plug):
    hot_plugged_interfaces = []
    # Perform extra 3 hot-plug actions (which are added to a previous hot-plug)
    for index in range(3):
        hot_plugged_interface_name = f"{HOT_PLUG_STR}-{index}"
        hot_plug_interface(
            vm=running_vm_for_nic_hot_plug,
            hot_plugged_interface_name=hot_plugged_interface_name,
            net_attach_def_name=network_attachment_definition_for_hot_plug.name,
        )
        hot_plugged_interfaces.append(hot_plugged_interface_name)

    return hot_plugged_interfaces


@pytest.fixture(scope="module")
def running_utility_vm_for_connectivity_check(
    namespace,
    unprivileged_client,
    network_attachment_definition_for_hot_plug,
    index_number,
):
    # The VM that is created with a secondary interface can utilize the same net-attach-def (and node bridge
    # interface) which is used by the VM with hot-plugged interface.
    yield from create_vm_with_secondary_interface_on_setup(
        namespace=namespace,
        client=unprivileged_client,
        bridge_nad=network_attachment_definition_for_hot_plug,
        vm_name=f"utility-{HOT_PLUG_STR}-vm",
        ipv4_address_subnet_prefix=IPV4_ADDRESS_SUBNET_PREFIX,
        ipv4_address_suffix=next(index_number),
    )


@pytest.fixture()
def hot_plugged_interface_with_address(running_vm_for_nic_hot_plug, index_number, hot_plugged_interface_name):
    set_secondary_static_ip_address(
        vm=running_vm_for_nic_hot_plug,
        ipv4_address=f"{IPV4_ADDRESS_SUBNET_PREFIX}.{next(index_number)}",
        vmi_interface=hot_plugged_interface_name,
    )


@pytest.fixture(scope="class")
def running_vm_with_secondary_and_hot_plugged_interfaces(
    namespace,
    unprivileged_client,
    network_attachment_definition_for_hot_plug,
    index_number,
):
    yield from create_vm_with_secondary_interface_on_setup(
        namespace=namespace,
        client=unprivileged_client,
        bridge_nad=network_attachment_definition_for_hot_plug,
        vm_name=f"vm-with-sec-and-{HOT_PLUG_STR}-interfaces",
        ipv4_address_subnet_prefix=IPV4_ADDRESS_SUBNET_PREFIX,
        ipv4_address_suffix=next(index_number),
    )


@pytest.fixture(scope="class")
def hot_plugged_interface_name_on_vm_created_with_secondary_interface(
    running_vm_with_secondary_and_hot_plugged_interfaces,
    network_attachment_definition_for_hot_plug,
):
    hot_plugged_interface_name = f"{HOT_PLUG_STR}-additional-iface"
    hot_plug_interface(
        vm=running_vm_with_secondary_and_hot_plugged_interfaces,
        hot_plugged_interface_name=hot_plugged_interface_name,
        net_attach_def_name=network_attachment_definition_for_hot_plug.name,
    )
    # In order to complete the interface hot-plug, and have the interface available in the guest VM -
    # the VM must be migrated.
    migrate_vm_and_verify(vm=running_vm_with_secondary_and_hot_plugged_interfaces)

    return hot_plugged_interface_name


@pytest.fixture()
def hot_plugged_second_interface_with_address(
    running_vm_with_secondary_and_hot_plugged_interfaces,
    index_number,
    hot_plugged_interface_name_on_vm_created_with_secondary_interface,
):
    set_secondary_static_ip_address(
        vm=running_vm_with_secondary_and_hot_plugged_interfaces,
        ipv4_address=f"{IPV4_ADDRESS_SUBNET_PREFIX}.{next(index_number)}",
        vmi_interface=hot_plugged_interface_name_on_vm_created_with_secondary_interface,
    )


@pytest.fixture()
def migrated_vm_with_hot_plugged_interface_attached(running_vm_for_nic_hot_plug):
    # In order to complete the interface hot-plug, and have the interface available in the guest VM -
    # the VM must be migrated.
    migrate_vm_and_verify(vm=running_vm_for_nic_hot_plug)
    return running_vm_for_nic_hot_plug


@pytest.fixture()
def running_vm_for_jumbo_nic_hot_plug(namespace, unprivileged_client):
    vm_name = f"jumbo-{HOT_PLUG_STR}-test-vm"
    with create_vm_for_hot_plug(
        namespace_name=namespace.name,
        vm_name=vm_name,
        client=unprivileged_client,
    ) as vm:
        yield vm


@pytest.fixture()
def bridge_jumbo_interface_for_hot_plug(hosts_common_available_ports, cluster_hardware_mtu):
    yield from create_bridge_interface_for_hot_plug(
        bridge_name=f"{HOT_PLUG_STR}-jumbo",
        # hosts_common_available_ports[-1] is already used for another tests bridge.
        bridge_port=hosts_common_available_ports[-2],
        mtu=cluster_hardware_mtu,
    )


@pytest.fixture()
def network_attachment_definition_for_jumbo_hot_plug(
    namespace,
    bridge_jumbo_interface_for_hot_plug,
    cluster_hardware_mtu,
):
    bridge_name = bridge_jumbo_interface_for_hot_plug.bridge_name
    with netattachdef.NetworkAttachmentDefinition(
        namespace=namespace.name,
        name=f"{bridge_name}-nad",
        config=netattachdef.NetConfig(
            bridge_name,
            [
                netattachdef.CNIPluginBridgeConfig(
                    bridge=bridge_name,
                    mtu=cluster_hardware_mtu,
                )
            ],
        ),
    ) as nad:
        yield nad


@pytest.fixture()
def hot_plugged_jumbo_interface_with_address(
    running_vm_for_jumbo_nic_hot_plug,
    network_attachment_definition_for_jumbo_hot_plug,
    index_number,
):
    hot_plugged_interface_name = f"{HOT_PLUG_STR}-jumbo-iface"
    hot_plug_interface_and_set_address(
        vm=running_vm_for_jumbo_nic_hot_plug,
        hot_plugged_interface_name=hot_plugged_interface_name,
        net_attach_def_name=network_attachment_definition_for_jumbo_hot_plug.name,
        ipv4_address=f"{IPV4_ADDRESS_SUBNET_PREFIX}.{next(index_number)}",
    )

    return hot_plugged_interface_name


@pytest.fixture()
def hot_plugged_jumbo_interface_in_utility_vm(
    running_utility_vm_for_connectivity_check,
    network_attachment_definition_for_jumbo_hot_plug,
    index_number,
):
    hot_plugged_interface_name = f"{HOT_PLUG_STR}-jumbo-utility-iface"

    hot_plug_interface_and_set_address(
        vm=running_utility_vm_for_connectivity_check,
        hot_plugged_interface_name=hot_plugged_interface_name,
        net_attach_def_name=network_attachment_definition_for_jumbo_hot_plug.name,
        ipv4_address=f"{IPV4_ADDRESS_SUBNET_PREFIX}.{next(index_number)}",
    )

    yield hot_plugged_interface_name

    hot_unplug_interface(
        vm=running_utility_vm_for_connectivity_check,
        hot_plugged_interface_name=hot_plugged_interface_name,
    )


@pytest.fixture()
def hot_plugged_interface_name_from_flat_overlay_network(
    running_vm_for_nic_hot_plug,
    flat_overlay_network_attachment_definition_for_hot_plug,
):
    hot_plugged_flat_interface_name = f"flat-{HOT_PLUG_STR}-iface"
    hot_plug_interface(
        vm=running_vm_for_nic_hot_plug,
        hot_plugged_interface_name=hot_plugged_flat_interface_name,
        net_attach_def_name=flat_overlay_network_attachment_definition_for_hot_plug.name,
    )

    return hot_plugged_flat_interface_name


@pytest.fixture()
def flat_overlay_network_attachment_definition_for_hot_plug(
    namespace,
):
    with network_nad(
        namespace=namespace,
        nad_type=FLAT_OVERLAY_STR,
        nad_name=f"{FLAT_OVERLAY_STR}-nad",
        network_name=f"{FLAT_OVERLAY_STR}-network",
        topology=FLAT_OVERLAY_STR,
    ) as nad:
        yield nad


@pytest.fixture()
def vm_for_hot_plug_and_kmp(namespace, unprivileged_client):
    with create_vm_for_hot_plug(
        namespace_name=namespace.name,
        vm_name=f"{HOT_PLUG_STR}-kmp-release-vm",
        client=unprivileged_client,
    ) as vm:
        yield vm


@pytest.fixture()
def hot_plugged_interface_for_kmp_removal(
    vm_for_hot_plug_and_kmp,
    network_attachment_definition_for_hot_plug,
):
    hot_plugged_interface_name = f"{HOT_PLUG_STR}-and-kmp-iface"
    hot_plug_interface(
        vm=vm_for_hot_plug_and_kmp,
        hot_plugged_interface_name=hot_plugged_interface_name,
        net_attach_def_name=network_attachment_definition_for_hot_plug.name,
    )

    return hot_plugged_interface_name


@pytest.fixture()
def hot_plugged_kmp_interface_mac_for_vm_deletion(
    vm_for_hot_plug_and_kmp,
    hot_plugged_interface_for_kmp_removal,
):
    return search_hot_plugged_interface_in_vmi(
        vm=vm_for_hot_plug_and_kmp,
        interface_name=hot_plugged_interface_for_kmp_removal,
    ).macAddress


@pytest.fixture()
def hot_plug_and_kmp_vm_delete_time(vm_for_hot_plug_and_kmp):
    current_time = time.time()
    vm_for_hot_plug_and_kmp.clean_up()
    return current_time


@pytest.fixture()
def kubemacpool_controller_log_for_vm_deletion(admin_client, hco_namespace, hot_plug_and_kmp_vm_delete_time):
    return get_kubemacpool_controller_log(
        client=admin_client,
        namespace_name=hco_namespace.name,
        log_start_time=hot_plug_and_kmp_vm_delete_time,
    )


@pytest.fixture()
def hot_unplugged_additional_interface(
    namespace,
    running_vm_with_secondary_and_hot_plugged_interfaces,
    hot_plugged_interface_name_on_vm_created_with_secondary_interface,
):
    hot_unplug_interface(
        vm=running_vm_with_secondary_and_hot_plugged_interfaces,
        hot_plugged_interface_name=hot_plugged_interface_name_on_vm_created_with_secondary_interface,
    )
    migrate_vm_and_verify(vm=running_vm_with_secondary_and_hot_plugged_interfaces)
    return hot_plugged_interface_name_on_vm_created_with_secondary_interface


@pytest.fixture(scope="class")
def hot_unplugged_interface_mac_address(
    hot_plugged_interface_name_on_vm_created_with_secondary_interface,
    running_vm_with_secondary_and_hot_plugged_interfaces,
):
    return search_hot_plugged_interface_in_vmi(
        vm=running_vm_with_secondary_and_hot_plugged_interfaces,
        interface_name=hot_plugged_interface_name_on_vm_created_with_secondary_interface,
    ).macAddress


@pytest.fixture()
def kubemacpool_controller_log_for_hot_unplug(admin_client, hco_namespace, secondary_interfaces_tests_start_time):
    return get_kubemacpool_controller_log(
        client=admin_client,
        namespace_name=hco_namespace.name,
        log_start_time=secondary_interfaces_tests_start_time,
    )


@pytest.fixture(scope="class")
def secondary_interfaces_tests_start_time():
    return time.time()


@pytest.fixture()
def mac_addresses_before_restart(running_vm_for_nic_hot_plug, hot_plugged_interface_name):
    return get_primary_and_hot_plugged_mac_addresses(
        vm=running_vm_for_nic_hot_plug,
        hot_plugged_interface=hot_plugged_interface_name,
    )


@pytest.fixture()
def mac_addresses_after_restart(running_vm_for_nic_hot_plug, hot_plugged_interface_name):
    running_vm_for_nic_hot_plug.restart(wait=True)
    running_vm(vm=running_vm_for_nic_hot_plug)

    return get_primary_and_hot_plugged_mac_addresses(
        vm=running_vm_for_nic_hot_plug,
        hot_plugged_interface=hot_plugged_interface_name,
    )


@pytest.fixture()
def hot_unplug_secondary_interface_from_setup(
    running_vm_with_secondary_and_hot_plugged_interfaces,
    network_attachment_definition_for_hot_plug,
    namespace,
):
    hot_unplug_interface(
        vm=running_vm_with_secondary_and_hot_plugged_interfaces,
        hot_plugged_interface_name=network_attachment_definition_for_hot_plug.name,
    )
    migrate_vm_and_verify(vm=running_vm_with_secondary_and_hot_plugged_interfaces)


@pytest.fixture()
def vm1_with_hot_plugged_sriov_interface(
    namespace,
    unprivileged_client,
    sriov_network_for_hot_plug,
    index_number,
):
    yield from create_vm_with_hot_plugged_sriov_interface(
        namespace_name=namespace.name,
        vm_name=f"{SRIOV}-{HOT_PLUG_STR}-vm1",
        sriov_network_for_hot_plug=sriov_network_for_hot_plug,
        ipv4_address=f"{IPV4_ADDRESS_SUBNET_PREFIX}.{next(index_number)}",
        client=unprivileged_client,
    )


@pytest.fixture()
def vm2_with_hot_plugged_sriov_interface(
    namespace,
    unprivileged_client,
    sriov_network_for_hot_plug,
    index_number,
):
    yield from create_vm_with_hot_plugged_sriov_interface(
        namespace_name=namespace.name,
        vm_name=f"{SRIOV}-{HOT_PLUG_STR}-vm2",
        sriov_network_for_hot_plug=sriov_network_for_hot_plug,
        ipv4_address=f"{IPV4_ADDRESS_SUBNET_PREFIX}.{next(index_number)}",
        client=unprivileged_client,
    )


@pytest.fixture(scope="module")
def sriov_network_for_hot_plug(sriov_node_policy, namespace, sriov_namespace):
    with network_nad(
        nad_type=SRIOV,
        nad_name="sriov-hot-plug-test-network",
        sriov_resource_name=sriov_node_policy.resource_name,
        namespace=sriov_namespace,
        sriov_network_namespace=namespace.name,
    ) as sriov_network:
        yield sriov_network


class TestHotPlugInterfaceToVmWithOnlyPrimaryInterface:
    @pytest.mark.polarion("CNV-10115")
    @pytest.mark.post_upgrade
    @pytest.mark.dependency(
        name="test_vmi_spec_updated_with_hot_plugged_interface",
    )
    def test_vmi_spec_updated_with_hot_plugged_interface(
        self,
        running_vm_for_nic_hot_plug,
        hot_plugged_interface_name,
    ):
        wait_for_interface_hot_plug_completion(
            vmi=running_vm_for_nic_hot_plug.vmi,
            interface_name=hot_plugged_interface_name,
        )

    @pytest.mark.polarion("CNV-10166")
    @pytest.mark.dependency(
        name="test_multiple_interfaces_hot_plugged",
        depends=["test_vmi_spec_updated_with_hot_plugged_interface"],
    )
    def test_multiple_interfaces_hot_plugged(
        self,
        running_vm_for_nic_hot_plug,
        multiple_hot_plugged_interfaces,
    ):
        # Hot-plug feature should be able to support up to 4 hot-plugged interfaces
        for interface in multiple_hot_plugged_interfaces:
            wait_for_interface_hot_plug_completion(vmi=running_vm_for_nic_hot_plug.vmi, interface_name=interface)

    @pytest.mark.ipv4
    @pytest.mark.polarion("CNV-10130")
    @pytest.mark.post_upgrade
    @pytest.mark.dependency(
        name=TEST_BASIC_HOT_PLUGGED_INTERFACE_CONNECTIVITY,
        depends=["test_vmi_spec_updated_with_hot_plugged_interface"],
    )
    def test_basic_connectivity_of_hot_plugged_interface(
        self,
        migrated_vm_with_hot_plugged_interface_attached,
        running_utility_vm_for_connectivity_check,
        hot_plugged_interface_with_address,
        network_attachment_definition_for_hot_plug,
    ):
        assert_ping_successful(
            src_vm=migrated_vm_with_hot_plugged_interface_attached,
            dst_ip=get_vmi_ip_v4_by_name(
                vm=running_utility_vm_for_connectivity_check,
                name=network_attachment_definition_for_hot_plug.name,
            ),
        )

    @pytest.mark.ipv4
    @pytest.mark.polarion("CNV-10131")
    @pytest.mark.dependency(
        name="test_basic_connectivity_of_hot_plugged_interface_after_second_migration",
        depends=[TEST_BASIC_HOT_PLUGGED_INTERFACE_CONNECTIVITY],
    )
    def test_basic_connectivity_of_hot_plugged_interface_after_second_migration(
        self,
        running_utility_vm_for_connectivity_check,
        network_attachment_definition_for_hot_plug,
        migrated_vm_with_hot_plugged_interface_attached,
    ):
        assert_ping_successful(
            src_vm=migrated_vm_with_hot_plugged_interface_attached,
            dst_ip=get_vmi_ip_v4_by_name(
                vm=running_utility_vm_for_connectivity_check,
                name=network_attachment_definition_for_hot_plug.name,
            ),
        )

    @pytest.mark.polarion("CNV-10137")
    @pytest.mark.dependency(
        name="test_mac_of_hot_plugged_interface_from_kubemacpool",
        depends=["test_vmi_spec_updated_with_hot_plugged_interface"],
    )
    def test_mac_of_hot_plugged_interface_from_kubemacpool(
        self,
        running_vm_for_nic_hot_plug,
        mac_pool,
        hot_plugged_interface_name,
    ):
        interface = search_hot_plugged_interface_in_vmi(
            vm=running_vm_for_nic_hot_plug, interface_name=hot_plugged_interface_name
        )
        assert mac_pool.mac_is_within_range(interface.macAddress), (
            f"MAC address {interface.macAddress} of hot-plugged interface {hot_plugged_interface_name} is out"
            f"of KubeMacPool range {mac_pool.range_start} - {mac_pool.range_end}"
        )

    @pytest.mark.polarion("CNV-10306")
    @pytest.mark.dependency(
        name="test_primary_interface_not_modified_after_hot_plug",
        depends=[TEST_BASIC_HOT_PLUGGED_INTERFACE_CONNECTIVITY],
    )
    def test_primary_interface_not_modified_after_hot_plug(
        self,
        running_vm_for_nic_hot_plug,
        mac_addresses_before_restart,
        mac_addresses_after_restart,
    ):
        # This test is executed to verify such bug (2224104) doesn't happen again.
        assert mac_addresses_after_restart == mac_addresses_before_restart

    @pytest.mark.ipv4
    @pytest.mark.polarion("CNV-10135")
    def test_connectivity_of_hot_plugged_jumbo_interface(
        self,
        running_vm_for_jumbo_nic_hot_plug,
        network_attachment_definition_for_jumbo_hot_plug,
        hot_plugged_jumbo_interface_with_address,
        hot_plugged_jumbo_interface_in_utility_vm,
        running_utility_vm_for_connectivity_check,
        cluster_hardware_mtu,
    ):
        assert_ping_successful(
            src_vm=running_vm_for_jumbo_nic_hot_plug,
            dst_ip=get_vmi_ip_v4_by_name(
                vm=running_utility_vm_for_connectivity_check,
                name=hot_plugged_jumbo_interface_in_utility_vm,
            ),
            packet_size=cluster_hardware_mtu,
        )

    @pytest.mark.polarion("CNV-10169")
    @pytest.mark.post_upgrade
    def test_hot_plug_flat_overlay_network(
        self,
        running_vm_for_nic_hot_plug,
        hot_plugged_interface_name_from_flat_overlay_network,
    ):
        wait_for_interface_hot_plug_completion(
            vmi=running_vm_for_nic_hot_plug.vmi,
            interface_name=hot_plugged_interface_name_from_flat_overlay_network,
        )

    @pytest.mark.polarion("CNV-10138")
    def test_mac_of_hot_plugged_interface_returned_to_kubemacpool_after_vm_delete(
        self,
        hot_plugged_kmp_interface_mac_for_vm_deletion,
        kubemacpool_controller_log_for_vm_deletion,
    ):
        assert check_mac_released(
            kubemacpool_controller_log=kubemacpool_controller_log_for_vm_deletion,
            interface_mac_address=hot_plugged_kmp_interface_mac_for_vm_deletion,
        ), (
            f"MAC address {hot_plugged_kmp_interface_mac_for_vm_deletion} "
            f"of hot-plugged interface was not released upon VM deletion."
        )

    @pytest.mark.special_infra
    @pytest.mark.ipv4
    @pytest.mark.polarion("CNV-10647")
    def test_connectivity_of_hot_plugged_sriov_interface(
        self,
        vm1_with_hot_plugged_sriov_interface,
        vm2_with_hot_plugged_sriov_interface,
        sriov_network_for_hot_plug,
    ):
        assert_ping_successful(
            src_vm=vm1_with_hot_plugged_sriov_interface,
            dst_ip=get_vmi_ip_v4_by_name(
                vm=vm2_with_hot_plugged_sriov_interface,
                name=sriov_network_for_hot_plug.name,
            ),
        )


@pytest.mark.usefixtures("secondary_interfaces_tests_start_time", "hot_unplugged_interface_mac_address")
class TestHotPlugInterfaceToVmWithSecondaryInterface:
    @pytest.mark.parametrize(
        "guest_interface_name",
        [
            pytest.param(
                "eth2",
                marks=(pytest.mark.polarion("CNV-10136")),
            ),
            pytest.param(
                SECONDARY_SETUP_INTERFACE_NAME,
                marks=(pytest.mark.polarion("CNV-10150")),
            ),
        ],
    )
    @pytest.mark.ipv4
    def test_basic_connectivity_vm_with_secondary_and_hot_plugged_interfaces(
        self,
        running_vm_with_secondary_and_hot_plugged_interfaces,
        running_utility_vm_for_connectivity_check,
        hot_plugged_interface_name_on_vm_created_with_secondary_interface,
        hot_plugged_second_interface_with_address,
        network_attachment_definition_for_hot_plug,
        guest_interface_name,
    ):
        assert_ping_successful(
            src_vm=running_vm_with_secondary_and_hot_plugged_interfaces,
            dst_ip=get_vmi_ip_v4_by_name(
                vm=running_utility_vm_for_connectivity_check,
                name=network_attachment_definition_for_hot_plug.name,
            ),
            interface=guest_interface_name,
        )

    @pytest.mark.polarion("CNV-10147")
    @pytest.mark.post_upgrade
    @pytest.mark.dependency(
        name="test_hot_unplugged_interface_removed_from_vmi_spec",
    )
    def test_hot_unplugged_interface_removed_from_vmi_spec(
        self,
        hot_unplugged_additional_interface,
        running_vm_with_secondary_and_hot_plugged_interfaces,
    ):
        with pytest.raises(IfaceNotFound):
            search_hot_plugged_interface_in_vmi(
                vm=running_vm_with_secondary_and_hot_plugged_interfaces,
                interface_name=hot_unplugged_additional_interface,
            )

    @pytest.mark.ipv4
    @pytest.mark.polarion("CNV-10148")
    @pytest.mark.post_upgrade
    @pytest.mark.dependency(
        name="test_basic_connectivity_vm_with_secondary_after_hot_unplug",
        depends=["test_hot_unplugged_interface_removed_from_vmi_spec"],
    )
    def test_basic_connectivity_vm_with_secondary_after_hot_unplug(
        self,
        running_vm_with_secondary_and_hot_plugged_interfaces,
        running_utility_vm_for_connectivity_check,
        network_attachment_definition_for_hot_plug,
    ):
        assert_ping_successful(
            src_vm=running_vm_with_secondary_and_hot_plugged_interfaces,
            dst_ip=get_vmi_ip_v4_by_name(
                vm=running_utility_vm_for_connectivity_check,
                name=network_attachment_definition_for_hot_plug.name,
            ),
            interface=SECONDARY_SETUP_INTERFACE_NAME,
        )

    @pytest.mark.polarion("CNV-10149")
    @pytest.mark.dependency(
        name="test_mac_of_hot_plugged_interface_returned_to_kubemacpool_after_hot_unplug",
        depends=["test_hot_unplugged_interface_removed_from_vmi_spec"],
    )
    def test_mac_of_hot_plugged_interface_returned_to_kubemacpool_after_hot_unplug(
        self,
        hot_unplugged_interface_mac_address,
        kubemacpool_controller_log_for_hot_unplug,
    ):
        assert check_mac_released(
            kubemacpool_controller_log=kubemacpool_controller_log_for_hot_unplug,
            interface_mac_address=hot_unplugged_interface_mac_address,
        ), (
            f"MAC address {hot_unplugged_interface_mac_address} of hot-plugged interface was "
            f"not released upon hot-unplug."
        )

    @pytest.mark.polarion("CNV-10164")
    def test_hot_unplug_secondary_interface_from_setup(
        self,
        running_vm_with_secondary_and_hot_plugged_interfaces,
        hot_unplug_secondary_interface_from_setup,
        network_attachment_definition_for_hot_plug,
    ):
        with pytest.raises(IfaceNotFound):
            search_hot_plugged_interface_in_vmi(
                vm=running_vm_with_secondary_and_hot_plugged_interfaces,
                interface_name=network_attachment_definition_for_hot_plug.name,
            )

import pytest

from libs.net.vmspec import lookup_iface_status
from tests.network.libs.ip import filter_link_local_addresses
from tests.network.utils import assert_no_ping
from utilities.constants import MTU_9000, QUARANTINED
from utilities.network import assert_ping_successful
from utilities.virt import migrate_vm_and_verify

pytestmark = [pytest.mark.special_infra, pytest.mark.sriov]


class TestPingConnectivity:
    @pytest.mark.post_upgrade
    @pytest.mark.polarion("CNV-3963")
    def test_sriov_basic_connectivity(
        self,
        subtests,
        sriov_network,
        sriov_vm1,
        sriov_vm2,
    ):
        dst_ips = filter_link_local_addresses(
            ip_addresses=lookup_iface_status(vm=sriov_vm2, iface_name=sriov_network.name)["ipAddresses"]
        )
        for dst_ip in dst_ips:
            with subtests.test(msg=f"Testing connectivity to {dst_ip}"):
                assert_ping_successful(src_vm=sriov_vm1, dst_ip=dst_ip)

    @pytest.mark.polarion("CNV-4505")
    @pytest.mark.usefixtures("sriov_network_mtu_9000")
    def test_sriov_custom_mtu_connectivity(
        self,
        subtests,
        sriov_network,
        sriov_vm1,
        sriov_vm2,
    ):
        dst_ips = filter_link_local_addresses(
            ip_addresses=lookup_iface_status(vm=sriov_vm2, iface_name=sriov_network.name)["ipAddresses"]
        )
        for dst_ip in dst_ips:
            with subtests.test(msg=f"Testing connectivity to {dst_ip} with MTU {MTU_9000}"):
                assert_ping_successful(src_vm=sriov_vm1, dst_ip=dst_ip, packet_size=MTU_9000)

    @pytest.mark.polarion("CNV-3958")
    @pytest.mark.xfail(
        reason=f"{QUARANTINED}: fails in CI due to issue in specific cluster; tracked in CNV-75730",
        run=False,
    )
    def test_sriov_basic_connectivity_vlan(
        self,
        subtests,
        sriov_network_vlan,
        sriov_vm3,
        sriov_vm4,
    ):
        dst_ips = filter_link_local_addresses(
            ip_addresses=lookup_iface_status(vm=sriov_vm4, iface_name=sriov_network_vlan.name)["ipAddresses"]
        )
        for dst_ip in dst_ips:
            with subtests.test(msg=f"Testing VLAN connectivity to {dst_ip}"):
                assert_ping_successful(src_vm=sriov_vm3, dst_ip=dst_ip)

    @pytest.mark.polarion("CNV-4713")
    @pytest.mark.xfail(
        reason=f"{QUARANTINED}: fails in CI due to issue in specific cluster; tracked in CNV-75730",
        run=False,
    )
    def test_sriov_no_connectivity_no_vlan_to_vlan(
        self,
        subtests,
        sriov_network_vlan,
        sriov_vm1,
        sriov_vm4,
    ):
        dst_ips = filter_link_local_addresses(
            ip_addresses=lookup_iface_status(vm=sriov_vm4, iface_name=sriov_network_vlan.name)["ipAddresses"]
        )
        for dst_ip in dst_ips:
            with subtests.test(msg=f"Testing no connectivity to {dst_ip}"):
                assert_no_ping(src_vm=sriov_vm1, dst_ip=dst_ip)


class TestSriovInterfacePersistence:
    @pytest.mark.post_upgrade
    @pytest.mark.polarion("CNV-4768")
    def test_sriov_interfaces_post_reboot(
        self,
        vm4_interfaces,
        restarted_sriov_vm4,
    ):
        # Check only the second interface (SR-IOV interface).
        lookup_iface_status(vm=restarted_sriov_vm4, iface_name=vm4_interfaces[1].name)
        assert restarted_sriov_vm4.vmi.interfaces[1] == vm4_interfaces[1]


class TestSriovLiveMigration:
    @pytest.mark.polarion("CNV-6455")
    def test_sriov_migration(
        self,
        subtests,
        sriov_network,
        sriov_vm_migrate,
        sriov_vm2,
    ):
        migrate_vm_and_verify(vm=sriov_vm_migrate, check_ssh_connectivity=True)
        dst_ips = filter_link_local_addresses(
            ip_addresses=lookup_iface_status(vm=sriov_vm_migrate, iface_name=sriov_network.name)["ipAddresses"]
        )
        for dst_ip in dst_ips:
            with subtests.test(msg=f"Testing connectivity to migrated VM at {dst_ip}"):
                assert_ping_successful(src_vm=sriov_vm2, dst_ip=dst_ip)


@pytest.mark.sno
@pytest.mark.tier3
@pytest.mark.dpdk
class TestSriovDpdk:
    @pytest.mark.polarion("CNV-7887")
    def test_sriov_dpdk_testpmd(
        self,
        sriov_network,
        sriov_dpdk_vm1,
        testpmd_output,
    ):
        assert int(testpmd_output) > 0, (
            f"testpmd should produce valid, non-zero statistics (actual result {testpmd_output})."
        )

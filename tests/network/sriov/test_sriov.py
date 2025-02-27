"""
SR-IOV Tests
"""

import logging

import pytest

from tests.network.utils import assert_no_ping
from utilities.constants import MTU_9000
from utilities.network import assert_ping_successful, get_vmi_ip_v4_by_name
from utilities.virt import migrate_vm_and_verify

LOGGER = logging.getLogger(__name__)


@pytest.mark.special_infra
class TestPingConnectivity:
    @pytest.mark.post_upgrade
    @pytest.mark.ipv4
    @pytest.mark.polarion("CNV-3963")
    def test_sriov_basic_connectivity(
        self,
        sriov_network,
        sriov_vm1,
        sriov_vm2,
        running_sriov_vm1,
        running_sriov_vm2,
    ):
        assert_ping_successful(
            src_vm=running_sriov_vm1,
            dst_ip=get_vmi_ip_v4_by_name(vm=running_sriov_vm2, name=sriov_network.name),
        )

    @pytest.mark.ipv4
    @pytest.mark.polarion("CNV-4505")
    def test_sriov_custom_mtu_connectivity(
        self,
        sriov_network,
        sriov_vm1,
        sriov_vm2,
        running_sriov_vm1,
        running_sriov_vm2,
        sriov_network_mtu_9000,
    ):
        assert_ping_successful(
            src_vm=running_sriov_vm1,
            dst_ip=get_vmi_ip_v4_by_name(vm=running_sriov_vm2, name=sriov_network.name),
            packet_size=MTU_9000,
        )

    @pytest.mark.ipv4
    @pytest.mark.polarion("CNV-3958")
    def test_sriov_basic_connectivity_vlan(
        self,
        sriov_network_vlan,
        sriov_vm3,
        sriov_vm4,
        running_sriov_vm3,
        running_sriov_vm4,
    ):
        assert_ping_successful(
            src_vm=running_sriov_vm3,
            dst_ip=get_vmi_ip_v4_by_name(vm=running_sriov_vm4, name=sriov_network_vlan.name),
        )

    @pytest.mark.ipv4
    @pytest.mark.polarion("CNV-4713")
    def test_sriov_no_connectivity_no_vlan_to_vlan(
        self,
        sriov_network_vlan,
        sriov_vm1,
        sriov_vm4,
        running_sriov_vm1,
        running_sriov_vm4,
    ):
        assert_no_ping(
            src_vm=running_sriov_vm1,
            dst_ip=get_vmi_ip_v4_by_name(vm=running_sriov_vm4, name=sriov_network_vlan.name),
        )

    @pytest.mark.post_upgrade
    @pytest.mark.polarion("CNV-4768")
    def test_sriov_interfaces_post_reboot(
        self,
        sriov_vm4,
        running_sriov_vm4,
        vm4_interfaces,
        restarted_sriov_vm4,
    ):
        # Check only the second interface (SR-IOV interface).
        assert restarted_sriov_vm4.vmi.interfaces[1] == vm4_interfaces[1]


@pytest.mark.special_infra
class TestSriovLiveMigration:
    @pytest.mark.ipv4
    @pytest.mark.polarion("CNV-6455")
    def test_sriov_migration(
        self,
        sriov_network,
        sriov_vm_migrate,
        sriov_vm2,
        running_sriov_vm_migrate,
        running_sriov_vm2,
    ):
        migrate_vm_and_verify(vm=sriov_vm_migrate, check_ssh_connectivity=True)
        assert_ping_successful(
            src_vm=running_sriov_vm2,
            dst_ip=get_vmi_ip_v4_by_name(vm=running_sriov_vm_migrate, name=sriov_network.name),
        )


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

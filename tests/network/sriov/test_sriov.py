"""
SR-IOV Tests
"""

import logging

import pytest

from libs.net.vmspec import lookup_iface_status_ip
from tests.network.utils import assert_no_ping
from utilities.constants import MTU_9000, QUARANTINED
from utilities.network import assert_ping_successful
from utilities.virt import migrate_vm_and_verify

LOGGER = logging.getLogger(__name__)

pytestmark = [pytest.mark.special_infra, pytest.mark.sriov]


class TestPingConnectivity:
    @pytest.mark.post_upgrade
    @pytest.mark.ipv4
    @pytest.mark.polarion("CNV-3963")
    def test_sriov_basic_connectivity(
        self,
        sriov_network,
        sriov_vm1,
        sriov_vm2,
    ):
        assert_ping_successful(
            src_vm=sriov_vm1,
            dst_ip=lookup_iface_status_ip(vm=sriov_vm2, iface_name=sriov_network.name, ip_family=4),
        )

    @pytest.mark.ipv4
    @pytest.mark.polarion("CNV-4505")
    def test_sriov_custom_mtu_connectivity(
        self,
        sriov_network,
        sriov_vm1,
        sriov_vm2,
        sriov_network_mtu_9000,
    ):
        assert_ping_successful(
            src_vm=sriov_vm1,
            dst_ip=lookup_iface_status_ip(vm=sriov_vm2, iface_name=sriov_network.name, ip_family=4),
            packet_size=MTU_9000,
        )

    @pytest.mark.ipv4
    @pytest.mark.polarion("CNV-3958")
    @pytest.mark.xfail(
        reason=f"{QUARANTINED}: fails in CI due to issue in specific cluster; tracked in CNV-75730",
        run=False,
    )
    def test_sriov_basic_connectivity_vlan(
        self,
        sriov_network_vlan,
        sriov_vm3,
        sriov_vm4,
    ):
        assert_ping_successful(
            src_vm=sriov_vm3,
            dst_ip=lookup_iface_status_ip(vm=sriov_vm4, iface_name=sriov_network_vlan.name, ip_family=4),
        )

    @pytest.mark.ipv4
    @pytest.mark.polarion("CNV-4713")
    @pytest.mark.xfail(
        reason=f"{QUARANTINED}: fails in CI due to issue in specific cluster; tracked in CNV-75730",
        run=False,
    )
    def test_sriov_no_connectivity_no_vlan_to_vlan(
        self,
        sriov_network_vlan,
        sriov_vm1,
        sriov_vm4,
    ):
        assert_no_ping(
            src_vm=sriov_vm1,
            dst_ip=lookup_iface_status_ip(vm=sriov_vm4, iface_name=sriov_network_vlan.name, ip_family=4),
        )

    @pytest.mark.post_upgrade
    @pytest.mark.polarion("CNV-4768")
    def test_sriov_interfaces_post_reboot(
        self,
        sriov_vm4,
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
    ):
        migrate_vm_and_verify(vm=sriov_vm_migrate, check_ssh_connectivity=True)
        assert_ping_successful(
            src_vm=sriov_vm2,
            dst_ip=lookup_iface_status_ip(vm=sriov_vm_migrate, iface_name=sriov_network.name, ip_family=4),
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

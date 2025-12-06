import pytest
from kubernetes.client.rest import ApiException

from utilities.network import assert_ping_successful, get_vmi_mac_address_by_iface_name
from utilities.virt import VirtualMachineForTests

from . import utils as kmp_utils


@pytest.mark.s390x
class TestKMPConnectivity:
    # KMPTestConnectivity setup example
    # Third octet is random
    # .........                                                                       ..........
    # |       |---eth0:           : POD network                   :auto       :eth0---|        |
    # |       |---eth1:172.16.37.1: Manual MAC from pool          :172.16.37.2:eth1---|        |
    # | VM-A  |---eth2:172.16.24.1: Automatic MAC from pool       :172.16.24.2:eth2---|  VM-B  |
    # |       |---eth3:172.16.51.1: Manual MAC not from pool      :172.16.51.2:eth3---|        |
    # |.......|---eth4:172.16.65.1: Automatic mac tuning network  :172.16.65.2:eth4---|........|
    @pytest.mark.post_upgrade
    @pytest.mark.polarion("CNV-2154")
    def test_manual_mac_from_pool(self, namespace, running_vm_a, running_vm_b):
        """Test that manually assigned mac address from pool is configured and working"""
        for vm in (running_vm_a, running_vm_b):
            kmp_utils.assert_manual_mac_configured(vm=vm, iface_config=vm.manual_mac_iface_config)
        assert_ping_successful(src_vm=running_vm_a, dst_ip=running_vm_b.manual_mac_iface_config.ip_address)

    @pytest.mark.polarion("CNV-2156")
    def test_manual_mac_not_from_pool(self, running_vm_a, running_vm_b):
        """Test that manually assigned mac address out of pool is configured and working"""
        for vm in (running_vm_a, running_vm_b):
            kmp_utils.assert_manual_mac_configured(vm=vm, iface_config=vm.manual_mac_out_pool_iface_config)
        assert_ping_successful(
            src_vm=running_vm_a,
            dst_ip=running_vm_b.manual_mac_out_pool_iface_config.ip_address,
        )

    @pytest.mark.gating
    @pytest.mark.polarion("CNV-2241")
    # Not marked as `conformance`; requires NMState
    def test_automatic_mac_from_pool_pod_network(self, mac_pool, running_vm_a, running_vm_b):
        """Test that automatic mac address assigned to POD's masquerade network
        from kubemacpool belongs to range and connectivity is OK"""
        for vm in (running_vm_a, running_vm_b):
            assert mac_pool.mac_is_within_range(
                mac=get_vmi_mac_address_by_iface_name(vmi=vm.vmi, iface_name=vm.default_masquerade_iface_config.name),
            )
        assert_ping_successful(
            src_vm=running_vm_a,
            dst_ip=running_vm_b.default_masquerade_iface_config.ip_address,
        )

    @pytest.mark.gating
    @pytest.mark.polarion("CNV-2155")
    # Not marked as `conformance`; requires NMState
    def test_automatic_mac_from_pool(self, mac_pool, running_vm_a, running_vm_b):
        """Test that automatic mac address assigned to interface
        from kubemacpool belongs to range and connectivity is OK"""
        for vm in (running_vm_a, running_vm_b):
            assert mac_pool.mac_is_within_range(
                mac=get_vmi_mac_address_by_iface_name(vmi=vm.vmi, iface_name=vm.auto_mac_iface_config.name),
            )
        assert_ping_successful(src_vm=running_vm_a, dst_ip=running_vm_b.auto_mac_iface_config.ip_address)

    @pytest.mark.polarion("CNV-2242")
    def test_automatic_mac_from_pool_tuning(self, mac_pool, running_vm_a, running_vm_b):
        """Test that automatic mac address assigned to tuning interface
        from kubemacpool is belongs to range and connectivity is OK"""
        for vm in (running_vm_a, running_vm_b):
            assert mac_pool.mac_is_within_range(
                mac=get_vmi_mac_address_by_iface_name(vmi=vm.vmi, iface_name=vm.auto_mac_tuning_iface_config.name),
            )
        assert_ping_successful(
            src_vm=running_vm_a,
            dst_ip=running_vm_b.auto_mac_tuning_iface_config.ip_address,
        )

    @pytest.mark.gating
    @pytest.mark.polarion("CNV-2157")
    # Not marked as `conformance`; requires NMState
    def test_mac_preserved_after_shutdown(self, restarted_vmi_a, restarted_vmi_b, running_vm_a, running_vm_b):
        """Test that all macs are preserved even after VM restart"""
        kmp_utils.assert_macs_preseved(vm=running_vm_a)
        kmp_utils.assert_macs_preseved(vm=running_vm_b)

    @pytest.mark.polarion("CNV-5941")
    def test_enabled_label_ns(
        self,
        mac_pool,
        kmp_enabled_ns,
        enabled_ns_nad,
        enabled_ns_vm,
    ):
        assert mac_pool.mac_is_within_range(
            mac=get_vmi_mac_address_by_iface_name(vmi=enabled_ns_vm.vmi, iface_name=enabled_ns_nad.name)
        )

    @pytest.mark.polarion("CNV-4217")
    def test_no_label_ns(
        self,
        mac_pool,
        no_label_ns,
        no_label_ns_nad,
        no_label_ns_vm,
    ):
        assert mac_pool.mac_is_within_range(
            mac=get_vmi_mac_address_by_iface_name(vmi=no_label_ns_vm.vmi, iface_name=no_label_ns_nad.name)
        )


class TestNegatives:
    @pytest.mark.polarion("CNV-4199")
    @pytest.mark.s390x
    def test_disabled_assignment_ns(
        self,
        mac_pool,
        disabled_ns,
        disabled_ns_nad,
        disabled_ns_vm,
    ):
        # KMP should not allocate.
        assert not mac_pool.mac_is_within_range(
            mac=get_vmi_mac_address_by_iface_name(vmi=disabled_ns_vm.vmi, iface_name=disabled_ns_nad.name)
        )


@pytest.mark.sno
@pytest.mark.polarion("CNV-4405")
@pytest.mark.single_nic
@pytest.mark.s390x
def test_kmp_down(unprivileged_client, namespace, kmp_down):
    with pytest.raises(ApiException):
        with VirtualMachineForTests(name="kmp-down-vm", namespace=namespace.name, client=unprivileged_client):
            return

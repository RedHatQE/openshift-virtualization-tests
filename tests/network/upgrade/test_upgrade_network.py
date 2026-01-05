import logging
import os
from ipaddress import ip_interface

import pytest

from tests.network.upgrade.utils import assert_label_in_namespace
from tests.upgrade_params import (
    IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID,
    IUO_UPGRADE_TEST_ORDERING_NODE_ID,
)
from utilities.constants import (
    DEPENDENCY_SCOPE_SESSION,
    KMP_DISABLED_LABEL,
    KMP_VM_ASSIGNMENT_LABEL,
)
from utilities.network import (
    assert_ping_successful,
    get_vmi_ip_v4_by_name,
    get_vmi_mac_address_by_iface_name,
)

LOGGER = logging.getLogger(__name__)
DEPENDENCIES_NODE_ID_PREFIX = f"{os.path.abspath(__file__)}::TestUpgradeNetwork"

pytestmark = [
    pytest.mark.upgrade,
    pytest.mark.ocp_upgrade,
    pytest.mark.cnv_upgrade,
    pytest.mark.eus_upgrade,
]


@pytest.mark.usefixtures("running_vm_with_bridge")
class TestUpgradeNetwork:
    """Pre-upgrade tests"""

    @pytest.mark.sno
    @pytest.mark.polarion("CNV-2988")
    @pytest.mark.order(before=IUO_UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(
        name=f"{DEPENDENCIES_NODE_ID_PREFIX}::test_vm_have_2_interfaces_before_upgrade",
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_vm_have_2_interfaces_before_upgrade(self, running_vm_with_bridge):
        assert len(running_vm_with_bridge.vmi.interfaces) == 2

    @pytest.mark.ipv4
    @pytest.mark.polarion("CNV-2750")
    @pytest.mark.order(before=IUO_UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(name=f"{DEPENDENCIES_NODE_ID_PREFIX}::test_linux_bridge_before_upgrade")
    def test_linux_bridge_before_upgrade(
        self,
        running_vm_upgrade_a,
        running_vm_upgrade_b,
        upgrade_bridge_marker_nad,
        bridge_on_one_node,
    ):
        assert_ping_successful(
            src_vm=running_vm_upgrade_a,
            dst_ip=get_vmi_ip_v4_by_name(vm=running_vm_upgrade_b, name=upgrade_bridge_marker_nad.name),
        )

    @pytest.mark.sno
    @pytest.mark.polarion("CNV-5944")
    @pytest.mark.order(before=IUO_UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(name=f"{DEPENDENCIES_NODE_ID_PREFIX}::test_kubemacpool_disabled_ns_before_upgrade")
    def test_kubemacpool_disabled_ns_before_upgrade(
        self,
        namespace_with_disabled_kmp,
    ):
        assert_label_in_namespace(
            labeled_namespace=namespace_with_disabled_kmp,
            label_key=KMP_VM_ASSIGNMENT_LABEL,
            expected_label_value=KMP_DISABLED_LABEL,
        )

    @pytest.mark.polarion("CNV-2745")
    @pytest.mark.order(before=IUO_UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(name=f"{DEPENDENCIES_NODE_ID_PREFIX}::test_kubemacpool_before_upgrade")
    def test_kubemacpool_before_upgrade(
        self,
        running_vm_upgrade_a,
        running_vm_upgrade_b,
        mac_pool,
        upgrade_bridge_marker_nad,
    ):
        for vm in (running_vm_upgrade_a, running_vm_upgrade_b):
            assert mac_pool.mac_is_within_range(
                mac=get_vmi_mac_address_by_iface_name(vmi=vm.vmi, iface_name=upgrade_bridge_marker_nad.name)
            )

    @pytest.mark.sno
    @pytest.mark.ipv4
    @pytest.mark.polarion("CNV-7343")
    @pytest.mark.order(before=IUO_UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(name=f"{DEPENDENCIES_NODE_ID_PREFIX}::test_vm_connectivity_with_macspoofing_before_upgrade")
    def test_vm_connectivity_with_macspoofing_before_upgrade(
        self,
        vma_upgrade_mac_spoof,
        vmb_upgrade_mac_spoof,
        running_vma_upgrade_mac_spoof,
        running_vmb_upgrade_mac_spoof,
    ):
        """
        Added test to verify ping works when macspoof is set.
        Adding field should not break existing tests. However this test will not work if nftables are missing.
        """
        assert_ping_successful(
            src_vm=vma_upgrade_mac_spoof,
            dst_ip=get_vmi_ip_v4_by_name(
                vm=vmb_upgrade_mac_spoof,
                name=vmb_upgrade_mac_spoof.interfaces[0],
            ),
        )

    """ Post-upgrade tests """

    @pytest.mark.polarion("CNV-2989")
    @pytest.mark.order(after=IUO_UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(
        depends=[
            IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID,
            f"{DEPENDENCIES_NODE_ID_PREFIX}::test_vm_have_2_interfaces_before_upgrade",
        ],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_vm_have_2_interfaces_after_upgrade(self, running_vm_with_bridge):
        assert len(running_vm_with_bridge.vmi.interfaces) == 2

    @pytest.mark.polarion("CNV-2748")
    @pytest.mark.order(after=IUO_UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(
        depends=[
            IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID,
            f"{DEPENDENCIES_NODE_ID_PREFIX}::test_linux_bridge_before_upgrade",
        ],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_linux_bridge_after_upgrade(
        self,
        running_vm_upgrade_a,
        running_vm_upgrade_b,
        upgrade_bridge_marker_nad,
        bridge_on_one_node,
    ):
        dst_ip_address = ip_interface(address=running_vm_upgrade_b.vmi.instance.status.interfaces[1].ipAddress).ip
        assert_ping_successful(src_vm=running_vm_upgrade_a, dst_ip=str(dst_ip_address))

    @pytest.mark.polarion("CNV-2746")
    @pytest.mark.order(after=IUO_UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(
        depends=[
            IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID,
            f"{DEPENDENCIES_NODE_ID_PREFIX}::test_kubemacpool_before_upgrade",
        ],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_kubemacpool_after_upgrade(
        self,
        running_vm_upgrade_a,
        running_vm_upgrade_b,
        mac_pool,
        upgrade_bridge_marker_nad,
    ):
        for vm in (running_vm_upgrade_a, running_vm_upgrade_b):
            assert mac_pool.mac_is_within_range(
                mac=get_vmi_mac_address_by_iface_name(vmi=vm.vmi, iface_name=upgrade_bridge_marker_nad.name)
            )

    @pytest.mark.sno
    @pytest.mark.polarion("CNV-5945")
    @pytest.mark.order(after=IUO_UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(
        depends=[
            IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID,
            f"{DEPENDENCIES_NODE_ID_PREFIX}::test_kubemacpool_disabled_ns_before_upgrade",
        ],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_kubemacpool_disabled_ns_after_upgrade(
        self,
        namespace_with_disabled_kmp,
    ):
        assert_label_in_namespace(
            labeled_namespace=namespace_with_disabled_kmp,
            label_key=KMP_VM_ASSIGNMENT_LABEL,
            expected_label_value=KMP_DISABLED_LABEL,
        )

    @pytest.mark.sno
    @pytest.mark.ipv4
    @pytest.mark.polarion("CNV-7402")
    @pytest.mark.order(after=IUO_UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(
        depends=[
            IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID,
            f"{DEPENDENCIES_NODE_ID_PREFIX}::test_vm_connectivity_with_macspoofing_before_upgrade",
        ],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_vm_connectivity_with_macspoofing_after_upgrade(
        self,
        vma_upgrade_mac_spoof,
        vmb_upgrade_mac_spoof,
    ):
        """
        Added test to verify ping works when macspoof is set.
        After upgrade, adding macspoofing in NAD should not make ping test to failed.
        This test is expected to fail if nftables are missing after upgrade.
        """
        assert_ping_successful(
            src_vm=vma_upgrade_mac_spoof,
            dst_ip=get_vmi_ip_v4_by_name(
                vm=vmb_upgrade_mac_spoof,
                name=vmb_upgrade_mac_spoof.interfaces[0],
            ),
        )

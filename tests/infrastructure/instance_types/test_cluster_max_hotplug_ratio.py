import bitmath
import pytest

from tests.infrastructure.instance_types.constants import CLUSTER_MAX_HOTPLUG_RATIO

pytestmark = pytest.mark.rwx_default_storage


class TestClusterMaxHotplugRatio:
    """
    Verify cluster-level maxHotplugRatio from HCO propagates to VMI spec
    when instancetype (u1.small) doesn't set maxSockets/maxGuest.
    """

    @pytest.mark.polarion("CNV-1234")
    def test_vmi_max_sockets_from_cluster_hotplug_ratio(self, vm_with_u1_small_instancetype):
        """Verify VMI maxSockets equals cluster maxHotplugRatio."""
        vmi_cpu = vm_with_u1_small_instancetype.vmi.instance.spec.domain.cpu
        assert vmi_cpu.maxSockets == CLUSTER_MAX_HOTPLUG_RATIO, (
            f"Expected maxSockets {CLUSTER_MAX_HOTPLUG_RATIO}, got {vmi_cpu.maxSockets}"
        )

    @pytest.mark.polarion("CNV-12345")
    def test_vmi_max_guest_memory_from_cluster_hotplug_ratio(
        self,
        is_s390x_cluster,
        u1_small_instancetype,
        vm_with_u1_small_instancetype,
    ):
        """Verify VMI maxGuest equals maxHotplugRatio * guestAtBoot (s390x unsupported)."""
        if is_s390x_cluster:
            pytest.skip("s390x doesn't support memory hotplug")

        # Calculate expected maxGuest from instancetype memory * maxHotplugRatio
        instancetype_memory_bytes = bitmath.parse_string_unsafe(
            s=u1_small_instancetype.instance.spec.memory.guest
        ).bytes
        expected_max_guest_bytes = instancetype_memory_bytes * CLUSTER_MAX_HOTPLUG_RATIO

        vmi_memory = vm_with_u1_small_instancetype.vmi.instance.spec.domain.memory
        vmi_max_guest_bytes = bitmath.parse_string_unsafe(s=vmi_memory.maxGuest).bytes
        assert vmi_max_guest_bytes == expected_max_guest_bytes, (
            f"Expected maxGuest {expected_max_guest_bytes} bytes, got {vmi_max_guest_bytes} bytes"
        )

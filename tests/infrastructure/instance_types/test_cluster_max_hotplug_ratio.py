# flake8: noqa: PID001 - Class-level parametrize; Polarion IDs are in pytest.param marks

import pytest
from bitmath import parse_string_unsafe

from tests.infrastructure.instance_types.constants import (
    CLUSTER_MAX_CPU_SOCKETS,
    CLUSTER_MAX_GUEST,
    CLUSTER_MAX_HOTPLUG_RATIO,
    CLUSTER_MAX_HOTPLUG_RATIO_LARGE,
    CLUSTER_MAX_HOTPLUG_RATIO_MIN,
)

pytestmark = pytest.mark.rwx_default_storage


@pytest.mark.parametrize(
    ("hco_live_update_scenario", "expected_vmi_limits"),
    [
        pytest.param(
            {"maxHotplugRatio": CLUSTER_MAX_HOTPLUG_RATIO},
            {
                "cpu_ratio": CLUSTER_MAX_HOTPLUG_RATIO,
                "mem_ratio": CLUSTER_MAX_HOTPLUG_RATIO,
            },
            id="ratio-only",
            marks=pytest.mark.polarion("CNV-13439"),
        ),
        pytest.param(
            {
                "maxCpuSockets": CLUSTER_MAX_CPU_SOCKETS,
                "maxHotplugRatio": CLUSTER_MAX_HOTPLUG_RATIO,
            },
            {
                "cpu_sockets": CLUSTER_MAX_CPU_SOCKETS,
                "mem_ratio": CLUSTER_MAX_HOTPLUG_RATIO,
            },
            id="sockets-explicit",
            marks=pytest.mark.polarion("CNV-13441"),
        ),
        pytest.param(
            {
                "maxCpuSockets": CLUSTER_MAX_CPU_SOCKETS,
                "maxHotplugRatio": CLUSTER_MAX_HOTPLUG_RATIO,
                "maxGuest": CLUSTER_MAX_GUEST,
            },
            {
                "cpu_sockets": CLUSTER_MAX_CPU_SOCKETS,
                "mem_value": CLUSTER_MAX_GUEST,
            },
            id="all-explicit",
            marks=pytest.mark.polarion("CNV-13443"),
        ),
        pytest.param(
            {"maxGuest": CLUSTER_MAX_GUEST, "maxHotplugRatio": CLUSTER_MAX_HOTPLUG_RATIO},
            {
                "cpu_ratio": CLUSTER_MAX_HOTPLUG_RATIO,
                "mem_value": CLUSTER_MAX_GUEST,
            },
            id="guest-explicit",
            marks=pytest.mark.polarion("CNV-13445"),
        ),
        pytest.param(
            {"maxHotplugRatio": CLUSTER_MAX_HOTPLUG_RATIO_MIN},
            {
                "cpu_ratio": CLUSTER_MAX_HOTPLUG_RATIO_MIN,
                "mem_ratio": CLUSTER_MAX_HOTPLUG_RATIO_MIN,
            },
            id="ratio-min",
            marks=pytest.mark.polarion("CNV-13447"),
        ),
        pytest.param(
            {"maxHotplugRatio": CLUSTER_MAX_HOTPLUG_RATIO_LARGE},
            {
                "cpu_ratio": CLUSTER_MAX_HOTPLUG_RATIO_LARGE,
                "mem_ratio": CLUSTER_MAX_HOTPLUG_RATIO_LARGE,
            },
            id="ratio-large",
            marks=pytest.mark.polarion("CNV-13449"),
        ),
    ],
    indirect=["hco_live_update_scenario"],
)
class TestClusterLiveUpdateParameterized:
    """Apply HCO liveUpdateConfiguration per scenario. HCO is restored after each scenario."""

    def test_vmi_max_sockets(
        self,
        u1_small_instancetype,
        expected_vmi_limits,
        vm_restarted_for_hco,
    ):
        if "cpu_sockets" in expected_vmi_limits:
            expected_sockets = expected_vmi_limits["cpu_sockets"]
        else:
            expected_sockets = u1_small_instancetype.instance.spec.cpu.guest * expected_vmi_limits["cpu_ratio"]
        actual_sockets = vm_restarted_for_hco.vmi.instance.spec.domain.cpu.maxSockets
        assert actual_sockets == expected_sockets, f"Expected maxSockets {expected_sockets}, got {actual_sockets}"

    def test_vmi_max_guest(
        self,
        u1_small_instancetype,
        expected_vmi_limits,
        vm_restarted_for_hco,
    ):
        if "mem_value" in expected_vmi_limits:
            expected_guest = parse_string_unsafe(s=expected_vmi_limits["mem_value"]).bytes
        else:
            guest_bytes = parse_string_unsafe(s=u1_small_instancetype.instance.spec.memory.guest).bytes
            expected_guest = guest_bytes * expected_vmi_limits["mem_ratio"]
        actual_guest = parse_string_unsafe(s=vm_restarted_for_hco.vmi.instance.spec.domain.memory.maxGuest).bytes
        assert actual_guest == expected_guest, f"Expected maxGuest {expected_guest} bytes, got {actual_guest} bytes"

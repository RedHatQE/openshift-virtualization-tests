"""
Create non-evictable VM with RWO Storage and evictionStrategy=True that should fire the VMCannotBeEvicted alert
"""

import pytest
from ocp_resources.datavolume import DataVolume
from pytest_testconfig import py_config

from tests.observability.constants import KUBEVIRT_STR_LOWER
from tests.os_params import FEDORA_LATEST_LABELS, RHEL_LATEST
from utilities.constants import LIVE_MIGRATE, WARNING_STR
from utilities.monitoring import validate_alerts


@pytest.mark.parametrize(
    "data_volume_scope_function, vm_from_template_with_existing_dv, alert_tested",
    [
        pytest.param(
            {
                "dv_name": "non-evictable-dv",
                "image": RHEL_LATEST["image_path"],
                "storage_class": py_config["default_storage_class"],
                "dv_size": RHEL_LATEST["dv_size"],
                "access_modes": DataVolume.AccessMode.RWO,
            },
            {
                "vm_name": "non-evictable-vm",
                "template_labels": FEDORA_LATEST_LABELS,
                "ssh": False,
                "guest_agent": False,
                "eviction_strategy": LIVE_MIGRATE,
            },
            {
                "alert_name": "VMCannotBeEvicted",
                "labels": {
                    "severity": WARNING_STR,
                    "operator_health_impact": "none",
                    "kubernetes_operator_component": KUBEVIRT_STR_LOWER,
                    "namespace": "alerts-virt-test-non-evictable-vm-alerts",
                },
                "check_alert_cleaned": True,
            },
            marks=pytest.mark.polarion("CNV-7484"),
        ),
    ],
    indirect=True,
)
def test_non_evictable_vm_fired_alert(
    prometheus,
    alert_tested,
    data_volume_scope_function,
    vm_from_template_with_existing_dv,
):
    validate_alerts(
        prometheus=prometheus,
        alert_dict=alert_tested,
    )

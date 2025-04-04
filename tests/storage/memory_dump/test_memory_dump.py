"""
Automation for Memory Dump
"""

import pytest
from pytest_testconfig import config as py_config

from tests.os_params import WINDOWS_11, WINDOWS_11_TEMPLATE_LABELS
from tests.storage.memory_dump.utils import wait_for_memory_dump_status_removed


@pytest.mark.tier3
@pytest.mark.parametrize(
    "golden_image_data_volume_scope_function, windows_vm_for_memory_dump",
    [
        pytest.param(
            {
                "dv_name": "dv-windows",
                "image": WINDOWS_11["image_path"],
                "storage_class": py_config["default_storage_class"],
                "dv_size": WINDOWS_11["dv_size"],
            },
            {
                "vm_name": "windows-vm-mem",
                "template_labels": WINDOWS_11_TEMPLATE_LABELS,
            },
            marks=pytest.mark.polarion("CNV-8518"),
        ),
    ],
    indirect=True,
)
def test_windows_memory_dump(
    skip_test_if_no_filesystem_sc,
    namespace,
    windows_vm_for_memory_dump,
    pvc_for_windows_memory_dump,
    windows_vm_memory_dump,
    windows_vm_memory_dump_completed,
    consumer_pod_for_verifying_windows_memory_dump,
    windows_vm_memory_dump_deletion,
):
    wait_for_memory_dump_status_removed(vm=windows_vm_for_memory_dump)

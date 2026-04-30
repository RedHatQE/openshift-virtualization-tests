"""
Automation for Memory Dump
"""

import pytest
from pytest_testconfig import config as py_config

from tests.storage.memory_dump.utils import wait_for_memory_dump_status_removed
from utilities.constants import Images


@pytest.mark.tier3
@pytest.mark.parametrize(
    "golden_image_data_source_scope_function",
    [
        pytest.param(
            {
                "dv_name": "dv-windows-2022",
                "image": f"{Images.Windows.DIR}/{Images.Windows.WIN2022_IMG}",
                "storage_class": py_config["default_storage_class"],
                "dv_size": Images.Windows.DEFAULT_DV_SIZE,
            },
            marks=pytest.mark.polarion("CNV-8518"),
        ),
    ],
    indirect=True,
)
def test_windows_memory_dump(
    namespace,
    windows_vm_for_memory_dump,
    pvc_for_windows_memory_dump,
    windows_vm_memory_dump,
    windows_vm_memory_dump_completed,
    consumer_pod_for_verifying_windows_memory_dump,
    windows_vm_memory_dump_deletion,
):
    wait_for_memory_dump_status_removed(vm=windows_vm_for_memory_dump)

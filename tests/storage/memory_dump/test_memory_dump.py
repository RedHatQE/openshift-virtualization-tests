"""
Automation for Memory Dump
"""

import pytest

from tests.storage.memory_dump.utils import wait_for_memory_dump_status_removed


@pytest.mark.tier3
@pytest.mark.polarion("CNV-8518")
def test_windows_memory_dump(
    namespace,
    windows_vm_with_vtpm_for_memory_dump,
    pvc_for_windows_memory_dump,
    windows_vm_memory_dump,
    windows_vm_memory_dump_completed,
    consumer_pod_for_verifying_windows_memory_dump,
    windows_vm_memory_dump_deletion,
):
    wait_for_memory_dump_status_removed(vm=windows_vm_with_vtpm_for_memory_dump)

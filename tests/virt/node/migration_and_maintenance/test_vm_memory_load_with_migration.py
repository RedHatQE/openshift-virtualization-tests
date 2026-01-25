import logging

import pytest

from tests.os_params import (
    FEDORA_LATEST,
    FEDORA_LATEST_LABELS,
    WINDOWS_10_TEMPLATE_LABELS,
)
from tests.utils import start_stress_on_vm
from tests.virt.constants import WINDOWS_10_WSL
from tests.virt.utils import get_stress_ng_pid, verify_stress_ng_pid_not_changed
from utilities.constants import STRESS_CPU_MEM_IO_COMMAND, TIMEOUT_20MIN, Images
from utilities.virt import migrate_vm_and_verify

LOGGER = logging.getLogger(__name__)

pytestmark = pytest.mark.rwx_default_storage


@pytest.fixture()
def cpu_mem_io_stress_started(vm_with_memory_load):
    start_stress_on_vm(
        vm=vm_with_memory_load,
        stress_command=STRESS_CPU_MEM_IO_COMMAND.format(workers="2", memory="50%", timeout="30m"),
    )


@pytest.fixture()
def stress_pid_before_migration(vm_with_memory_load, cpu_mem_io_stress_started):
    stress_pid = get_stress_ng_pid(
        ssh_exec=vm_with_memory_load.ssh_exec,
        windows="windows" in vm_with_memory_load.name,
    )
    assert stress_pid, "Can't get stress-ng pid before migration"
    return stress_pid


@pytest.fixture()
def migrate_vm_with_memory_load(vm_with_memory_load):
    migrate_vm_and_verify(vm=vm_with_memory_load, check_ssh_connectivity=True, timeout=TIMEOUT_20MIN)


@pytest.mark.usefixtures("migration_policy_with_allow_auto_converge")
class TestMigrationVMWithMemoryLoad:
    @pytest.mark.parametrize(
        "golden_image_data_source_for_test_scope_function, vm_with_memory_load",
        [
            pytest.param(
                {"os_dict": FEDORA_LATEST},
                {
                    "vm_name": "fedora-vm-with-memory-load",
                    "template_labels": FEDORA_LATEST_LABELS,
                    "memory_guest": "4Gi",
                    "cpu_cores": 2,
                },
                marks=pytest.mark.polarion("CNV-4661"),
            ),
        ],
        indirect=True,
    )
    @pytest.mark.s390x
    def test_fedora_vm_migrate_with_memory_load(
        self,
        vm_with_memory_load,
        stress_pid_before_migration,
        migrate_vm_with_memory_load,
    ):
        verify_stress_ng_pid_not_changed(vm=vm_with_memory_load, initial_pid=stress_pid_before_migration)

    @pytest.mark.ibm_bare_metal
    @pytest.mark.parametrize(
        "golden_image_data_source_for_test_scope_function, vm_with_memory_load",
        [
            pytest.param(
                {"os_dict": WINDOWS_10_WSL},
                {
                    "vm_name": "windows-vm-with-memory-load",
                    "template_labels": WINDOWS_10_TEMPLATE_LABELS,
                    "memory_guest": Images.Windows.DEFAULT_MEMORY_SIZE_WSL,
                    "cpu_cores": 16,
                    "cpu_threads": 1,
                },
                marks=[pytest.mark.special_infra, pytest.mark.high_resource_vm],
            ),
        ],
        indirect=True,
    )
    @pytest.mark.polarion("CNV-9844")
    def test_windows_vm_migrate_with_memory_load(
        self,
        vm_with_memory_load,
        stress_pid_before_migration,
        migrate_vm_with_memory_load,
    ):
        verify_stress_ng_pid_not_changed(
            vm=vm_with_memory_load,
            initial_pid=stress_pid_before_migration,
            windows=True,
        )

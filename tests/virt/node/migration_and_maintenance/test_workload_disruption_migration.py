from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from ocp_resources.migration_policy import MigrationPolicy
from ocp_resources.resource import ResourceEditor

from tests.os_params import RHEL_LATEST, RHEL_LATEST_LABELS, WINDOWS_LATEST, WINDOWS_LATEST_LABELS
from tests.utils import (
    assert_guest_os_memory_amount,
    clean_up_migration_jobs,
    wait_for_guest_os_cpu_count,
)
from tests.virt.constants import WORKLOAD_DISRUPTION_VM_LABEL
from utilities.constants import (
    REGEDIT_PROC_NAME,
    SIX_CPU_SOCKETS,
    SIX_GI_MEMORY,
    TIMEOUT_15MIN,
    TIMEOUT_30MIN,
)
from utilities.virt import (
    check_migration_process_after_node_drain,
    fetch_pid_from_linux_vm,
    fetch_pid_from_windows_vm,
    migrate_vm_and_verify,
    node_mgmt_console,
    start_and_fetch_processid_on_linux_vm,
    start_and_fetch_processid_on_windows_vm,
)

if TYPE_CHECKING:
    from utilities.virt import VirtualMachineForTests

pytestmark = [pytest.mark.rwx_default_storage]


RHEL_CLASS_NAME = "TestRhelWorkloadMigration"
WIN_CLASS_NAME = "TestWindowsWorkloadMigration"


def assert_expected_migration_mode(vm: VirtualMachineForTests, expected_mode: str) -> None:
    migration_state = vm.vmi.instance.status.migrationState
    assert migration_state.mode == expected_mode, (
        f"Migration mode is not {expected_mode}! VMI MigrationState {migration_state}"
    )


def assert_same_pid_after_migration(orig_pid: str, vm: VirtualMachineForTests) -> None:
    if "windows" in vm.name:
        new_pid = fetch_pid_from_windows_vm(vm=vm, process_name=REGEDIT_PROC_NAME)
    else:
        new_pid = fetch_pid_from_linux_vm(vm=vm, process_name="ping")
    assert new_pid == orig_pid, f"PID mismatch after migration! orig_pid: {orig_pid}; new_pid: {new_pid}"


@pytest.fixture(scope="module")
def workload_disruption_migration_policy():
    with MigrationPolicy(
        name="workload-migration-mp",
        allow_workload_disruption=True,
        allow_auto_converge=True,
        bandwidth_per_migration="60Mi",
        completion_timeout_per_gb=5,
        vmi_selector=WORKLOAD_DISRUPTION_VM_LABEL,
    ) as mp:
        yield mp


@pytest.fixture(scope="class")
def migration_mode(request, workload_disruption_migration_policy):
    mode = request.param["mode"]
    policy_patch: dict[str, object] = {"allowPostCopy": mode == "PostCopy"}
    policy_patch.update(request.param.get("extra_patch", {}))
    with ResourceEditor(patches={workload_disruption_migration_policy: {"spec": policy_patch}}):
        yield mode


@pytest.fixture(scope="class")
def vm_background_process_id(vm_with_hotplug_support):
    if "windows" in vm_with_hotplug_support.name:
        return start_and_fetch_processid_on_windows_vm(vm=vm_with_hotplug_support, process_name=REGEDIT_PROC_NAME)
    else:
        return start_and_fetch_processid_on_linux_vm(vm=vm_with_hotplug_support, process_name="ping", args="localhost")


@pytest.fixture()
def migrated_vm_with_hotplug_support(vm_with_hotplug_support):
    migrate_vm_and_verify(
        vm=vm_with_hotplug_support,
        timeout=TIMEOUT_30MIN if "windows" in vm_with_hotplug_support.name else TIMEOUT_15MIN,
        check_ssh_connectivity=True,
    )


@pytest.fixture()
def drained_node_for_hotplug_vm(admin_client, vm_with_hotplug_support):
    with node_mgmt_console(
        admin_client=admin_client,
        node=vm_with_hotplug_support.vmi.get_node(privileged_client=admin_client),
        node_mgmt="drain",
    ):
        check_migration_process_after_node_drain(
            client=admin_client, vm=vm_with_hotplug_support, admin_client=admin_client
        )
    clean_up_migration_jobs(client=admin_client, vm=vm_with_hotplug_support)


@pytest.mark.parametrize(
    "golden_image_data_source_for_test_scope_class, vm_with_hotplug_support, migration_mode",
    [
        pytest.param(
            {"os_dict": RHEL_LATEST},
            {
                "template_labels": RHEL_LATEST_LABELS,
                "vm_name": "rhel-post-copy-vm",
                "additional_labels": WORKLOAD_DISRUPTION_VM_LABEL,
            },
            {"mode": "PostCopy", "extra_patch": {"completionTimeoutPerGiB": 1}},
            id="RHEL-PostCopy",
        ),
        pytest.param(
            {"os_dict": RHEL_LATEST},
            {
                "template_labels": RHEL_LATEST_LABELS,
                "vm_name": "rhel-paused-vm",
                "additional_labels": WORKLOAD_DISRUPTION_VM_LABEL,
            },
            {"mode": "Paused", "extra_patch": {"completionTimeoutPerGiB": 1}},
            id="RHEL-Paused",
        ),
    ],
    indirect=True,
)
class TestRhelWorkloadMigration:
    @pytest.mark.dependency(name=f"{RHEL_CLASS_NAME}::migrate_vm")
    @pytest.mark.polarion("CNV-15225")
    def test_awd_migration_mode(
        self,
        vm_with_hotplug_support,
        vm_background_process_id,
        migrated_vm_with_hotplug_support,
        migration_mode,
    ):
        assert_expected_migration_mode(vm=vm_with_hotplug_support, expected_mode=migration_mode)
        assert_same_pid_after_migration(orig_pid=vm_background_process_id, vm=vm_with_hotplug_support)

    @pytest.mark.dependency(name=f"{RHEL_CLASS_NAME}::node_drain", depends=[f"{RHEL_CLASS_NAME}::migrate_vm"])
    @pytest.mark.polarion("CNV-15245")
    def test_awd_node_drain(
        self,
        vm_with_hotplug_support,
        vm_background_process_id,
        drained_node_for_hotplug_vm,
        migration_mode,
    ):
        assert_expected_migration_mode(vm=vm_with_hotplug_support, expected_mode=migration_mode)
        assert_same_pid_after_migration(orig_pid=vm_background_process_id, vm=vm_with_hotplug_support)

    @pytest.mark.parametrize(
        "hotplugged_sockets_memory_guest", [pytest.param({"sockets": SIX_CPU_SOCKETS})], indirect=True
    )
    @pytest.mark.dependency(name=f"{RHEL_CLASS_NAME}::hotplug_cpu", depends=[f"{RHEL_CLASS_NAME}::node_drain"])
    @pytest.mark.polarion("CNV-15234")
    def test_awd_hotplug_cpu(
        self,
        hotplugged_sockets_memory_guest,
        vm_with_hotplug_support,
        vm_background_process_id,
        migration_mode,
    ):
        assert_expected_migration_mode(vm=vm_with_hotplug_support, expected_mode=migration_mode)
        wait_for_guest_os_cpu_count(vm=vm_with_hotplug_support, spec_cpu_amount=SIX_CPU_SOCKETS)
        assert_same_pid_after_migration(orig_pid=vm_background_process_id, vm=vm_with_hotplug_support)

    @pytest.mark.parametrize(
        "hotplugged_sockets_memory_guest", [pytest.param({"memory_guest": SIX_GI_MEMORY})], indirect=True
    )
    @pytest.mark.dependency(depends=[f"{RHEL_CLASS_NAME}::hotplug_cpu"])
    @pytest.mark.polarion("CNV-15235")
    def test_awd_hotplug_memory(
        self,
        hotplugged_sockets_memory_guest,
        vm_with_hotplug_support,
        vm_background_process_id,
        migration_mode,
    ):
        assert_expected_migration_mode(vm=vm_with_hotplug_support, expected_mode=migration_mode)
        assert_guest_os_memory_amount(vm=vm_with_hotplug_support, spec_memory_amount=SIX_GI_MEMORY)
        assert_same_pid_after_migration(orig_pid=vm_background_process_id, vm=vm_with_hotplug_support)


@pytest.mark.parametrize(
    "golden_image_data_source_for_test_scope_class, vm_with_hotplug_support, migration_mode",
    [
        pytest.param(
            {"os_dict": WINDOWS_LATEST},
            {
                "template_labels": WINDOWS_LATEST_LABELS,
                "vm_name": "windows-post-copy-vm",
                "additional_labels": WORKLOAD_DISRUPTION_VM_LABEL,
            },
            {"mode": "PostCopy"},
            id="WIN-PostCopy",
            marks=[pytest.mark.special_infra, pytest.mark.high_resource_vm],
        ),
        pytest.param(
            {"os_dict": WINDOWS_LATEST},
            {
                "template_labels": WINDOWS_LATEST_LABELS,
                "vm_name": "windows-paused-vm",
                "additional_labels": WORKLOAD_DISRUPTION_VM_LABEL,
            },
            {"mode": "Paused"},
            id="WIN-Paused",
            marks=[pytest.mark.special_infra, pytest.mark.high_resource_vm],
        ),
    ],
    indirect=True,
)
class TestWindowsWorkloadMigration:
    @pytest.mark.dependency(name=f"{WIN_CLASS_NAME}::migrate_vm")
    @pytest.mark.polarion("CNV-15246")
    def test_awd_migration_mode(
        self,
        vm_with_hotplug_support,
        vm_background_process_id,
        migrated_vm_with_hotplug_support,
        migration_mode,
    ):
        assert_expected_migration_mode(vm=vm_with_hotplug_support, expected_mode=migration_mode)
        assert_same_pid_after_migration(orig_pid=vm_background_process_id, vm=vm_with_hotplug_support)

    @pytest.mark.parametrize(
        "hotplugged_sockets_memory_guest", [pytest.param({"sockets": SIX_CPU_SOCKETS})], indirect=True
    )
    @pytest.mark.dependency(depends=[f"{WIN_CLASS_NAME}::migrate_vm"])
    @pytest.mark.polarion("CNV-15247")
    def test_awd_hotplug_cpu(
        self,
        hotplugged_sockets_memory_guest,
        vm_with_hotplug_support,
        vm_background_process_id,
        migration_mode,
    ):
        assert_expected_migration_mode(vm=vm_with_hotplug_support, expected_mode=migration_mode)
        wait_for_guest_os_cpu_count(vm=vm_with_hotplug_support, spec_cpu_amount=SIX_CPU_SOCKETS)
        assert_same_pid_after_migration(orig_pid=vm_background_process_id, vm=vm_with_hotplug_support)

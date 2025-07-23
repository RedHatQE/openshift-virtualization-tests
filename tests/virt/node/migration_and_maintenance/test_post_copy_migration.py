import logging

import pytest
from ocp_resources.migration_policy import MigrationPolicy
from pytest_testconfig import config as py_config

from tests.utils import (
    assert_guest_os_cpu_count,
    assert_guest_os_memory_amount,
)
from tests.virt.constants import VM_LABEL
from tests.virt.utils import assert_migration_post_copy_mode
from utilities.constants import (
    REGEDIT_PROC_NAME,
    SIX_CPU_SOCKETS,
    SIX_GI_MEMORY,
    TIMEOUT_15MIN,
    TIMEOUT_30MIN,
    Images,
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

pytestmark = [pytest.mark.rwx_default_storage, pytest.mark.usefixtures("created_post_copy_migration_policy")]


LOGGER = logging.getLogger(__name__)
TESTS_CLASS_NAME = "TestPostCopyMigration"


def assert_same_pid_after_migration(orig_pid, vm):
    if "windows" in vm.name:
        new_pid = fetch_pid_from_windows_vm(vm=vm, process_name=REGEDIT_PROC_NAME)
    else:
        new_pid = fetch_pid_from_linux_vm(vm=vm, process_name="ping")
    assert new_pid == orig_pid, f"PID mismatch after migration! orig_pid: {orig_pid}; new_pid: {new_pid}"


@pytest.fixture(scope="module")
def created_post_copy_migration_policy():
    with MigrationPolicy(
        name="post-copy-migration-mp",
        allow_auto_converge=True,
        bandwidth_per_migration="100Mi",
        completion_timeout_per_gb=1,
        allow_post_copy=True,
        vmi_selector=VM_LABEL,
    ) as mp:
        yield mp


@pytest.fixture(scope="class")
def vm_background_process_id(hotplugged_vm):
    if "windows" in hotplugged_vm.name:
        return start_and_fetch_processid_on_windows_vm(vm=hotplugged_vm, process_name=REGEDIT_PROC_NAME)
    else:
        return start_and_fetch_processid_on_linux_vm(vm=hotplugged_vm, process_name="ping", args="localhost")


@pytest.fixture()
def migrated_hotplugged_vm(hotplugged_vm):
    migrate_vm_and_verify(
        vm=hotplugged_vm,
        timeout=TIMEOUT_30MIN if "windows" in hotplugged_vm.name else TIMEOUT_15MIN,
        check_ssh_connectivity=True,
    )


@pytest.fixture()
def drained_node_with_hotplugged_vm(admin_client, hotplugged_vm):
    with node_mgmt_console(node=hotplugged_vm.privileged_vmi.node, node_mgmt="drain"):
        check_migration_process_after_node_drain(dyn_client=admin_client, vm=hotplugged_vm)


@pytest.mark.parametrize(
    "golden_image_data_volume_scope_class, hotplugged_vm",
    [
        pytest.param(
            {
                "dv_name": "dv-rhel-latest-vm",
                "image": py_config["latest_rhel_os_dict"]["image_path"],
                "storage_class": py_config["default_storage_class"],
                "dv_size": Images.Rhel.DEFAULT_DV_SIZE,
            },
            {
                "template_labels": py_config["latest_rhel_os_dict"]["template_labels"],
                "vm_name": "rhel-latest-post-copy-migration-vm",
                "additional_labels": VM_LABEL,
            },
            id="RHEL-VM",
        ),
        pytest.param(
            {
                "dv_name": "dv-windows-latest-vm",
                "image": f"{Images.Windows.DIR}/{Images.Windows.WIN11_IMG}",
                "storage_class": py_config["default_storage_class"],
                "dv_size": Images.Windows.DEFAULT_DV_SIZE,
            },
            {
                "template_labels": py_config.get("latest_windows_os_dict", {}).get("template_labels"),
                "vm_name": "windows-latest-post-copy-migration-vm",
                "additional_labels": VM_LABEL,
            },
            id="WIN-VM",
            marks=[pytest.mark.special_infra, pytest.mark.high_resource_vm],
        ),
    ],
    indirect=True,
)
class TestPostCopyMigration:
    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME}::migrate_vm")
    @pytest.mark.polarion("CNV-11421")
    def test_migrate_vm(self, hotplugged_vm, vm_background_process_id, migrated_hotplugged_vm):
        assert_migration_post_copy_mode(vm=hotplugged_vm)
        assert_same_pid_after_migration(orig_pid=vm_background_process_id, vm=hotplugged_vm)

    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME}::node_drain", depends=[f"{TESTS_CLASS_NAME}::migrate_vm"])
    @pytest.mark.polarion("CNV-11422")
    def test_node_drain(self, hotplugged_vm, vm_background_process_id, drained_node_with_hotplugged_vm):
        assert_migration_post_copy_mode(vm=hotplugged_vm)
        assert_same_pid_after_migration(orig_pid=vm_background_process_id, vm=hotplugged_vm)

    @pytest.mark.parametrize(
        "hotplugged_sockets_memory_guest", [pytest.param({"sockets": SIX_CPU_SOCKETS})], indirect=True
    )
    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME}::hotplug_cpu", depends=[f"{TESTS_CLASS_NAME}::node_drain"])
    @pytest.mark.polarion("CNV-11423")
    def test_hotplug_cpu(self, hotplugged_sockets_memory_guest, hotplugged_vm, vm_background_process_id):
        assert_guest_os_cpu_count(vm=hotplugged_vm, spec_cpu_amount=SIX_CPU_SOCKETS)
        assert_same_pid_after_migration(orig_pid=vm_background_process_id, vm=hotplugged_vm)

    @pytest.mark.parametrize(
        "hotplugged_sockets_memory_guest", [pytest.param({"memory_guest": SIX_GI_MEMORY})], indirect=True
    )
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::hotplug_cpu"])
    @pytest.mark.polarion("CNV-11424")
    def test_hotplug_memory(self, hotplugged_sockets_memory_guest, hotplugged_vm, vm_background_process_id):
        assert_guest_os_memory_amount(vm=hotplugged_vm, spec_memory_amount=SIX_GI_MEMORY)
        assert_same_pid_after_migration(orig_pid=vm_background_process_id, vm=hotplugged_vm)

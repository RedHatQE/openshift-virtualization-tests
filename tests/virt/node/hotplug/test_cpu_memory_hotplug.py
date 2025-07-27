import logging

import pytest
from kubernetes.dynamic.exceptions import UnprocessibleEntityError
from ocp_resources.virtual_machine_snapshot import VirtualMachineSnapshot
from pytest_testconfig import config as py_config

from tests.utils import (
    assert_guest_os_cpu_count,
    assert_guest_os_memory_amount,
    assert_restart_required_condition,
    hotplug_spec_vm,
)
from utilities.constants import (
    FIVE_GI_MEMORY,
    FOUR_CPU_SOCKETS,
    FOUR_GI_MEMORY,
    SIX_CPU_SOCKETS,
    SIX_GI_MEMORY,
    TEN_CPU_SOCKETS,
    TWELVE_GI_MEMORY,
    Images,
)
from utilities.virt import (
    migrate_vm_and_verify,
    restart_vm_wait_for_running_vm,
)

pytestmark = pytest.mark.rwx_default_storage


LOGGER = logging.getLogger(__name__)
TESTS_CLASS_NAME = "TestCPUHotPlug"

LATEST_WINDOWS_OS_DICT = py_config.get("latest_windows_os_dict", {})


@pytest.fixture()
def xfail_windows_memory_hotunplug(hotplugged_vm):
    if "windows" in hotplugged_vm.name:
        pytest.xfail(reason="Windows OS doesn't officially support memory hot unplug!")


@pytest.fixture(scope="class")
def hotplug_vm_snapshot(hotplugged_vm):
    with VirtualMachineSnapshot(
        name=f"{hotplugged_vm.name}-snapshot",
        namespace=hotplugged_vm.namespace,
        vm_name=hotplugged_vm.name,
    ) as snapshot:
        snapshot.wait_snapshot_done()
        yield snapshot


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
                "vm_name": "rhel-latest-cpu-hotplug-vm",
            },
            id="RHEL-VM",
        ),
        pytest.param(
            {
                "dv_name": "dv-windows-latest-vm",
                "image": LATEST_WINDOWS_OS_DICT.get("image_path"),
                "storage_class": py_config["default_storage_class"],
                "dv_size": Images.Windows.DEFAULT_DV_SIZE,
            },
            {
                "template_labels": LATEST_WINDOWS_OS_DICT.get("template_labels"),
                "vm_name": "windows-latest-cpu-hotplug-vm",
            },
            id="WIN-VM",
            marks=[pytest.mark.special_infra, pytest.mark.high_resource_vm],
        ),
    ],
    indirect=True,
)
class TestCPUHotPlug:
    @pytest.mark.parametrize(
        "hotplugged_sockets_memory_guest", [pytest.param({"sockets": SIX_CPU_SOCKETS})], indirect=True
    )
    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME}::hotplug_cpu")
    @pytest.mark.polarion("CNV-10695")
    def test_hotplug_cpu(self, hotplugged_sockets_memory_guest, hotplugged_vm):
        assert_guest_os_cpu_count(vm=hotplugged_vm, spec_cpu_amount=SIX_CPU_SOCKETS)

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::hotplug_cpu"])
    @pytest.mark.polarion("CNV-10696")
    def test_migrate_snapshot_hotplugged_vm(self, hotplug_vm_snapshot, hotplugged_vm):
        migrate_vm_and_verify(vm=hotplugged_vm, check_ssh_connectivity=True)

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::hotplug_cpu"])
    @pytest.mark.polarion("CNV-10697")
    def test_restart_hotplugged_vm(self, hotplugged_vm):
        restart_vm_wait_for_running_vm(vm=hotplugged_vm)

    @pytest.mark.parametrize(
        "hotplugged_sockets_memory_guest",
        [pytest.param({"sockets": FOUR_CPU_SOCKETS, "skip_migration": True})],
        indirect=True,
    )
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::hotplug_cpu"])
    @pytest.mark.polarion("CNV-10698")
    def test_decrease_cpu_value(self, hotplugged_sockets_memory_guest, hotplugged_vm):
        assert_restart_required_condition(
            vm=hotplugged_vm, expected_message="Reduction of CPU socket count requires a restart"
        )

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::hotplug_cpu"])
    @pytest.mark.polarion("CNV-10699")
    def test_hotplug_cpu_above_max_value(self, hotplugged_vm):
        with pytest.raises(UnprocessibleEntityError):
            hotplug_spec_vm(vm=hotplugged_vm, sockets=TEN_CPU_SOCKETS)
            pytest.fail("Socket value set higher than max value!")


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
                "vm_name": "rhel-latest-memory-hotplug-vm",
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
                "vm_name": "windows-latest-cpu-hotplug-vm",
            },
            id="WIN-VM",
            marks=[pytest.mark.special_infra, pytest.mark.high_resource_vm],
        ),
    ],
    indirect=True,
)
class TestMemoryHotPlug:
    @pytest.mark.parametrize(
        "hotplugged_sockets_memory_guest", [pytest.param({"memory_guest": SIX_GI_MEMORY})], indirect=True
    )
    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME}::hotplug_memory")
    @pytest.mark.polarion("CNV-10676")
    def test_hotplug_memory(self, hotplugged_sockets_memory_guest, hotplugged_vm):
        assert_guest_os_memory_amount(vm=hotplugged_vm, spec_memory_amount=SIX_GI_MEMORY)

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::hotplug_memory"])
    @pytest.mark.polarion("CNV-10677")
    def test_migrate_snapshot_hotplugged_vm(self, hotplug_vm_snapshot, hotplugged_vm):
        migrate_vm_and_verify(vm=hotplugged_vm, check_ssh_connectivity=True)

    @pytest.mark.parametrize(
        "hotplugged_sockets_memory_guest", [pytest.param({"memory_guest": FIVE_GI_MEMORY})], indirect=True
    )
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::hotplug_memory"])
    @pytest.mark.polarion("CNV-10679")
    def test_decrease_memory_value(
        self, xfail_windows_memory_hotunplug, hotplugged_sockets_memory_guest, hotplugged_vm
    ):
        assert_guest_os_memory_amount(vm=hotplugged_vm, spec_memory_amount=FIVE_GI_MEMORY)

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::hotplug_memory"])
    @pytest.mark.polarion("CNV-10678")
    def test_restart_hotplugged_vm(self, hotplugged_vm):
        restart_vm_wait_for_running_vm(vm=hotplugged_vm)

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::hotplug_memory"])
    @pytest.mark.polarion("CNV-10681")
    def test_hotplug_memory_above_max_value(self, hotplugged_vm):
        with pytest.raises(UnprocessibleEntityError):
            hotplug_spec_vm(vm=hotplugged_vm, memory_guest=TWELVE_GI_MEMORY)
            pytest.fail("Memory value set higher than max value!")

    @pytest.mark.parametrize(
        "hotplugged_sockets_memory_guest",
        [pytest.param({"memory_guest": FOUR_GI_MEMORY, "skip_migration": True})],
        indirect=True,
    )
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::hotplug_memory"])
    @pytest.mark.polarion("CNV-10682")
    def test_reduce_memory_below_start_value(self, hotplugged_sockets_memory_guest, hotplugged_vm):
        assert_restart_required_condition(
            vm=hotplugged_vm,
            expected_message="memory updated in template spec to a value lower than what the VM started with",
        )

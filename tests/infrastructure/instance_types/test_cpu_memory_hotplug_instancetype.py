import pytest
from kubernetes.dynamic.exceptions import UnprocessibleEntityError
from ocp_resources.virtual_machine_snapshot import VirtualMachineSnapshot
from pytest_testconfig import config as py_config

from tests.utils import (
    assert_guest_os_cpu_count,
    assert_restart_required_condition,
    clean_up_migration_jobs,
    hotplug_instance_type_vm_and_verify,
    update_vm_instancetype_name,
)
from utilities.constants import (
    FOUR_CPU_SOCKETS,
    SIX_CPU_SOCKETS,
    TEN_CPU_SOCKETS,
    Images,
)
from utilities.ssp import cluster_instance_type_for_hot_plug
from utilities.storage import data_volume_template_with_source_ref_dict
from utilities.virt import (
    VirtualMachineForTests,
    migrate_vm_and_verify,
    restart_vm_wait_for_running_vm,
    running_vm,
)

pytestmark = pytest.mark.usefixtures("skip_if_no_common_modern_cpu", "skip_access_mode_rwo_scope_module")

TESTS_CLASS_NAME = "TestCPUHotPlugInstancetype"


@pytest.fixture(scope="class")
def instance_type_hotplug_vm(
    namespace,
    unprivileged_client,
    golden_image_data_source_scope_class,
    four_sockets_instance_type,
):
    with VirtualMachineForTests(
        name="rhel-hotplug-instance-type-vm",
        namespace=namespace.name,
        client=unprivileged_client,
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=golden_image_data_source_scope_class
        ),
        vm_instance_type=four_sockets_instance_type,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture(scope="class")
def four_sockets_instance_type(cpu_for_migration):
    with cluster_instance_type_for_hot_plug(
        guest_sockets=FOUR_CPU_SOCKETS, cpu_model=cpu_for_migration
    ) as instance_type:
        yield instance_type


@pytest.fixture(scope="class")
def six_sockets_instance_type(cpu_for_migration):
    with cluster_instance_type_for_hot_plug(
        guest_sockets=SIX_CPU_SOCKETS, cpu_model=cpu_for_migration
    ) as instance_type:
        yield instance_type


@pytest.fixture(scope="class")
def ten_sockets_instance_type(cpu_for_migration):
    with cluster_instance_type_for_hot_plug(
        guest_sockets=TEN_CPU_SOCKETS, cpu_model=cpu_for_migration
    ) as instance_type:
        yield instance_type


@pytest.fixture()
def hotplugged_six_sockets_instance_type(admin_client, instance_type_hotplug_vm, six_sockets_instance_type):
    hotplug_instance_type_vm_and_verify(
        vm=instance_type_hotplug_vm, client=admin_client, instance_type=six_sockets_instance_type
    )
    yield
    clean_up_migration_jobs(client=admin_client, vm=instance_type_hotplug_vm)


@pytest.fixture(scope="class")
def hotplug_vm_snapshot_instance_type(instance_type_hotplug_vm):
    with VirtualMachineSnapshot(
        name=f"{instance_type_hotplug_vm.name}-snapshot",
        namespace=instance_type_hotplug_vm.namespace,
        vm_name=instance_type_hotplug_vm.name,
    ) as snapshot:
        snapshot.wait_snapshot_done()
        yield snapshot


@pytest.mark.parametrize(
    "golden_image_data_volume_scope_class",
    [
        pytest.param(
            {
                "dv_name": "dv-rhel-latest-vm",
                "image": py_config["latest_rhel_os_dict"]["image_path"],
                "storage_class": py_config["default_storage_class"],
                "dv_size": Images.Rhel.DEFAULT_DV_SIZE,
            },
            id="RHEL-VM",
        ),
    ],
    indirect=True,
)
@pytest.mark.s390x
class TestCPUHotPlugInstanceType:
    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME}::hotplug_cpu_instance_type")
    @pytest.mark.polarion("CNV-11401")
    def test_hotplug_cpu_instance_type(self, instance_type_hotplug_vm, hotplugged_six_sockets_instance_type):
        assert_guest_os_cpu_count(vm=instance_type_hotplug_vm, spec_cpu_amount=SIX_CPU_SOCKETS)

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::hotplug_cpu_instance_type"])
    @pytest.mark.polarion("CNV-11402")
    def test_migrate_snapshot_hotplugged_vm(self, hotplug_vm_snapshot_instance_type, instance_type_hotplug_vm):
        migrate_vm_and_verify(vm=instance_type_hotplug_vm, check_ssh_connectivity=True)

    @pytest.mark.dependency(
        name=f"{TESTS_CLASS_NAME}::decrease_cpu_value", depends=[f"{TESTS_CLASS_NAME}::hotplug_cpu_instance_type"]
    )
    @pytest.mark.polarion("CNV-11404")
    def test_decrease_cpu_value(self, instance_type_hotplug_vm, four_sockets_instance_type):
        update_vm_instancetype_name(vm=instance_type_hotplug_vm, instance_type_name=four_sockets_instance_type.name)
        assert_restart_required_condition(
            vm=instance_type_hotplug_vm, expected_message="Reduction of CPU socket count requires a restart"
        )

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::decrease_cpu_value"])
    @pytest.mark.polarion("CNV-11403")
    def test_restart_hotplugged_vm(self, instance_type_hotplug_vm):
        restart_vm_wait_for_running_vm(vm=instance_type_hotplug_vm)

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::hotplug_cpu_instance_type"])
    @pytest.mark.polarion("CNV-11405")
    def test_hotplug_cpu_above_max_value(self, instance_type_hotplug_vm, ten_sockets_instance_type):
        with pytest.raises(UnprocessibleEntityError):
            update_vm_instancetype_name(vm=instance_type_hotplug_vm, instance_type_name=ten_sockets_instance_type.name)
            pytest.fail("Socket value set higher than max value!")

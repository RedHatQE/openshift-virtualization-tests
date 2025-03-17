import pytest
from kubernetes.dynamic.exceptions import UnprocessibleEntityError
from ocp_resources.virtual_machine_cluster_instancetype import VirtualMachineClusterInstancetype
from ocp_resources.virtual_machine_snapshot import VirtualMachineSnapshot
from pytest_testconfig import config as py_config

from tests.utils import (
    assert_guest_os_cpu_count,
    assert_restart_required_codition,
    clean_up_migration_jobs,
    hotplug_instance_type_vm,
    hotplug_resource_and_wait_hotplug_migration_finish,
)
from utilities.constants import (
    EIGHT_CPU_SOCKETS,
    FOUR_CPU_SOCKETS,
    FOUR_GI_MEMORY,
    SIX_CPU_SOCKETS,
    TEN_CPU_SOCKETS,
    Images,
)
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
    hot_plug_instance_type,
):
    with VirtualMachineForTests(
        name="rhel-hotplug-instance-type-vm",
        namespace=namespace.name,
        client=unprivileged_client,
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=golden_image_data_source_scope_class
        ),
        vm_instance_type=hot_plug_instance_type,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture(scope="class")
def hot_plug_instance_type(cpu_for_migration):
    with VirtualMachineClusterInstancetype(
        name="hot-plug-instance-type",
        memory={"guest": FOUR_GI_MEMORY},
        cpu={
            "guest": FOUR_CPU_SOCKETS,
            "model": cpu_for_migration,
            "maxSockets": EIGHT_CPU_SOCKETS,
        },
    ) as instance_type:
        yield instance_type


@pytest.fixture()
def hotplugged_six_sockets_instance_type(admin_client, instance_type_hotplug_vm, unprivileged_client):
    hotplug_resource_and_wait_hotplug_migration_finish(
        vm=instance_type_hotplug_vm, client=unprivileged_client, sockets=SIX_CPU_SOCKETS
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
class TestCPUHotPlugInstanceType:
    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME}::hotplug_cpu_instance_type")
    @pytest.mark.polarion("CNV-11401")
    def test_hotplug_cpu_instance_type(self, instance_type_hotplug_vm, hotplugged_six_sockets_instance_type):
        assert_guest_os_cpu_count(vm=instance_type_hotplug_vm, spec_cpu_amount=SIX_CPU_SOCKETS)

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::hotplug_cpu_instance_type"])
    @pytest.mark.polarion("CNV-11402")
    def test_migrate_snapshot_hotplugged_vm(self, hotplug_vm_snapshot_instance_type, instance_type_hotplug_vm):
        migrate_vm_and_verify(vm=instance_type_hotplug_vm, check_ssh_connectivity=True)

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::hotplug_cpu_instance_type"])
    @pytest.mark.polarion("CNV-11403")
    def test_restart_hotplugged_vm(self, instance_type_hotplug_vm):
        restart_vm_wait_for_running_vm(vm=instance_type_hotplug_vm)

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::hotplug_cpu_instance_type"])
    @pytest.mark.polarion("CNV-11404")
    def test_decrease_cpu_value(self, instance_type_hotplug_vm):
        hotplug_instance_type_vm(vm=instance_type_hotplug_vm, sockets=FOUR_CPU_SOCKETS)
        assert_restart_required_codition(
            vm=instance_type_hotplug_vm, expected_message="Reduction of CPU socket count requires a restart"
        )

    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::hotplug_cpu_instance_type"])
    @pytest.mark.polarion("CNV-11405")
    def test_hotplug_cpu_above_max_value(self, instance_type_hotplug_vm):
        with pytest.raises(UnprocessibleEntityError):
            hotplug_instance_type_vm(vm=instance_type_hotplug_vm, sockets=TEN_CPU_SOCKETS)
            pytest.fail("Socket value set higher then max value!")

"""
Automation for Hot Plug
"""

import logging
import shlex

import pytest
from ocp_resources.datavolume import DataVolume
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.storage_profile import StorageProfile

from tests.utils import create_windows2022_dv_from_registry, create_windows2022_vm_with_vtpm_from_registry
from utilities.constants import HOTPLUG_DISK_SERIAL, Images
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.jira import is_jira_open
from utilities.storage import (
    assert_disk_serial,
    assert_hotplugvolume_nonexist,
    create_dv,
    virtctl_volume,
    wait_for_vm_volume_ready,
)
from utilities.virt import (
    VirtualMachineForTests,
    fedora_vm_body,
    migrate_vm_and_verify,
    running_vm,
)

LOGGER = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.usefixtures("enabled_feature_gate_for_declarative_hotplug_volumes"),
    pytest.mark.post_upgrade,
]


def is_dv_migratable(dv):
    return StorageProfile(name=dv.storage_class).first_claim_property_set_access_modes()[0] == DataVolume.AccessMode.RWX


@pytest.fixture(scope="module")
def enabled_feature_gate_for_declarative_hotplug_volumes(
    hyperconverged_resource_scope_module,
):
    with ResourceEditorValidateHCOReconcile(
        patches={
            hyperconverged_resource_scope_module: {"spec": {"featureGates": {"declarativeHotplugVolumes": True}}},
        },
        list_resource_reconcile=[KubeVirt],
        wait_for_reconcile_post_update=True,
    ):
        yield


@pytest.fixture(scope="class")
def hotplug_volume_windows_scope_class(
    request, namespace, vm_instance_from_template_multi_storage_scope_class, blank_disk_dv_multi_storage_scope_class
):
    with virtctl_volume(
        action="add",
        namespace=namespace.name,
        vm_name=vm_instance_from_template_multi_storage_scope_class.name,
        volume_name=blank_disk_dv_multi_storage_scope_class.name,
        **request.param,
    ) as res:
        status, out, err = res
        assert status, f"Failed to add volume to VM, out: {out}, err: {err}."
        yield


@pytest.fixture(scope="class")
def windows_dv_from_registry_scope_class(
    unprivileged_client,
    namespace,
    storage_class_matrix__class__,
):
    """Creates a Windows 2022 DataVolume from registry container disk."""
    with create_windows2022_dv_from_registry(
        dv_name="dv-windows-2022-hotplug",
        namespace=namespace.name,
        client=unprivileged_client,
        storage_class=next(iter(storage_class_matrix__class__)),
    ) as dv_dict:
        yield dv_dict


@pytest.fixture(scope="class")
def vm_instance_from_template_multi_storage_scope_class(
    unprivileged_client,
    namespace,
    modern_cpu_for_migration,
    windows_dv_from_registry_scope_class,
):
    """Creates a Windows 2022 VM with vTPM from registry container disk."""
    with create_windows2022_vm_with_vtpm_from_registry(
        dv_dict=windows_dv_from_registry_scope_class,
        namespace=namespace.name,
        client=unprivileged_client,
        vm_name="vm-win-2022-hotplug",
        cpu_model=modern_cpu_for_migration,
    ) as vm:
        yield vm


@pytest.fixture(scope="class")
def hotplug_volume_scope_class(
    request, namespace, fedora_vm_for_hotplug_scope_class, blank_disk_dv_multi_storage_scope_class
):
    with virtctl_volume(
        action="add",
        namespace=namespace.name,
        vm_name=fedora_vm_for_hotplug_scope_class.name,
        volume_name=blank_disk_dv_multi_storage_scope_class.name,
        **request.param,
    ) as res:
        status, out, err = res
        assert status, f"Failed to add volume to VM, out: {out}, err: {err}."
        yield


@pytest.fixture(scope="class")
def param_substring_scope_class(storage_class_name_scope_class):
    return storage_class_name_scope_class[0:3].strip("-")


@pytest.fixture(scope="class")
def fedora_vm_for_hotplug_scope_class(unprivileged_client, namespace, param_substring_scope_class, cpu_for_migration):
    name = f"fedora-hotplug-{param_substring_scope_class}"
    memory_requests = None
    cpu_requests = None

    if is_jira_open(jira_id="CNV-71599"):
        memory_requests = f"{float(Images.Fedora.DEFAULT_MEMORY_SIZE[:-2]) * 2}Gi"
        cpu_requests = 1

    with VirtualMachineForTests(
        client=unprivileged_client,
        name=name,
        memory_requests=memory_requests,
        memory_limits=memory_requests,
        namespace=namespace.name,
        body=fedora_vm_body(name=name),
        cpu_model=cpu_for_migration,
        cpu_limits=cpu_requests,
        cpu_requests=cpu_requests,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture(scope="class")
def blank_disk_dv_multi_storage_scope_class(
    unprivileged_client, namespace, param_substring_scope_class, storage_class_name_scope_class
):
    with create_dv(
        client=unprivileged_client,
        source="blank",
        dv_name=f"blank-dv-{param_substring_scope_class}",
        namespace=namespace.name,
        size="1Gi",
        storage_class=storage_class_name_scope_class,
        consume_wffc=False,
    ) as dv:
        yield dv


@pytest.mark.parametrize(
    "hotplug_volume_scope_class",
    [
        pytest.param({"persist": True}),
    ],
    indirect=True,
)
@pytest.mark.conformance
@pytest.mark.gating
class TestHotPlugWithPersist:
    @pytest.mark.sno
    @pytest.mark.polarion("CNV-6014")
    @pytest.mark.dependency(name="test_hotplug_volume_with_persist")
    @pytest.mark.s390x
    def test_hotplug_volume_with_persist(
        self,
        blank_disk_dv_multi_storage_scope_class,
        fedora_vm_for_hotplug_scope_class,
        hotplug_volume_scope_class,
    ):
        wait_for_vm_volume_ready(vm=fedora_vm_for_hotplug_scope_class)
        assert_hotplugvolume_nonexist(vm=fedora_vm_for_hotplug_scope_class)

    @pytest.mark.polarion("CNV-11390")
    @pytest.mark.dependency(depends=["test_hotplug_volume_with_persist"])
    @pytest.mark.s390x
    def test_hotplug_volume_with_persist_migrate(
        self,
        blank_disk_dv_multi_storage_scope_class,
        fedora_vm_for_hotplug_scope_class,
        hotplug_volume_scope_class,
    ):
        if is_dv_migratable(dv=blank_disk_dv_multi_storage_scope_class):
            migrate_vm_and_verify(vm=fedora_vm_for_hotplug_scope_class, check_ssh_connectivity=True)


@pytest.mark.parametrize(
    "hotplug_volume_scope_class",
    [
        pytest.param({"persist": True, "serial": HOTPLUG_DISK_SERIAL}),
    ],
    indirect=True,
)
@pytest.mark.conformance
@pytest.mark.gating
class TestHotPlugWithSerialPersist:
    @pytest.mark.sno
    @pytest.mark.polarion("CNV-6425")
    @pytest.mark.dependency(name="test_hotplug_volume_with_persist")
    @pytest.mark.s390x
    def test_hotplug_volume_with_serial_and_persist(
        self,
        blank_disk_dv_multi_storage_scope_class,
        fedora_vm_for_hotplug_scope_class,
        hotplug_volume_scope_class,
    ):
        wait_for_vm_volume_ready(vm=fedora_vm_for_hotplug_scope_class)
        assert_disk_serial(vm=fedora_vm_for_hotplug_scope_class)
        assert_hotplugvolume_nonexist(vm=fedora_vm_for_hotplug_scope_class)

    @pytest.mark.polarion("CNV-6425b")
    @pytest.mark.dependency(depends=["test_hotplug_volume_with_persist"])
    @pytest.mark.s390x
    def test_hotplug_volume_with_serial_and_persist_migrate(
        self,
        blank_disk_dv_multi_storage_scope_class,
        fedora_vm_for_hotplug_scope_class,
        hotplug_volume_scope_class,
    ):
        if is_dv_migratable(dv=blank_disk_dv_multi_storage_scope_class):
            migrate_vm_and_verify(vm=fedora_vm_for_hotplug_scope_class, check_ssh_connectivity=True)


@pytest.mark.parametrize(
    "hotplug_volume_windows_scope_class",
    [
        pytest.param(
            {"persist": True, "serial": HOTPLUG_DISK_SERIAL},
        ),
    ],
    indirect=True,
)
@pytest.mark.tier3
class TestHotPlugWindows:
    @pytest.mark.polarion("CNV-6525")
    @pytest.mark.dependency(name="test_windows_hotplug")
    def test_windows_hotplug(
        self,
        blank_disk_dv_multi_storage_scope_class,
        vm_instance_from_template_multi_storage_scope_class,
        hotplug_volume_windows_scope_class,
    ):
        wait_for_vm_volume_ready(vm=vm_instance_from_template_multi_storage_scope_class)
        assert_disk_serial(
            command=shlex.split("wmic diskdrive get SerialNumber"),
            vm=vm_instance_from_template_multi_storage_scope_class,
        )
        assert_hotplugvolume_nonexist(vm=vm_instance_from_template_multi_storage_scope_class)

    @pytest.mark.polarion("CNV-11391")
    @pytest.mark.dependency(depends=["test_windows_hotplug"])
    def test_windows_hotplug_migrate(
        self,
        unprivileged_client,
        blank_disk_dv_multi_storage_scope_class,
        vm_instance_from_template_multi_storage_scope_class,
        hotplug_volume_windows_scope_class,
    ):
        if is_dv_migratable(dv=blank_disk_dv_multi_storage_scope_class):
            migrate_vm_and_verify(
                vm=vm_instance_from_template_multi_storage_scope_class,
                check_ssh_connectivity=True,
            )

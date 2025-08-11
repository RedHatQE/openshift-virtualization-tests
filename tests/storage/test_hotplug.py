"""
Automation for Hot Plug
"""

import logging
import shlex

import pytest
from ocp_resources.datavolume import DataVolume
from ocp_resources.storage_profile import StorageProfile

from tests.os_params import WINDOWS_LATEST, WINDOWS_LATEST_LABELS
from utilities.constants import HOTPLUG_DISK_SERIAL
from utilities.storage import (
    assert_disk_serial,
    assert_hotplugvolume_nonexist_optional_restart,
    create_dv,
    data_volume,
    virtctl_volume,
    wait_for_vm_volume_ready,
)
from utilities.virt import (
    VirtualMachineForTests,
    fedora_vm_body,
    migrate_vm_and_verify,
    running_vm,
    vm_instance_from_template,
    wait_for_windows_vm,
)

LOGGER = logging.getLogger(__name__)

pytestmark = pytest.mark.post_upgrade


def is_dv_migratable(dv):
    return StorageProfile(name=dv.storage_class).first_claim_property_set_access_modes()[0] == DataVolume.AccessMode.RWX


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
def vm_instance_from_template_multi_storage_scope_class(
    request,
    unprivileged_client,
    namespace,
    data_volume_multi_storage_scope_class,
    cpu_for_migration,
):
    """Calls vm_instance_from_template contextmanager

    Creates a VM from template and starts it (if requested).
    """
    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        existing_data_volume=data_volume_multi_storage_scope_class,
        vm_cpu_model=cpu_for_migration if request.param.get("set_vm_common_cpu") else None,
    ) as vm:
        yield vm


@pytest.fixture(scope="class")
def started_windows_vm_scope_class(
    request,
    vm_instance_from_template_multi_storage_scope_class,
):
    wait_for_windows_vm(
        vm=vm_instance_from_template_multi_storage_scope_class,
        version=request.param["os_version"],
    )


@pytest.fixture(scope="class")
def data_volume_multi_storage_scope_class(
    request,
    namespace,
    storage_class_matrix__class__,
    schedulable_nodes,
):
    yield from data_volume(
        request=request,
        namespace=namespace,
        storage_class_matrix=storage_class_matrix__class__,
        schedulable_nodes=schedulable_nodes,
    )


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
def fedora_vm_for_hotplug_scope_class(namespace, param_substring_scope_class, cpu_for_migration):
    name = f"fedora-hotplug-{param_substring_scope_class}"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        body=fedora_vm_body(name=name),
        cpu_model=cpu_for_migration,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture(scope="class")
def storage_class_name_scope_class(storage_class_matrix__class__):
    return [*storage_class_matrix__class__][0]


@pytest.fixture(scope="class")
def blank_disk_dv_multi_storage_scope_class(namespace, param_substring_scope_class, storage_class_name_scope_class):
    with create_dv(
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
        pytest.param({"serial": HOTPLUG_DISK_SERIAL}),
    ],
    indirect=True,
)
@pytest.mark.gating
class TestHotPlugWithSerial:
    @pytest.mark.sno
    @pytest.mark.polarion("CNV-6013")
    @pytest.mark.dependency(name="test_hotplug_volume_with_serial")
    @pytest.mark.s390x
    def test_hotplug_volume_with_serial(
        self,
        blank_disk_dv_multi_storage_scope_class,
        fedora_vm_for_hotplug_scope_class,
        hotplug_volume_scope_class,
    ):
        wait_for_vm_volume_ready(vm=fedora_vm_for_hotplug_scope_class)
        assert_disk_serial(vm=fedora_vm_for_hotplug_scope_class)

    @pytest.mark.polarion("CNV-11389")
    @pytest.mark.dependency(depends=["test_hotplug_volume_with_serial"])
    def test_hotplug_volume_with_serial_migrate(
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
        pytest.param({"persist": True}),
    ],
    indirect=True,
)
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
        assert_hotplugvolume_nonexist_optional_restart(vm=fedora_vm_for_hotplug_scope_class, restart=True)

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
        assert_hotplugvolume_nonexist_optional_restart(vm=fedora_vm_for_hotplug_scope_class, restart=True)

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
    "data_volume_multi_storage_scope_class,"
    "vm_instance_from_template_multi_storage_scope_class,"
    "started_windows_vm_scope_class,"
    "hotplug_volume_windows_scope_class",
    [
        pytest.param(
            {
                "dv_name": "dv-windows",
                "image": WINDOWS_LATEST.get("image_path"),
                "dv_size": WINDOWS_LATEST.get("dv_size"),
            },
            {
                "vm_name": f"vm-win-{WINDOWS_LATEST.get('os_version')}",
                "template_labels": WINDOWS_LATEST_LABELS,
            },
            {"os_version": WINDOWS_LATEST.get("os_version")},
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
        data_volume_multi_storage_scope_class,
        vm_instance_from_template_multi_storage_scope_class,
        started_windows_vm_scope_class,
        hotplug_volume_windows_scope_class,
    ):
        wait_for_vm_volume_ready(vm=vm_instance_from_template_multi_storage_scope_class)
        assert_disk_serial(
            command=shlex.split("wmic diskdrive get SerialNumber"),
            vm=vm_instance_from_template_multi_storage_scope_class,
        )
        assert_hotplugvolume_nonexist_optional_restart(
            vm=vm_instance_from_template_multi_storage_scope_class,
            restart=True,
        )

    @pytest.mark.polarion("CNV-11391")
    @pytest.mark.dependency(depends=["test_windows_hotplug"])
    def test_windows_hotplug_migrate(
        self,
        unprivileged_client,
        blank_disk_dv_multi_storage_scope_class,
        data_volume_multi_storage_scope_class,
        vm_instance_from_template_multi_storage_scope_class,
        started_windows_vm_scope_class,
        hotplug_volume_windows_scope_class,
    ):
        if is_dv_migratable(dv=blank_disk_dv_multi_storage_scope_class):
            migrate_vm_and_verify(
                vm=vm_instance_from_template_multi_storage_scope_class,
                check_ssh_connectivity=True,
            )

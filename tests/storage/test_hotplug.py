"""
Automation for Hot Plug
"""

from __future__ import annotations

import contextlib
import logging
import shlex
from typing import TYPE_CHECKING

import pytest
from ocp_resources.datavolume import DataVolume
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.storage_profile import StorageProfile

from tests.storage.constants import BLANK_DV_SIZE, NUM_HOTPLUG_DISKS
from tests.storage.utils import assert_disk_bus
from tests.utils import create_windows2022_vm_with_data_volume_template
from utilities.constants.storage import HOTPLUG_DISK_SCSI_BUS, HOTPLUG_DISK_SERIAL, HOTPLUG_DISK_VIRTIO_BUS
from utilities.constants.virt import WIN_2K22
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.storage import (
    assert_disk_serial,
    assert_hotplugvolume_nonexist,
    create_dv,
    data_volume_template_with_source_ref_dict,
    virtctl_volume,
    wait_for_vm_volume_ready,
)
from utilities.virt import (
    VirtualMachineForTests,
    migrate_vm_and_verify,
    restart_vm_wait_for_running_vm,
    running_vm,
)

if TYPE_CHECKING:
    from kubernetes.dynamic import DynamicClient

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
    request, namespace, vm_instance_multi_storage_scope_class, blank_disk_dv_multi_storage_scope_class
):
    with virtctl_volume(
        action="add",
        namespace=namespace.name,
        vm_name=vm_instance_multi_storage_scope_class.name,
        volume_name=blank_disk_dv_multi_storage_scope_class.name,
        **request.param,
    ) as res:
        status, out, err = res
        assert status, f"Failed to add volume to VM, out: {out}, err: {err}."
        yield


@pytest.fixture(scope="class")
def vm_instance_multi_storage_scope_class(
    unprivileged_client,
    namespace,
    modern_cpu_for_migration,
    windows_validation_os_images_data_source_scope_session,
    storage_class_name_scope_class,
):
    """Creates a Windows 2022 VM with vTPM from the session-scoped Windows DataSource."""
    with create_windows2022_vm_with_data_volume_template(
        dv_template=data_volume_template_with_source_ref_dict(
            data_source=windows_validation_os_images_data_source_scope_session,
            storage_class=storage_class_name_scope_class,
        ),
        namespace=namespace.name,
        client=unprivileged_client,
        vm_name=f"vm-{WIN_2K22}-hotplug",
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
def fedora_vm_for_hotplug_scope_class(
    unprivileged_client,
    namespace,
    param_substring_scope_class,
    fedora_data_source_scope_module,
    storage_class_name_scope_class,
    cpu_for_migration,
):
    with VirtualMachineForTests(
        name=f"fedora-hotplug-{param_substring_scope_class}",
        namespace=namespace.name,
        client=unprivileged_client,
        vm_instance_type_infer=True,
        vm_preference_infer=True,
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=fedora_data_source_scope_module,
            storage_class=storage_class_name_scope_class,
        ),
        cpu_model=cpu_for_migration,
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


@pytest.fixture(scope="class")
def blank_dvs_for_hotplug_scope_class(
    request, unprivileged_client, namespace, param_substring_scope_class, storage_class_name_scope_class
):
    """Yields a list of blank DataVolumes sized for hotplug testing.

    Yields:
        list[DataVolume]: Blank DVs whose count is driven by the indirect ``request.param``.
    """
    with contextlib.ExitStack() as stack:
        dvs = []
        for idx in range(request.param):
            dv = stack.enter_context(
                cm=create_dv(
                    source="blank",
                    dv_name=f"blank-dv-hotplug-{param_substring_scope_class}-{idx}",
                    client=unprivileged_client,
                    namespace=namespace.name,
                    size=BLANK_DV_SIZE,
                    storage_class=storage_class_name_scope_class,
                    consume_wffc=False,
                )
            )
            dvs.append(dv)
        yield dvs


@pytest.fixture(scope="class")
def hotplugged_dvs_scope_class(blank_dvs_for_hotplug_scope_class, fedora_vm_for_hotplug_scope_class):
    """Hotplugs all blank DVs to the VM with persist; first disk also receives a serial.

    Yields:
        list[DataVolume]: The hotplugged DVs after they become ready on the VM.
    """
    with contextlib.ExitStack() as stack:
        for idx, dv in enumerate(blank_dvs_for_hotplug_scope_class):
            params = {"persist": True}
            if idx == 0:
                params["serial"] = HOTPLUG_DISK_SERIAL
            status, out, err = stack.enter_context(
                cm=virtctl_volume(
                    action="add",
                    namespace=fedora_vm_for_hotplug_scope_class.namespace,
                    vm_name=fedora_vm_for_hotplug_scope_class.name,
                    volume_name=dv.name,
                    **params,
                )
            )
            assert status, f"Failed to add volume {dv.name} to VM, out: {out}, err: {err}."
            wait_for_vm_volume_ready(
                vm=fedora_vm_for_hotplug_scope_class,
                volume_name=dv.name,
            )
        yield blank_dvs_for_hotplug_scope_class


@pytest.mark.parametrize(
    ("hotplug_volume_scope_class", "expected_bus"),
    [
        pytest.param({"persist": True, "bus": HOTPLUG_DISK_VIRTIO_BUS}, HOTPLUG_DISK_VIRTIO_BUS, id="virtio-bus"),
        pytest.param({"persist": True, "bus": HOTPLUG_DISK_SCSI_BUS}, HOTPLUG_DISK_SCSI_BUS, id="scsi-bus"),
    ],
    indirect=["hotplug_volume_scope_class"],
    scope="class",
)
@pytest.mark.conformance
@pytest.mark.gating
@pytest.mark.usefixtures("hotplug_volume_scope_class")
class TestHotPlugWithPersist:
    @pytest.mark.sno
    @pytest.mark.polarion("CNV-6014")
    @pytest.mark.dependency(name="test_hotplug_volume_with_bus_and_persist")
    @pytest.mark.s390x
    def test_hotplug_volume_with_bus_and_persist(
        self,
        blank_disk_dv_multi_storage_scope_class,
        fedora_vm_for_hotplug_scope_class,
        expected_bus,
    ):
        wait_for_vm_volume_ready(
            vm=fedora_vm_for_hotplug_scope_class, volume_name=blank_disk_dv_multi_storage_scope_class.name
        )
        assert_hotplugvolume_nonexist(vm=fedora_vm_for_hotplug_scope_class)
        assert_disk_bus(
            vm=fedora_vm_for_hotplug_scope_class,
            volume=blank_disk_dv_multi_storage_scope_class,
            expected_bus=expected_bus,
        )

    @pytest.mark.polarion("CNV-11390")
    @pytest.mark.dependency(depends=["test_hotplug_volume_with_bus_and_persist"])
    @pytest.mark.usefixtures("expected_bus")
    @pytest.mark.s390x
    def test_hotplug_volume_with_bus_and_persist_migrate(
        self,
        admin_client: DynamicClient,
        blank_disk_dv_multi_storage_scope_class: DataVolume,
        fedora_vm_for_hotplug_scope_class: VirtualMachineForTests,
    ):
        if is_dv_migratable(dv=blank_disk_dv_multi_storage_scope_class):
            migrate_vm_and_verify(
                vm=fedora_vm_for_hotplug_scope_class, client=admin_client, check_ssh_connectivity=True
            )


@pytest.mark.parametrize(
    "blank_dvs_for_hotplug_scope_class",
    [
        pytest.param(1, marks=[pytest.mark.gating, pytest.mark.sno, pytest.mark.s390x], id="1-disk"),
        pytest.param(NUM_HOTPLUG_DISKS, marks=[pytest.mark.conformance, pytest.mark.tier3], id="3-hotplugged"),
    ],
    indirect=True,
    scope="class",
)
@pytest.mark.usefixtures("hotplugged_dvs_scope_class")
class TestHotPlugWithSerialPersist:
    @pytest.mark.polarion("CNV-6425")
    @pytest.mark.dependency(name="test_hotplug_volume_with_serial_and_persist")
    def test_hotplug_volume_with_serial_and_persist(
        self,
        hotplugged_dvs_scope_class: list[DataVolume],
        fedora_vm_for_hotplug_scope_class: VirtualMachineForTests,
    ):
        assert_disk_serial(vm=fedora_vm_for_hotplug_scope_class)
        assert_hotplugvolume_nonexist(vm=fedora_vm_for_hotplug_scope_class)

    @pytest.mark.polarion("CNV-6425b")
    @pytest.mark.dependency(depends=["test_hotplug_volume_with_serial_and_persist"])
    def test_hotplug_volume_with_serial_and_persist_migrate(
        self,
        admin_client: DynamicClient,
        hotplugged_dvs_scope_class: list[DataVolume],
        fedora_vm_for_hotplug_scope_class: VirtualMachineForTests,
    ):
        if all(is_dv_migratable(dv=dv) for dv in hotplugged_dvs_scope_class):
            migrate_vm_and_verify(
                vm=fedora_vm_for_hotplug_scope_class, client=admin_client, check_ssh_connectivity=True
            )

    @pytest.mark.conformance
    @pytest.mark.polarion("CNV-16331")
    @pytest.mark.dependency(depends=["test_hotplug_volume_with_serial_and_persist"])
    def test_hotplug_volume_with_serial_and_persist_after_reboot(
        self,
        hotplugged_dvs_scope_class: list[DataVolume],
        fedora_vm_for_hotplug_scope_class: VirtualMachineForTests,
    ):
        """
        Test that hotplugged persistent disks survive VM reboot.

        Preconditions:
            - Running Fedora VM with hotplugged disks persisted to VM spec

        Steps:
            1. Restart the VM and wait for it to reach Running state
            2. Verify each hotplugged volume is ready on the VM
            3. Verify disk serial is visible inside the guest

        Expected:
            - Disk serial is visible after reboot
        """
        restart_vm_wait_for_running_vm(vm=fedora_vm_for_hotplug_scope_class, check_ssh_connectivity=True)
        for dv in hotplugged_dvs_scope_class:
            wait_for_vm_volume_ready(vm=fedora_vm_for_hotplug_scope_class, volume_name=dv.name)
        assert_disk_serial(vm=fedora_vm_for_hotplug_scope_class)


@pytest.mark.parametrize(
    "hotplug_volume_windows_scope_class",
    [
        pytest.param(
            {"persist": True, "serial": HOTPLUG_DISK_SERIAL},
        ),
    ],
    indirect=True,
)
@pytest.mark.usefixtures("hotplug_volume_windows_scope_class")
@pytest.mark.tier3
class TestHotPlugWindows:
    @pytest.mark.polarion("CNV-6525")
    @pytest.mark.dependency(name="test_windows_hotplug")
    def test_windows_hotplug(
        self,
        blank_disk_dv_multi_storage_scope_class,
        vm_instance_multi_storage_scope_class,
    ):
        wait_for_vm_volume_ready(
            vm=vm_instance_multi_storage_scope_class,
            volume_name=blank_disk_dv_multi_storage_scope_class.name,
        )
        assert_disk_serial(
            command=shlex.split("wmic diskdrive get SerialNumber"),
            vm=vm_instance_multi_storage_scope_class,
        )
        assert_hotplugvolume_nonexist(vm=vm_instance_multi_storage_scope_class)

    @pytest.mark.polarion("CNV-11391")
    @pytest.mark.dependency(depends=["test_windows_hotplug"])
    def test_windows_hotplug_migrate(
        self,
        admin_client: DynamicClient,
        blank_disk_dv_multi_storage_scope_class: DataVolume,
        vm_instance_multi_storage_scope_class: VirtualMachineForTests,
    ):
        if is_dv_migratable(dv=blank_disk_dv_multi_storage_scope_class):
            migrate_vm_and_verify(
                vm=vm_instance_multi_storage_scope_class,
                client=admin_client,
                check_ssh_connectivity=True,
            )

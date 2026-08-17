"""
Automation for Hot Plug
"""

from __future__ import annotations

import logging
import shlex
from contextlib import ExitStack
from typing import TYPE_CHECKING

import pytest
from ocp_resources.datavolume import DataVolume
from ocp_resources.storage_profile import StorageProfile

from tests.storage.constants import BLANK_DV_SIZE, NUM_HOTPLUG_DISKS
from tests.storage.utils import assert_disk_bus, expected_hotplug_serials
from tests.utils import create_windows2022_vm
from utilities.constants.storage import HOTPLUG_DISK_SCSI_BUS, HOTPLUG_DISK_SERIAL, HOTPLUG_DISK_VIRTIO_BUS
from utilities.constants.virt import WIN_2K22
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
    pytest.mark.post_upgrade,
]


def is_dv_migratable(dv: DataVolume, client: DynamicClient) -> bool:
    return (
        StorageProfile(name=dv.storage_class, client=client).first_claim_property_set_access_modes()[0]
        == DataVolume.AccessMode.RWX
    )


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
    with create_windows2022_vm(
        data_volume_template=data_volume_template_with_source_ref_dict(
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
        size=BLANK_DV_SIZE,
        storage_class=storage_class_name_scope_class,
        consume_wffc=False,
    ) as dv:
        yield dv


@pytest.fixture(scope="class")
def blank_dvs_multi_storage_for_hotplug_scope_class(
    request, unprivileged_client, namespace, param_substring_scope_class, storage_class_name_scope_class
):
    """Yields a list of blank DataVolumes sized for hotplug testing.

    Yields:
        list[DataVolume]: Blank DVs whose count is driven by the indirect ``request.param``.
    """
    with ExitStack() as stack:
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
def hotplugged_dvs_scope_class(
    request, blank_dvs_multi_storage_for_hotplug_scope_class, fedora_vm_for_hotplug_scope_class
):
    """Hotplugs all blank DVs to the VM and waits for each volume to become ready.

    Args passed via ``request.param`` (dict):
        persist: Whether to persist the hotplugged volume to the VM spec.
        serial: Optional serial string to assign to each hotplugged disk.

    Yields:
        list[DataVolume]: The hotplugged DVs after they become ready on the VM.
    """
    hotplug_opts = request.param
    serial_base = hotplug_opts.get("serial")
    num_dvs = len(blank_dvs_multi_storage_for_hotplug_scope_class)
    with ExitStack() as stack:
        for idx, dv in enumerate(blank_dvs_multi_storage_for_hotplug_scope_class):
            disk_serial = (f"{serial_base}-{idx}" if num_dvs > 1 else serial_base) if serial_base else None
            status, out, err = stack.enter_context(
                cm=virtctl_volume(
                    action="add",
                    namespace=fedora_vm_for_hotplug_scope_class.namespace,
                    vm_name=fedora_vm_for_hotplug_scope_class.name,
                    volume_name=dv.name,
                    persist=hotplug_opts.get("persist"),
                    serial=disk_serial,
                )
            )
            assert status, f"Failed to add volume {dv.name} to VM, out: {out}, err: {err}."
            wait_for_vm_volume_ready(
                vm=fedora_vm_for_hotplug_scope_class,
                volume_name=dv.name,
            )
        yield blank_dvs_multi_storage_for_hotplug_scope_class


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
        if is_dv_migratable(dv=blank_disk_dv_multi_storage_scope_class, client=admin_client):
            migrate_vm_and_verify(
                vm=fedora_vm_for_hotplug_scope_class, client=admin_client, check_ssh_connectivity=True
            )


@pytest.mark.parametrize(
    ("blank_dvs_multi_storage_for_hotplug_scope_class", "hotplugged_dvs_scope_class"),
    [
        pytest.param(
            1,
            {"persist": True, "serial": HOTPLUG_DISK_SERIAL},
            marks=[pytest.mark.gating, pytest.mark.sno, pytest.mark.s390x],
            id="1-disk",
        ),
        pytest.param(
            NUM_HOTPLUG_DISKS,
            {"persist": True, "serial": HOTPLUG_DISK_SERIAL},
            marks=[pytest.mark.conformance, pytest.mark.tier3],
            id="3-hotplugged",
        ),
    ],
    indirect=True,
    scope="class",
)
@pytest.mark.usefixtures("hotplugged_dvs_scope_class")
class TestHotPlugWithSerialPersist:
    """
    Test hotplug volume persistence with serial identification, migration, and reboot survival.

    Jira: https://issues.redhat.com/browse/CNV-88910  # <skip-jira-utils-check>

    Parametrize:
        - 1-disk [Markers: gating, sno, s390x]: one blank DV hotplugged and persisted to the VM spec
        - 3-hotplugged [Markers: conformance, tier3]: three blank DVs hotplugged and persisted to the VM spec

    Preconditions:
        - Running Fedora VM
        - N blank DataVolumes hotplugged to the VM with persistence enabled and a unique serial per disk
    """

    @pytest.mark.polarion("CNV-6425")
    @pytest.mark.dependency(name="test_hotplug_volume_with_serial_and_persist", scope="class")
    def test_hotplug_volume_with_serial_and_persist(
        self,
        hotplugged_dvs_scope_class: list[DataVolume],
        fedora_vm_for_hotplug_scope_class: VirtualMachineForTests,
    ):
        """
        Verify that persisted hotplugged disks are visible with correct serials and converted to regular disks.

        Preconditions:
            - Running Fedora VM with hotplugged disks persisted to the VM spec

        Steps:
            1. Verify all disk serials are visible inside the guest
            2. Verify none of the volumes still carry a hotplug marker

        Expected:
            - All disk serials are visible and all hotplugged volumes are converted to regular disks
        """
        assert_disk_serial(
            vm=fedora_vm_for_hotplug_scope_class,
            serials=expected_hotplug_serials(count=len(hotplugged_dvs_scope_class), serial=HOTPLUG_DISK_SERIAL),
        )
        assert_hotplugvolume_nonexist(vm=fedora_vm_for_hotplug_scope_class)

    @pytest.mark.polarion("CNV-6425b")
    # Depends on the base persist test: migration only makes sense once hotplug + persist is confirmed working.
    @pytest.mark.dependency(depends=["test_hotplug_volume_with_serial_and_persist"], scope="class")
    def test_hotplug_volume_with_serial_and_persist_migrate(
        self,
        admin_client: DynamicClient,
        hotplugged_dvs_scope_class: list[DataVolume],
        fedora_vm_for_hotplug_scope_class: VirtualMachineForTests,
    ):
        """
        Verify that disk serials remain visible after live migrating a VM with persisted hotplugged disks.

        Preconditions:
            - Running Fedora VM with hotplugged disks persisted to the VM spec
            - All hotplugged DataVolumes support RWX access mode (required for live migration)

        Steps:
            1. Live migrate the VM
            2. Verify each persisted volume is ready after migration
            3. Verify all disk serials are visible inside the guest

        Expected:
            - All hotplugged volumes are ready and their disk serials are visible after migration
        """
        if all(is_dv_migratable(dv=dv, client=admin_client) for dv in hotplugged_dvs_scope_class):
            migrate_vm_and_verify(
                vm=fedora_vm_for_hotplug_scope_class, client=admin_client, check_ssh_connectivity=True
            )
            for data_volume in hotplugged_dvs_scope_class:
                wait_for_vm_volume_ready(vm=fedora_vm_for_hotplug_scope_class, volume_name=data_volume.name)
            assert_disk_serial(
                vm=fedora_vm_for_hotplug_scope_class,
                serials=expected_hotplug_serials(count=len(hotplugged_dvs_scope_class), serial=HOTPLUG_DISK_SERIAL),
            )
        else:
            LOGGER.warning(
                f"Skipping migration for VM {fedora_vm_for_hotplug_scope_class.name}: "
                "not all hotplugged DVs support RWX access mode"
            )

    @pytest.mark.polarion("CNV-16331")
    # Depends on the base persist test to avoid validating reboot behavior on top of a broken persistence step.
    @pytest.mark.dependency(depends=["test_hotplug_volume_with_serial_and_persist"], scope="class")
    def test_hotplug_volume_with_serial_and_persist_after_reboot(
        self,
        hotplugged_dvs_scope_class: list[DataVolume],
        fedora_vm_for_hotplug_scope_class: VirtualMachineForTests,
    ):
        """
        Test that hotplugged persistent disks survive VM reboot.

        Jira: https://issues.redhat.com/browse/CNV-92782  # <skip-jira-utils-check>

        Preconditions:
            - Running Fedora VM with hotplugged disks persisted to VM spec

        Steps:
            1. Restart the VM and wait for it to reach Running state
            2. Verify each hotplugged volume is ready on the VM
            3. Verify all disk serials are visible inside the guest

        Expected:
            - All hotplugged volumes are ready and their disk serials are visible after reboot
        """
        restart_vm_wait_for_running_vm(vm=fedora_vm_for_hotplug_scope_class, check_ssh_connectivity=True)
        for dv in hotplugged_dvs_scope_class:
            wait_for_vm_volume_ready(vm=fedora_vm_for_hotplug_scope_class, volume_name=dv.name)
        assert_disk_serial(
            vm=fedora_vm_for_hotplug_scope_class,
            serials=expected_hotplug_serials(count=len(hotplugged_dvs_scope_class), serial=HOTPLUG_DISK_SERIAL),
        )


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
@pytest.mark.conformance
@pytest.mark.windows
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
        if is_dv_migratable(dv=blank_disk_dv_multi_storage_scope_class, client=admin_client):
            migrate_vm_and_verify(
                vm=vm_instance_multi_storage_scope_class,
                client=admin_client,
                check_ssh_connectivity=True,
            )

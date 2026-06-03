"""
Fixtures for Windows storage tests using self-validation golden image.

These tests require a Windows 11 golden image DataSource to be created beforehand
via the self-validation setup script (setup-golden-image.sh).
"""

import os

import pytest
from ocp_resources.data_source import DataSource
from ocp_resources.datavolume import DataVolume
from ocp_resources.virtual_machine_cluster_instancetype import VirtualMachineClusterInstancetype
from ocp_resources.virtual_machine_cluster_preference import VirtualMachineClusterPreference
from ocp_resources.virtual_machine_instance import VirtualMachineInstance

from utilities.constants import TIMEOUT_5SEC, TIMEOUT_10MIN, U1_LARGE
from utilities.storage import add_dv_to_vm, data_volume_template_with_source_ref_dict
from utilities.virt import VirtualMachineForTests, running_vm

WINDOWS_GOLDEN_IMAGE_NAME = "windows11-golden-image"
WINDOWS_GOLDEN_IMAGE_NAMESPACE = "openshift-virtualization-os-images"
BLANK_DATA_DISK_SIZE = "1Gi"
WINDOWS_11_PREFERENCE = "windows.11"


@pytest.fixture(scope="session")
def skip_if_windows_eula_not_accepted():
    """Skip Windows tests if ACCEPT_WINDOWS_EULA is not set to true."""
    if os.environ.get("ACCEPT_WINDOWS_EULA", "").lower() != "true":
        pytest.skip(
            "Windows tests require ACCEPT_WINDOWS_EULA=true. "
            "Set this environment variable to accept Microsoft EULA and enable Windows testing."
        )


@pytest.fixture(scope="module")
def windows11_golden_image_data_source(unprivileged_client, golden_images_namespace):
    """Get the Windows 11 golden image DataSource created by self-validation setup."""
    data_source = DataSource(
        client=unprivileged_client,
        name=WINDOWS_GOLDEN_IMAGE_NAME,
        namespace=golden_images_namespace.name,
    )
    if not data_source.exists:
        pytest.skip(
            f"Windows golden image DataSource '{WINDOWS_GOLDEN_IMAGE_NAME}' not found in "
            f"'{golden_images_namespace.name}'. Run self-validation with ACCEPT_WINDOWS_EULA=true to create it."
        )
    data_source.wait_for_condition(
        condition=data_source.Condition.READY,
        status=data_source.Condition.Status.TRUE,
        timeout=TIMEOUT_5SEC,
    )
    return data_source


@pytest.fixture(scope="class")
def windows_vm_from_golden_image(
    unprivileged_client,
    namespace,
    windows11_golden_image_data_source,
):
    """Create a Windows VM from the self-validation golden image DataSource."""
    with VirtualMachineForTests(
        client=unprivileged_client,
        name=f"{windows11_golden_image_data_source.name}-test-vm",
        namespace=namespace.name,
        vm_instance_type=VirtualMachineClusterInstancetype(client=unprivileged_client, name=U1_LARGE),
        vm_preference=VirtualMachineClusterPreference(client=unprivileged_client, name=WINDOWS_11_PREFERENCE),
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=windows11_golden_image_data_source,
        ),
    ) as vm:
        yield vm


@pytest.fixture(scope="class")
def blank_data_disk_template(namespace, snapshot_storage_class_name_scope_module):
    """Create a blank DataVolume template dict for use as a second disk."""
    dv = DataVolume(
        name="windows-data-disk",
        namespace=namespace.name,
        source="blank",
        size=BLANK_DATA_DISK_SIZE,
        storage_class=snapshot_storage_class_name_scope_module,
        api_name="storage",
    )
    dv.to_dict()
    return dv.res


@pytest.fixture(scope="class")
def windows_vm_with_data_disk(
    unprivileged_client,
    namespace,
    windows11_golden_image_data_source,
    snapshot_storage_class_name_scope_module,
    blank_data_disk_template,
):
    """Create a running Windows VM with boot disk + blank data disk, guest agent connected."""
    with VirtualMachineForTests(
        client=unprivileged_client,
        name="windows-snapshot-test-vm",
        namespace=namespace.name,
        vm_instance_type=VirtualMachineClusterInstancetype(client=unprivileged_client, name=U1_LARGE),
        vm_preference=VirtualMachineClusterPreference(client=unprivileged_client, name=WINDOWS_11_PREFERENCE),
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=windows11_golden_image_data_source,
            storage_class=snapshot_storage_class_name_scope_module,
        ),
    ) as vm:
        add_dv_to_vm(vm=vm, template_dv=blank_data_disk_template)
        running_vm(vm=vm, wait_for_interfaces=True, check_ssh_connectivity=False)
        vm.vmi.wait_for_condition(
            condition=VirtualMachineInstance.Condition.Type.AGENT_CONNECTED,
            status=VirtualMachineInstance.Condition.Status.TRUE,
            timeout=TIMEOUT_10MIN,
        )
        yield vm

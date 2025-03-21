import logging

import pytest
from packaging import version

from tests.utils import vm_object_from_template
from tests.virt.cluster.common_templates.utils import xfail_old_guest_agent_version
from utilities.constants import REGEDIT_PROC_NAME
from utilities.infra import is_jira_open
from utilities.storage import create_or_update_data_source, data_volume
from utilities.virt import (
    start_and_fetch_processid_on_linux_vm,
    start_and_fetch_processid_on_windows_vm,
    vm_instance_from_template,
)

LOGGER = logging.getLogger(__name__)


# CentOS
@pytest.fixture(scope="class")
def golden_image_data_volume_multi_centos_multi_storage_scope_class(
    admin_client,
    golden_images_namespace,
    storage_class_matrix__class__,
    schedulable_nodes,
    centos_os_matrix__class__,
):
    yield from data_volume(
        namespace=golden_images_namespace,
        storage_class_matrix=storage_class_matrix__class__,
        schedulable_nodes=schedulable_nodes,
        os_matrix=centos_os_matrix__class__,
        check_dv_exists=True,
        admin_client=admin_client,
    )


@pytest.fixture(scope="class")
def golden_image_data_source_multi_centos_multi_storage_scope_class(
    admin_client, golden_image_data_volume_multi_centos_multi_storage_scope_class
):
    yield from create_or_update_data_source(
        admin_client=admin_client,
        dv=golden_image_data_volume_multi_centos_multi_storage_scope_class,
    )


@pytest.fixture(scope="class")
def golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class(
    unprivileged_client,
    namespace,
    centos_os_matrix__class__,
    golden_image_data_source_multi_centos_multi_storage_scope_class,
):
    return vm_object_from_template(
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        os_matrix=centos_os_matrix__class__,
        data_source_object=golden_image_data_source_multi_centos_multi_storage_scope_class,
    )


# Fedora
@pytest.fixture(scope="class")
def golden_image_data_volume_multi_fedora_os_multi_storage_scope_class(
    admin_client,
    golden_images_namespace,
    storage_class_matrix__class__,
    schedulable_nodes,
    fedora_os_matrix__class__,
):
    yield from data_volume(
        namespace=golden_images_namespace,
        storage_class_matrix=storage_class_matrix__class__,
        schedulable_nodes=schedulable_nodes,
        os_matrix=fedora_os_matrix__class__,
        check_dv_exists=True,
        admin_client=admin_client,
    )


@pytest.fixture(scope="class")
def golden_image_data_source_multi_fedora_os_multi_storage_scope_class(
    admin_client, golden_image_data_volume_multi_fedora_os_multi_storage_scope_class
):
    yield from create_or_update_data_source(
        admin_client=admin_client,
        dv=golden_image_data_volume_multi_fedora_os_multi_storage_scope_class,
    )


@pytest.fixture(scope="class")
def golden_image_vm_object_from_template_multi_fedora_os_multi_storage_scope_class(
    request,
    unprivileged_client,
    namespace,
    fedora_os_matrix__class__,
    golden_image_data_source_multi_fedora_os_multi_storage_scope_class,
):
    return vm_object_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        os_matrix=fedora_os_matrix__class__,
        data_source_object=golden_image_data_source_multi_fedora_os_multi_storage_scope_class,
    )


# RHEL
@pytest.fixture(scope="class")
def golden_image_data_volume_multi_rhel_os_multi_storage_scope_class(
    admin_client,
    golden_images_namespace,
    storage_class_matrix__class__,
    schedulable_nodes,
    rhel_os_matrix__class__,
):
    yield from data_volume(
        namespace=golden_images_namespace,
        storage_class_matrix=storage_class_matrix__class__,
        schedulable_nodes=schedulable_nodes,
        os_matrix=rhel_os_matrix__class__,
        check_dv_exists=True,
        admin_client=admin_client,
    )


@pytest.fixture(scope="class")
def golden_image_data_source_multi_rhel_os_multi_storage_scope_class(
    admin_client, golden_image_data_volume_multi_rhel_os_multi_storage_scope_class
):
    yield from create_or_update_data_source(
        admin_client=admin_client,
        dv=golden_image_data_volume_multi_rhel_os_multi_storage_scope_class,
    )


@pytest.fixture(scope="class")
def golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class(
    unprivileged_client,
    namespace,
    rhel_os_matrix__class__,
    golden_image_data_source_multi_rhel_os_multi_storage_scope_class,
):
    return vm_object_from_template(
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        os_matrix=rhel_os_matrix__class__,
        data_source_object=golden_image_data_source_multi_rhel_os_multi_storage_scope_class,
    )


# Windows
@pytest.fixture(scope="class")
def golden_image_data_volume_multi_windows_os_multi_storage_scope_class(
    admin_client,
    golden_images_namespace,
    storage_class_matrix__class__,
    schedulable_nodes,
    windows_os_matrix__class__,
):
    yield from data_volume(
        namespace=golden_images_namespace,
        storage_class_matrix=storage_class_matrix__class__,
        schedulable_nodes=schedulable_nodes,
        os_matrix=windows_os_matrix__class__,
        check_dv_exists=True,
        admin_client=admin_client,
    )


@pytest.fixture(scope="class")
def golden_image_data_source_multi_windows_os_multi_storage_scope_class(
    admin_client, golden_image_data_volume_multi_windows_os_multi_storage_scope_class
):
    yield from create_or_update_data_source(
        admin_client=admin_client,
        dv=golden_image_data_volume_multi_windows_os_multi_storage_scope_class,
    )


@pytest.fixture(scope="class")
def golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class(
    unprivileged_client,
    namespace,
    windows_os_matrix__class__,
    golden_image_data_source_multi_windows_os_multi_storage_scope_class,
):
    return vm_object_from_template(
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        os_matrix=windows_os_matrix__class__,
        data_source_object=golden_image_data_source_multi_windows_os_multi_storage_scope_class,
    )


@pytest.fixture()
def xfail_guest_agent_info_on_win2025(windows_os_matrix__class__):
    # Bug fixed on qemu-ga but not get the latest build, skip win-2025 until get the latest build
    if "win-2025" in [*windows_os_matrix__class__][0] and is_jira_open(jira_id="CNV-52655"):
        pytest.xfail(reason="Expected failure on Windows 2025 until the latest Guest Agent build is available")


# Tablet
@pytest.fixture()
def golden_image_vm_instance_from_template_multi_storage_dv_scope_class_vm_scope_function(
    request,
    unprivileged_client,
    namespace,
    golden_image_data_source_multi_storage_scope_class,
    cpu_for_migration,
):
    """Calls vm_instance_from_template contextmanager

    Creates a VM from template and starts it (if requested).
    VM is created with function scope whereas golden image DV is created with class scope. to be used when a number
    of tests (each creates its relevant VM) are gathered under a class and use the same golden image DV.
    """

    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_source=golden_image_data_source_multi_storage_scope_class,
        vm_cpu_model=cpu_for_migration if request.param.get("set_vm_common_cpu") else None,
    ) as vm:
        yield vm


@pytest.fixture()
def golden_image_vm_object_from_template_multi_storage_dv_scope_class_vm_scope_function(
    request,
    unprivileged_client,
    namespace,
    golden_image_data_source_multi_storage_scope_class,
):
    """VM is created with function scope whereas golden image DV is created with class scope. to be used when a number
    of tests (each creates its relevant VM) are gathered under a class and use the same golden image DV.
    """
    return vm_object_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_source_object=golden_image_data_source_multi_storage_scope_class,
    )


@pytest.fixture()
def golden_image_vm_object_from_template_multi_storage_scope_function(
    request,
    unprivileged_client,
    namespace,
    golden_image_data_source_multi_storage_scope_function,
):
    return vm_object_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_source_object=golden_image_data_source_multi_storage_scope_function,
    )


@pytest.fixture(scope="class")
def golden_image_vm_object_from_template_multi_storage_scope_class(
    request,
    unprivileged_client,
    namespace,
    golden_image_data_source_multi_storage_scope_class,
):
    return vm_object_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_source_object=golden_image_data_source_multi_storage_scope_class,
    )


@pytest.fixture()
def xfail_rhel_with_old_guest_agent(
    golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
):
    xfail_old_guest_agent_version(
        vm=golden_image_vm_object_from_template_multi_rhel_os_multi_storage_scope_class,
        ga_version="4.2.0",
    )


@pytest.fixture()
def xfail_on_rhel_version_below_rhel9(rhel_os_matrix__class__):
    os_ver_str = rhel_os_matrix__class__[[*rhel_os_matrix__class__][0]]["os_version"]
    if version.parse(os_ver_str) < version.parse("9"):
        pytest.xfail(reason="EFI is not enabled by default on RHEL8 and older")


@pytest.fixture(scope="class")
def ping_process_in_centos_os(
    golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class,
):
    process_name = "ping"
    return start_and_fetch_processid_on_linux_vm(
        vm=golden_image_vm_object_from_template_multi_centos_multi_storage_scope_class,
        process_name=process_name,
        args="localhost",
    )


@pytest.fixture(scope="class")
def ping_process_in_fedora_os(
    golden_image_vm_object_from_template_multi_fedora_os_multi_storage_scope_class,
):
    process_name = "ping"
    return start_and_fetch_processid_on_linux_vm(
        vm=golden_image_vm_object_from_template_multi_fedora_os_multi_storage_scope_class,
        process_name=process_name,
        args="localhost",
    )


@pytest.fixture(scope="class")
def regedit_process_in_windows_os(
    golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class,
):
    return start_and_fetch_processid_on_windows_vm(
        vm=golden_image_vm_object_from_template_multi_windows_os_multi_storage_scope_class,
        process_name=REGEDIT_PROC_NAME,
    )

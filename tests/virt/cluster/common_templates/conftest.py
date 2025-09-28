import logging

import pytest
from packaging import version

from tests.virt.cluster.common_templates.utils import (
    get_matrix_os_golden_image_data_source,
    matrix_os_vm_from_template,
    xfail_old_guest_agent_version,
)
from tests.virt.utils import get_data_volume_template_dict_with_default_storage_class
from utilities.constants import REGEDIT_PROC_NAME
from utilities.virt import (
    start_and_fetch_processid_on_linux_vm,
    start_and_fetch_processid_on_windows_vm,
    vm_instance_from_template,
)

LOGGER = logging.getLogger(__name__)


# CentOS
@pytest.fixture(scope="class")
def matrix_centos_os_golden_image_data_source(admin_client, golden_images_namespace, centos_os_matrix__class__):
    yield from get_matrix_os_golden_image_data_source(
        admin_client=admin_client, golden_images_namespace=golden_images_namespace, os_matrix=centos_os_matrix__class__
    )


@pytest.fixture(scope="class")
def matrix_centos_os_vm_from_template(
    unprivileged_client,
    namespace,
    centos_os_matrix__class__,
    matrix_centos_os_golden_image_data_source,
):
    return matrix_os_vm_from_template(
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        os_matrix=centos_os_matrix__class__,
        data_source_object=matrix_centos_os_golden_image_data_source,
        data_volume_template=get_data_volume_template_dict_with_default_storage_class(
            data_source=matrix_centos_os_golden_image_data_source
        ),
    )


# Fedora
@pytest.fixture(scope="class")
def matrix_fedora_os_golden_image_data_source(admin_client, golden_images_namespace, fedora_os_matrix__class__):
    yield from get_matrix_os_golden_image_data_source(
        admin_client=admin_client, golden_images_namespace=golden_images_namespace, os_matrix=fedora_os_matrix__class__
    )


@pytest.fixture(scope="class")
def matrix_fedora_os_vm_from_template(
    request,
    unprivileged_client,
    namespace,
    fedora_os_matrix__class__,
    matrix_fedora_os_golden_image_data_source,
):
    return matrix_os_vm_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        os_matrix=fedora_os_matrix__class__,
        data_source_object=matrix_fedora_os_golden_image_data_source,
        data_volume_template=get_data_volume_template_dict_with_default_storage_class(
            data_source=matrix_fedora_os_golden_image_data_source
        ),
    )


# RHEL
@pytest.fixture(scope="class")
def matrix_rhel_os_golden_image_data_source(admin_client, golden_images_namespace, rhel_os_matrix__class__):
    yield from get_matrix_os_golden_image_data_source(
        admin_client=admin_client, golden_images_namespace=golden_images_namespace, os_matrix=rhel_os_matrix__class__
    )


@pytest.fixture(scope="class")
def matrix_rhel_os_vm_from_template(
    unprivileged_client,
    namespace,
    rhel_os_matrix__class__,
    matrix_rhel_os_golden_image_data_source,
):
    return matrix_os_vm_from_template(
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        os_matrix=rhel_os_matrix__class__,
        data_source_object=matrix_rhel_os_golden_image_data_source,
        data_volume_template=get_data_volume_template_dict_with_default_storage_class(
            data_source=matrix_rhel_os_golden_image_data_source
        ),
    )


# Windows
@pytest.fixture(scope="class")
def matrix_windows_os_golden_image_data_source(admin_client, golden_images_namespace, windows_os_matrix__class__):
    yield from get_matrix_os_golden_image_data_source(
        admin_client=admin_client, golden_images_namespace=golden_images_namespace, os_matrix=windows_os_matrix__class__
    )


@pytest.fixture(scope="class")
def matrix_windows_os_vm_from_template(
    unprivileged_client,
    namespace,
    windows_os_matrix__class__,
    matrix_windows_os_golden_image_data_source,
):
    return matrix_os_vm_from_template(
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        os_matrix=windows_os_matrix__class__,
        data_source_object=matrix_windows_os_golden_image_data_source,
        data_volume_template=get_data_volume_template_dict_with_default_storage_class(
            data_source=matrix_windows_os_golden_image_data_source
        ),
    )


# Tablet
@pytest.fixture()
def tablet_device_vm(
    request,
    unprivileged_client,
    namespace,
    golden_image_data_volume_template_for_test_scope_class,
    cpu_for_migration,
):
    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_volume_template=golden_image_data_volume_template_for_test_scope_class,
        vm_cpu_model=cpu_for_migration if request.param.get("set_vm_common_cpu") else None,
    ) as vm:
        yield vm


@pytest.fixture()
def xfail_rhel_with_old_guest_agent(matrix_rhel_os_vm_from_template):
    xfail_old_guest_agent_version(vm=matrix_rhel_os_vm_from_template, ga_version="4.2.0")


@pytest.fixture()
def xfail_on_rhel_version_below_rhel9(rhel_os_matrix__class__):
    os_ver_str = rhel_os_matrix__class__[[*rhel_os_matrix__class__][0]]["os_version"]
    if version.parse(os_ver_str) < version.parse("9"):
        pytest.xfail(reason="EFI is not enabled by default on RHEL8 and older")


@pytest.fixture(scope="class")
def ping_process_in_centos_os(matrix_centos_os_vm_from_template):
    return start_and_fetch_processid_on_linux_vm(
        vm=matrix_centos_os_vm_from_template, process_name="ping", args="localhost"
    )


@pytest.fixture(scope="class")
def ping_process_in_fedora_os(matrix_fedora_os_vm_from_template):
    return start_and_fetch_processid_on_linux_vm(
        vm=matrix_fedora_os_vm_from_template, process_name="ping", args="localhost"
    )


@pytest.fixture(scope="class")
def regedit_process_in_windows_os(matrix_windows_os_vm_from_template):
    return start_and_fetch_processid_on_windows_vm(
        vm=matrix_windows_os_vm_from_template, process_name=REGEDIT_PROC_NAME
    )

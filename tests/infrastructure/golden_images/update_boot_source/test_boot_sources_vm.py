import logging

import pytest
from ocp_resources.data_source import DataSource

from tests.infrastructure.golden_images.utils import assert_os_version_mismatch_in_vm
from utilities.constants import TIMEOUT_5SEC
from utilities.infra import validate_os_info_vmi_vs_linux_os
from utilities.storage import data_volume_template_with_source_ref_dict
from utilities.virt import VirtualMachineForTests, running_vm

LOGGER = logging.getLogger(__name__)


@pytest.fixture()
def boot_source_preference_from_data_source_dict(
    request, data_source_from_data_import_cron, data_import_cron_matrix__function__
):
    preference_name = data_import_cron_matrix__function__[[*data_import_cron_matrix__function__][0]]["preference"]
    if "fedora" in data_source_from_data_import_cron.name:
        preference_name = f"fedora{request.getfixturevalue('latest_fedora_release_version')}"
    return preference_name


@pytest.fixture()
def data_source_from_data_import_cron(
    golden_images_namespace,
    data_import_cron_matrix__function__,
):
    data_source = DataSource(name=[*data_import_cron_matrix__function__][0], namespace=golden_images_namespace.name)
    data_source.wait_for_condition(
        condition=data_source.Condition.READY, status=data_source.Condition.Status.TRUE, timeout=TIMEOUT_5SEC
    )
    return data_source


@pytest.fixture()
def auto_update_boot_source_instance_type_vm(
    unprivileged_client,
    namespace,
    data_source_from_data_import_cron,
):
    LOGGER.info(f"Create a VM using {data_source_from_data_import_cron.name} dataSource")
    with VirtualMachineForTests(
        client=unprivileged_client,
        name=f"{data_source_from_data_import_cron.name}-data-source-vm",
        namespace=namespace.name,
        vm_instance_type_infer=True,
        vm_preference_infer=True,
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=data_source_from_data_import_cron,
        ),
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.mark.polarion("CNV-11774")
@pytest.mark.s390x
def test_instance_type_vm_from_auto_update_boot_source(
    auto_update_boot_source_instance_type_vm,
    boot_source_preference_from_data_source_dict,
):
    LOGGER.info(f"Verify {auto_update_boot_source_instance_type_vm.name} OS version and virtctl info")
    assert_os_version_mismatch_in_vm(
        vm=auto_update_boot_source_instance_type_vm,
        expected_os=boot_source_preference_from_data_source_dict,
    )
    validate_os_info_vmi_vs_linux_os(vm=auto_update_boot_source_instance_type_vm)

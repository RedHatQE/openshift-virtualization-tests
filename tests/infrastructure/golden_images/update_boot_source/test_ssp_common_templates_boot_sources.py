import logging

import pytest
from ocp_resources.data_source import DataSource
from ocp_resources.datavolume import DataVolume
from pytest_testconfig import py_config
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.infrastructure.golden_images.update_boot_source.utils import get_all_dic_volume_names, template_labels
from tests.infrastructure.golden_images.utils import (
    assert_missing_golden_image_pvc,
    assert_os_version_mismatch_in_vm,
)
from utilities.artifactory import (
    cleanup_artifactory_secret_and_config_map,
    get_artifactory_config_map,
    get_artifactory_secret,
)
from utilities.constants import OS_FLAVOR_FEDORA, RHEL9_STR, TIMEOUT_5MIN, TIMEOUT_5SEC, Images
from utilities.infra import (
    validate_os_info_vmi_vs_linux_os,
)
from utilities.virt import VirtualMachineForTestsFromTemplate, running_vm

LOGGER = logging.getLogger(__name__)


@pytest.fixture()
def boot_source_os_from_data_source_dict(auto_update_data_source_matrix__function__):
    return auto_update_data_source_matrix__function__[[*auto_update_data_source_matrix__function__][0]]["template_os"]


@pytest.fixture()
def matrix_data_source(unprivileged_client, auto_update_data_source_matrix__function__, golden_images_namespace):
    return DataSource(
        client=unprivileged_client,
        name=[*auto_update_data_source_matrix__function__][0],
        namespace=golden_images_namespace.name,
    )


@pytest.fixture()
def existing_data_source_volume(
    admin_client,
    golden_images_namespace,
    matrix_data_source,
):
    existing_volume_names = get_all_dic_volume_names(
        client=admin_client,
        namespace=golden_images_namespace.name,
    )

    source = matrix_data_source.source

    assert any(source.name in name for name in existing_volume_names), (
        f"DataSource source {source.kind} {source.name} is missing"
    )

    return matrix_data_source


@pytest.fixture()
def auto_update_boot_source_vm(
    unprivileged_client,
    namespace,
    existing_data_source_volume,
    boot_source_os_from_data_source_dict,
):
    LOGGER.info(f"Create a VM using {existing_data_source_volume.name} dataSource")
    with VirtualMachineForTestsFromTemplate(
        name=f"{existing_data_source_volume.name}-vm",
        namespace=namespace.name,
        client=unprivileged_client,
        labels=template_labels(os=boot_source_os_from_data_source_dict),
        data_source=existing_data_source_volume,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture()
def vm_without_boot_source(unprivileged_client, namespace, rhel9_data_source_scope_session):
    with VirtualMachineForTestsFromTemplate(
        name=f"{rhel9_data_source_scope_session.name}-vm",
        namespace=namespace.name,
        client=unprivileged_client,
        labels=template_labels(os="rhel9.0"),
        data_source=rhel9_data_source_scope_session,
        non_existing_pvc=True,
    ) as vm:
        vm.start()
        assert_missing_golden_image_pvc(vm=vm)
        yield vm


@pytest.fixture()
def opted_out_rhel9_data_source(rhel9_data_source_scope_session):
    LOGGER.info(f"Wait for DataSource {rhel9_data_source_scope_session.name} to opt out")
    try:
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_5MIN,
            sleep=TIMEOUT_5SEC,
            func=lambda: rhel9_data_source_scope_session.source.name == RHEL9_STR,
        ):
            if sample:
                return
    except TimeoutExpiredError:
        LOGGER.error(f"{rhel9_data_source_scope_session.name} DataSource source was not updated.")
        raise


@pytest.fixture()
def rhel9_dv(admin_client, golden_images_namespace, rhel9_data_source_scope_session, rhel9_http_image_url):
    artifactory_secret = get_artifactory_secret(namespace=golden_images_namespace.name)
    artifactory_config_map = get_artifactory_config_map(namespace=golden_images_namespace.name)
    with DataVolume(
        client=admin_client,
        name=rhel9_data_source_scope_session.source.name,
        namespace=golden_images_namespace.name,
        url=rhel9_http_image_url,
        secret=artifactory_secret,
        cert_configmap=artifactory_config_map.name,
        source="http",
        size=Images.Rhel.DEFAULT_DV_SIZE,
        storage_class=py_config["default_storage_class"],
        bind_immediate_annotation=True,
        api_name="storage",
    ) as dv:
        dv.wait_for_dv_success()
        yield dv
    cleanup_artifactory_secret_and_config_map(
        artifactory_secret=artifactory_secret, artifactory_config_map=artifactory_config_map
    )


@pytest.mark.polarion("CNV-7586")
def test_vm_from_auto_update_boot_source(
    auto_update_boot_source_vm,
    boot_source_os_from_data_source_dict,
    latest_fedora_release_version,
):
    LOGGER.info(f"Verify {auto_update_boot_source_vm.name} OS version and virtctl info")
    if OS_FLAVOR_FEDORA in boot_source_os_from_data_source_dict and latest_fedora_release_version:
        boot_source_os_from_data_source_dict = f"fedora{latest_fedora_release_version}"
    assert_os_version_mismatch_in_vm(
        vm=auto_update_boot_source_vm,
        expected_os=boot_source_os_from_data_source_dict,
    )
    validate_os_info_vmi_vs_linux_os(vm=auto_update_boot_source_vm)


@pytest.mark.polarion("CNV-7565")
@pytest.mark.s390x
def test_common_templates_boot_source_reference(base_templates):
    source_ref_str = "sourceRef"
    LOGGER.info(f"Verify all common templates use {source_ref_str} in dataVolumeTemplates")
    failed_templates = [
        template.name
        for template in base_templates
        if not template.instance.objects[0].spec.dataVolumeTemplates[0].spec.get(source_ref_str)
    ]
    assert not failed_templates, f"Some templates do not use {source_ref_str}, templates: {failed_templates}"


@pytest.mark.polarion("CNV-7535")
def test_vm_with_uploaded_golden_image_opt_out(
    admin_client,
    golden_images_namespace,
    disabled_common_boot_image_import_hco_spec_scope_function,
    opted_out_rhel9_data_source,
    vm_without_boot_source,
    rhel9_dv,
):
    LOGGER.info(f"Test VM with manually uploaded {rhel9_dv.name} golden image DV")
    running_vm(vm=vm_without_boot_source)

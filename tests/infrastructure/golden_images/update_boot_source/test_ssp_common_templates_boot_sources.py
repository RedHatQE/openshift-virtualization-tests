import logging
import re

import pytest
from ocp_resources.data_source import DataSource
from ocp_resources.datavolume import DataVolume
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from pytest_testconfig import py_config
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.infrastructure.golden_images.update_boot_source.utils import (
    template_labels,
)
from tests.infrastructure.golden_images.utils import (
    assert_missing_golden_image_pvc,
)
from utilities.constants import OS_FLAVOR_RHEL, TIMEOUT_5MIN, TIMEOUT_5SEC, Images
from utilities.infra import (
    cleanup_artifactory_secret_and_config_map,
    get_artifactory_config_map,
    get_artifactory_secret,
    validate_os_info_vmi_vs_linux_os,
)
from utilities.storage import data_volume_template_with_source_ref_dict
from utilities.virt import VirtualMachineForTests, VirtualMachineForTestsFromTemplate, running_vm

LOGGER = logging.getLogger(__name__)
RHEL9_NAME = "rhel9"


def assert_os_version_mismatch_in_vm(vm, latest_fedora_release_version):
    vm_os = vm.ssh_exec.os.release_str.lower()
    expected_os_params = re.match(
        r"(?P<os_name>[a-z]+)(?:\.stream|\.|$)(?P<os_ver>[0-9]*)", vm.instance.spec.preference.name
    ).groupdict()
    expected_name_in_vm_os = (
        "red hat" if expected_os_params["os_name"] == OS_FLAVOR_RHEL else expected_os_params["os_name"]
    )
    expected_os_params["os_ver"] = expected_os_params["os_ver"] or latest_fedora_release_version
    assert re.match(rf"{expected_name_in_vm_os}.*{expected_os_params['os_ver']}.*", vm_os), (
        f"Wrong VM OS, expected: {expected_name_in_vm_os}, actual: {vm_os}"
    )


@pytest.fixture()
def matrix_data_source(auto_update_data_source_matrix__function__, golden_images_namespace):
    return DataSource(
        name=[*auto_update_data_source_matrix__function__][0],
        namespace=golden_images_namespace.name,
    )


@pytest.fixture()
def rhel9_data_source(golden_images_namespace):
    return DataSource(
        name=RHEL9_NAME,
        namespace=golden_images_namespace.name,
    )


@pytest.fixture()
def existing_data_source_volume(
    golden_images_persistent_volume_claims_scope_function,
    golden_images_volume_snapshot_scope_function,
    matrix_data_source,
):
    source = matrix_data_source.source
    if source.kind == PersistentVolumeClaim.kind:
        cluster_volumes = golden_images_persistent_volume_claims_scope_function
    else:
        cluster_volumes = golden_images_volume_snapshot_scope_function
    assert any([source.name in volume.name for volume in cluster_volumes]), (
        f"DataSource source {source.kind} {source.name} is missing"
    )
    return matrix_data_source


@pytest.fixture()
def auto_update_boot_source_vm(
    unprivileged_client,
    namespace,
    existing_data_source_volume,
):
    LOGGER.info(f"Create a VM using {existing_data_source_volume.name} dataSource")
    with VirtualMachineForTests(
        client=unprivileged_client,
        name=f"{existing_data_source_volume.name}-data-source-vm",
        namespace=namespace.name,
        vm_instance_type_infer=True,
        vm_preference_infer=True,
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=existing_data_source_volume,
        ),
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture()
def vm_without_boot_source(unprivileged_client, namespace, rhel9_data_source):
    with VirtualMachineForTestsFromTemplate(
        name=f"{rhel9_data_source.name}-vm",
        namespace=namespace.name,
        client=unprivileged_client,
        labels=template_labels(os="rhel9.0"),
        data_source=rhel9_data_source,
        non_existing_pvc=True,
    ) as vm:
        vm.start()
        assert_missing_golden_image_pvc(vm=vm)
        yield vm


@pytest.fixture()
def opted_out_rhel9_data_source(rhel9_data_source):
    LOGGER.info(f"Wait for DataSource {rhel9_data_source.name} to opt out")
    try:
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_5MIN,
            sleep=TIMEOUT_5SEC,
            func=lambda: rhel9_data_source.source.name == RHEL9_NAME,
        ):
            if sample:
                return
    except TimeoutExpiredError:
        LOGGER.error(f"{rhel9_data_source.name} DataSource source was not updated.")
        raise


@pytest.fixture()
def rhel9_dv(admin_client, golden_images_namespace, rhel9_data_source, rhel9_http_image_url):
    artifactory_secret = get_artifactory_secret(namespace=golden_images_namespace.name)
    artifactory_config_map = get_artifactory_config_map(namespace=golden_images_namespace.name)
    with DataVolume(
        client=admin_client,
        name=rhel9_data_source.source.name,
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
    latest_fedora_release_version,
):
    LOGGER.info(f"Verify {auto_update_boot_source_vm.name} OS version and virtctl info")
    assert_os_version_mismatch_in_vm(
        vm=auto_update_boot_source_vm,
        latest_fedora_release_version=latest_fedora_release_version,
    )
    validate_os_info_vmi_vs_linux_os(vm=auto_update_boot_source_vm)


@pytest.mark.polarion("CNV-7565")
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
    disabled_common_boot_image_import_feature_gate_scope_function,
    opted_out_rhel9_data_source,
    vm_without_boot_source,
    rhel9_dv,
):
    LOGGER.info(f"Test VM with manually uploaded {rhel9_dv.name} golden image DV")
    running_vm(vm=vm_without_boot_source)

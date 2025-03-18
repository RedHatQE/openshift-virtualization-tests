import logging
from copy import deepcopy

import pytest
from benedict import benedict
from kubernetes.dynamic.exceptions import ResourceNotFoundError
from ocp_resources.data_import_cron import DataImportCron
from ocp_resources.data_source import DataSource
from ocp_resources.datavolume import DataVolume
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_resources.storage_profile import StorageProfile
from ocp_resources.volume_snapshot import VolumeSnapshot

from tests.os_params import RHEL_LATEST_LABELS
from utilities.constants import DATA_IMPORT_CRON_ENABLE, TIMEOUT_3MIN
from utilities.hco import (
    disable_common_boot_image_import_hco_spec,
    update_hco_templates_spec,
    wait_for_auto_boot_config_stabilization,
)
from utilities.ssp import wait_for_deleted_data_import_crons
from utilities.storage import (
    data_volume_dict_modify_to_source_ref,
    verify_dv_and_pvc_does_not_exist,
    wait_for_succeeded_dv,
    wait_for_volume_snapshot_ready_to_use,
)
from utilities.virt import running_vm, vm_instance_from_template

LOGGER = logging.getLogger(__name__)

pytestmark = pytest.mark.usefixtures(
    "skip_if_no_storage_profile_with_snapshot_import_cron_format",
)
RHEL9_STR = "rhel9"


def get_rhel9_data_import_cron_template(common_templates):
    for template in common_templates:
        if template["metadata"]["name"].startswith(RHEL9_STR):
            updated_template = benedict(deepcopy(template), keypath_separator="->")
            del updated_template["status"]
            return updated_template
    pytest.fail(f"{RHEL9_STR} system boot source template should exist on HCO")


@pytest.fixture(scope="module")
def skip_if_no_storage_profile_with_snapshot_import_cron_format(
    snapshot_storage_class_name_scope_module,
):
    sc_storage_profile = StorageProfile(name=snapshot_storage_class_name_scope_module)
    if not sc_storage_profile.instance.status.get("dataImportCronSourceFormat") == "snapshot":
        pytest.skip(f"Cant create cached snapshot for {snapshot_storage_class_name_scope_module} storageclass")


@pytest.fixture(scope="module")
def updated_templates_rhel9_data_import_cron(
    admin_client,
    hco_namespace,
    original_rhel9_boot_source_pvc,
    snapshot_storage_class_name_scope_module,
    hyperconverged_resource_scope_module,
    hyperconverged_status_templates_scope_module,
    golden_images_namespace,
    rhel9_boot_source_name,
):
    """
    Changing rhel9 template in HCO to a snapshot capable storageclass
    """
    updated_template = get_rhel9_data_import_cron_template(
        common_templates=hyperconverged_status_templates_scope_module
    )
    updated_template["spec"]["template"]["spec"]["storage"].update({
        "storageClassName": snapshot_storage_class_name_scope_module
    })
    yield from update_hco_templates_spec(
        admin_client=admin_client,
        hco_namespace=hco_namespace,
        hyperconverged_resource=hyperconverged_resource_scope_module,
        updated_template=updated_template,
    )
    if original_rhel9_boot_source_pvc:
        LOGGER.info(f"Deleting {rhel9_boot_source_name} VolumeSnapshot and wait for the PVC to recreate")
        VolumeSnapshot(
            name=rhel9_boot_source_name,
            namespace=golden_images_namespace.name,
        ).clean_up()
        wait_for_succeeded_dv(namespace=golden_images_namespace.name, dv_name=rhel9_boot_source_name)
        wait_for_auto_boot_config_stabilization(admin_client=admin_client, hco_namespace=hco_namespace)


@pytest.fixture(scope="module")
def rhel9_data_import_cron(admin_client, golden_images_namespace, updated_templates_rhel9_data_import_cron):
    data_import_cron = DataImportCron(
        name=updated_templates_rhel9_data_import_cron["metadata"]["name"],
        namespace=golden_images_namespace.name,
        client=admin_client,
    )
    if data_import_cron.exists:
        return data_import_cron
    raise ResourceNotFoundError(f"{RHEL9_STR} DataImportCron should in the cluster")


@pytest.fixture(scope="module")
def original_rhel9_boot_source_pvc(rhel9_data_source_scope_module):
    return isinstance(rhel9_data_source_scope_module.source, PersistentVolumeClaim)


@pytest.fixture(scope="module")
def updated_rhel9_boot_source(
    original_rhel9_boot_source_pvc,
    golden_images_namespace,
    rhel9_boot_source_name,
    rhel9_data_import_cron,
):
    if original_rhel9_boot_source_pvc:
        # deleting the dv to create the cached snapshot
        DataVolume(
            name=rhel9_boot_source_name,
            namespace=golden_images_namespace.name,
        ).clean_up()


@pytest.fixture(scope="module")
def rhel9_data_source_scope_module(golden_images_namespace):
    data_source = DataSource(
        name=RHEL9_STR,
        namespace=golden_images_namespace.name,
    )
    if data_source.exists:
        return data_source
    raise ResourceNotFoundError(f"{RHEL9_STR} DataImportCron should exist in the cluster")


@pytest.fixture(scope="module")
def rhel9_boot_source_name(rhel9_data_source_scope_module):
    return rhel9_data_source_scope_module.source.name


@pytest.fixture(scope="module")
def rhel9_cached_snapshot(
    rhel9_boot_source_name,
    golden_images_namespace,
    updated_rhel9_boot_source,
):
    # wait for the snapshot to be created
    rhel9_volume_snapshot = wait_for_volume_snapshot_ready_to_use(
        namespace=golden_images_namespace.name, name=rhel9_boot_source_name
    )
    verify_dv_and_pvc_does_not_exist(name=rhel9_boot_source_name, namespace=golden_images_namespace.name)
    yield rhel9_volume_snapshot


@pytest.fixture()
def disabled_common_boot_image_import_hco_spec_rhel9_scope_function(
    admin_client,
    hyperconverged_resource_scope_function,
    golden_images_namespace,
    rhel9_data_import_cron,
):
    yield from disable_common_boot_image_import_hco_spec(
        admin_client=admin_client,
        hco_resource=hyperconverged_resource_scope_function,
        golden_images_namespace=golden_images_namespace,
        golden_images_data_import_crons=[rhel9_data_import_cron],
    )


@pytest.fixture()
def disabled_data_import_cron_annotation_rhel9(
    admin_client,
    hco_namespace,
    rhel9_cached_snapshot,
    rhel9_data_source_scope_module,
    hyperconverged_status_templates_scope_function,
    hyperconverged_resource_scope_function,
):
    updated_template = get_rhel9_data_import_cron_template(
        common_templates=hyperconverged_status_templates_scope_function
    )
    updated_template[DATA_IMPORT_CRON_ENABLE] = "false"
    yield from update_hco_templates_spec(
        admin_client=admin_client,
        hco_namespace=hco_namespace,
        hyperconverged_resource=hyperconverged_resource_scope_function,
        updated_template=updated_template,
    )
    rhel9_data_source_scope_module.wait_for_condition(
        condition=rhel9_data_source_scope_module.Condition.READY,
        status=rhel9_data_source_scope_module.Condition.Status.TRUE,
        timeout=TIMEOUT_3MIN,
    )


@pytest.fixture()
def rhel9_golden_image_vm(
    request,
    snapshot_storage_class_name_scope_module,
    rhel9_cached_snapshot,
    rhel9_data_source_scope_module,
    unprivileged_client,
    namespace,
):
    dv = DataVolume(
        name=f"{RHEL9_STR}-test-vm",
        namespace=namespace.name,
        size=rhel9_cached_snapshot.instance.status.get("restoreSize"),
        storage_class=snapshot_storage_class_name_scope_module,
        api_name="storage",
    )
    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_volume_template=data_volume_dict_modify_to_source_ref(
            dv=dv,
            data_source=rhel9_data_source_scope_module,
        ),
    ) as vm:
        yield vm


@pytest.mark.polarion("CNV-10721")
def test_automatic_update_for_system_cached_snapshot(
    rhel9_cached_snapshot,
    disabled_common_boot_image_import_hco_spec_rhel9_scope_function,
    rhel9_data_source_scope_module,
):
    rhel9_data_source_scope_module.wait_for_condition(
        condition=rhel9_data_source_scope_module.Condition.READY,
        status=rhel9_data_source_scope_module.Condition.Status.FALSE,
        timeout=TIMEOUT_3MIN,
    )


@pytest.mark.polarion("CNV-10722")
def test_disable_automatic_update_using_annotation(
    disabled_data_import_cron_annotation_rhel9,
    rhel9_data_import_cron,
    rhel9_data_source_scope_module,
):
    wait_for_deleted_data_import_crons(data_import_crons=[rhel9_data_import_cron])
    rhel9_data_source_scope_module.wait_for_condition(
        condition=rhel9_data_source_scope_module.Condition.READY,
        status=rhel9_data_source_scope_module.Condition.Status.FALSE,
        timeout=TIMEOUT_3MIN,
    )


@pytest.mark.parametrize(
    "rhel9_golden_image_vm",
    [
        pytest.param(
            {
                "vm_name": "vm-10722",
                "template_labels": RHEL_LATEST_LABELS,
            },
            marks=pytest.mark.polarion("CNV-10749"),
        ),
    ],
    indirect=True,
)
def test_unprivileged_user_vm_snapshot_datasource(rhel9_golden_image_vm):
    running_vm(vm=rhel9_golden_image_vm)

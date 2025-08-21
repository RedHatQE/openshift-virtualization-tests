import logging
import re

import pytest
from kubernetes.dynamic.exceptions import UnprocessibleEntityError
from ocp_resources.data_import_cron import DataImportCron
from ocp_resources.data_source import DataSource
from ocp_resources.datavolume import DataVolume
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_resources.resource import ResourceEditor
from pytest_testconfig import py_config
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.infrastructure.golden_images.constants import (
    CUSTOM_DATA_IMPORT_CRON_NAME,
    CUSTOM_DATA_SOURCE_NAME,
    DEFAULT_FEDORA_REGISTRY_URL,
)
from tests.infrastructure.golden_images.update_boot_source.utils import get_all_dic_volume_names
from utilities.constants import (
    BIND_IMMEDIATE_ANNOTATION,
    QUARANTINED,
    TIMEOUT_1MIN,
    TIMEOUT_2MIN,
    TIMEOUT_5MIN,
    TIMEOUT_10MIN,
    Images,
)
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.infra import create_ns
from utilities.ssp import (
    get_data_import_crons,
    matrix_auto_boot_data_import_cron_prefixes,
    wait_for_condition_message_value,
    wait_for_deleted_data_import_crons,
)
from utilities.storage import DATA_IMPORT_CRON_SUFFIX, data_volume_template_with_source_ref_dict
from utilities.virt import VirtualMachineForTests, running_vm

LOGGER = logging.getLogger(__name__)


pytestmark = pytest.mark.post_upgrade


def wait_for_existing_auto_update_data_import_crons(admin_client, namespace):
    def _get_missing_data_import_crons(_client, _namespace, _auto_boot_data_import_cron_prefixes):
        data_import_crons = get_data_import_crons(admin_client=_client, namespace=_namespace)
        return [
            data_import_cron_prefix
            for data_import_cron_prefix in _auto_boot_data_import_cron_prefixes
            if data_import_cron_prefix
            not in [
                re.sub(DATA_IMPORT_CRON_SUFFIX, "", data_import_cron.name) for data_import_cron in data_import_crons
            ]
        ]

    sample = None
    auto_boot_data_import_cron_prefixes = matrix_auto_boot_data_import_cron_prefixes()
    try:
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_2MIN,
            sleep=5,
            func=_get_missing_data_import_crons,
            _client=admin_client,
            _namespace=namespace,
            _auto_boot_data_import_cron_prefixes=auto_boot_data_import_cron_prefixes,
        ):
            if not sample:
                return
    except TimeoutExpiredError:
        LOGGER.error(f"Some dataImportCron resources are missing: {sample}")
        raise


def wait_for_created_volume_from_data_import_cron(custom_data_source):
    try:
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_5MIN,
            sleep=5,
            func=lambda: custom_data_source.source.exists,
        ):
            if sample:
                return
    except TimeoutExpiredError:
        LOGGER.error(
            f"Volume was not created under {custom_data_source.namespace} namespace, "
            f"DataSource conditions: {custom_data_source.instance.get('status', {}).get('conditions')}"
        )
        raise


def create_vm_with_infer_from_volume(
    client,
    namespace,
    data_source_for_test,
):
    with VirtualMachineForTests(
        name="vm-with-infer-from-volume",
        namespace=namespace.name,
        client=client,
        vm_instance_type_infer=True,
        vm_preference_infer=True,
        data_volume_template=data_volume_template_with_source_ref_dict(data_source=data_source_for_test),
    ) as vm:
        return vm


@pytest.fixture()
def failed_volume_creation(custom_data_import_cron_scope_function):
    LOGGER.info("Verify volume was not created.")
    wait_for_condition_message_value(
        resource=custom_data_import_cron_scope_function,
        expected_message="No current import",
    )


@pytest.fixture()
def updated_data_import_cron(
    updated_hco_with_custom_data_import_cron_scope_function,
    hyperconverged_resource_scope_function,
):
    updated_hco_with_custom_data_import_cron_scope_function["spec"]["template"]["spec"]["source"]["registry"]["url"] = (
        DEFAULT_FEDORA_REGISTRY_URL
    )
    ResourceEditor(
        patches={
            hyperconverged_resource_scope_function: {
                "spec": {"dataImportCronTemplates": [updated_hco_with_custom_data_import_cron_scope_function]}
            }
        }
    ).update()


@pytest.fixture()
def reconciled_custom_data_source(custom_data_source_scope_function):
    try:
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_10MIN,
            sleep=5,
            func=lambda: custom_data_source_scope_function.source.exists,
        ):
            if sample:
                return
    except TimeoutExpiredError:
        LOGGER.error(
            "DataSource was not reconciled to reference a PVC or VolumeSnapshot, "
            f"DataSource spec: {custom_data_source_scope_function.instance.get('spec')}"
        )
        raise


@pytest.fixture()
def vm_from_custom_data_import_cron(custom_data_source_scope_function, namespace, unprivileged_client):
    with VirtualMachineForTests(
        name=f"{custom_data_source_scope_function.name}-vm",
        namespace=namespace.name,
        client=unprivileged_client,
        memory_guest=Images.Fedora.DEFAULT_MEMORY_SIZE,
        data_volume_template=data_volume_template_with_source_ref_dict(data_source=custom_data_source_scope_function),
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture()
def data_import_cron_namespace(admin_client, unprivileged_client):
    yield from create_ns(
        admin_client=admin_client,
        unprivileged_client=unprivileged_client,
        name="data-import-cron-using-default-sc",
    )


@pytest.fixture()
def created_persistent_volume_claim(unprivileged_client, data_import_cron_namespace):
    def _get_pvc():
        return list(
            PersistentVolumeClaim.get(
                dyn_client=unprivileged_client,
                namespace=data_import_cron_namespace.name,
            )
        )[0]

    try:
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_1MIN,
            sleep=1,
            func=_get_pvc,
            exceptions_dict={IndexError: []},
        ):
            if sample:
                created_dv = DataVolume(name=sample.name, namespace=sample.namespace)
                created_dv.wait_for_dv_success()
                yield sample
                created_dv.clean_up()
                break
    except TimeoutExpiredError:
        LOGGER.error(f"No PVCs were created in {data_import_cron_namespace.name}")
        raise


@pytest.fixture(scope="class")
def golden_images_data_import_cron_spec(
    golden_images_data_import_crons_scope_class,
):
    assert golden_images_data_import_crons_scope_class, (
        f"No data import cron job found in {py_config['golden_images_namespace']}"
    )
    return golden_images_data_import_crons_scope_class[0].instance.spec


@pytest.fixture()
def created_data_import_cron(
    unprivileged_client,
    data_import_cron_namespace,
    golden_images_data_import_cron_spec,
):
    cron_template_spec = golden_images_data_import_cron_spec.template.spec
    with DataImportCron(
        name="data-import-cron-for-test",
        namespace=data_import_cron_namespace.name,
        managed_data_source=golden_images_data_import_cron_spec.managedDataSource,
        schedule=golden_images_data_import_cron_spec.schedule,
        annotations=BIND_IMMEDIATE_ANNOTATION,
        template={
            "spec": {
                "source": {
                    "registry": {
                        "url": cron_template_spec.source.registry.url,
                        "pullMethod": "node",
                    }
                },
                "storage": {
                    "resources": {"requests": {"storage": cron_template_spec.storage.resources.requests.storage}}
                },
            }
        },
    ) as data_import_cron:
        yield data_import_cron


@pytest.fixture
def existing_dic_volumes_before_disable(admin_client, golden_images_namespace):
    return get_all_dic_volume_names(client=admin_client, namespace=golden_images_namespace.name)


@pytest.mark.polarion("CNV-7531")
@pytest.mark.s390x
def test_opt_in_data_import_cron_creation(
    admin_client,
    golden_images_namespace,
):
    LOGGER.info("Verify all DataImportCrons are created when opted in")
    wait_for_existing_auto_update_data_import_crons(admin_client=admin_client, namespace=golden_images_namespace)


@pytest.mark.parametrize(
    "updated_hco_with_custom_data_import_cron_scope_function",
    [
        pytest.param(
            {
                "data_import_cron_name": CUSTOM_DATA_IMPORT_CRON_NAME,
                "data_import_cron_source_url": DEFAULT_FEDORA_REGISTRY_URL,
                "managed_data_source_name": CUSTOM_DATA_SOURCE_NAME,
            },
            marks=(pytest.mark.polarion("CNV-7885")),
        ),
    ],
    indirect=True,
)
@pytest.mark.s390x
def test_custom_data_import_cron_via_hco(
    updated_hco_with_custom_data_import_cron_scope_function,
    reconciled_custom_data_source,
    vm_from_custom_data_import_cron,
):
    LOGGER.info(
        "Test VM running using DataSource from custom DataImportCron "
        f"{updated_hco_with_custom_data_import_cron_scope_function['metadata']['name']}"
    )
    running_vm(vm=vm_from_custom_data_import_cron)


@pytest.mark.parametrize(
    "updated_hco_with_custom_data_import_cron_scope_function",
    [
        pytest.param(
            {
                "data_import_cron_name": CUSTOM_DATA_IMPORT_CRON_NAME,
                "data_import_cron_source_url": DEFAULT_FEDORA_REGISTRY_URL,
                "managed_data_source_name": CUSTOM_DATA_SOURCE_NAME,
            },
            marks=(pytest.mark.polarion("CNV-8096")),
        ),
    ],
    indirect=True,
)
@pytest.mark.s390x
def test_opt_out_custom_data_import_cron_via_hco_not_deleted(
    admin_client,
    updated_hco_with_custom_data_import_cron_scope_function,
    disabled_common_boot_image_import_hco_spec_scope_function,
    golden_images_namespace,
):
    LOGGER.info("Test Custom DataImportCron is not deleted after opt-out")
    assert DataImportCron(
        client=admin_client,
        name=CUSTOM_DATA_IMPORT_CRON_NAME,
        namespace=golden_images_namespace.name,
    ).exists, f"Custom DataImportCron {CUSTOM_DATA_IMPORT_CRON_NAME} not found after opt out"


@pytest.mark.s390x
class TestDataImportCronDefaultStorageClass:
    @pytest.mark.polarion("CNV-7594")
    def test_data_import_cron_using_default_storage_class(
        self,
        updated_default_storage_class_scope_function,
        created_data_import_cron,
        created_persistent_volume_claim,
    ):
        LOGGER.info(
            "Test DataImportCron and DV creation when using default storage class "
            f"{updated_default_storage_class_scope_function.name}"
        )
        current_sc = created_persistent_volume_claim.instance.spec.storageClassName
        assert current_sc == updated_default_storage_class_scope_function.name, (
            f"PVC {created_persistent_volume_claim.name} expected storage class: "
            f"{updated_default_storage_class_scope_function.name}, "
            f"current storage class: {created_persistent_volume_claim}"
        )


@pytest.mark.xfail(
    reason=f"{QUARANTINED}: This test still fail in some cases ; tracked in CNV-62615",
    run=False,
)
@pytest.mark.polarion("CNV-7532")
@pytest.mark.s390x
def test_data_import_cron_deletion_on_opt_out(
    admin_client,
    golden_images_namespace,
    existing_dic_volumes_before_disable,
    golden_images_data_import_crons_scope_function,
    disabled_common_boot_image_import_hco_spec_scope_function,
):
    LOGGER.info("Verify DataImportCrons are deleted after opt-out.")
    wait_for_deleted_data_import_crons(data_import_crons=golden_images_data_import_crons_scope_function)
    volumes_after = get_all_dic_volume_names(client=admin_client, namespace=golden_images_namespace.name)
    assert set(existing_dic_volumes_before_disable) == set(volumes_after), (
        "DataImportCron deletion should not affect existing volumes.\n"
        f"Volumes before: {sorted(existing_dic_volumes_before_disable)}\n"
        f"Volumes after: {sorted(volumes_after)}\n"
        f"Added: {sorted(set(volumes_after) - set(existing_dic_volumes_before_disable))}\n"
        f"Removed: {sorted(set(existing_dic_volumes_before_disable) - set(volumes_after))}"
    )


@pytest.mark.polarion("CNV-7569")
@pytest.mark.s390x
def test_data_import_cron_reconciled_after_deletion(
    golden_images_data_import_crons_scope_function,
):
    data_import_cron = golden_images_data_import_crons_scope_function[0]
    LOGGER.info(f"Verify dataImportCron {data_import_cron.name} is reconciled after deletion.")

    data_import_cron_orig_uid = data_import_cron.instance.metadata.uid
    # Not passing 'wait' as creation time is almost instant
    data_import_cron.delete()

    try:
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_5MIN,
            sleep=5,
            func=lambda: data_import_cron.instance.metadata.uid != data_import_cron_orig_uid,
        ):
            if sample:
                return
    except TimeoutExpiredError:
        LOGGER.error("DataImportCron was not reconciled after deletion")
        raise


@pytest.mark.polarion("CNV-8032")
@pytest.mark.s390x
def test_data_import_cron_blocked_update(
    golden_images_data_import_crons_scope_function,
):
    updated_data_import_cron = golden_images_data_import_crons_scope_function[0]
    LOGGER.info(f"Verify dataImportCron {updated_data_import_cron.name} cannot be updated.")
    with pytest.raises(UnprocessibleEntityError, match=r".*Cannot update DataImportCron Spec.*"):
        with ResourceEditorValidateHCOReconcile(
            patches={updated_data_import_cron: {"spec": {"managedDataSource": CUSTOM_DATA_SOURCE_NAME}}},
        ):
            return


@pytest.mark.parametrize(
    "updated_hco_with_custom_data_import_cron_scope_function",
    [
        pytest.param(
            {
                "data_import_cron_name": "dic-non-existing-source",
                "data_import_cron_source_url": "docker://non-existing-url",
                "managed_data_source_name": "non-existing-url-data-source",
            },
            marks=(pytest.mark.polarion("CNV-7575")),
        ),
    ],
    indirect=True,
)
@pytest.mark.s390x
def test_custom_data_import_cron_image_updated_via_hco(
    admin_client,
    updated_hco_with_custom_data_import_cron_scope_function,
    custom_data_source_scope_function,
    failed_volume_creation,
    updated_data_import_cron,
):
    LOGGER.info("Verify custom volume is created after DataImportCron update with a valid registry URL.")
    wait_for_created_volume_from_data_import_cron(custom_data_source=custom_data_source_scope_function)


@pytest.mark.polarion("CNV-7669")
@pytest.mark.s390x
def test_data_import_cron_recreated_after_opt_out_opt_in(
    admin_client,
    golden_images_namespace,
    disabled_common_boot_image_import_hco_spec_scope_function,
    enabled_common_boot_image_import_feature_gate_scope_function,
):
    LOGGER.info("Verify dataImportCron is re-created after opt-out -> opt-in")
    wait_for_existing_auto_update_data_import_crons(admin_client=admin_client, namespace=golden_images_namespace)


@pytest.mark.parametrize(
    "updated_hco_with_custom_data_import_cron_scope_function",
    [
        pytest.param(
            {
                "data_import_cron_name": "data-import-cron-with-invalid-source-url",
                "data_import_cron_source_url": "non-existing-url",
                "managed_data_source_name": "invalid-source-url-data-source",
            },
            marks=(pytest.mark.polarion("CNV-8078")),
        ),
    ],
    indirect=True,
)
@pytest.mark.s390x
def test_data_import_cron_invalid_source_url_failed_creation(
    updated_hco_with_custom_data_import_cron_scope_function,
    ssp_resource_scope_function,
):
    def get_ssp_degraded_condition(_ssp_cr):
        return [
            condition
            for condition in _ssp_cr.instance.status.conditions
            if condition["type"] == ssp_resource_scope_function.Condition.DEGRADED
        ]

    LOGGER.info("verify SSP reports invalid source URL in custom dataImportCron.")
    expected_degradation_message = "Illegal registry source URL scheme"
    sample = None
    try:
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_2MIN,
            sleep=5,
            func=get_ssp_degraded_condition,
            _ssp_cr=ssp_resource_scope_function,
        ):
            if sample and expected_degradation_message in sample[0]["message"]:
                return
    except TimeoutExpiredError:
        LOGGER.error(
            "SSP degraded conditions do not report failed dataImportCron configuration; "
            f"excepted error: {expected_degradation_message}, actual conditions: {sample}"
        )
        raise


@pytest.mark.polarion("CNV-9917")
@pytest.mark.s390x
def test_data_source_instancetype_preference_label(
    unprivileged_client,
    namespace,
    golden_images_namespace,
    golden_images_data_import_crons_scope_function,
):
    failed_data_source_list = []
    for data_source in golden_images_data_import_crons_scope_function:
        data_source_name = data_source.instance.spec.managedDataSource
        try:
            with create_vm_with_infer_from_volume(
                client=unprivileged_client,
                namespace=namespace,
                data_source_for_test=DataSource(name=data_source_name, namespace=golden_images_namespace.name),
            ):
                pass
        except Exception as exp:
            failed_data_source_list.append(data_source_name)
            LOGGER.error(f"VM with data source: {data_source_name} creation failed from unexpected reason: {exp}")
    assert not failed_data_source_list, (
        f"Could not create VMs with the following data sources: {failed_data_source_list}"
    )

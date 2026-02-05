import logging

import pytest
from kubernetes.dynamic.exceptions import UnprocessibleEntityError
from ocp_resources.data_import_cron import DataImportCron
from ocp_resources.data_source import DataSource
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.infrastructure.golden_images.constants import (
    CUSTOM_DATA_IMPORT_CRON_NAME,
    CUSTOM_DATA_SOURCE_NAME,
)
from tests.infrastructure.golden_images.update_boot_source.utils import (
    get_all_dic_volume_names,
    get_image_version,
    wait_for_created_volume_from_data_import_cron,
    wait_for_existing_auto_update_data_import_crons,
)
from utilities.constants import (
    DEFAULT_FEDORA_REGISTRY_URL,
    TIMEOUT_2MIN,
    TIMEOUT_5MIN,
    TIMEOUT_5SEC,
)
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.ssp import (
    wait_for_deleted_data_import_crons,
)
from utilities.storage import data_volume_template_with_source_ref_dict
from utilities.virt import VirtualMachineForTests, running_vm

LOGGER = logging.getLogger(__name__)


pytestmark = pytest.mark.post_upgrade


@pytest.mark.polarion("CNV-12414")
def test_updated_rhel_image(golden_images_data_import_crons_scope_class, latest_rhel_release_versions_dict, subtests):
    for rhel_dic in [dic for dic in golden_images_data_import_crons_scope_class if "rhel" in dic.name.lower()]:
        rhel_instance_dict = rhel_dic.instance
        image_reference_version = get_image_version(
            image=rhel_instance_dict.metadata.annotations.get("cdi.kubevirt.io/storage.import.imageStreamDockerRef")
        )
        with subtests.test(rhel_dic_name=rhel_dic.name, managed_data_source=rhel_instance_dict.spec.managedDataSource):
            managed_data_source = rhel_instance_dict.spec.managedDataSource
            assert managed_data_source, "spec.managedDataSource doesn't exists"
            assert latest_rhel_release_versions_dict[managed_data_source] == image_reference_version


class TestDataImportCronValidation:
    """verify existing DICs behavior"""

    @pytest.mark.polarion("CNV-7531")
    @pytest.mark.s390x
    def test_opt_in_data_import_cron_creation(self, admin_client, golden_images_namespace):
        LOGGER.info("Verify all DataImportCrons are created when opted in")
        wait_for_existing_auto_update_data_import_crons(admin_client=admin_client, namespace=golden_images_namespace)

    @pytest.mark.polarion("CNV-8032")
    @pytest.mark.s390x
    def test_data_import_cron_blocked_update(self, golden_images_data_import_crons_scope_function):
        first_data_import_cron = golden_images_data_import_crons_scope_function[0]
        LOGGER.info(f"Verify dataImportCron {first_data_import_cron.name} cannot be updated.")
        with pytest.raises(UnprocessibleEntityError, match=r".*Cannot update DataImportCron Spec.*"):
            with ResourceEditorValidateHCOReconcile(
                patches={first_data_import_cron: {"spec": {"managedDataSource": CUSTOM_DATA_SOURCE_NAME}}},
            ):
                pytest.fail("Expected UnprocessibleEntityError was not raised")


class TestDataImportCronOptOutOptIn:
    """Tests for DICs opt-out/opt-in."""

    @pytest.mark.polarion("CNV-7532")
    def test_data_import_cron_deletion_on_opt_out(
        self,
        admin_client,
        golden_images_namespace,
        existing_dic_volumes_before_disable,
        golden_images_data_import_crons_scope_function,
        disabled_common_boot_image_import_hco_spec_scope_function,
    ):
        LOGGER.info("Verify DataImportCrons are deleted after opt-out.")
        wait_for_deleted_data_import_crons(data_import_crons=golden_images_data_import_crons_scope_function)
        volumes_after = get_all_dic_volume_names(client=admin_client, namespace=golden_images_namespace.name)
        missing_volumes = set(existing_dic_volumes_before_disable) - set(volumes_after)
        assert not missing_volumes, (
            f"DataImportCron deletion should not affect existing volumes.\n"
            f"Missing volumes: {sorted(missing_volumes)}\n"
            f"Volumes before: {sorted(existing_dic_volumes_before_disable)}\n"
            f"Volumes after: {sorted(volumes_after)}"
        )

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
    def test_opt_out_preserves_custom_dics(
        self,
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

    @pytest.mark.polarion("CNV-7669")
    def test_opt_in_recreates_all_default_dics(
        self,
        admin_client,
        golden_images_namespace,
        disabled_common_boot_image_import_hco_spec_scope_function,
        enabled_common_boot_image_import_feature_gate_scope_function,
    ):
        LOGGER.info("Verify dataImportCron is re-created after opt-out -> opt-in")
        wait_for_existing_auto_update_data_import_crons(admin_client=admin_client, namespace=golden_images_namespace)


class TestDataImportCronReconciliation:
    """Tests for DIC recreation after deletion"""

    @pytest.mark.polarion("CNV-7569")
    @pytest.mark.s390x
    def test_data_import_cron_auto_recreation_after_deletion(self, golden_images_data_import_crons_scope_function):
        data_import_cron = golden_images_data_import_crons_scope_function[0]
        LOGGER.info(f"Verify dataImportCron {data_import_cron.name} is reconciled after deletion.")
        data_import_cron_orig_uid = data_import_cron.instance.metadata.uid
        data_import_cron.delete()

        try:
            for sample in TimeoutSampler(
                wait_timeout=TIMEOUT_5MIN,
                sleep=TIMEOUT_5SEC,
                func=lambda: data_import_cron.instance.metadata.uid != data_import_cron_orig_uid,
            ):
                if sample:
                    return
        except TimeoutExpiredError:
            LOGGER.error("DataImportCron was not reconciled after deletion")
            raise


class TestCustomDataImportCron:
    """Tests for user-defined custom DataImportCrons"""

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
    def test_custom_data_import_cron_creation(
        self,
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
                    "data_import_cron_name": "dic-non-existing-source",
                    "data_import_cron_source_url": "docker://non-existing-url",
                    "managed_data_source_name": "non-existing-url-data-source",
                },
                marks=(pytest.mark.polarion("CNV-7575")),
            ),
        ],
        indirect=True,
    )
    def test_custom_data_import_cron_image_update(
        self,
        admin_client,
        updated_hco_with_custom_data_import_cron_scope_function,
        custom_data_source_scope_function,
        failed_volume_creation,
        updated_data_import_cron,
    ):
        LOGGER.info("Verify custom volume is created after DataImportCron update with a valid registry URL.")
        wait_for_created_volume_from_data_import_cron(custom_data_source=custom_data_source_scope_function)

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
    def test_custom_data_import_cron_invalid_source_validation(
        self,
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
                sleep=TIMEOUT_5SEC,
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


class TestDataSourceVmCreation:
    """verify vm creation for datasources created from SSP data import cron"""

    @pytest.mark.polarion("CNV-9917")
    def test_all_datasources_support_vm_creation(
        self,
        unprivileged_client,
        namespace,
        golden_images_namespace,
        golden_images_data_import_crons_scope_function,
    ):
        failed_data_source_list = []
        for data_source in golden_images_data_import_crons_scope_function:
            data_source_name = data_source.instance.spec.managedDataSource
            try:
                with VirtualMachineForTests(
                    name=f"vm-{data_source_name}",
                    namespace=namespace.name,
                    client=unprivileged_client,
                    vm_instance_type_infer=True,
                    vm_preference_infer=True,
                    data_volume_template=data_volume_template_with_source_ref_dict(
                        data_source=DataSource(name=data_source_name, namespace=golden_images_namespace.name)
                    ),
                ):
                    pass
            except Exception as exp:
                failed_data_source_list.append(data_source_name)
                LOGGER.error(f"VM with data source: {data_source_name} creation failed from unexpected reason: {exp}")
        assert not failed_data_source_list, (
            f"Could not create VMs with the following data sources: {failed_data_source_list}"
        )


class TestDataImportCronDefaultStorageClass:
    """Tests for DataImportCron with different storage classes"""

    @pytest.mark.polarion("CNV-7594")
    def test_data_import_cron_uses_default_storage_class(
        self, updated_default_storage_class_scope_function, created_data_import_cron, created_persistent_volume_claim
    ):
        LOGGER.info(
            "Test DataImportCron and DV creation when using default storage class "
            f"{updated_default_storage_class_scope_function.name}"
        )
        current_sc = created_persistent_volume_claim.instance.spec.storageClassName
        assert current_sc == updated_default_storage_class_scope_function.name, (
            f"PVC {created_persistent_volume_claim.name} expected storage class: "
            f"{updated_default_storage_class_scope_function.name}, "
            f"current storage class: {current_sc}"
        )

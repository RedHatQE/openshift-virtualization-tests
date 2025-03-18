import logging

import pytest
from kubernetes.dynamic.exceptions import NotFoundError
from ocp_resources.cdi import CDI
from ocp_resources.data_import_cron import DataImportCron
from ocp_resources.data_source import DataSource
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_resources.ssp import SSP
from ocp_resources.volume_snapshot import VolumeSnapshot
from timeout_sampler import TimeoutSampler

from tests.infrastructure.golden_images.update_boot_source.utils import (
    generate_data_import_cron_dict,
)
from utilities.constants import TIMEOUT_2MIN
from utilities.hco import (
    ResourceEditorValidateHCOReconcile,
    enable_common_boot_image_import_spec_wait_for_data_import_cron,
)
from utilities.storage import RESOURCE_MANAGED_BY_DATA_IMPORT_CRON_LABEL

LOGGER = logging.getLogger(__name__)


@pytest.fixture()
def enabled_common_boot_image_import_feature_gate_scope_function(
    admin_client,
    hyperconverged_resource_scope_function,
    golden_images_namespace,
):
    enable_common_boot_image_import_spec_wait_for_data_import_cron(
        hco_resource=hyperconverged_resource_scope_function,
        admin_client=admin_client,
        namespace=golden_images_namespace,
    )


@pytest.fixture(scope="class")
def enabled_common_boot_image_import_feature_gate_scope_class(
    admin_client,
    hyperconverged_resource_scope_class,
    golden_images_namespace,
):
    enable_common_boot_image_import_spec_wait_for_data_import_cron(
        hco_resource=hyperconverged_resource_scope_class,
        admin_client=admin_client,
        namespace=golden_images_namespace,
    )


@pytest.fixture()
def golden_images_persistent_volume_claims_scope_function(golden_images_namespace):
    return list(
        PersistentVolumeClaim.get(
            namespace=golden_images_namespace.name,
            label_selector=RESOURCE_MANAGED_BY_DATA_IMPORT_CRON_LABEL,
        )
    )


@pytest.fixture()
def golden_images_volume_snapshot_scope_function(golden_images_namespace):
    return list(
        VolumeSnapshot.get(
            namespace=golden_images_namespace.name,
            label_selector=RESOURCE_MANAGED_BY_DATA_IMPORT_CRON_LABEL,
        )
    )


@pytest.fixture()
def updated_hco_with_custom_data_import_cron_scope_function(request, hyperconverged_resource_scope_function):
    data_import_cron_dict = generate_data_import_cron_dict(
        name=request.param["data_import_cron_name"],
        source_url=request.param["data_import_cron_source_url"],
        managed_data_source_name=request.param["managed_data_source_name"],
    )
    with ResourceEditorValidateHCOReconcile(
        patches={
            hyperconverged_resource_scope_function: {"spec": {"dataImportCronTemplates": [data_import_cron_dict]}}
        },
        list_resource_reconcile=[SSP, CDI],
    ):
        yield data_import_cron_dict


@pytest.fixture()
def custom_data_import_cron_scope_function(
    admin_client,
    golden_images_namespace,
    updated_hco_with_custom_data_import_cron_scope_function,
):
    expected_data_import_cron_name = updated_hco_with_custom_data_import_cron_scope_function["metadata"]["name"]
    for sample in TimeoutSampler(
        wait_timeout=TIMEOUT_2MIN,
        sleep=5,
        func=lambda: list(
            DataImportCron.get(
                dyn_client=admin_client,
                name=expected_data_import_cron_name,
                namespace=golden_images_namespace.name,
            )
        ),
        exceptions_dict={NotFoundError: []},
    ):
        if sample:
            return sample[0]


@pytest.fixture()
def custom_data_source_scope_function(admin_client, custom_data_import_cron_scope_function):
    custom_data_source_name = custom_data_import_cron_scope_function.instance.spec.managedDataSource
    try:
        return list(
            DataSource.get(
                dyn_client=admin_client,
                name=custom_data_source_name,
                namespace=custom_data_import_cron_scope_function.namespace,
            )
        )[0]
    except NotFoundError:
        LOGGER.error(
            f"DataSource {custom_data_source_name} is not found under "
            f"{custom_data_import_cron_scope_function.namespace} namespace."
        )
        raise

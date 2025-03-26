import pytest
from ocp_resources.data_import_cron import DataImportCron
from ocp_resources.datavolume import DataVolume

from tests.storage.utils import create_vm_from_dv
from utilities.constants import BIND_IMMEDIATE_ANNOTATION, TIMEOUT_5MIN, WILDCARD_CRON_EXPRESSION, Images
from utilities.infra import create_ns
from utilities.ssp import wait_for_condition_message_value
from utilities.storage import create_dv

LAST_IMPORT_IS_UP_TO_DATE_MESSAGE = "Latest import is up to date"


@pytest.fixture()
def data_import_cron_pvc_source_namespace(unprivileged_client):
    yield from create_ns(unprivileged_client=unprivileged_client, name="test-data-import-cron-pvc-source")


@pytest.fixture()
def data_import_cron_pvc_target_namespace(unprivileged_client):
    yield from create_ns(unprivileged_client=unprivileged_client, name="test-data-import-cron-pvc-target")


@pytest.fixture()
def dv_vm_for_data_import_cron(
    data_import_cron_pvc_source_namespace, storage_class_name_scope_module, rhel9_http_image_url
):
    with create_dv(
        dv_name="dv-pvc-source-rhel",
        namespace=data_import_cron_pvc_source_namespace.name,
        url=rhel9_http_image_url,
        size=Images.Rhel.DEFAULT_DV_SIZE,
        storage_class=storage_class_name_scope_module,
    ) as dv:
        dv.wait_for_status(
            status=DataVolume.Status.IMPORT_IN_PROGRESS,
            timeout=TIMEOUT_5MIN,
            stop_status=DataVolume.Status.SUCCEEDED,
        )
        create_vm_from_dv(
            dv=dv,
            start=False,
        )
        yield dv


@pytest.fixture()
def data_import_cron_pvc_source(
    unprivileged_client,
    data_import_cron_pvc_target_namespace,
    storage_class_with_filesystem_volume_mode,
    storage_class_name_scope_module,
    dv_vm_for_data_import_cron,
    storage_class_matrix__module__,
):
    with DataImportCron(
        name="pvc-import-cron",
        namespace=data_import_cron_pvc_target_namespace.name,
        schedule=WILDCARD_CRON_EXPRESSION,
        managed_data_source="pvc-import-datasource-pvc-source",
        annotations=BIND_IMMEDIATE_ANNOTATION,
        template={
            "spec": {
                "source": {
                    "pvc": {
                        "name": dv_vm_for_data_import_cron.name,
                        "namespace": dv_vm_for_data_import_cron.namespace,
                    }
                },
                "sourceFormat": "pvc",
                "volumeMode": storage_class_matrix__module__[storage_class_name_scope_module]["volume_mode"],
                "storage": {
                    "storageClassName": storage_class_name_scope_module,
                    "accessModes": [storage_class_matrix__module__[storage_class_name_scope_module]["access_mode"]],
                    "resources": {"requests": {"storage": "20Gi"}},
                },
            }
        },
    ) as data_import_cron:
        wait_for_condition_message_value(resource=data_import_cron, expected_message=LAST_IMPORT_IS_UP_TO_DATE_MESSAGE)
        yield data_import_cron

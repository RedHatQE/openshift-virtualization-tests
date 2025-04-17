import logging

import pytest
from ocp_resources.data_import_cron import DataImportCron
from ocp_resources.data_source import DataSource

from utilities.constants import BIND_IMMEDIATE_ANNOTATION, OS_FLAVOR_RHEL, Images
from utilities.infra import create_ns
from utilities.storage import create_dv, data_volume_template_with_source_ref_dict
from utilities.virt import VirtualMachineForTests, running_vm

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="class")
def data_import_cron_pvc_target_namespace(unprivileged_client):
    yield from create_ns(unprivileged_client=unprivileged_client, name="import-namespace")


@pytest.fixture(scope="class")
def dv_source_for_data_import_cron(namespace, storage_class_name_scope_module, rhel9_http_image_url):
    with create_dv(
        dv_name="dv-source-rhel",
        namespace=namespace.name,
        url=rhel9_http_image_url,
        size=Images.Rhel.DEFAULT_DV_SIZE,
        storage_class=storage_class_name_scope_module,
    ) as dv:
        yield dv


@pytest.fixture()
def vm_for_data_source_import(
    data_import_cron_pvc_target_namespace, imported_data_source, storage_class_name_scope_module, unprivileged_client
):
    with VirtualMachineForTests(
        name="vm-with-imported-data-source",
        namespace=data_import_cron_pvc_target_namespace.name,
        client=unprivileged_client,
        os_flavor=OS_FLAVOR_RHEL,
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=DataSource(
                name=imported_data_source.name, namespace=data_import_cron_pvc_target_namespace.name
            ),
            storage_class=storage_class_name_scope_module,
        ),
        memory_guest=Images.Rhel.DEFAULT_MEMORY_SIZE,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture(scope="class")
def data_import_cron_with_pvc_source(
    data_import_cron_pvc_target_namespace,
    dv_source_for_data_import_cron,
    imported_data_source,
    storage_class_name_scope_module,
):
    with DataImportCron(
        name="datasource-with-pvc-source",
        namespace=data_import_cron_pvc_target_namespace.name,
        schedule="*/1 * * * *",
        managed_data_source=imported_data_source.name,
        annotations=BIND_IMMEDIATE_ANNOTATION,
        template={
            "spec": {
                "source": {
                    "pvc": {
                        "name": dv_source_for_data_import_cron.name,
                        "namespace": dv_source_for_data_import_cron.namespace,
                    }
                },
                "storage": {
                    "resources": {"requests": {"storage": dv_source_for_data_import_cron.size}},
                    "storageClassName": storage_class_name_scope_module,
                },
            }
        },
    ) as data_import_cron:
        data_import_cron.wait_for_condition(condition="UpToDate", status=data_import_cron.Condition.Status.TRUE)
        yield data_import_cron
    imported_data_source.clean_up(wait=True)


@pytest.fixture(scope="class")
def imported_data_source(data_import_cron_pvc_target_namespace):
    yield DataSource(namespace=data_import_cron_pvc_target_namespace.name, name="target-data-source")

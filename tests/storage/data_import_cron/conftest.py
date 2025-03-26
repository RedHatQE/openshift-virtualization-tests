import pytest
from ocp_resources.data_import_cron import DataImportCron
from ocp_resources.data_source import DataSource
from ocp_resources.datavolume import DataVolume

from utilities.constants import BIND_IMMEDIATE_ANNOTATION, Images
from utilities.infra import create_ns
from utilities.storage import create_dv, create_vm_from_dv
from utilities.virt import running_vm


@pytest.fixture(scope="class")
def data_import_cron_pvc_target_namespace(unprivileged_client):
    yield from create_ns(unprivileged_client=unprivileged_client, name="pvc-target")


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
def recreate_dv_source_for_data_import_cron(
    namespace, storage_class_name_scope_module, rhel9_http_image_url, dv_source_for_data_import_cron
):
    dv_source_for_data_import_cron.delete(wait=True)
    with create_dv(
        dv_name="dv-source-rhel",
        namespace=namespace.name,
        url=rhel9_http_image_url,
        size=Images.Rhel.DEFAULT_DV_SIZE,
        storage_class=storage_class_name_scope_module,
    ) as dv:
        dv.wait_for_status(status=DataVolume.Status.SUCCEEDED)
        yield dv


@pytest.fixture(scope="class")
def vm_for_dv_target(namespace, dv_source_for_data_import_cron, data_import_cron_with_pvc_source, target_imported_pvc):
    with create_vm_from_dv(dv=target_imported_pvc, start=False) as vm:
        running_vm(vm=vm, check_ssh_connectivity=False, wait_for_interfaces=False)
        yield vm


@pytest.fixture(scope="class")
def data_import_cron_with_pvc_source(
    unprivileged_client,
    data_import_cron_pvc_target_namespace,
    storage_class_name_scope_module,
    dv_source_for_data_import_cron,
):
    data_source = DataSource(
        name="data-import-cron-with-pvc-source", namespace=data_import_cron_pvc_target_namespace.name
    )
    with DataImportCron(
        name="data-import-cron-with-pvc-source",
        namespace=data_import_cron_pvc_target_namespace.name,
        schedule="*/3 * * * *",
        managed_data_source="datasource-with-pvc-source",
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
                },
            }
        },
    ) as data_import_cron:
        data_import_cron.wait_for_condition(condition="UpToDate", status=data_import_cron.Condition.Status.TRUE)
        yield data_import_cron
    data_source.clean_up(wait=True)


@pytest.fixture(scope="class")
def target_imported_pvc(
    unprivileged_client,
    data_import_cron_pvc_target_namespace,
    dv_source_for_data_import_cron,
    data_import_cron_with_pvc_source,
):
    return list(
        DataVolume.get(
            dyn_client=unprivileged_client,
            namespace=data_import_cron_pvc_target_namespace.name,
        )
    )[0]

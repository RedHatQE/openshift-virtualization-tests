import logging

import pytest
from ocp_resources.cluster_role import ClusterRole
from ocp_resources.data_import_cron import DataImportCron
from ocp_resources.data_source import DataSource
from ocp_resources.resource import Resource

from tests.storage.constants import QUAY_FEDORA_CONTAINER_IMAGE
from tests.storage.utils import create_role_binding
from utilities.constants import BIND_IMMEDIATE_ANNOTATION, OS_FLAVOR_FEDORA, REGISTRY_STR, TIMEOUT_10MIN, Images
from utilities.infra import create_ns
from utilities.storage import create_dv, data_volume_template_with_source_ref_dict
from utilities.virt import VirtualMachineForTests, running_vm

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="class")
def data_import_cron_pvc_target_namespace(admin_client, unprivileged_client):
    yield from create_ns(admin_client=admin_client, unprivileged_client=unprivileged_client, name="import-namespace")


@pytest.fixture(scope="class")
def dv_source_for_data_import_cron(namespace, storage_class_name_scope_module, unprivileged_client):
    with create_dv(
        dv_name="dv-source-fedora",
        namespace=namespace.name,
        source=REGISTRY_STR,
        url=QUAY_FEDORA_CONTAINER_IMAGE,
        size=Images.Fedora.DEFAULT_DV_SIZE,
        storage_class=storage_class_name_scope_module,
        client=unprivileged_client,
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
        os_flavor=OS_FLAVOR_FEDORA,
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=DataSource(
                name=imported_data_source.name, namespace=data_import_cron_pvc_target_namespace.name
            ),
            storage_class=storage_class_name_scope_module,
        ),
        memory_guest=Images.Fedora.DEFAULT_MEMORY_SIZE,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture(scope="class")
def data_import_cron_with_pvc_source(
    data_import_cron_pvc_target_namespace,
    dv_source_for_data_import_cron,
    imported_data_source,
    storage_class_name_scope_module,
    cdi_cloner_rbac,
    unprivileged_client,
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
        client=unprivileged_client,
    ) as data_import_cron:
        data_import_cron.wait_for_condition(
            condition="UpToDate", status=data_import_cron.Condition.Status.TRUE, timeout=TIMEOUT_10MIN
        )
        yield data_import_cron
    imported_data_source.clean_up(wait=True)


@pytest.fixture(scope="class")
def imported_data_source(data_import_cron_pvc_target_namespace):
    yield DataSource(namespace=data_import_cron_pvc_target_namespace.name, name="target-data-source")


@pytest.fixture(scope="class")
def cdi_cloner_rbac(dv_source_for_data_import_cron, data_import_cron_pvc_target_namespace, admin_client):
    """
    Creates a ClusterRole for DataVolume cloning and a RoleBinding in the source
        namespace to allow the target namespace's ServiceAccount to clone DataVolumes.

    Args:
        dv_source_for_data_import_cron: DataVolume fixture that provides the source
            namespace.
        data_import_cron_pvc_target_namespace: Namespace fixture representing the
            target namespace.
        admin_client: Admin client used to create and manage cluster-scoped RBAC
            resources.
    """

    with ClusterRole(
        name="datavolume-cloner",
        client=admin_client,
        rules=[
            {
                "apiGroups": [Resource.ApiGroup.CDI_KUBEVIRT_IO],
                "resources": ["datavolumes", "datavolumes/source"],
                "verbs": ["*"],
            }
        ],
    ) as cluster_role:
        with create_role_binding(
            client=admin_client,
            name=f"allow-clone-to-{data_import_cron_pvc_target_namespace.name}",
            namespace=dv_source_for_data_import_cron.namespace,
            subjects_kind="ServiceAccount",
            subjects_name="default",
            subjects_namespace=data_import_cron_pvc_target_namespace.name,
            role_ref_kind=cluster_role.kind,
            role_ref_name=cluster_role.name,
        ):
            yield

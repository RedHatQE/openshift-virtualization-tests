import pytest
from ocp_resources.cluster_role_binding import ClusterRoleBinding
from ocp_resources.config_map import ConfigMap
from ocp_resources.data_import_cron import DataImportCron
from ocp_resources.job import Job
from ocp_resources.resource import ResourceEditor
from ocp_resources.role import Role
from ocp_resources.role_binding import RoleBinding
from ocp_resources.service_account import ServiceAccount
from ocp_resources.storage_class import StorageClass
from ocp_resources.storage_profile import StorageProfile

from tests.storage.checkups.constants import (
    ACCESS_MODES,
    CHECKUP_RULES,
    NAME_STR,
    NON_EXISTENT_STR,
    SPEC_STR,
    STORAGE_CHECKUP_STR,
)
from tests.storage.checkups.utils import update_storage_profile
from tests.storage.utils import create_cirros_vm
from tests.utils import get_image_from_csv
from utilities.constants import (
    BIND_IMMEDIATE_ANNOTATION,
    OUTDATED,
    TIMEOUT_10MIN,
    VALUE_STR,
    WILDCARD_CRON_EXPRESSION,
    StorageClassNames,
)
from utilities.infra import create_ns
from utilities.storage import update_default_sc

KUBEVIRT_STORAGE_CHECKUP = "kubevirt-storage-checkup"


@pytest.fixture(scope="package")
def checkups_namespace():
    yield from create_ns(
        name="test-storage-checkups",
    )


@pytest.fixture(scope="package")
def checkup_service_account(checkups_namespace):
    with ServiceAccount(name="storage-checkup-sa", namespace=checkups_namespace.name) as sa:
        yield sa


@pytest.fixture(scope="package")
def checkup_role(checkups_namespace):
    with Role(
        name="storage-checkup-role",
        namespace=checkups_namespace.name,
        rules=CHECKUP_RULES,
    ) as role:
        yield role


@pytest.fixture(scope="package")
def checkup_role_binding(checkups_namespace, checkup_service_account, checkup_role):
    with RoleBinding(
        name=checkup_role.name,
        namespace=checkups_namespace.name,
        subjects_kind=checkup_service_account.kind,
        subjects_name=checkup_service_account.name,
        role_ref_kind=checkup_role.kind,
        role_ref_name=checkup_role.name,
    ) as role_binding:
        yield role_binding


@pytest.fixture(scope="package")
def checkup_cluster_reader(checkups_namespace, checkup_role_binding, checkup_service_account):
    with ClusterRoleBinding(
        name=f"{KUBEVIRT_STORAGE_CHECKUP}-clustereader",
        cluster_role="cluster-reader",
        subjects=[
            {
                "kind": ServiceAccount.kind,
                NAME_STR: checkup_service_account.name,
                "namespace": checkups_namespace.name,
            }
        ],
    ) as crb:
        yield crb


@pytest.fixture(scope="package")
def checkup_image_url(csv_related_images_scope_session):
    return get_image_from_csv(
        image_string=KUBEVIRT_STORAGE_CHECKUP,
        csv_related_images=csv_related_images_scope_session,
    )


@pytest.fixture(scope="function")
def checkup_configmap(checkups_namespace):
    with ConfigMap(
        name="storage-checkup-config",
        namespace=checkups_namespace.name,
        data={f"{SPEC_STR}.timeout": "10m"},
    ) as configmap:
        yield configmap


@pytest.fixture(scope="function")
def checkup_job(
    request,
    checkups_namespace,
    checkup_image_url,
    checkup_cluster_reader,
    checkup_service_account,
    checkup_configmap,
):
    containers = [
        {
            NAME_STR: STORAGE_CHECKUP_STR,
            "image": checkup_image_url,
            "imagePullPolicy": "Always",
            "env": [
                {NAME_STR: "CONFIGMAP_NAMESPACE", VALUE_STR: checkups_namespace.name},
                {
                    NAME_STR: "CONFIGMAP_NAME",
                    VALUE_STR: checkup_configmap.name,
                },
            ],
        }
    ]
    with Job(
        name=STORAGE_CHECKUP_STR,
        namespace=checkups_namespace.name,
        service_account=checkup_service_account.name,
        restart_policy="Never",
        backoff_limit=0,
        containers=containers,
    ) as job:
        job.wait_for_condition(
            condition=request.param["expected_condition"],
            status=job.Condition.Status.TRUE,
            timeout=TIMEOUT_10MIN,
        )
        yield job


@pytest.fixture()
def updated_two_default_storage_classes(removed_default_storage_classes, cluster_storage_classes):
    first_sc, second_sc = cluster_storage_classes[:2]
    with update_default_sc(default=True, storage_class=first_sc):
        with update_default_sc(
            default=True,
            storage_class=second_sc,
        ):
            yield


@pytest.fixture()
def storage_class_with_unknown_provisioner():
    with StorageClass(
        name="sc-non-existent-provisioner",
        provisioner=NON_EXISTENT_STR,
        reclaim_policy=StorageClass.ReclaimPolicy.DELETE,
        volume_binding_mode=StorageClass.VolumeBindingMode.Immediate,
    ) as sc:
        yield sc


@pytest.fixture()
def updated_default_storage_profile(default_sc):
    storage_profile = StorageProfile(name=default_sc.name)
    claim_property_set_dict = update_storage_profile(storage_profile=storage_profile)
    with ResourceEditor(patches={storage_profile: {SPEC_STR: {"claimPropertySets": [claim_property_set_dict]}}}):
        yield storage_profile


@pytest.fixture()
def skip_if_no_ocs_rbd_non_virt_sc(cluster_storage_classes_names):
    if StorageClassNames.CEPH_RBD not in cluster_storage_classes_names:
        pytest.skip(f"Skip due to no storageclass  {StorageClassNames.CEPH_RBD} in the cluster")


@pytest.fixture()
def ocs_rbd_non_virt_vm_for_checkups_test(admin_client, checkups_namespace):
    with create_cirros_vm(
        storage_class=StorageClassNames.CEPH_RBD,
        namespace=checkups_namespace.name,
        client=admin_client,
        dv_name="dv-10709",
        vm_name="vm-10709",
        wait_running=True,
    ) as vm:
        yield vm


@pytest.fixture()
def broken_data_import_cron(golden_images_namespace):
    with DataImportCron(
        name="broken-data-import-cron",
        namespace=golden_images_namespace.name,
        schedule=WILDCARD_CRON_EXPRESSION,
        garbage_collect=OUTDATED,
        managed_data_source="broken-data-source",
        annotations=BIND_IMMEDIATE_ANNOTATION,
        template={
            "spec": {
                "source": {
                    "registry": {
                        "imageStream": NON_EXISTENT_STR,
                        "pullMethod": "node",
                    }
                },
                "storage": {
                    "resources": {
                        "requests": {
                            "storage": "30Gi",
                        }
                    }
                },
            }
        },
    ) as data_import_cron:
        yield data_import_cron


@pytest.fixture()
def storage_class_with_hpp_provisioner():
    with StorageClass(
        name="test-sc-hpp",
        provisioner=StorageClass.Provisioner.HOSTPATH,
        reclaim_policy=StorageClass.ReclaimPolicy.DELETE,
        volume_binding_mode=StorageClass.VolumeBindingMode.Immediate,
    ) as sc:
        yield sc


@pytest.fixture()
def updated_storage_class_snapshot_clone_strategy(storage_class_with_hpp_provisioner):
    storage_profile = StorageProfile(name=storage_class_with_hpp_provisioner.name)
    with ResourceEditor(patches={storage_profile: {SPEC_STR: {"cloneStrategy": "snapshot"}}}):
        yield storage_profile


@pytest.fixture()
def default_storage_class_access_modes(default_sc):
    storage_profile = StorageProfile(name=default_sc.name)
    return storage_profile.instance.status.claimPropertySets[0][ACCESS_MODES]


@pytest.fixture()
def rhel9_data_import_cron_source_format(admin_client, golden_images_namespace):
    data_import_cron = DataImportCron(
        name="rhel9-image-cron",
        namespace=golden_images_namespace.name,
        client=admin_client,
    )
    return data_import_cron.instance.status["sourceFormat"]

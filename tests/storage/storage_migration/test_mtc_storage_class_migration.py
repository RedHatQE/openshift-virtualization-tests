import logging

import pytest
from ocp_resources.mig_cluster import MigCluster
from ocp_resources.mig_migration import MigMigration
from ocp_resources.mig_plan import MigPlan
from ocp_resources.resource import ResourceEditor
from pytest_testconfig import config as py_config

from tests.storage.storage_migration.utils import CONTENT, FILE_BEFORE_STORAGE_MIGRATION, check_file_in_vm
from utilities.constants import TIMEOUT_1MIN

LOGGER = logging.getLogger(__name__)

OPENSHIFT_MIGRATION_NAMESPACE = "openshift-migration"


@pytest.fixture(scope="module")
def mig_cluster():
    mig_cluster = MigCluster(name="host", namespace=OPENSHIFT_MIGRATION_NAMESPACE)
    assert mig_cluster.exists, f"MigCluster {MigCluster.name} does not exists"
    return mig_cluster


@pytest.fixture(scope="module")
def mig_cluster_ref_dict(mig_cluster):
    return {"name": f"{mig_cluster.name}", "namespace": f"{mig_cluster.namespace}"}


@pytest.fixture()
def storage_mig_plan(mig_cluster_ref_dict, namespace, target_storage_class):
    with MigPlan(
        name="storage-mig-plan",
        namespace=OPENSHIFT_MIGRATION_NAMESPACE,
        src_mig_cluster_ref=mig_cluster_ref_dict,
        dest_mig_cluster_ref=mig_cluster_ref_dict,
        live_migrate=True,
        namespaces=[namespace.name],
        refresh=False,
    ) as mig_plan:
        mig_plan.wait_for_condition(
            condition=mig_plan.Condition.READY, status=mig_plan.Condition.Status.TRUE, timeout=TIMEOUT_1MIN
        )
        # Edit the target storageClass, accessModes, volumeMode
        mig_plan_dict = mig_plan.instance.to_dict()
        mig_plan_persistent_volumes_dict = mig_plan_dict["spec"]["persistentVolumes"][0].copy()
        mig_plan_persistent_volumes_dict["selection"]["storageClass"] = f"{target_storage_class}"
        mig_plan_persistent_volumes_dict["pvc"]["accessModes"][0] = "auto"
        mig_plan_persistent_volumes_dict["pvc"]["volumeMode"] = "auto"
        patch = {mig_plan: {"spec": {"persistentVolumes": [mig_plan_persistent_volumes_dict]}}}
        ResourceEditor(patches=patch).update()
        yield mig_plan


@pytest.fixture()
def storage_mig_migration(storage_mig_plan):
    with MigMigration(
        name="mig-migration-abc",
        namespace=OPENSHIFT_MIGRATION_NAMESPACE,
        mig_plan_ref={"name": f"{storage_mig_plan.name}", "namespace": f"{storage_mig_plan.namespace}"},
        migrate_state=True,
        quiesce_pods=True,  # CutOver -> Start migration
        stage=False,
    ) as mig_migration:
        mig_migration.wait_for_condition(
            condition=mig_migration.Condition.READY, status=mig_migration.Condition.Status.TRUE, timeout=TIMEOUT_1MIN
        )
        mig_migration.wait_for_condition(
            condition=mig_migration.Condition.Type.SUCCEEDED, status=mig_migration.Condition.Status.TRUE
        )
        yield mig_migration


@pytest.mark.parametrize(
    "source_storage_class, target_storage_class",
    [
        pytest.param(
            {"source_storage_class": py_config["source_storage_class_for_storage_migration"]},
            {"target_storage_class": py_config["target_storage_class_for_storage_migration"]},
            marks=pytest.mark.polarion("CNV-"),
            id="source_a_target_b",
        )
    ],
    indirect=True,
)
def test_vm_for_sc_mig(
    source_vm_for_storage_class_migration,
    written_file_to_vm_before_migration,
    target_storage_class,
    storage_mig_plan,
    storage_mig_migration,
    deleted_completed_virt_launcher_source_pod,
    deleted_old_dv,
):
    LOGGER.info("HEY")

    check_file_in_vm(
        vm=source_vm_for_storage_class_migration,
        file_name=FILE_BEFORE_STORAGE_MIGRATION,
        file_content=CONTENT,
    )

    # import ipdb
    # ipdb.set_trace()

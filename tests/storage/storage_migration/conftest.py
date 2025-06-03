from copy import deepcopy

import pytest
from ocp_resources.data_source import DataSource
from ocp_resources.datavolume import DataVolume
from ocp_resources.mig_cluster import MigCluster
from ocp_resources.mig_migration import MigMigration
from ocp_resources.mig_plan import MigPlan
from ocp_resources.resource import ResourceEditor
from ocp_resources.virtual_machine_cluster_instancetype import VirtualMachineClusterInstancetype
from ocp_resources.virtual_machine_cluster_preference import VirtualMachineClusterPreference

from tests.storage.storage_migration.constants import CONTENT, FILE_BEFORE_STORAGE_MIGRATION
from tests.storage.storage_migration.utils import get_source_virt_launcher_pod
from utilities.constants import (
    OS_FLAVOR_FEDORA,
    OS_FLAVOR_RHEL,
    TIMEOUT_1MIN,
    TIMEOUT_5SEC,
    TIMEOUT_10MIN,
    U1_SMALL,
    Images,
)
from utilities.storage import data_volume_template_with_source_ref_dict, write_file
from utilities.virt import VirtualMachineForTests, get_vm_boot_time, running_vm, vm_instance_from_template

OPENSHIFT_MIGRATION_NAMESPACE = "openshift-migration"


@pytest.fixture(scope="module")
def golden_images_rhel9_data_source(golden_images_namespace):
    return DataSource(namespace=golden_images_namespace.name, name="rhel9", ensure_exists=True)


@pytest.fixture(scope="module")
def mig_cluster(admin_client):
    return MigCluster(name="host", namespace=OPENSHIFT_MIGRATION_NAMESPACE, client=admin_client, ensure_exists=True)


@pytest.fixture(scope="class")
def storage_mig_plan(admin_client, namespace, mig_cluster, target_storage_class):
    mig_cluster_ref_dict = {"name": mig_cluster.name, "namespace": mig_cluster.namespace}
    with MigPlan(
        name="storage-mig-plan",
        namespace=mig_cluster.namespace,
        client=admin_client,
        src_mig_cluster_ref=mig_cluster_ref_dict,
        dest_mig_cluster_ref=mig_cluster_ref_dict,
        live_migrate=True,
        namespaces=[namespace.name],
        refresh=False,
    ) as mig_plan:
        mig_plan.wait_for_condition(
            condition=mig_plan.Condition.READY, status=mig_plan.Condition.Status.TRUE, timeout=TIMEOUT_1MIN
        )
        # Edit the target PVCs' storageClass, accessModes, volumeMode
        mig_plan_persistent_volumes_dict = deepcopy(mig_plan.instance.to_dict()["spec"]["persistentVolumes"])
        for pvc_dict in mig_plan_persistent_volumes_dict:
            pvc_dict["selection"]["storageClass"] = target_storage_class
            pvc_dict["pvc"]["accessModes"][0] = "auto"
            pvc_dict["pvc"]["volumeMode"] = "auto"
        ResourceEditor(patches={mig_plan: {"spec": {"persistentVolumes": mig_plan_persistent_volumes_dict}}}).update()
        yield mig_plan


@pytest.fixture(scope="class")
def storage_mig_migration(admin_client, storage_mig_plan):
    with MigMigration(
        name="mig-migration-abc",
        namespace=storage_mig_plan.namespace,
        client=admin_client,
        mig_plan_ref={"name": storage_mig_plan.name, "namespace": storage_mig_plan.namespace},
        migrate_state=True,
        quiesce_pods=True,  # CutOver -> Start migration
        stage=False,
    ) as mig_migration:
        mig_migration.wait_for_condition(
            condition=mig_migration.Condition.READY, status=mig_migration.Condition.Status.TRUE, timeout=TIMEOUT_1MIN
        )
        mig_migration.wait_for_condition(
            condition=mig_migration.Condition.Type.SUCCEEDED,
            status=mig_migration.Condition.Status.TRUE,
            timeout=TIMEOUT_10MIN,
            sleep_time=TIMEOUT_5SEC,
        )
        yield mig_migration


@pytest.fixture(scope="class")
def source_storage_class(request):
    # Storage class for the original VMs creation
    return request.param["source_storage_class"]


@pytest.fixture(scope="class")
def target_storage_class(request):
    return request.param["target_storage_class"]


@pytest.fixture(scope="class")
def vm_for_storage_class_migration_with_instance_type(
    unprivileged_client,
    namespace,
    golden_images_fedora_data_source,
    source_storage_class,
    cpu_for_migration,
):
    with VirtualMachineForTests(
        name="vm-with-instance-type",
        namespace=namespace.name,
        client=unprivileged_client,
        os_flavor=OS_FLAVOR_FEDORA,
        vm_instance_type=VirtualMachineClusterInstancetype(name=U1_SMALL),
        vm_preference=VirtualMachineClusterPreference(name=OS_FLAVOR_FEDORA),
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=golden_images_fedora_data_source,
            storage_class=source_storage_class,
        ),
        cpu_model=cpu_for_migration,
    ) as vm:
        vm.start()
        yield vm


@pytest.fixture(scope="class")
def vm_for_storage_class_migration_from_template_with_data_source(
    unprivileged_client, namespace, golden_images_rhel9_data_source, source_storage_class, cpu_for_migration
):
    with VirtualMachineForTests(
        name="vm-from-template-and-data-source",
        namespace=namespace.name,
        client=unprivileged_client,
        os_flavor=OS_FLAVOR_RHEL,
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=golden_images_rhel9_data_source,
            storage_class=source_storage_class,
        ),
        memory_guest=Images.Rhel.DEFAULT_MEMORY_SIZE,
        cpu_model=cpu_for_migration,
    ) as vm:
        vm.start()
        yield vm


@pytest.fixture(scope="class")
def vm_for_storage_class_migration_from_template_with_dv(
    unprivileged_client,
    namespace,
    source_storage_class,
    cpu_for_migration,
    rhel_latest_os_params,
    artifactory_secret_scope_module,
    artifactory_config_map_scope_module,
):
    dv = DataVolume(
        name="dv-rhel-imported",
        namespace=namespace.name,
        source="http",
        url=rhel_latest_os_params["rhel_image_path"],
        size=Images.Rhel.DEFAULT_DV_SIZE,
        storage_class=source_storage_class,
        api_name="storage",
        secret=artifactory_secret_scope_module,
        cert_configmap=artifactory_config_map_scope_module.name,
    )
    dv.to_dict()
    with VirtualMachineForTests(
        name="vm-from-template-and-imported-dv",
        namespace=namespace.name,
        client=unprivileged_client,
        os_flavor=OS_FLAVOR_RHEL,
        memory_guest=Images.Rhel.DEFAULT_MEMORY_SIZE,
        data_volume_template={"metadata": dv.res["metadata"], "spec": dv.res["spec"]},
        cpu_model=cpu_for_migration,
    ) as vm:
        vm.start()
        yield vm


@pytest.fixture(scope="class")
def vm_for_storage_class_migration_from_template_with_existing_dv(
    request,
    unprivileged_client,
    namespace,
    data_volume_scope_class,
):
    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        existing_data_volume=data_volume_scope_class,
    ) as vm:
        vm.start()
        yield vm


@pytest.fixture(scope="class")
def vms_for_storage_class_migration(request):
    """
    Only fixtures from the "vms_fixtures" test param will be called
    Only VMs that are listed in "vms_fixtures" param will be created
    VM fixtures that are not listed in the param will not be called, and those VMs will not be created
    """
    vms = [request.getfixturevalue(argname=vm_fixture) for vm_fixture in request.param["vms_fixtures"]]
    yield vms


@pytest.fixture(scope="class")
def booted_vms_for_storage_class_migration(vms_for_storage_class_migration):
    for vm in vms_for_storage_class_migration:
        running_vm(vm=vm)
    yield vms_for_storage_class_migration


@pytest.fixture(scope="class")
def written_file_to_vms_before_migration(booted_vms_for_storage_class_migration):
    for vm in booted_vms_for_storage_class_migration:
        write_file(
            vm=vm,
            filename=FILE_BEFORE_STORAGE_MIGRATION,
            content=CONTENT,
            stop_vm=False,
        )
    yield booted_vms_for_storage_class_migration


@pytest.fixture(scope="class")
def online_vms_for_storage_class_migration(booted_vms_for_storage_class_migration, request):
    # Stop the VMs that should not be Running, and only yield the VMs that should be Running
    running_vms = []
    for vm, is_online in zip(booted_vms_for_storage_class_migration, request.param["online_vm"]):
        if is_online is True:
            running_vms.append(vm)
        else:
            vm.stop(wait=True)
    yield running_vms


@pytest.fixture(scope="class")
def linux_vms_boot_time_before_storage_migration(online_vms_for_storage_class_migration):
    yield {vm.name: get_vm_boot_time(vm=vm) for vm in online_vms_for_storage_class_migration}


@pytest.fixture(scope="class")
def deleted_completed_virt_launcher_source_pod(unprivileged_client, online_vms_for_storage_class_migration):
    for vm in online_vms_for_storage_class_migration:
        source_pod = get_source_virt_launcher_pod(client=unprivileged_client, vm=vm)
        source_pod.wait_for_status(status=source_pod.Status.SUCCEEDED)
        source_pod.delete(wait=True)


@pytest.fixture(scope="class")
def deleted_old_dvs_of_online_vms(
    unprivileged_client, online_vms_for_storage_class_migration, deleted_completed_virt_launcher_source_pod
):
    for vm in online_vms_for_storage_class_migration:
        dv_name = vm.instance.status.volumeUpdateState.volumeMigrationState.migratedVolumes[0].sourcePVCInfo.claimName
        dv = DataVolume(client=unprivileged_client, name=dv_name, namespace=vm.namespace, ensure_exists=True)
        assert dv.delete(wait=True)


@pytest.fixture(scope="class")
def deleted_old_dvs_of_stopped_vms(unprivileged_client, namespace):
    for dv in DataVolume.get(dyn_client=unprivileged_client, namespace=namespace.name):
        # target DV after migration name is: <source-dv-name>-mig-<generated_suffix>
        if "-mig-" not in dv.name:
            assert dv.delete(wait=True)

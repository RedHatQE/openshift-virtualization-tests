import shlex
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
from pyhelper_utils.shell import run_ssh_commands

from tests.storage.storage_migration.constants import (
    CONTENT,
    FILE_BEFORE_STORAGE_MIGRATION,
    HOTPLUGGED_DEVICE,
    MOUNT_HOTPLUGGED_DEVICE_PATH,
    WINDOWS_FILE_WITH_PATH,
    WINDOWS_TEST_DIRECTORY_PATH,
)
from tests.storage.storage_migration.utils import get_source_virt_launcher_pod, get_storage_class_for_storage_migration
from tests.storage.utils import create_windows_directory
from utilities.constants import (
    OS_FLAVOR_FEDORA,
    OS_FLAVOR_RHEL,
    OS_FLAVOR_WINDOWS,
    TIMEOUT_1MIN,
    TIMEOUT_5SEC,
    TIMEOUT_10MIN,
    U1_SMALL,
    Images,
)
from utilities.infra import get_http_image_url
from utilities.storage import (
    create_dv,
    data_volume_template_with_source_ref_dict,
    virtctl_volume,
    wait_for_vm_volume_ready,
    write_file,
)
from utilities.virt import (
    VirtualMachineForTests,
    fedora_vm_body,
    get_vm_boot_time,
    running_vm,
    vm_instance_from_template,
)

OPENSHIFT_MIGRATION_NAMESPACE = "openshift-migration"
DEFAULT_DV_SIZE = "1Gi"


@pytest.fixture(scope="module")
def golden_images_rhel9_data_source(golden_images_namespace):
    return DataSource(
        namespace=golden_images_namespace.name, name="rhel9", client=golden_images_namespace.client, ensure_exists=True
    )


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
        teardown=False,
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
            # vTPM PVC should be skipped
            if pvc_dict["pvc"]["name"].startswith("persistent-state"):
                pvc_dict["selection"]["action"] = "skip"
        ResourceEditor(patches={mig_plan: {"spec": {"persistentVolumes": mig_plan_persistent_volumes_dict}}}).update()
        yield mig_plan
        mig_plan.clean_up()


@pytest.fixture(scope="class")
def storage_mig_migration(admin_client, storage_mig_plan):
    with MigMigration(
        name="mig-migration-storage",
        namespace=storage_mig_plan.namespace,
        client=admin_client,
        mig_plan_ref={"name": storage_mig_plan.name, "namespace": storage_mig_plan.namespace},
        migrate_state=True,
        quiesce_pods=True,  # CutOver -> Start migration
        stage=False,
        teardown=False,
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
        mig_migration.clean_up()


@pytest.fixture(scope="class")
def source_storage_class(request, cluster_storage_classes_names):
    # Storage class for the original VMs creation
    return get_storage_class_for_storage_migration(
        storage_class=request.param["source_storage_class"], cluster_storage_classes_names=cluster_storage_classes_names
    )


@pytest.fixture(scope="class")
def target_storage_class(request, cluster_storage_classes_names):
    return get_storage_class_for_storage_migration(
        storage_class=request.param["target_storage_class"], cluster_storage_classes_names=cluster_storage_classes_names
    )


@pytest.fixture(scope="class")
def vm_for_storage_class_migration_with_instance_type(
    unprivileged_client,
    namespace,
    golden_images_namespace,
    source_storage_class,
    cpu_for_migration,
):
    golden_images_fedora_data_source = DataSource(
        namespace=golden_images_namespace.name,
        name=OS_FLAVOR_FEDORA,
        client=golden_images_namespace.client,
        ensure_exists=True,
    )
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
    cleaned_up_standalone_data_volume_after_storage_migration,
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
def vms_boot_time_before_storage_migration(online_vms_for_storage_class_migration):
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


@pytest.fixture(scope="class")
def blank_disk_dv_for_storage_migration(unprivileged_client, namespace, source_storage_class):
    with create_dv(
        source="blank",
        dv_name="blank-dv-for-hotplug",
        client=unprivileged_client,
        namespace=namespace.name,
        size=DEFAULT_DV_SIZE,
        storage_class=source_storage_class,
        consume_wffc=False,
    ) as dv:
        yield dv


@pytest.fixture(scope="class")
def fedora_vm_for_hotplug_and_storage_migration(unprivileged_client, namespace, cpu_for_migration):
    name = "fedora-volume-hotplug-vm"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        body=fedora_vm_body(name=name),
        cpu_model=cpu_for_migration,
        client=unprivileged_client,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture(scope="class")
def vm_for_storage_class_migration_with_hotplugged_volume(
    namespace, blank_disk_dv_for_storage_migration, fedora_vm_for_hotplug_and_storage_migration
):
    with virtctl_volume(
        action="add",
        namespace=namespace.name,
        vm_name=fedora_vm_for_hotplug_and_storage_migration.name,
        volume_name=blank_disk_dv_for_storage_migration.name,
        persist=True,
    ) as res:
        status, out, err = res
        assert status, f"Failed to add volume to VM, out: {out}, err: {err}."
        wait_for_vm_volume_ready(vm=fedora_vm_for_hotplug_and_storage_migration)
        yield fedora_vm_for_hotplug_and_storage_migration


@pytest.fixture(scope="class")
def vm_with_mounted_hotplugged_disk(vm_for_storage_class_migration_with_hotplugged_volume):
    # Mount the disk to the VM
    run_ssh_commands(
        host=vm_for_storage_class_migration_with_hotplugged_volume.ssh_exec,
        commands=[
            shlex.split(cmd)
            for cmd in [
                f"sudo mkfs.ext4 {HOTPLUGGED_DEVICE}",
                f"sudo mkdir {MOUNT_HOTPLUGGED_DEVICE_PATH}",
                f"sudo mount {HOTPLUGGED_DEVICE} {MOUNT_HOTPLUGGED_DEVICE_PATH}",
            ]
        ],
    )
    yield vm_for_storage_class_migration_with_hotplugged_volume


@pytest.fixture(scope="class")
def written_file_to_the_mounted_hotplugged_disk(vm_with_mounted_hotplugged_disk):
    run_ssh_commands(
        host=vm_with_mounted_hotplugged_disk.ssh_exec,
        commands=shlex.split(
            f"echo '{CONTENT}' | sudo tee {MOUNT_HOTPLUGGED_DEVICE_PATH}/{FILE_BEFORE_STORAGE_MIGRATION}"
        ),
    )
    yield vm_with_mounted_hotplugged_disk


@pytest.fixture(scope="class")
def windows_vm_with_vtpm_for_storage_migration(
    unprivileged_client,
    namespace,
    modern_cpu_for_migration,
    source_storage_class,
    artifactory_secret_scope_module,
    artifactory_config_map_scope_module,
):
    dv = DataVolume(
        name="windows-11-dv",
        namespace=namespace.name,
        storage_class=source_storage_class,
        source="http",
        # Using WSL image to avoid the issue of the Windows VM not being able to boot
        url=get_http_image_url(image_directory=Images.Windows.DIR, image_name=Images.Windows.WIN11_WSL2_IMG),
        size=Images.Windows.DEFAULT_DV_SIZE,
        client=unprivileged_client,
        api_name="storage",
        secret=artifactory_secret_scope_module,
        cert_configmap=artifactory_config_map_scope_module.name,
    )
    dv.to_dict()
    with VirtualMachineForTests(
        os_flavor=OS_FLAVOR_WINDOWS,
        name="windows-11-vm",
        namespace=namespace.name,
        client=unprivileged_client,
        vm_instance_type=VirtualMachineClusterInstancetype(name="u1.large"),
        vm_preference=VirtualMachineClusterPreference(name="windows.11"),
        data_volume_template={"metadata": dv.res["metadata"], "spec": dv.res["spec"]},
        cpu_model=modern_cpu_for_migration,
    ) as vm:
        vm.start()
        yield vm


@pytest.fixture(scope="class")
def created_windows_directory(booted_vms_for_storage_class_migration):
    for vm in booted_vms_for_storage_class_migration:
        create_windows_directory(windows_vm=vm, directory_path=WINDOWS_TEST_DIRECTORY_PATH)


@pytest.fixture(scope="class")
def written_file_to_windows_vms_before_migration(booted_vms_for_storage_class_migration, created_windows_directory):
    for vm in booted_vms_for_storage_class_migration:
        cmd = shlex.split(
            f'powershell -command "\\"{CONTENT}\\" | Out-File -FilePath {WINDOWS_FILE_WITH_PATH} -Append"'
        )
        run_ssh_commands(host=vm.ssh_exec, commands=cmd)
    yield booted_vms_for_storage_class_migration


@pytest.fixture(scope="class")
def cleaned_up_standalone_data_volume_after_storage_migration(unprivileged_client, namespace, data_volume_scope_class):
    yield
    for dv in DataVolume.get(dyn_client=unprivileged_client, namespace=namespace.name):
        if dv.name.startswith(f"{data_volume_scope_class.name}-mig"):
            assert dv.clean_up(wait=True)

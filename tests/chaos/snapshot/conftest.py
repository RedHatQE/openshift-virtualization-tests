import pytest
from ocp_resources.datavolume import DataVolume

from tests.chaos.snapshot.utils import VirtualMachineSnapshotWithDeadline
from utilities.constants import OS_FLAVOR_RHEL, TIMEOUT_8MIN, TIMEOUT_10MIN, Images
from utilities.virt import VirtualMachineForTests


@pytest.fixture()
def chaos_dv_rhel9_for_snapshot(
    admin_client,
    chaos_namespace,
    storage_class_matrix_snapshot_matrix__function__,
    rhel9_http_image_url,
    artifactory_secret_chaos_namespace_scope_module,
    artifactory_config_map_chaos_namespace_scope_module,
):
    yield DataVolume(
        source="http",
        name="chaos-dv",
        api_name="storage",
        namespace=chaos_namespace.name,
        url=rhel9_http_image_url,
        size=Images.Rhel.DEFAULT_DV_SIZE,
        storage_class=[*storage_class_matrix_snapshot_matrix__function__][0],
        client=admin_client,
        secret=artifactory_secret_chaos_namespace_scope_module,
        cert_configmap=artifactory_config_map_chaos_namespace_scope_module.name,
    )


@pytest.fixture()
def chaos_vm_rhel9_for_snapshot(admin_client, chaos_namespace, chaos_dv_rhel9_for_snapshot):
    chaos_dv_rhel9_for_snapshot.to_dict()
    with VirtualMachineForTests(
        client=admin_client,
        name="vm-chaos-snapshot",
        namespace=chaos_namespace.name,
        os_flavor=OS_FLAVOR_RHEL,
        memory_guest=Images.Rhel.DEFAULT_MEMORY_SIZE,
        data_volume_template={
            "metadata": chaos_dv_rhel9_for_snapshot.res["metadata"],
            "spec": chaos_dv_rhel9_for_snapshot.res["spec"],
        },
    ) as vm:
        vm.start(wait=True, timeout=TIMEOUT_10MIN)
        yield vm


@pytest.fixture()
def chaos_online_snapshots(
    request,
    admin_client,
    chaos_vm_rhel9_for_snapshot,
):
    vm_snapshots = []
    for idx in range(request.param["number_of_snapshots"]):
        with VirtualMachineSnapshotWithDeadline(
            name=f"snapshot-{chaos_vm_rhel9_for_snapshot.name}-{idx}",
            namespace=chaos_vm_rhel9_for_snapshot.namespace,
            vm_name=chaos_vm_rhel9_for_snapshot.name,
            client=admin_client,
            teardown=False,
            failure_deadline=TIMEOUT_8MIN,
        ) as vm_snapshot:
            vm_snapshots.append(vm_snapshot)
            vm_snapshot.wait_snapshot_done(timeout=TIMEOUT_8MIN)
    yield vm_snapshots

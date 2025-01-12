import pytest
from ocp_resources.deployment import Deployment
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_resources.virtual_machine import VirtualMachine

from tests.chaos.constants import STRESS_NG
from utilities.constants import (
    TIMEOUT_2MIN,
    TIMEOUT_5MIN,
    TIMEOUT_5SEC,
    Images,
    NamespacesNames,
    StorageClassNames,
)
from utilities.virt import VirtualMachineForTests, running_vm

pytestmark = [
    pytest.mark.chaos,
    pytest.mark.usefixtures("chaos_namespace", "cluster_monitoring_process", "skip_on_aws_cluster"),
]


@pytest.mark.parametrize(
    "chaos_vms_list_rhel9, pod_deleting_process",
    [
        pytest.param(
            {
                "number_of_vms": 3,
            },
            {
                "pod_prefix": "apiserver",
                "resource": Deployment,
                "namespace_name": NamespacesNames.OPENSHIFT_APISERVER,
                "ratio": 0.5,
                "interval": TIMEOUT_5SEC,
                "max_duration": TIMEOUT_5MIN,
            },
        )
    ],
    indirect=True,
)
@pytest.mark.polarion("CNV-5428")
def test_pod_delete_openshift_apiserver(
    pod_deleting_process,
    chaos_vms_list_rhel9,
):
    """
    Verifies that VMs can be created, started, stopped and deleted
    while openshift-apiserver pods are continuously being deleted.
    """
    for vm in chaos_vms_list_rhel9:
        vm.deploy()
        running_vm(vm=vm, wait_for_interfaces=False, check_ssh_connectivity=False)


@pytest.mark.parametrize(
    "rebooted_master_node",
    [
        pytest.param(
            {"master_node_to_reboot": "node_without_kmp_manager"},
            id="nodes_without_kmp_manager",
            marks=pytest.mark.polarion("CNV-9293"),
        ),
    ],
    indirect=True,
)
def test_master_node_restart(
    admin_client,
    chaos_namespace,
    rebooting_master_node,
):
    """
    This test verifies that a RHEL VM can be created, started, stopped and deleted
    while a given master node (randomly selected either from the nodes that have
    kubemacpool-mac-controller-manager pod or from the nodes that don't have it) is rebooted.
    """
    with VirtualMachineForTests(
        client=admin_client,
        name="vm-chaos",
        namespace=chaos_namespace.name,
        image=Images.Rhel.RHEL9_REGISTRY_GUEST_IMG,
        memory_requests=Images.Rhel.DEFAULT_MEMORY_SIZE,
    ) as vm:
        running_vm(vm=vm, wait_for_interfaces=False, check_ssh_connectivity=False)


@pytest.mark.parametrize(
    "chaos_dv_rhel9, downscaled_storage_provisioner_deployment",
    [
        pytest.param(
            {"storage_class": StorageClassNames.CEPH_RBD_VIRTUALIZATION},
            {"storage_provisioner_deployment": "csi-rbdplugin-provisioner"},
            id="ceph-rbd",
        ),
    ],
    indirect=True,
)
@pytest.mark.polarion("CNV-5438")
def test_ceph_storage_outage(
    skip_test_if_no_ocs_sc,
    chaos_dv_rhel9,
    chaos_vm_rhel9_with_dv,
    downscaled_storage_provisioner_deployment,
):
    """
    This test makes storage unavailable by downscaling the csi-rbdplugin-provisioner deployment to 0
    while creating a vm with a dv, then it verifies
    that the vm can only be created when storage becomes available again.
    """

    # Create a vm with a dv while storage is unavailable.
    chaos_vm_rhel9_with_dv.deploy()
    chaos_vm_rhel9_with_dv.start(wait=False)

    # Verify that dv and vm are not ready while chaos is being injected.
    chaos_dv_rhel9.pvc.wait_for_status(status=PersistentVolumeClaim.Status.PENDING, sleep=TIMEOUT_2MIN)
    expected_status = VirtualMachine.Status.PROVISIONING
    chaos_vm_rhel9_with_dv.wait_for_specific_status(status=expected_status, sleep=TIMEOUT_2MIN)

    # Verify that vm creation is resumed and vm reaches running state after deployment is restored.
    downscaled_storage_provisioner_deployment["deployment"].scale_replicas(
        replica_count=downscaled_storage_provisioner_deployment["initial_replicas"]
    )
    downscaled_storage_provisioner_deployment["deployment"].wait_for_replicas()
    chaos_dv_rhel9.wait_for_dv_success(failure_timeout=TIMEOUT_5MIN)
    chaos_vm_rhel9_with_dv.wait_for_ready_status(status=True)


@pytest.mark.parametrize(
    "chaos_worker_background_process",
    [
        pytest.param(
            {
                "max_duration": TIMEOUT_2MIN,
                "background_command": f"{STRESS_NG}  --io 5 -t 120s",
                "process_name": STRESS_NG,
            },
        ),
    ],
    indirect=True,
)
@pytest.mark.polarion("CNV-6994")
def test_host_io_stress(
    vm_with_nginx_service,
    vm_node_with_chaos_label,
    nginx_monitoring_process,
    chaos_worker_background_process,
):
    """
    This experiment tests the resilience of the worker node and CNV by running an NGINX server within a VM,
    stressing the worker IO and testing to make sure the server
    and its VMI remain responsive throughout chaos duration.
    """
    chaos_worker_background_process.join()
    nginx_monitoring_process.join()
    assert nginx_monitoring_process.exitcode == 0, (
        f"The NGINX server running inside VM {vm_with_nginx_service.vmi.name} failed to remain responsive "
        f"during the sampling duration"
    )

    assert chaos_worker_background_process.exitcode == 0, "Background process execution failed"


@pytest.mark.usefixtures("deleted_pod_by_name_prefix")
@pytest.mark.parametrize("chaos_vms_instancetype_list", [pytest.param({"number_of_vms": 3})], indirect=True)
class TestVMInstanceTypeOperationsPodDelete:
    @pytest.mark.polarion("CNV-11108")
    @pytest.mark.first
    def test_deploy_vm(self, chaos_vms_instancetype_list, deleted_pod_by_name_prefix):
        for vm in chaos_vms_instancetype_list:
            vm.deploy(wait=False)
        for vm in chaos_vms_instancetype_list:
            running_vm(vm=vm)

    @pytest.mark.polarion("CNV-11297")
    @pytest.mark.order(after="test_deploy_vm")
    def test_restart_vm(self, chaos_vms_instancetype_list, deleted_pod_by_name_prefix):
        for vm in chaos_vms_instancetype_list:
            vm.restart(wait=True)

    @pytest.mark.polarion("CNV-11109")
    @pytest.mark.order(after="test_deploy_vm")
    def test_stop_vm(self, chaos_vms_instancetype_list, deleted_pod_by_name_prefix):
        for vm in chaos_vms_instancetype_list:
            vm.stop(wait=False)
        for vm in chaos_vms_instancetype_list:
            vm.wait_for_ready_status(status=None, timeout=TIMEOUT_2MIN)

    @pytest.mark.polarion("CNV-11298")
    @pytest.mark.last
    def test_delete_vm(self, chaos_vms_instancetype_list, deleted_pod_by_name_prefix):
        for vm in chaos_vms_instancetype_list:
            vm.delete(wait=True)

"""
Utilities for Hostpath Provisioner CSI Custom Resource permutations tests
"""

import logging
from contextlib import contextmanager

from ocp_resources.daemonset import DaemonSet
from ocp_resources.persistent_volume import PersistentVolume
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_resources.pod import Pod
from ocp_resources.resource import ResourceEditor
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from utilities.artifactory import get_http_image_url
from utilities.constants import (
    HOSTPATH_PROVISIONER_CSI,
    HOSTPATH_PROVISIONER_OPERATOR,
    HPP_POOL,
    TIMEOUT_1MIN,
    TIMEOUT_2MIN,
    Images,
)
from utilities.infra import (
    ExecCommandOnPod,
    get_resources_by_name_prefix,
)
from utilities.storage import (
    check_disk_count_in_vm,
    create_dv,
    verify_hpp_pool_health,
    verify_hpp_pool_pvcs_are_bound,
    wait_for_hpp_pods,
)

LOGGER = logging.getLogger(__name__)

TYPE = "type"
DV_NAME = "dv_name"
VM_NAME = "vm_name"
HPP_KEY = "hpp-key"
HPP_VAL = "hpp-val1"
NODE_SELECTOR = "node_selector"

HCO_NODE_PLACEMENT = {
    "infra": {},
    "workloads": {
        "nodePlacement": {
            "nodeSelector": {HPP_KEY: HPP_VAL},
        }
    },
}

HPP_NODE_PLACEMENT_DICT = {
    NODE_SELECTOR: {
        "spec": {
            "workload": {
                "nodeSelector": {HPP_KEY: HPP_VAL},
            }
        }
    },
    "affinity": {
        "spec": {
            "workload": {
                "affinity": {
                    "nodeAffinity": {
                        "requiredDuringSchedulingIgnoredDuringExecution": {
                            "nodeSelectorTerms": [
                                {
                                    "matchExpressions": [
                                        {
                                            "key": HPP_KEY,
                                            "operator": "In",
                                            "values": [HPP_VAL],
                                        }
                                    ]
                                }
                            ]
                        }
                    }
                }
            }
        }
    },
    "tolerations": {
        "spec": {
            "workload": {
                "tolerations": [
                    {
                        "effect": "NoExecute",
                        "key": HPP_KEY,
                        "operator": "Exists",
                        "value": HPP_VAL,
                    }
                ]
            }
        }
    },
}


@contextmanager
def update_node_taint(node):
    with ResourceEditor(
        patches={node: {"spec": {"taints": [{"effect": "NoExecute", "key": HPP_KEY, "value": HPP_VAL}]}}}
    ):
        yield


@contextmanager
def cirros_dv_on_hpp(dv_name, storage_class, namespace):
    with create_dv(
        dv_name=dv_name,
        namespace=namespace.name,
        url=get_http_image_url(image_directory=Images.Cirros.DIR, image_name=Images.Cirros.QCOW2_IMG),
        size=Images.Cirros.DEFAULT_DV_SIZE,
        storage_class=storage_class,
    ) as dv:
        yield dv


@contextmanager
def edit_hpp_with_node_selector(hpp_resource, hpp_daemonset, schedulable_nodes, expected_num_of_running_pods=1):
    with ResourceEditor(patches={hpp_resource: HPP_NODE_PLACEMENT_DICT[NODE_SELECTOR]}):
        wait_for_desired_hpp_pods_running(hpp_daemonset=hpp_daemonset, number_of_pods=expected_num_of_running_pods)
        yield
    wait_for_desired_hpp_pods_running(hpp_daemonset=hpp_daemonset, number_of_pods=len(schedulable_nodes))


def wait_for_desired_hpp_pods_running(hpp_daemonset, number_of_pods):
    LOGGER.info(f"Wait for {number_of_pods} hpp pods to be running")
    for sample in TimeoutSampler(
        wait_timeout=TIMEOUT_2MIN,
        sleep=1,
        func=lambda: hpp_daemonset.instance.status.desiredNumberScheduled == number_of_pods,
    ):
        if sample:
            hpp_daemonset.wait_until_deployed()
            break


def wait_for_hpp_csi_pods_to_be_running(hco_namespace, schedulable_nodes):
    hpp_csi_daemonset = DaemonSet(
        name=HOSTPATH_PROVISIONER_CSI,
        namespace=hco_namespace.name,
    )
    wait_for_desired_hpp_pods_running(hpp_daemonset=hpp_csi_daemonset, number_of_pods=len(schedulable_nodes))


def wait_for_hpp_csi_pods_to_be_deleted(client, pod_prefix):
    LOGGER.info(f"Wait for all {pod_prefix} pods to be deleted")
    for hpp_pods in wait_for_hpp_pods(client=client, pod_prefix=pod_prefix):
        if not hpp_pods:
            break


def wait_for_hpp_operator_running(client):
    LOGGER.info(f"Wait for {HOSTPATH_PROVISIONER_OPERATOR} pod to be Running")
    for hpp_operator_pod in wait_for_hpp_pods(client=client, pod_prefix=HOSTPATH_PROVISIONER_OPERATOR):
        if hpp_operator_pod:
            hpp_operator_pod[0].wait_for_status(status=Pod.Status.RUNNING, timeout=TIMEOUT_1MIN)
            break


def delete_hpp_pool_pvcs(hco_namespace):
    LOGGER.info(f"Wait for {HPP_POOL} PVCs to be Deleted")
    pvcs = get_resources_by_name_prefix(
        prefix=HPP_POOL,
        namespace=hco_namespace.name,
        api_resource_name=PersistentVolumeClaim,
    )
    [pvc.delete() for pvc in pvcs]
    [pvc.wait_deleted() for pvc in pvcs]


def delete_hpp_pool_pvs():
    LOGGER.info(f"Delete {HPP_POOL} PVs")
    for pv in PersistentVolume.get():
        pv_instance = pv.exists
        if pv_instance:
            pv_claim_ref_name = pv_instance.get("spec", {}).get("claimRef", {}).get("name")
            if (
                pv_claim_ref_name
                and pv_claim_ref_name.startswith(HPP_POOL)
                and pv_instance.status.phase == PersistentVolume.Status.RELEASED
            ):
                try:
                    pv.delete()
                except TimeoutExpiredError:
                    LOGGER.info("PV was already cleaned-up")


def get_utility_pod_on_specific_node(admin_client, node):
    return [
        pod
        for pod in Pod.get(client=admin_client, label_selector="cnv-test=utility-pods-for-hpp-test")
        if pod.node.name == node
    ][0]


def wait_for_utility_pod_to_be_running(admin_client, node):
    LOGGER.info(f"Wait for utility pod from node {node} to be running")
    for util_pod in TimeoutSampler(
        wait_timeout=TIMEOUT_2MIN,
        sleep=3,
        func=get_utility_pod_on_specific_node,
        admin_client=admin_client,
        node=node,
    ):
        if util_pod:
            util_pod.wait_for_status(status=util_pod.Status.RUNNING, timeout=TIMEOUT_2MIN)
            break


def refresh_utility_pod(admin_client, node):
    # Utility pods were created at the beginning of the test call,
    # but DV's PVC wasn't created yet at that moment,
    # so we need to delete the utility pod and wait till it'll be recreated.
    get_utility_pod_on_specific_node(admin_client=admin_client, node=node).delete(wait=True)
    wait_for_utility_pod_to_be_running(admin_client=admin_client, node=node)
    return get_utility_pod_on_specific_node(admin_client=admin_client, node=node)


def assert_image_location_via_node_utility_pod(dv, storage_pool_path, admin_client):
    node = dv.pvc.selected_node
    utility_pod = refresh_utility_pod(admin_client=admin_client, node=node)
    path = f"{storage_pool_path}/csi/{dv.pvc.instance.spec.volumeName}"
    LOGGER.info(f"Verify disk.img is at /var/{path}")
    out = ExecCommandOnPod(utility_pods=[utility_pod], node=node).exec(command=f"ls /var/{path}/")
    assert out == "disk.img", f"Expected to get disk.img, but got: {out}"


def is_hpp_cr_with_pvc_template(hpp_custom_resource):
    if hpp_custom_resource.instance.spec.pathConfig:
        return False
    return any([template.get("pvcTemplate") for template in hpp_custom_resource.instance.spec.storagePools])


def verify_hpp_cr_installed_successfully(hco_namespace, schedulable_nodes, client, hpp_custom_resource):
    wait_for_hpp_csi_pods_to_be_running(hco_namespace=hco_namespace, schedulable_nodes=schedulable_nodes)
    if is_hpp_cr_with_pvc_template(hpp_custom_resource=hpp_custom_resource):
        verify_hpp_pool_health(
            admin_client=client,
            schedulable_nodes=schedulable_nodes,
            hco_namespace=hco_namespace,
        )


def verify_hpp_cr_deleted_successfully(hco_namespace, schedulable_nodes, client, is_hpp_cr_with_pvc_template=False):
    wait_for_hpp_csi_pods_to_be_deleted(client=client, pod_prefix=HOSTPATH_PROVISIONER_CSI)
    if is_hpp_cr_with_pvc_template:
        wait_for_hpp_csi_pods_to_be_deleted(client=client, pod_prefix=HPP_POOL)
        wait_for_hpp_operator_running(client=client)
        # Check PVCs are still there and Bound
        verify_hpp_pool_pvcs_are_bound(
            schedulable_nodes=schedulable_nodes,
            hco_namespace=hco_namespace,
        )
        # Delete PVCs to cleanup the cluster
        delete_hpp_pool_pvcs(hco_namespace=hco_namespace)
        # Delete the Released PVs to cleanup the cluster
        delete_hpp_pool_pvs()


def check_disk_count_in_vm_and_image_location(vm, dv, hpp_csi_storage_class, admin_client):
    check_disk_count_in_vm(vm=vm)
    assert_image_location_via_node_utility_pod(
        dv=dv,
        admin_client=admin_client,
        storage_pool_path=hpp_csi_storage_class.instance.parameters.storagePool,
    )

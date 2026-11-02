import logging

from kubernetes.dynamic import DynamicClient
from ocp_resources.deployment import Deployment
from ocp_utilities.operators import TIMEOUT_5MIN
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from utilities.constants.components import (
    HOSTPATH_PROVISIONER,
    HOSTPATH_PROVISIONER_OPERATOR,
)
from utilities.constants.namespaces import NamespacesNames
from utilities.constants.timeouts import (
    TIMEOUT_5SEC,
    TIMEOUT_10MIN,
    TIMEOUT_15MIN,
)
from utilities.exceptions import ResourceMismatch
from utilities.infra import get_not_running_pods, get_pod_by_name_prefix
from utilities.storage import verify_hpp_pool_health

LOGGER = logging.getLogger(__name__)


def wait_for_pod_running_by_prefix(
    admin_client,
    namespace_name,
    pod_prefix,
    expected_number_of_pods,
    number_of_consecutive_checks=3,
    timeout=TIMEOUT_5MIN,
):
    samples = TimeoutSampler(
        wait_timeout=timeout,
        sleep=TIMEOUT_5SEC,
        func=get_pod_by_name_prefix,
        client=admin_client,
        pod_prefix=pod_prefix,
        namespace=namespace_name,
        get_all=True,
    )
    pod_names = None
    not_running_pods = None
    try:
        current_check = 0
        for sample in samples:
            if sample:
                not_running_pods = get_not_running_pods(pods=sample)
                pod_names = [pod.name for pod in sample]
                LOGGER.info(f"All {pod_prefix} pods: {pod_names}, not running: {not_running_pods}")
                if not_running_pods:
                    current_check = 0
                else:
                    if expected_number_of_pods == len(sample):
                        current_check += 1
                    else:
                        current_check = 0
            if current_check >= number_of_consecutive_checks:
                return True
    except TimeoutExpiredError:
        LOGGER.error(
            f"timeout waiting for all {pod_prefix} pods in namespace {namespace_name} to reach "
            f"running state, out of {pod_names}, following pods are in not running state: {not_running_pods}"
        )
        raise


def restart_ocs_operator_for_virt_sc(admin_client: DynamicClient) -> None:
    """Restart ocs-operator to trigger ocs-storagecluster-ceph-rbd-virtualization creation.

    OCS creates the virt StorageClass only when the VirtualMachine CRD is present on the cluster.
    After CNV reinstall, ocs-operator must be restarted to reconcile and create the SC.
    This is a workaround for BZ2322458.

    Args:
        admin_client: Kubernetes dynamic client.
    """
    ocs_operator = Deployment(
        client=admin_client,
        name="ocs-operator",
        namespace=NamespacesNames.OPENSHIFT_STORAGE,
        ensure_exists=True,
    )

    if not ocs_operator.instance.spec.replicas:
        raise ResourceMismatch("ocs-operator has zero replicas; cannot restart it to create virt StorageClass")

    LOGGER.info("Waiting for ocs-operator pod to become available before deletion (BZ2322458 workaround)")
    for ocs_pod in TimeoutSampler(
        wait_timeout=TIMEOUT_5MIN,
        sleep=TIMEOUT_5SEC,
        func=get_pod_by_name_prefix,
        client=admin_client,
        pod_prefix="ocs-operator",
        namespace=NamespacesNames.OPENSHIFT_STORAGE,
    ):
        if ocs_pod:
            break

    LOGGER.info("Deleting ocs-operator pod to trigger virt StorageClass creation (BZ2322458 workaround)")
    ocs_pod.delete(wait=True)
    ocs_operator.wait_for_replicas(timeout=TIMEOUT_10MIN)


def validate_hpp_installation(admin_client, cnv_namespace, schedulable_nodes):
    hpp_deployment = Deployment(name=HOSTPATH_PROVISIONER_OPERATOR, namespace=cnv_namespace.name, client=admin_client)
    assert hpp_deployment.exists
    hpp_deployment.wait_for_replicas(timeout=TIMEOUT_15MIN)
    wait_for_pod_running_by_prefix(
        admin_client=admin_client,
        namespace_name=cnv_namespace.name,
        pod_prefix=HOSTPATH_PROVISIONER,
        expected_number_of_pods=len(schedulable_nodes) + int(hpp_deployment.instance.status.replicas),
    )
    verify_hpp_pool_health(
        admin_client=admin_client,
        schedulable_nodes=schedulable_nodes,
        hco_namespace=cnv_namespace,
    )

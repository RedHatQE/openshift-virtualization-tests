import logging

from ocp_resources.cluster_role_binding import ClusterRoleBinding
from ocp_resources.replica_set import ReplicaSet
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.observability.alerts.constants import BAD_HTTPGET_PATH
from tests.observability.utils import get_kubevirt_operator_role_binding_resource
from utilities.constants import TIMEOUT_5MIN, TIMEOUT_5SEC, TIMEOUT_8MIN, VIRT_OPERATOR
from utilities.infra import get_deployment_by_name
from utilities.virt import get_all_virt_pods_with_running_status

LOGGER = logging.getLogger(__name__)


def wait_for_role_binding_resource(admin_client, cluster_role_binding):
    sampler = TimeoutSampler(
        wait_timeout=TIMEOUT_8MIN,
        sleep=TIMEOUT_5SEC,
        func=lambda: list(
            ClusterRoleBinding.get(
                dyn_client=admin_client,
                name=cluster_role_binding,
                cluster_role=cluster_role_binding,
            )
        ),
    )
    try:
        for sample in sampler:
            if sample:
                return
    except TimeoutExpiredError:
        LOGGER.error(f"{cluster_role_binding} ClusterRoleBinding Resource doesn't exists.")
        raise


def wait_kubevirt_operator_role_binding_resource(admin_client):
    sampler = TimeoutSampler(
        wait_timeout=TIMEOUT_8MIN,
        sleep=5,
        func=get_kubevirt_operator_role_binding_resource,
        admin_client=admin_client,
    )

    try:
        for sample in sampler:
            if sample:
                return
    except TimeoutExpiredError:
        LOGGER.error("Kubevirt-operator ClusterRoleBinding not found")
        raise


def get_number_of_virt_pods(admin_client, hco_namespace):
    virt_pods_with_running_status = get_all_virt_pods_with_running_status(
        dyn_client=admin_client, hco_namespace=hco_namespace
    )
    return len(virt_pods_with_running_status.keys())


def wait_for_all_virt_pods_running(admin_client, hco_namespace, number_of_virt_pods):
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_5MIN,
        sleep=TIMEOUT_5SEC,
        exceptions_dict={AssertionError: []},
        func=get_all_virt_pods_with_running_status,
        dyn_client=admin_client,
        hco_namespace=hco_namespace,
    )
    sample = None
    try:
        for sample in samples:
            if len(sample.keys()) == number_of_virt_pods:
                return
    except TimeoutExpiredError:
        LOGGER.error(
            f"{number_of_virt_pods} virt pods were expected to be in running state."
            f"Currently state of virt pods are :{sample}"
        )
        raise


def delete_replica_set_by_prefix(replica_set_prefix, namespace, dyn_client):
    for replica_set in get_replica_set_by_name_prefix(
        dyn_client=dyn_client, replica_set_prefix=replica_set_prefix, namespace=namespace
    ):
        replica_set.delete(wait=True)


def get_replica_set_by_name_prefix(dyn_client, replica_set_prefix, namespace):
    replica_sets = [
        replica
        for replica in ReplicaSet.get(dyn_client=dyn_client, namespace=namespace)
        if replica.name.startswith(replica_set_prefix)
    ]
    assert replica_sets, f"A ReplicaSet with the {replica_set_prefix} prefix does not exist"
    return replica_sets


def wait_hco_csv_updated_virt_operator_httpget(namespace, updated_hco_field):
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_5MIN,
        sleep=TIMEOUT_5SEC,
        func=get_deployment_by_name,
        namespace_name=namespace,
        deployment_name=VIRT_OPERATOR,
    )
    httpget_path = None
    try:
        for sample in samples:
            if sample:
                httpget_path = sample.instance.spec.template.spec.containers[0].readinessProbe.httpGet.path
            LOGGER.info(f"{VIRT_OPERATOR} deployment httpGet path value: {httpget_path}, expected: {updated_hco_field}")
            if httpget_path == updated_hco_field:
                return
    except TimeoutExpiredError:
        LOGGER.error(f"{VIRT_OPERATOR} not updated, httpGet path value: {httpget_path}, expected: {updated_hco_field}")
        raise


def csv_dict_with_bad_virt_operator_httpget_path(hco_csv_dict):
    for deployment in hco_csv_dict["spec"]["install"]["spec"]["deployments"]:
        if deployment["name"] == VIRT_OPERATOR:
            deployment["spec"]["template"]["spec"]["containers"][0]["readinessProbe"]["httpGet"]["path"] = (
                BAD_HTTPGET_PATH
            )
            return hco_csv_dict
    raise ValueError(f"{VIRT_OPERATOR} not found in hco_csv")

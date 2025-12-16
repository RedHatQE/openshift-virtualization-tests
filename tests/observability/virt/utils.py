import logging

from kubernetes.dynamic import DynamicClient
from ocp_resources.replica_set import ReplicaSet
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.observability.constants import BAD_HTTPGET_PATH
from utilities.constants import TIMEOUT_5MIN, TIMEOUT_5SEC, VIRT_OPERATOR
from utilities.infra import get_deployment_by_name

LOGGER = logging.getLogger(__name__)


def delete_replica_set_by_prefix(replica_set_prefix: str, namespace: str, dyn_client: DynamicClient) -> None:
    for replica_set in get_replica_set_by_name_prefix(
        dyn_client=dyn_client, replica_set_prefix=replica_set_prefix, namespace=namespace
    ):
        replica_set.delete(wait=True)


def get_replica_set_by_name_prefix(dyn_client: DynamicClient, replica_set_prefix: str, namespace: str) -> list:
    replica_sets = [
        replica
        for replica in ReplicaSet.get(dyn_client=dyn_client, namespace=namespace)
        if replica.name.startswith(replica_set_prefix)
    ]
    assert replica_sets, f"A ReplicaSet with the {replica_set_prefix} prefix does not exist"
    return replica_sets


def wait_hco_csv_updated_virt_operator_httpget(namespace: str, updated_hco_field: str, client: DynamicClient) -> None:
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_5MIN,
        sleep=TIMEOUT_5SEC,
        func=get_deployment_by_name,
        namespace_name=namespace,
        deployment_name=VIRT_OPERATOR,
        client=client,
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


def csv_dict_with_bad_virt_operator_httpget_path(hco_csv_dict: dict) -> dict:
    for deployment in hco_csv_dict["spec"]["install"]["spec"]["deployments"]:
        if deployment["name"] == VIRT_OPERATOR:
            deployment["spec"]["template"]["spec"]["containers"][0]["readinessProbe"]["httpGet"]["path"] = (
                BAD_HTTPGET_PATH
            )
            return hco_csv_dict
    raise ValueError(f"{VIRT_OPERATOR} not found in hco_csv")

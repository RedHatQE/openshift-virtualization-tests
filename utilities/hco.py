from kubernetes.dynamic.exceptions import ResourceNotFoundError

from ocp_resources.hyperconverged import HyperConverged
from utilities.constants import HYPERCONVERGED_NAME
from utilities.exceptions import ClusterSanityError


def get_hyperconverged_resource(namespace_name):
    hco = HyperConverged(name=HYPERCONVERGED_NAME, namespace=namespace_name)
    if hco.exists:
        return hco
    raise ResourceNotFoundError(
        f"Hyperconverged resource not found in {namespace_name}"
    )


def cluster_sanity_hyperconverged(namespace, expected_hco_status):
    hyperconverged = get_hyperconverged_resource(namespace_name=namespace)
    current_status_conditions = hyperconverged.instance.status.conditions
    mismatch_statuses = get_hco_mismatch_statuses(
        hco_status_conditions=current_status_conditions,
        expected_hco_status=expected_hco_status,
    )

    if mismatch_statuses:
        raise ClusterSanityError(
            err_str=f"{mismatch_statuses} \nHCO is unhealthy. "
            f"Expected {expected_hco_status}, Current: {current_status_conditions}"
        )


def get_hco_mismatch_statuses(hco_status_conditions, expected_hco_status):
    current_status = {
        condition["type"]: condition["status"] for condition in hco_status_conditions
    }
    mismatch_statuses = []

    for condition_type, condition_status in expected_hco_status.items():
        if current_status[condition_type] != condition_status:
            mismatch_statuses.append({condition_type: current_status[condition_type]})

    return mismatch_statuses

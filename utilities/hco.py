import json

from kubernetes.dynamic.exceptions import ResourceNotFoundError

from ocp_resources.hyperconverged import HyperConverged
from ocp_resources.resource import Resource
from utilities.constants import HYPERCONVERGED_NAME
from utilities.exceptions import (
    HyperconvergedNotHealthyCondition,
    HyperconvergedSystemHealthException,
)


def get_hyperconverged_resource(namespace_name):
    hco = HyperConverged(name=HYPERCONVERGED_NAME, namespace=namespace_name)
    if hco.exists:
        return hco
    raise ResourceNotFoundError(
        f"Hyperconverged resource not found in {namespace_name}"
    )


def assert_hyperconverged_health(
    hyperconverged, hyperconverged_status_conditions=None, system_health_status=None
):
    if not hyperconverged_status_conditions:
        hyperconverged_status_conditions = {
            Resource.Condition.AVAILABLE: Resource.Condition.Status.TRUE,
            Resource.Condition.PROGRESSING: Resource.Condition.Status.FALSE,
            Resource.Condition.RECONCILE_COMPLETE: Resource.Condition.Status.TRUE,
            Resource.Condition.DEGRADED: Resource.Condition.Status.FALSE,
            Resource.Condition.UPGRADEABLE: Resource.Condition.Status.TRUE,
        }
    hyperconverged_obj_status = hyperconverged.instance.status

    health_mismatch_conditions = [
        condition
        for condition in hyperconverged_obj_status.conditions
        if condition.type in hyperconverged_status_conditions
        and hyperconverged_status_conditions[condition.type] != condition.status
    ]
    if health_mismatch_conditions:
        raise HyperconvergedNotHealthyCondition(
            "Hyperconverged status condition unhealthy "
            f"expected: {json.dumps(hyperconverged_status_conditions, indent=3)}:"
            f"actual: {json.dumps(health_mismatch_conditions, indent=3,)}"
        )

    if (
        system_health_status
        and hyperconverged_obj_status.systemHealthStatus != system_health_status
    ):
        raise HyperconvergedSystemHealthException(
            f"Hyperconverged systemHealthStatus expected: {system_health_status},"
            f" actual: {hyperconverged_obj_status.systemHealthStatus}"
        )

"""
Strict Reconciliation Tests
"""

import logging

import pytest
from ocp_resources.cluster_role import ClusterRole
from ocp_resources.cluster_role_binding import ClusterRoleBinding
from ocp_resources.config_map import ConfigMap
from ocp_resources.resource import ResourceEditor
from ocp_resources.role import Role
from ocp_resources.role_binding import RoleBinding
from ocp_resources.secret import Secret
from pytest_testconfig import config as py_config
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from utilities.virt import wait_for_kubevirt_conditions

LOGGER = logging.getLogger(__name__)
MANAGED_RESOURCE_NAME1 = "kubevirt-apiserver"
MANAGED_RESOURCE_NAME2 = "kubevirt-ca"

ROLE_BINDING_SUBJECT = [
    {
        "kind": "ServiceAccount",
        "name": "default",
        "namespace": py_config["hco_namespace"],
    }
]

CM_DATA = {"ca-bundle": "No CA Bundle"}
SECRET_DATA = {
    "tls.crt": "Tm8gdGxzLmNydAo=",
    "tls.key": "Tm8gdGxzLmtleQo=",
}


def update_resource(resource, resource_dict):
    updated_resource = ResourceEditor(patches={resource: resource_dict})
    updated_resource.update(backup_resources=True)
    return updated_resource


def update_resource_and_prepare_sampler(resource, resource_dict):
    updated_resource = update_resource(resource=resource, resource_dict=resource_dict)
    LOGGER.info(f"Waiting for resource {resource.kind}: {resource.name} to be reconciled.")
    samples = TimeoutSampler(
        wait_timeout=45,
        sleep=5,
        func=lambda: resource.instance.to_dict(),
    )
    return {
        "updated_resource": updated_resource,
        "samples": samples,
    }


def restore_and_log_error(
    resource,
    updated_resource,
    expected_value,
    actual_value,
):
    updated_resource.restore()  # Only restore explicitly, if virt-operator fails to revert automatically.
    LOGGER.error(f"Timeout waiting for {resource.kind}: {resource.name} resource being reconciled.")
    LOGGER.error(f"Expected: {expected_value}\n Actual: {actual_value}")
    raise


def verify_resource_reconciled(admin_client, hco_namespace, resource):
    if resource.kind == ConfigMap.kind:
        verify_reconciled_configmap_resource(resource=resource, resource_dict={"data": CM_DATA})
    elif resource.kind == Secret.kind:
        verify_reconciled_secret_resource(resource=resource, resource_dict={"data": SECRET_DATA})
    elif resource.kind == Role.kind or resource.kind == ClusterRole.kind:
        resource_dict = resource.instance.to_dict()
        resource_dict["rules"][0]["verbs"].remove("get")
        verify_reconciled_role_or_clusterrole_resource(resource=resource, resource_dict=resource_dict)
    elif resource.kind == RoleBinding.kind or resource.kind == ClusterRoleBinding.kind:
        verify_reconciled_rolebinding_or_clusterrolebinding_resource(
            resource=resource, resource_dict={"subjects": ROLE_BINDING_SUBJECT}
        )
    else:
        raise ValueError(
            f"This Resource Kind: {resource.kind} is not handled currently. "
            f"Explicity specify update_and_wait_for_<resource>_reconcile function and the resource_dict (i.e, patch), "
            f"to be passed to the ResourceEditor"
        )
    wait_for_kubevirt_conditions(admin_client=admin_client, hco_namespace=hco_namespace)


def verify_reconciled_role_or_clusterrole_resource(resource, resource_dict):
    original_resource_dict = resource.instance.to_dict()
    updated_and_reconciled_resource = update_resource_and_prepare_sampler(
        resource=resource, resource_dict=resource_dict
    )
    entity = []
    try:
        for sample in updated_and_reconciled_resource["samples"]:
            sample_rules = sample.get("rules")
            entity.append(sample_rules)
            if original_resource_dict["rules"][0]["verbs"] == sample_rules[0]["verbs"]:
                break
    except TimeoutExpiredError:
        restore_and_log_error(
            resource=resource,
            updated_resource=updated_and_reconciled_resource["updated_resource"],
            expected_value=original_resource_dict["rules"][0]["verbs"],
            actual_value=entity[-1][0]["verbs"],
        )


def verify_reconciled_rolebinding_or_clusterrolebinding_resource(resource, resource_dict):
    original_resource_dict = resource.instance.to_dict()
    updated_and_reconciled_resource = update_resource_and_prepare_sampler(
        resource=resource, resource_dict=resource_dict
    )
    entity = []
    try:
        for sample in updated_and_reconciled_resource["samples"]:
            sample_subjects = sample.get("subjects")
            entity.append(sample_subjects)
            if (
                len(sample_subjects) == len(original_resource_dict["subjects"])
                and original_resource_dict["subjects"][0]["name"] == sample_subjects[0]["name"]
            ):
                break
    except TimeoutExpiredError:
        restore_and_log_error(
            resource=resource,
            updated_resource=updated_and_reconciled_resource["updated_resource"],
            expected_value=original_resource_dict["subjects"][0]["name"],
            actual_value=entity[-1][0]["name"],
        )


def verify_reconciled_configmap_resource(resource, resource_dict):
    updated_and_reconciled_resource = update_resource_and_prepare_sampler(
        resource=resource, resource_dict=resource_dict
    )
    entity = []
    try:
        for sample in updated_and_reconciled_resource["samples"]:
            sample_data = sample.get("data")
            entity.append(sample_data)
            if CM_DATA["ca-bundle"] != sample_data["ca-bundle"]:
                break
    except TimeoutExpiredError:
        restore_and_log_error(
            resource=resource,
            updated_resource=updated_and_reconciled_resource["updated_resource"],
            expected_value="Expecting ca-bundle, after reconcile",
            actual_value=entity[-1]["ca-bundle"],
        )


def verify_reconciled_secret_resource(resource, resource_dict):
    updated_and_reconciled_resource = update_resource_and_prepare_sampler(
        resource=resource, resource_dict=resource_dict
    )
    entity = []
    try:
        for sample in updated_and_reconciled_resource["samples"]:
            sample_data = sample.get("data")
            entity.append(sample_data)
            if SECRET_DATA["tls.crt"] != sample_data["tls.crt"]:
                break
    except TimeoutExpiredError:
        restore_and_log_error(
            resource=resource,
            updated_resource=updated_and_reconciled_resource["updated_resource"],
            expected_value="Expecting tls.crt in base64 format, after reconcile",
            actual_value=entity[-1]["tls.crt"],
        )


@pytest.mark.s390x
@pytest.mark.gating
@pytest.mark.parametrize(
    ("resource_type", "managed_resource_name"),
    [
        pytest.param(
            Role,
            MANAGED_RESOURCE_NAME1,
            marks=(pytest.mark.polarion("CNV-5981")),
            id="test_strict_reconcile_role_only",
        ),
        pytest.param(
            ClusterRole,
            MANAGED_RESOURCE_NAME1,
            marks=(pytest.mark.polarion("CNV-5983")),
            id="test_strict_reconcile_clusterrole_only",
        ),
        pytest.param(
            RoleBinding,
            MANAGED_RESOURCE_NAME1,
            marks=(pytest.mark.polarion("CNV-5982"),),
            id="test_strict_reconcile_rolebinding",
        ),
        pytest.param(
            ClusterRoleBinding,
            MANAGED_RESOURCE_NAME1,
            marks=(pytest.mark.polarion("CNV-5984"),),
            id="test_strict_reconcile_clusterrolebinding",
        ),
        pytest.param(
            ConfigMap,
            MANAGED_RESOURCE_NAME2,
            marks=(pytest.mark.polarion("CNV-5979"),),
            id="test_strict_reconcile_configmap",
        ),
        pytest.param(
            Secret,
            MANAGED_RESOURCE_NAME2,
            marks=(pytest.mark.polarion("CNV-5980")),
            id="test_strict_reconcile_secret",
        ),
    ],
)
def test_strict_reconcile_resources(admin_client, hco_namespace, resource_type, managed_resource_name):
    """Test that virt-operator strictly reconciles managed KubeVirt resources successfully"""
    for resource in resource_type.get(
        dyn_client=admin_client,
        namespace=hco_namespace.name,
        name=managed_resource_name,
    ):
        verify_resource_reconciled(resource=resource, admin_client=admin_client, hco_namespace=hco_namespace)

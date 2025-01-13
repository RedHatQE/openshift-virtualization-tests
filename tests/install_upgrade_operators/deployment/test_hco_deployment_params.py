import pytest

from tests.install_upgrade_operators.deployment.utils import (
    assert_cnv_deployment_container_env_image_not_in_upstream,
    assert_cnv_deployment_container_image_not_in_upstream,
    validate_liveness_probe_fields,
    validate_request_fields,
)
from utilities.constants import (
    ALL_CNV_DEPLOYMENTS,
    HCO_OPERATOR,
    HCO_WEBHOOK,
    VIRT_OPERATOR,
)

pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno]


@pytest.mark.gating
@pytest.mark.parametrize(
    "deployment_by_name",
    [
        pytest.param(
            {"deployment_name": HCO_WEBHOOK},
            marks=(pytest.mark.polarion("CNV-6500")),
            id="test-hco-webhook-liveness-probe",
        ),
        pytest.param(
            {"deployment_name": HCO_OPERATOR},
            marks=(pytest.mark.polarion("CNV-6499")),
            id="test-hco-operator-liveness-probe",
        ),
    ],
    indirect=True,
)
def test_liveness_probe(deployment_by_name):
    """Validates various livenessProbe fields values for different deployment objects"""
    validate_liveness_probe_fields(deployment=deployment_by_name)


@pytest.mark.gating
@pytest.mark.parametrize(
    "deployment_by_name, cpu_min_value",
    [
        pytest.param(
            {"deployment_name": HCO_WEBHOOK},
            5,
            marks=(pytest.mark.polarion("CNV-7187")),
            id="test-hco-webhook-req-param",
        ),
        pytest.param(
            {"deployment_name": HCO_OPERATOR},
            5,
            marks=(pytest.mark.polarion("CNV-7188")),
            id="test-hco-operator-req-param",
        ),
    ],
    indirect=["deployment_by_name"],
)
def test_request_param(deployment_by_name, cpu_min_value):
    """Validates resources.requests fields keys and default cpu values for different deployment objects"""
    validate_request_fields(deployment=deployment_by_name, cpu_min_value=cpu_min_value)


@pytest.mark.gating
@pytest.mark.polarion("CNV-7675")
def test_cnv_deployment_priority_class_name(
    skip_on_hpp_pool,
    cnv_deployment_by_name,
):
    if not cnv_deployment_by_name.instance.spec.template.spec.priorityClassName:
        pytest.fail(
            f"For cnv deployment {cnv_deployment_by_name.name}, spec.template.spec.priorityClassName has not been set."
        )


@pytest.mark.gating
@pytest.mark.polarion("CNV-8289")
def test_no_new_cnv_deployments_added(cnv_deployments_excluding_hpp_pool):
    """
    Since cnv deployments image validations are done via polarion parameterization, this test has been added
    to catch any new cnv deployments that is not part of cnv_deployment_matrix
    """
    new_deployment = [
        deployment.name
        for deployment in cnv_deployments_excluding_hpp_pool
        if list(filter(deployment.name.startswith, ALL_CNV_DEPLOYMENTS)) == []
    ]
    assert not new_deployment, f"New cnv deployment: {new_deployment}, has been added."


@pytest.mark.gating
@pytest.mark.polarion("CNV-8264")
def test_cnv_deployment_container_image(cnv_deployment_by_name):
    assert_cnv_deployment_container_image_not_in_upstream(cnv_deployment=cnv_deployment_by_name)
    assert_cnv_deployment_container_env_image_not_in_upstream(cnv_deployment=cnv_deployment_by_name)


@pytest.mark.polarion("CNV-8374")
def test_cnv_deployment_sno_one_replica_set(skip_if_not_sno_cluster, cnv_deployment_by_name):
    deployment_instance = cnv_deployment_by_name.instance
    deployment_name = cnv_deployment_by_name.name
    deployment_status_replicas = deployment_instance.status.replicas
    deployment_spec_replicas = deployment_instance.spec.replicas

    expected_replica = 2 if deployment_name == VIRT_OPERATOR else 1

    assert deployment_status_replicas == expected_replica, (
        f"On SNO cluster deployment {deployment_name} number of "
        f"status.replicas: {deployment_status_replicas}, expected number of "
        f"replicas: {expected_replica}"
    )
    assert deployment_spec_replicas == expected_replica, (
        f"On SNO cluster deployment {deployment_name} number of "
        f"spec.replicas: {deployment_spec_replicas}, expected number of  replicas: {expected_replica}"
    )

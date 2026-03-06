import pytest

from tests.install_upgrade_operators.deployment.utils import (
    assert_cnv_deployment_container_env_image_not_in_upstream,
    assert_cnv_deployment_container_image_not_in_upstream,
    validate_deployment_request_fields,
    validate_liveness_probe_fields,
)
from utilities.constants import (
    ALL_CNV_DEPLOYMENTS,
    HCO_OPERATOR,
    HCO_WEBHOOK,
    HPP_POOL,
)

pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno, pytest.mark.arm64, pytest.mark.s390x]


@pytest.mark.gating
@pytest.mark.conformance
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
@pytest.mark.conformance
@pytest.mark.polarion("CNV-14635")
def test_deployment_request_param(cnv_deployment_by_name):
    """Validates resources.requests fields keys and default cpu values for different deployment objects"""
    validate_deployment_request_fields(deployment=cnv_deployment_by_name, cpu_min_value=5)


@pytest.mark.gating
@pytest.mark.conformance
@pytest.mark.polarion("CNV-7675")
def test_cnv_deployment_priority_class_name(
    cnv_deployment_by_name,
    xfail_if_jira_76659_open_and_migration_controller_deployment,
):
    if cnv_deployment_by_name.name.startswith(HPP_POOL):
        pytest.xfail("HPP pool deployment doesn't have priority class name")
    elif not cnv_deployment_by_name.instance.spec.template.spec.priorityClassName:
        pytest.fail(
            f"For cnv deployment {cnv_deployment_by_name.name}, spec.template.spec.priorityClassName has not been set."
        )


@pytest.mark.skip_must_gather_collection
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
@pytest.mark.conformance
@pytest.mark.polarion("CNV-8264")
def test_cnv_deployment_container_image(cnv_deployment_by_name):
    assert_cnv_deployment_container_image_not_in_upstream(cnv_deployment=cnv_deployment_by_name)
    assert_cnv_deployment_container_env_image_not_in_upstream(cnv_deployment=cnv_deployment_by_name)

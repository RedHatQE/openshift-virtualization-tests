import logging

import pytest

from tests.install_upgrade_operators.deployment.utils import (
    assert_cnv_deployment_container_env_image_not_in_upstream,
    assert_cnv_deployment_container_image_not_in_upstream,
    validate_liveness_probe_fields,
    validate_request_fields,
)
from utilities.constants.components import (
    HCO_OPERATOR,
    HCO_WEBHOOK,
    HPP_POOL,
    KUBEVIRT_MIGRATION_CONTROLLER,
)

LOGGER = logging.getLogger(__name__)

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
@pytest.mark.conformance
@pytest.mark.polarion("CNV-7675")
def test_cnv_deployment_priority_class_name(subtests, discovered_cnv_deployments, jira_76659_open):
    for deployment in discovered_cnv_deployments:
        with subtests.test(msg=deployment.name):
            if deployment.name.startswith(HPP_POOL):
                LOGGER.info(f"Skipping HPP pool deployment {deployment.name}: no priorityClassName expected")
                continue
            if deployment.name == KUBEVIRT_MIGRATION_CONTROLLER and jira_76659_open:
                pytest.xfail(f"{KUBEVIRT_MIGRATION_CONTROLLER} deployment is not running due to CNV-76659 bug")
            assert deployment.instance.spec.template.spec.priorityClassName, (
                f"Deployment {deployment.name} has no priorityClassName set"
            )


@pytest.mark.gating
@pytest.mark.conformance
@pytest.mark.polarion("CNV-8264")
def test_cnv_deployment_container_image(subtests, discovered_cnv_deployments):
    for deployment in discovered_cnv_deployments:
        with subtests.test(msg=deployment.name):
            assert_cnv_deployment_container_image_not_in_upstream(cnv_deployment=deployment)
            assert_cnv_deployment_container_env_image_not_in_upstream(cnv_deployment=deployment)

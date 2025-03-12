"""
Node Health Check with Self-Node-Remediation(SNR)
"""

import pytest
from ocp_resources.node_health_check import NodeHealthCheck
from ocp_resources.self_node_remediation_templates import SelfNodeRemediationTemplate

from tests.infrastructure.workload_availability.remediation_fencing.constants import (
    NODE_KUBELET_STOP,
    REMEDIATION_OPERATOR_NAMESPACE,
    SELECTOR_MATCH_EXPRESSIONS,
    UNHEALTHY_CONDITIONS,
)
from tests.infrastructure.workload_availability.remediation_fencing.utils import (
    verify_vm_and_node_recovery_after_node_failure,
    wait_for_nodehealthcheck_enabled_phase,
)

pytestmark = [
    pytest.mark.usefixtures(
        "fail_if_compact_cluster_and_jira_47277_open",
    ),
    pytest.mark.node_remediation,
    pytest.mark.destructive,
    pytest.mark.special_infra,
]


@pytest.fixture(scope="module")
def created_nodehealthcheck_snr_object(snr_remediation_template):
    with NodeHealthCheck(
        name="nhc-remediation-snr",
        min_unhealthy=1,
        selector_match_expressions=SELECTOR_MATCH_EXPRESSIONS,
        unhealthy_conditions=UNHEALTHY_CONDITIONS,
        remediation_template=snr_remediation_template,
    ) as nhc_snr:
        wait_for_nodehealthcheck_enabled_phase(nodehealthcheck_object=nhc_snr)
        yield nhc_snr


@pytest.fixture(scope="module")
def snr_remediation_template(checkup_nodehealthcheck_operator_deployment):
    template = next(SelfNodeRemediationTemplate.get(namespace=REMEDIATION_OPERATOR_NAMESPACE))
    return {
        "apiVersion": template.api_version,
        "name": template.name,
        "namespace": template.namespace,
        "kind": template.kind,
    }


@pytest.mark.parametrize(
    "node_operation",
    [
        pytest.param(
            NODE_KUBELET_STOP,
            marks=pytest.mark.polarion("CNV-8991"),
        ),
    ],
    indirect=True,
)
def test_snr_based_vm_and_node_recovery_after_node_failure(
    node_operation,
    created_nodehealthcheck_snr_object,
    nhc_vm_with_run_strategy_always,
    vm_node_before_failure,
    performed_node_operation,
):
    verify_vm_and_node_recovery_after_node_failure(node=vm_node_before_failure, vm=nhc_vm_with_run_strategy_always)

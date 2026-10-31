"""
Node Health Check with FenceAgentRemediation(FAR)
"""

import pytest
from ocp_resources.fence_agent_remediation_templates import FenceAgentsRemediationTemplate
from ocp_resources.node_health_check import NodeHealthCheck

from tests.infrastructure.workload_availability.remediation_fencing.constants import (
    NODE_KUBELET_STOP,
    NODE_SHUTDOWN,
    REMEDIATION_OPERATOR_NAMESPACE,
    SELECTOR_MATCH_EXPRESSIONS,
    UNHEALTHY_CONDITIONS,
)
from tests.infrastructure.workload_availability.remediation_fencing.utils import (
    bmc_details_from_bare_metal_hosts,
    fence_agent_node_parameters,
    verify_vm_and_node_recovery_after_node_failure,
    wait_for_nodehealthcheck_enabled_phase,
)

pytestmark = [pytest.mark.destructive, pytest.mark.special_infra, pytest.mark.node_remediation_ipmi_enabled]


@pytest.fixture(scope="session")
def extracted_bmc_nodes_ipmi_data(admin_client):
    """BMC address and credentials keyed by BareMetalHost name."""
    return bmc_details_from_bare_metal_hosts(admin_client=admin_client)


@pytest.fixture(scope="session")
def generated_node_parameters(extracted_bmc_nodes_ipmi_data, workers):
    """FAR nodeParameters built from BareMetalHost BMC data."""
    return fence_agent_node_parameters(
        bmc_nodes_ipmi_data=extracted_bmc_nodes_ipmi_data,
        worker_node_names=[worker.name for worker in workers],
    )


@pytest.fixture(scope="module")
def far_remediation_template(admin_client, generated_node_parameters):
    with FenceAgentsRemediationTemplate(
        name="nhc-remediation-far",
        namespace=REMEDIATION_OPERATOR_NAMESPACE,
        client=admin_client,
        agent="fence_ipmilan",
        node_parameters=generated_node_parameters,
        shared_parameters={"--lanplus": ""},
    ) as far_resource:
        yield {
            "apiVersion": far_resource.api_version,
            "name": far_resource.name,
            "namespace": far_resource.namespace,
            "kind": far_resource.kind,
        }


@pytest.fixture(scope="module")
def created_nodehealthcheck_far_object(admin_client, far_remediation_template):
    with NodeHealthCheck(
        name="nhc-remediation-far",
        client=admin_client,
        min_unhealthy=1,
        selector_match_expressions=SELECTOR_MATCH_EXPRESSIONS,
        unhealthy_conditions=UNHEALTHY_CONDITIONS,
        remediation_template=far_remediation_template,
    ) as nhc_far:
        wait_for_nodehealthcheck_enabled_phase(nodehealthcheck_object=nhc_far)
        yield nhc_far


@pytest.mark.parametrize(
    "node_operation",
    [
        pytest.param(
            NODE_KUBELET_STOP,
            marks=pytest.mark.polarion("CNV-10608"),
        ),
        pytest.param(
            NODE_SHUTDOWN,
            marks=pytest.mark.polarion("CNV-10607"),
        ),
    ],
    indirect=True,
)
def test_far_based_vm_and_node_recovery_after_node_failure(
    node_operation,
    created_nodehealthcheck_far_object,
    nhc_vm_with_run_strategy_always,
    vm_node_before_failure,
    performed_node_operation,
):
    verify_vm_and_node_recovery_after_node_failure(node=vm_node_before_failure, vm=nhc_vm_with_run_strategy_always)

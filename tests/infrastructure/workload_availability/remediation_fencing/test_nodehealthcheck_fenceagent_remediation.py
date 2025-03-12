"""
Node Health Check with FenceAgentRemediation(FAR)
"""

import pytest
import yaml
from kubernetes.dynamic.exceptions import ResourceNotFoundError
from ocp_resources.config_map import ConfigMap
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
    verify_vm_and_node_recovery_after_node_failure,
    wait_for_nodehealthcheck_enabled_phase,
)

pytestmark = [pytest.mark.destructive, pytest.mark.special_infra, pytest.mark.node_remediation_ipmi_enabled]


@pytest.fixture(scope="session")
def cluster_config_data(kube_system_namespace):
    cluster_creation_config_map = ConfigMap(name="cluster-config-v1", namespace=kube_system_namespace.name)
    if cluster_creation_config_map.exists:
        return yaml.safe_load(cluster_creation_config_map.instance["data"]["install-config"])
    raise ResourceNotFoundError("ConfigMap cluster-config-v1 not found")


@pytest.fixture(scope="session")
def extracted_bmc_nodes_ipmi_data(cluster_config_data):
    bmc_details = {
        host["name"]: {
            "address": host["bmc"]["address"],
            "password": host["bmc"]["password"],
            "username": host["bmc"]["username"],
        }
        for host in cluster_config_data.get("platform", {}).get("baremetal", {}).get("hosts", [])
    }
    if bmc_details:
        return bmc_details
    raise ValueError("Failed to extract BMC data from the provided cluster configuration data")


@pytest.fixture(scope="session")
def generated_node_parameters(extracted_bmc_nodes_ipmi_data):
    node_parameters = {"--ip": {}, "--username": {}, "--password": {}}

    for node_name, params in extracted_bmc_nodes_ipmi_data.items():
        node_parameters["--ip"][node_name] = params["address"].split("//")[1].split(":")[0]
        node_parameters["--username"][node_name] = params["username"]
        node_parameters["--password"][node_name] = params["password"]

    return node_parameters


@pytest.fixture(scope="module")
def far_remediation_template(generated_node_parameters):
    with FenceAgentsRemediationTemplate(
        name="nhc-remediation-far",
        namespace=REMEDIATION_OPERATOR_NAMESPACE,
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
def created_nodehealthcheck_far_object(far_remediation_template):
    with NodeHealthCheck(
        name="nhc-remediation-far",
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

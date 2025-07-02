import logging
from collections import defaultdict

import pytest

from utilities.constants import BRIDGE_MARKER, CLUSTER_NETWORK_ADDONS_OPERATOR
from utilities.infra import get_node_audit_log_line_dict

LOGGER = logging.getLogger(__name__)

POD_SECURITY_AUDIT_VIOLATIONS = "pod-security.kubernetes.io/audit-violations"
POD_SECURITY_REASON = "authorization.k8s.io/reason"
HCO_NAMESPACE = "openshift-cnv"

pytestmark = [pytest.mark.arm64]


class PodSecurityViolationError(Exception):
    pass


@pytest.fixture()
def pod_security_violations_apis_calls(audit_logs, hco_namespace):
    failed_api_calls = defaultdict(list)
    for node, logs in audit_logs.items():
        for audit_log_entry_dict in get_node_audit_log_line_dict(
            logs=logs, node=node, log_entry=POD_SECURITY_AUDIT_VIOLATIONS
        ):
            audit_log_annotations = audit_log_entry_dict["annotations"]
            pod_audit_violations = audit_log_annotations.get(POD_SECURITY_AUDIT_VIOLATIONS)
            pod_security_reason = audit_log_annotations.get(POD_SECURITY_REASON)
            user_agent = audit_log_entry_dict["userAgent"]
            component_namespace = audit_log_entry_dict["objectRef"].get("namespace")

            # Based on https://issues.redhat.com/browse/CNV-39620 <skip-jira-utils-check>
            # ignoring the pod security violation log with the following conditions:
            # userAgent is CNAO, verb is create/update,
            # requestURI contains '/apis/apps/v1/namespace/openshift-cnv/daemonsets',
            # violation reason contains 'to ServiceAccount cnao/openshift-cnv',
            # violation contains 'container "cni-plugins"' or 'container "bridge-marker"'
            if (
                CLUSTER_NETWORK_ADDONS_OPERATOR in user_agent
                and f"/apis/apps/v1/namespaces/{HCO_NAMESPACE}/daemonsets" in audit_log_entry_dict["requestURI"]
                and audit_log_entry_dict["verb"] in ["create", "update"]
                and f'to ServiceAccount "{CLUSTER_NETWORK_ADDONS_OPERATOR}/{HCO_NAMESPACE}' in pod_security_reason
                and ('container "cni-plugins"' or f'container "{BRIDGE_MARKER}"' in pod_audit_violations)
            ):
                continue

            if (
                pod_audit_violations
                and "would violate PodSecurity" in pod_audit_violations
                and component_namespace == hco_namespace.name
            ):
                failed_api_calls[user_agent].append(audit_log_entry_dict)
    return failed_api_calls


@pytest.mark.polarion("CNV-9115")
@pytest.mark.s390x
def test_cnv_pod_security_violation_audit_logs(pod_security_violations_apis_calls):
    LOGGER.info("Test pod security violations API calls:")
    if pod_security_violations_apis_calls:
        formatted_output = ""
        for user_agent, errors in pod_security_violations_apis_calls.items():
            formatted_output += f"User-agent: {user_agent}, Violations:\n"
            for error in errors:
                formatted_output += f"\t{error}\n"
            formatted_output += f"{'-' * 100}\n"
        raise PodSecurityViolationError(formatted_output)

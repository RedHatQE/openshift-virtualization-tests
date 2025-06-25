import logging
from collections import defaultdict

import pytest
from packaging.version import Version

from utilities.infra import get_node_audit_log_line_dict

LOGGER = logging.getLogger(__name__)

DEPRECATED_API_MAX_VERSION = "1.25"
DEPRECATED_API_LOG_ENTRY = '"k8s.io/deprecated":"true"'


class DeprecatedAPIError(Exception):
    """
    Raises when calling a deprecated API
    """

    def __init__(self, message):
        self.message = message
        super().__init__(self.message)


def skip_component_check(user_agent, deprecation_version):
    ignored_components_list = [
        "cluster-version-operator",
        "kube-controller-manager",
        "cluster-policy-controller",
        "jaeger-operator",
        "rook",
    ]

    # Skip if deprecated version does not exist
    if not deprecation_version:
        return True

    # Skip OCP core and kubernetes components
    for comp_name in ignored_components_list:
        if comp_name in user_agent:
            return True

    # Skip if deprecated version is greater than DEPRECATED_API_MAX_VERSION
    if Version(deprecation_version) > Version(DEPRECATED_API_MAX_VERSION):
        return True

    return False


def failure_not_in_component_list(component, annotations, audit_log_entry_dict):
    object_ref_str = "objectRef"

    for failure_entry in component:
        if (
            annotations != failure_entry["annotations"]
            and audit_log_entry_dict[object_ref_str] != failure_entry[object_ref_str]
        ):
            return True

    return False


def format_printed_deprecations_dict(deprecated_calls):
    formatted_output = ""
    for comp, errors in deprecated_calls.items():
        formatted_output += f"Component: {comp}\n\nCalls:\n"
        for error in errors:
            formatted_output += f"\t{error}\n"
        formatted_output += "\n\n\n"

    return formatted_output


@pytest.fixture()
def deprecated_apis_calls(audit_logs):
    """Go over control plane nodes audit logs and look for calls using deprecated APIs"""
    failed_api_calls = defaultdict(list)
    for node, logs in audit_logs.items():
        for audit_log_entry_dict in get_node_audit_log_line_dict(
            logs=logs, node=node, log_entry=DEPRECATED_API_LOG_ENTRY
        ):
            annotations = audit_log_entry_dict["annotations"]
            user_agent = audit_log_entry_dict["userAgent"]
            component = failed_api_calls.get(user_agent)

            if skip_component_check(
                user_agent=user_agent,
                deprecation_version=annotations.get("k8s.io/removed-release"),
            ):
                continue

            # Add new component to dict if not already in it
            if not component:
                failed_api_calls[user_agent].append(audit_log_entry_dict)

            # Add failure dict if failure annotations and object_ref not in component list of errors
            else:
                if failure_not_in_component_list(
                    component=component,
                    annotations=annotations,
                    audit_log_entry_dict=audit_log_entry_dict,
                ):
                    failed_api_calls[user_agent].append(audit_log_entry_dict)

    return failed_api_calls


@pytest.mark.s390x
@pytest.mark.polarion("CNV-6679")
@pytest.mark.order("last")
@pytest.mark.s390x
def test_deprecated_apis_in_audit_logs(deprecated_apis_calls):
    LOGGER.info(f"Test deprecated API calls, max version for deprecation check: {DEPRECATED_API_MAX_VERSION}")
    if deprecated_apis_calls:
        raise DeprecatedAPIError(message=format_printed_deprecations_dict(deprecated_calls=deprecated_apis_calls))

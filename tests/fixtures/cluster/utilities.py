"""Cluster utility fixtures and audit-log parsing helpers."""

import logging
import re
from bisect import bisect_left
from collections import defaultdict
from datetime import datetime

import pytest
from ocp_resources.daemonset import DaemonSet
from ocp_resources.resource import ResourceEditor
from ocp_resources.secret import Secret
from ocp_resources.service_account import ServiceAccount

from tests.fixtures.cluster.auth import ACCESS_TOKEN, HTPASSWD_PROVIDER_DICT, HTTP_SECRET_NAME
from utilities.constants.cluster import CNV_TEST_SERVICE_ACCOUNT, UTILITY
from utilities.constants.namespaces import NamespacesNames
from utilities.infra import (
    add_scc_to_service_account,
    generate_openshift_pull_secret_file,
    get_daemonset_yaml_file_with_image_hash,
    get_utility_pods_from_nodes,
)

LOGGER = logging.getLogger(__name__)

AUDIT_LOG_NAME_PATTERN = re.compile(r"audit-(\d{4}-\d{2}-\d{2})T(\d{2})-(\d{2})-(\d{2}\.\d{3})\.log")
ACTIVE_AUDIT_LOG_NAME = "audit.log"


def _rotated_audit_log_timestamp(*, log_name: str) -> datetime | None:
    """Extract the timestamp embedded in a rotated audit log file name.

    Args:
        log_name: Audit log file name, as reported by ``oc adm logs``.

    Returns:
        The timestamp of the rotated log, or None when the name is not a rotated audit log
        or carries a timestamp that does not parse.
    """
    match = AUDIT_LOG_NAME_PATTERN.match(string=log_name)
    if not match:
        LOGGER.info(f"Skipping non-audit file: {log_name}")
        return None

    timestamp_str = f"{match.group(1)}T{match.group(2)}:{match.group(3)}:{match.group(4)}"
    try:
        return datetime.strptime(timestamp_str, "%Y-%m-%dT%H:%M:%S.%f")
    except ValueError as err:
        LOGGER.warning(f"Invalid timestamp in log {log_name}: {err}")
        return None


def audit_log_files_per_node(*, command_output: list[str]) -> dict[str, list[str | tuple[str, datetime]]]:
    """Group audit log file names by the node that holds them.

    Args:
        command_output: Lines reported by ``oc adm logs``, each formatted as ``<node> <log-name>``.

    Returns:
        Node name to its audit log entries, where the active log is a plain name and each
        rotated log is a ``(name, timestamp)`` tuple.
    """
    nodes_logs: dict[str, list[str | tuple[str, datetime]]] = defaultdict(list)
    for line in command_output:
        parts = line.split()
        if len(parts) != 2:
            LOGGER.error(f"Fail to get log: {line}")
            continue

        node, log_name = parts
        if log_name == ACTIVE_AUDIT_LOG_NAME:
            nodes_logs[node].append(log_name)
            continue

        log_timestamp = _rotated_audit_log_timestamp(log_name=log_name)
        if log_timestamp:
            nodes_logs[node].append((log_name, log_timestamp))

    return nodes_logs


def relevant_audit_logs(*, log_entries: list[str | tuple[str, datetime]], session_start_time: datetime) -> list[str]:
    """Select the audit logs that can hold events of the current session.

    Args:
        log_entries: Audit log entries of a single node, as returned by ``audit_log_files_per_node``.
        session_start_time: Start time of the current test session.

    Returns:
        The active log plus every rotated log from the one immediately preceding
        ``session_start_time`` to the newest one.
    """
    active_logs = [log_name for log_name in log_entries if isinstance(log_name, str)]
    rotated_with_timestamps = sorted(
        (entry for entry in log_entries if isinstance(entry, tuple)), key=lambda entry: entry[1]
    )
    timestamps = [timestamp for _, timestamp in rotated_with_timestamps]
    start_index = max(0, bisect_left(a=timestamps, x=session_start_time) - 1)
    relevant_rotated = [log_name for log_name, _ in rotated_with_timestamps[start_index:]]

    return relevant_rotated + active_logs


@pytest.fixture(scope="session")
def generated_pulled_secret(
    is_production_source,
    installing_cnv,
    admin_client,
):
    if is_production_source and installing_cnv:
        return
    return generate_openshift_pull_secret_file()


@pytest.fixture(scope="session")
def cnv_tests_utilities_service_account(admin_client, cnv_tests_utilities_namespace, installing_cnv):
    if installing_cnv:
        yield
    else:
        with ServiceAccount(
            client=admin_client,
            name=CNV_TEST_SERVICE_ACCOUNT,
            namespace=cnv_tests_utilities_namespace.name,
        ) as service_account:
            add_scc_to_service_account(
                namespace=cnv_tests_utilities_namespace.name,
                scc_name="privileged",
                sa_name=service_account.name,
            )
            yield service_account


@pytest.fixture(scope="session")
def utility_daemonset(
    admin_client,
    installing_cnv,
    generated_pulled_secret,
    cnv_tests_utilities_namespace,
    cnv_tests_utilities_service_account,
):
    """
    Deploy utility daemonset into the cnv-tests-utilities namespace.

    This daemonset deploys a pod on every node with hostNetwork and the main usage is to run commands on the hosts.
    For example to create linux bridge and other components related to the host configuration.
    """
    if installing_cnv:
        yield
    else:
        modified_ds_yaml_file = get_daemonset_yaml_file_with_image_hash(
            generated_pulled_secret=generated_pulled_secret,
            service_account=cnv_tests_utilities_service_account,
        )
        with DaemonSet(client=admin_client, yaml_file=modified_ds_yaml_file) as ds:
            ds.wait_until_deployed()
            yield ds


@pytest.fixture(scope="session")
def leftovers_cleanup(admin_client, cnv_tests_utilities_namespace, identity_provider_config):
    LOGGER.info("Checking for leftover resources")
    secret = Secret(
        client=admin_client,
        name=HTTP_SECRET_NAME,
        namespace=NamespacesNames.OPENSHIFT_CONFIG,
    )
    ds = None
    if cnv_tests_utilities_namespace:
        ds = DaemonSet(
            client=admin_client,
            name=UTILITY,
            namespace=cnv_tests_utilities_namespace.name,
        )
    #  Delete Secret and DaemonSet created by us.
    for resource_ in (secret, ds):
        if resource_ and resource_.exists:
            resource_.delete(wait=True)

    #  Remove leftovers from OAuth
    if not identity_provider_config:
        # When running CI (k8s) OAuth is not exists on the cluster.
        LOGGER.warning("OAuth does not exist on the cluster")
        return

    identity_providers_spec = identity_provider_config.instance.to_dict()["spec"]
    identity_providers_token = identity_providers_spec.get("tokenConfig")
    identity_providers = identity_providers_spec.get("identityProviders", [])

    if ACCESS_TOKEN == identity_providers_token:
        identity_providers_spec["tokenConfig"] = None

    if HTPASSWD_PROVIDER_DICT in identity_providers:
        identity_providers.pop(identity_providers.index(HTPASSWD_PROVIDER_DICT))
        identity_providers_spec["identityProviders"] = identity_providers or None

    r_editor = ResourceEditor(
        patches={
            identity_provider_config: {
                "metadata": {"name": identity_provider_config.name},
                "spec": identity_providers_spec,
            }
        }
    )
    r_editor.update()


@pytest.fixture(scope="session")
def workers_utility_pods(admin_client, workers, utility_daemonset, installing_cnv):
    """
    Get utility pods from worker nodes.
    When the tests start we deploy a pod on every worker node in the cluster using a daemonset.
    These pods have a label of cnv-test=utility and they are privileged pods with hostnetwork=true
    """
    if installing_cnv:
        return None
    return get_utility_pods_from_nodes(
        nodes=workers,
        admin_client=admin_client,
        label_selector="cnv-test=utility",
    )


@pytest.fixture(scope="session")
def control_plane_utility_pods(admin_client, installing_cnv, control_plane_nodes, utility_daemonset):
    """
    Get utility pods from control plane nodes.
    When the tests start we deploy a pod on every control plane node in the cluster using a daemonset.
    These pods have a label of cnv-test=utility and they are privileged pods with hostnetwork=true
    """
    if installing_cnv:
        return None
    return get_utility_pods_from_nodes(
        nodes=control_plane_nodes,
        admin_client=admin_client,
        label_selector="cnv-test=utility",
    )

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pprint import pformat
from threading import Thread
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ocp_resources.subscription import Subscription
    from ocp_utilities.monitoring import Prometheus

from deepdiff import DeepDiff
from kubernetes.dynamic import DynamicClient
from kubernetes.dynamic.exceptions import NotFoundError, ResourceNotFoundError
from ocp_resources.cluster_service_version import ClusterServiceVersion
from ocp_resources.cluster_version import ClusterVersion
from ocp_resources.hyperconverged import HyperConverged
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.machine_config_pool import MachineConfigPool
from ocp_resources.namespace import Namespace
from ocp_resources.resource import Resource, ResourceEditor
from packaging.version import Version
from pyhelper_utils.shell import run_command
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.install_upgrade_operators.constants import WORKLOAD_UPDATE_STRATEGY_KEY_NAME, WORKLOADUPDATEMETHODS
from tests.install_upgrade_operators.utils import wait_for_install_plan
from tests.upgrade_params import EUS
from utilities.constants import (
    BASE_EXCEPTIONS_DICT,
    FIRING_STATE,
    HCO_CATALOG_SOURCE,
    IMAGE_CRON_STR,
    TIMEOUT_5SEC,
    TIMEOUT_10MIN,
    TIMEOUT_10SEC,
    TIMEOUT_20MIN,
    TIMEOUT_30MIN,
    TIMEOUT_30SEC,
    TIMEOUT_180MIN,
    TSC_FREQUENCY,
    NamespacesNames,
)
from utilities.data_collector import write_to_file
from utilities.hco import ResourceEditorValidateHCOReconcile, wait_for_hco_conditions, wait_for_hco_version
from utilities.infra import (
    get_clusterversion,
    get_csv_by_name,
    get_deployments,
    get_pod_by_name_prefix,
    get_pods,
    stable_channel_released_to_prod,
    wait_for_consistent_resource_conditions,
    wait_for_version_explorer_response,
)
from utilities.operator import (
    approve_install_plan,
    get_hco_csv_name_by_version,
    update_image_in_catalog_source,
    update_subscription_source,
    wait_for_mcp_update_completion,
)

LOGGER = logging.getLogger(__name__)
TIER_2_PODS_TYPE = "tier-2"


def wait_for_pod_replacement(client, hco_namespace, pod_name, related_images, status_dict):
    """
    Wait for a new pod to be created and running


    Args:
        client (DynamicClient): OCP Client to use
        hco_namespace (Namespace): HCO namespace
        pod_name (str): Pod name
        related_images (dict): "image" and "strategy" information

    Raises:
        TimeoutExpiredError: if a pod with the expected image is not created or if the pod is not running.
    """

    def _is_expected_pod_image(_client, _pod_name, _hco_namespace, _related_images):
        _pods = get_pod_by_name_prefix(
            client=_client,
            pod_prefix=_pod_name,
            namespace=_hco_namespace,
            get_all=True,
        )
        _replaced_pods = [_pod for _pod in _pods if _pod.instance.spec.containers[0].image in _related_images]

        if len(_pods) == len(_replaced_pods):
            return _replaced_pods
        LOGGER.warning(f"{len(_pods)}/{len(_replaced_pods)} {_pod_name} pods has been replaced.")

    LOGGER.info(f"Verify new pod {pod_name} replacement.")

    new_pod_sampler = TimeoutSampler(
        wait_timeout=TIMEOUT_30MIN,
        sleep=1,
        func=_is_expected_pod_image,
        _client=client,
        _pod_name=pod_name,
        _hco_namespace=hco_namespace,
        _related_images=related_images,
    )

    new_pods = []
    try:
        for pods in new_pod_sampler:
            if pods:
                new_pods = pods
                break
    except TimeoutExpiredError:
        LOGGER.error(f"For {pod_name} type new pods are not created, expected: {related_images}")
        status_dict[pod_name] = False
    for new_pod in new_pods:
        status_running = new_pod.Status.RUNNING
        LOGGER.info(f"Wait for {new_pod.name} to be {status_running}")
        new_pod.wait_for_status(status=status_running, timeout=TIMEOUT_30MIN)


def wait_for_pods_replacement_by_type(client, hco_namespace, related_images, pod_list):
    LOGGER.info("Wait for pod replacement.")
    threads = []
    status_dict = {}

    for pod_name in pod_list:
        sub_thread = Thread(
            name=pod_name,
            target=wait_for_pod_replacement,
            kwargs={
                "client": client,
                "hco_namespace": hco_namespace,
                "pod_name": pod_name,
                "related_images": related_images,
                "status_dict": status_dict,
            },
        )
        threads.append(sub_thread)
        sub_thread.start()

    for thread in threads:
        thread.join()

    assert not status_dict, f"Failures during operator pods replacement. Failed processes:\n{status_dict}"


def wait_for_expected_pods_exist(
    client,
    hco_namespace,
    expected_images,
):
    """
    Verifies that only pods with expected images (taken from target CSV) exist.

    Args:
        client (DynamicClient): OCP Client to use
        hco_namespace (Namespace): HCO namespace
        expected_images (list): of expected images

    Raises:
        AssertionError if there are pods' images which do not match the expected images list
    """
    LOGGER.info("Verify all cnv pods have the right image and no leftover pods exist")

    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_10MIN,
        sleep=TIMEOUT_10SEC,
        func=get_pods_with_mismatch_image,
        client=client,
        hco_namespace=hco_namespace,
        expected_images=expected_images,
    )
    sample = None
    try:
        for sample in samples:
            if not sample:
                return
            else:
                LOGGER.info(f"Following pods images are waiting to be replaced: {sample}")
    except TimeoutExpiredError:
        LOGGER.error(
            f"The following pods images were not replaced / removed: {sample}.Expected images: {expected_images}"
        )
        raise


def get_pods_with_mismatch_image(client, hco_namespace, expected_images):
    cnv_pods = get_pods(client=client, namespace=hco_namespace)
    mismatching_pods = {}
    for pod in cnv_pods:
        pod_instance = pod.instance
        if pod_instance.spec.containers[0].image not in expected_images and not (
            IMAGE_CRON_STR in pod.name or pod_instance.status.phase in pod.Status.SUCCEEDED
        ):
            mismatching_pods[pod.name] = {pod_instance.spec.containers[0].image: pod_instance.status.phase}
    LOGGER.info(f"Mismatch pod: {mismatching_pods}")
    return mismatching_pods


def get_nodes_taints(nodes):
    """
    Capture taints information out of all nodes and create a dictionary.

    Args:
        nodes (list): list of Node objects

    Returns:
        nodes_dict (dict): dictionary containing taints information associated with every nodes
    """
    return {node.name: node.instance.spec.taints for node in nodes}


def verify_nodes_taints_after_upgrade(nodes, nodes_taints_before_upgrade):
    """
    Verify that none of the nodes taints changed after cnv upgrade

    Args:
        nodes (list): list of Node objects
        nodes_taints_before_upgrade(dict): dictionary containing node taints
    """
    nodes_taints_after_upgrade = get_nodes_taints(nodes=nodes)
    taint_diff = {
        node_name: {
            "before": nodes_taints_before_upgrade[node_name],
            "after": nodes_taints_after_upgrade[node_name],
        }
        for node_name in nodes_taints_after_upgrade
        if nodes_taints_after_upgrade[node_name] != nodes_taints_before_upgrade[node_name]
    }
    assert not taint_diff, f"Mismatch in node taints found after upgrade: {taint_diff}"


def get_nodes_labels(nodes, cnv_upgrade):
    """
    Based on cnv_upgrade type being used, this function captures appropriate labels information from the nodes.
    For ocp upgrade, any labels containing Resource.ApiGroup.KUBEVIRT_IO string would be collected to ensure such
    labels remains unaltered post ocp upgrade, while for cnv upgrade non-cnv labels would be checked to ensure no
    accidental modification happened to those during upgrade.
    Please note: node.labels are tuples

    Args:
        nodes (list): list of Node objects
        cnv_upgrade (bool): True if cnv upgrade else False

    Returns:
        nodes_dict (dict): dictionary containing labels and taints information associated with every nodes
    """
    return {
        node.name: {
            label_key: label_value
            for label_key, label_value in node.labels
            if (cnv_upgrade and Resource.ApiGroup.KUBEVIRT_IO not in label_key)
            or (not cnv_upgrade and Resource.ApiGroup.KUBEVIRT_IO in label_key and TSC_FREQUENCY not in label_key)
        }
        for node in nodes
    }


def verify_nodes_labels_after_upgrade(nodes, nodes_labels_before_upgrade, cnv_upgrade):
    """
    Validate that node labels after upgrade are as expected, in case of y stream upgrade ensures that expected changes
    in node labels don't cause failure

    Args:
        nodes (list): List of node objects
        nodes_labels_before_upgrade (dict): dictionary containing labels of all nodes in the cluster
        cnv_upgrade (boolean): indicates if a given upgrade is ocp or cnv upgrade

    Raises:
        AssertionError: Asserts on node label mismatch
    """
    nodes_labels_after_upgrade = get_nodes_labels(nodes=nodes, cnv_upgrade=cnv_upgrade)
    nodes_changed = [
        node_with_label_diff
        for node_name in nodes_labels_after_upgrade
        if (
            node_with_label_diff := get_node_with_label_value_diff(
                labels_before_upgrade=nodes_labels_before_upgrade[node_name],
                labels_after_upgrade=nodes_labels_after_upgrade[node_name],
                node_name=node_name,
            )
        )
    ]
    assert not nodes_changed, f"Mismatch in the following nodes labels after upgrade: {nodes_changed}"


def get_node_with_label_value_diff(labels_before_upgrade, labels_after_upgrade, node_name):
    """
    Logging the labels values changes by category for a specific node.

    Args:
        labels_before_upgrade(dict): before upgrade labels values.
        labels_after_upgrade(dict): after upgrade labels values.
        node_name(string): the name of the node.

    Returns:
        string: the name of the node.
    """
    diff_dict = DeepDiff(t1=labels_before_upgrade, t2=labels_after_upgrade, verbose_level=2)
    if diff_dict:
        format_dict_output(diff_dict=diff_dict)
        LOGGER.error(f"Mismatch for {node_name}:\n{pformat(diff_dict)}")
        return node_name


def format_dict_output(diff_dict):
    # removes the '[root]' chars around each label name
    for key, labels_dict in diff_dict.items():
        formatted_labels_dict = {
            label_name.lstrip("root[").strip("']"): label_value for label_name, label_value in labels_dict.items()
        }
        diff_dict.update({key: formatted_labels_dict})


def wait_for_hco_upgrade(client: DynamicClient, hco_namespace: Namespace, cnv_target_version: str) -> None:
    LOGGER.info(f"Wait for HCO version to be updated to {cnv_target_version}.")
    wait_for_hco_version(
        client=client,
        hco_ns_name=hco_namespace.name,
        cnv_version=cnv_target_version,
    )
    LOGGER.info("Wait for HCO stable conditions after upgrade")
    wait_for_hco_conditions(
        admin_client=client,
        hco_namespace=hco_namespace,
        wait_timeout=TIMEOUT_20MIN,
    )


def wait_for_post_upgrade_deployments_replicas(client, hco_namespace):
    LOGGER.info("Wait for deployments replicas.")
    for deployment in get_deployments(admin_client=client, namespace=hco_namespace.name):
        deployment.wait_for_replicas(timeout=TIMEOUT_10MIN)


def verify_upgrade_cnv(client, hco_namespace, expected_images):
    wait_for_post_upgrade_deployments_replicas(client=client, hco_namespace=hco_namespace)

    wait_for_expected_pods_exist(
        client=client,
        hco_namespace=hco_namespace,
        expected_images=expected_images,
    )


def approve_cnv_upgrade_install_plan(client, hco_namespace, hco_target_csv_name, is_production_source):
    LOGGER.info("Get the upgrade install plan.")
    install_plan = wait_for_install_plan(
        client=client,
        hco_namespace=hco_namespace,
        hco_target_csv_name=hco_target_csv_name,
        is_production_source=is_production_source,
    )

    LOGGER.info(f"Approve the upgrade install plan {install_plan.name} to trigger the upgrade.")
    approve_install_plan(install_plan=install_plan)


def wait_for_cluster_version_stable_conditions(admin_client):
    wait_for_consistent_resource_conditions(
        dynamic_client=admin_client,
        expected_conditions={
            Resource.Condition.AVAILABLE: Resource.Condition.Status.TRUE,
            Resource.Condition.PROGRESSING: Resource.Condition.Status.FALSE,
            Resource.Condition.FAILING: Resource.Condition.Status.FALSE,
        },
        resource_kind=ClusterVersion,
        condition_key1="type",
        condition_key2="status",
        polling_interval=30,
        exceptions_dict={
            **BASE_EXCEPTIONS_DICT,
            NotFoundError: [],
            ResourceNotFoundError: [],
        },
    )


def wait_for_cluster_version_state_and_version(cluster_version, target_ocp_version):
    def _cluster_version_state_and_version(_cluster_version, _target_ocp_version):
        cluster_version_status_history = _cluster_version.instance.status.history[0]
        LOGGER.info(f"clusterversion status.histroy: {cluster_version_status_history}")
        return (
            cluster_version_status_history.state == _cluster_version.Status.COMPLETED
            and cluster_version_status_history.version == target_ocp_version
        )

    try:
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_180MIN,
            sleep=10,
            func=_cluster_version_state_and_version,
            _cluster_version=cluster_version,
            _target_ocp_version=target_ocp_version,
        ):
            if sample:
                return

    except TimeoutExpiredError:
        LOGGER.error(
            "Timeout reached while upgrading OCP. "
            f"clusterversion conditions: {cluster_version.instance.status.conditions}"
        )
        raise


def extract_ocp_version_from_ocp_image(ocp_image_url: str) -> str:
    """
    Extract the OCP version from the OCP URL input.
    Expected inputs / output examples:
      quay.io/openshift-release-dev/ocp-release:4.10.9-x86_64 -> 4.10.9
      quay.io/openshift-release-dev/ocp-release:4.10.0-rc.6-x86_64 -> 4.10.0-rc.6
      registry.ci.openshift.org/ocp/release:4.11.0-0.nightly-2022-04-01-172551 -> 4.11.0-0.nightly-2022-04-01-172551
      registry.ci.openshift.org/ocp/release:4.11.0-0.ci-2022-04-06-165430 -> 4.11.0-0.ci-2022-04-06-165430
    """
    ocp_version_match = re.search(r"release:(.*?)(?:-x86_64$|$)", ocp_image_url)
    ocp_version = ocp_version_match.group(1) if ocp_version_match else None
    assert ocp_version, f"Cannot extract OCP version. OCP image url: {ocp_image_url} is invalid"
    LOGGER.info(f"OCP version {ocp_version} extracted from ocp image: {ocp_version}")
    return ocp_version


def run_ocp_upgrade_command(ocp_image_url: str) -> None:
    LOGGER.info(f"Executing OCP upgrade command to image {ocp_image_url}")
    rc, out, err = run_command(
        command=[
            "oc",
            "adm",
            "upgrade",
            "--force=true",
            "--allow-explicit-upgrade",
            "--allow-upgrade-with-warnings",
            "--to-image",
            ocp_image_url,
        ],
        verify_stderr=False,
        check=False,
    )
    assert rc, f"OCP upgrade command failed. out: {out}. err: {err}"


def verify_upgrade_ocp(
    admin_client,
    target_ocp_version,
    machine_config_pools_list,
    initial_mcp_conditions,
    nodes,
):
    wait_for_cluster_version_state_and_version(
        cluster_version=get_clusterversion(client=admin_client),
        target_ocp_version=target_ocp_version,
    )
    wait_for_mcp_update_completion(
        machine_config_pools_list=machine_config_pools_list,
        initial_mcp_conditions=initial_mcp_conditions,
        nodes=nodes,
        timeout=TIMEOUT_180MIN,
    )

    wait_for_cluster_version_stable_conditions(
        admin_client=admin_client,
    )


def get_all_firing_cnv_alerts(prometheus: Prometheus, file_name: str, base_directory: str) -> list[dict[str, Any]]:
    """Returns all currently firing CNV alerts.

    Args:
        prometheus: Prometheus client instance.
        file_name: Name of the file to write alert data to.
        base_directory: Directory path for writing alert data files.

    Returns:
        List of alert dicts for firing alerts with kubernetes_operator_part_of=kubevirt.
    """
    cnv_alerts = [
        alert
        for alert in prometheus.alerts()["data"]["alerts"]
        if alert["labels"].get("kubernetes_operator_part_of") == "kubevirt" and alert["state"] == FIRING_STATE
    ]
    LOGGER.info(f"Firing CNV alerts: {[alert['labels']['alertname'] for alert in cnv_alerts]}")
    write_to_file(
        base_directory=base_directory,
        file_name=file_name,
        content=json.dumps(cnv_alerts),
    )
    return cnv_alerts


def query_alerts_fired_in_range(
    prometheus: Prometheus,
    start_time: datetime,
) -> list[dict[str, Any]]:
    """Returns raw CNV firing-alert results since start_time using a range vector selector.

    Uses an instant query with a PromQL range vector selector to retrieve all alert
    samples since start_time, including alerts that have since resolved.

    Args:
        prometheus: Prometheus client instance.
        start_time: Start of the lookback window.

    Returns:
        List of result dicts, each containing 'metric' labels and 'values' timestamps.
    """
    duration_seconds = int((datetime.now(tz=timezone.utc) - start_time).total_seconds())
    query = f'ALERTS{{alertstate="{FIRING_STATE}",kubernetes_operator_part_of="kubevirt"}}[{duration_seconds}s]'
    return prometheus.query_sampler(query=query)


def get_alerts_fired_during_upgrade(
    prometheus: Prometheus,
    before_upgrade_alert_names: set[str],
    upgrade_start_time: datetime,
    base_directory: str,
) -> dict[str, list[dict[str, Any]]]:
    """Returns new alerts that fired during the upgrade, grouped by alertname.

    Uses an instant query with a PromQL range vector selector over the upgrade window to
    catch all alerts that reached firing state, including those that resolved before this
    function runs. Filters out alerts that were already firing before the upgrade started.

    Args:
        prometheus: Prometheus client instance.
        before_upgrade_alert_names: Alert names captured before upgrade.
        upgrade_start_time: Datetime of when the upgrade started.
        base_directory: Directory path for writing alert data files.

    Returns:
        Dict mapping alertname to the list of full result objects (metric + values) for that alert.
    """
    fired_alerts = query_alerts_fired_in_range(
        prometheus=prometheus,
        start_time=upgrade_start_time,
    )

    alerts_by_name: dict[str, list[dict[str, Any]]] = {}
    for alert in fired_alerts:
        alert_name = alert["metric"]["alertname"]
        if alert_name not in before_upgrade_alert_names:
            alerts_by_name.setdefault(alert_name, []).append(alert)

    if alerts_by_name:
        write_to_file(
            base_directory=base_directory,
            file_name="alerts_fired_during_upgrade.json",
            content=json.dumps(fired_alerts, indent=2),
        )
    return alerts_by_name


def get_upgrade_path(target_version: str, channel: str = "stable") -> dict[str, Any]:
    """Query the version explorer for upgrade paths to a target CNV version on a given channel."""
    return wait_for_version_explorer_response(
        api_end_point="GetUpgradePath",
        query_string=f"targetVersion={target_version}&channel={channel}",
    )


def find_path_with_start_version(paths: list[dict[str, Any]], start_version: str) -> dict[str, Any] | None:
    """Find an upgrade path entry matching start_version."""
    for path in paths:
        if str(path["startVersion"]).lstrip("v") == start_version:
            return path
    return None


def get_cnv_image_url_for_version(version: str, channel: str) -> str:
    """Return the CNV image URL of the first successful build for a version on a given channel."""
    builds = get_build_info_by_version(version=version, channel=channel)["successful_builds"]
    assert builds, f"No successful builds for {version} on {channel} channel"
    return builds[0]["iib"]


def get_stable_released_builds(minor_version: str) -> list[dict[str, Any]]:
    """Return stable released builds for a minor version, sorted newest-first."""
    builds = wait_for_version_explorer_response(
        api_end_point="GetReleasedBuilds",
        query_string=f"minor_version={minor_version}&stage=false",
    )["builds"]
    stable_builds = sorted(
        [build for build in builds if stable_channel_released_to_prod(channels=build["channels"])],
        key=lambda build: Version(version=build["csv_version"]),
        reverse=True,
    )
    assert stable_builds, f"No stable released builds for {minor_version}"
    return stable_builds


def get_stable_channel_iib(build: dict[str, Any]) -> str:
    """Extract the IIB URL from a build's stable channel entry."""
    stable_entry = next(
        (item for item in build["channels"] if item.get("channel") == "stable" and item.get("released_to_prod")),
        None,
    )
    if not stable_entry:
        raise ValueError(f"No stable released channel entry in build: {build}")
    return stable_entry["iib"]


def build_version_images(
    versions: list[str],
    target_version: str,
    target_cnv_image_url: str,
    channel: str = "stable",
) -> dict[str, dict[str, str]]:
    """Build a {version: {"cnv_image_url": ..., "channel": ...}} dict from a versions list."""
    images: dict[str, dict[str, str]] = {}
    for raw_version in versions:
        version = raw_version.lstrip("v")
        if version == target_version:
            images[version] = {"cnv_image_url": target_cnv_image_url, "channel": channel}
        else:
            images[version] = {
                "cnv_image_url": get_cnv_image_url_for_version(version=version, channel=channel),
                "channel": channel,
            }
    return images


def find_intermediate_cnv_versions(
    current_version: str,
    target_version: str,
    target_channel: str = "stable",
) -> tuple[dict[str, dict[str, str]], dict[str, Any]]:
    """Find the intermediate CNV versions for an EUS-to-EUS upgrade.

    Walks stable z-streams for the intermediate minor (current+1) from latest to oldest,
    picks the first valid startVersion in the target's upgrade path, then resolves the
    full hop path from current to intermediate.

    Returns:
        Tuple of (non_eus_images, target_step).
    """
    target_paths = get_upgrade_path(target_version=target_version, channel=target_channel)["path"]
    assert target_paths, f"No upgrade paths for {target_version} on {target_channel} channel"

    current = Version(version=current_version)
    intermediate_minor = f"{current.major}.{current.minor + 1}"
    stable_builds = get_stable_released_builds(minor_version=intermediate_minor)

    for build in stable_builds:
        intermediate_version = build["csv_version"].lstrip("v")
        target_step = find_path_with_start_version(paths=target_paths, start_version=intermediate_version)
        if not target_step:
            continue

        LOGGER.info(f"Using {intermediate_version} as intermediate version for EUS upgrade to {target_version}")
        intermediate_iib = get_stable_channel_iib(build=build)

        intermediate_paths = get_upgrade_path(target_version=intermediate_version, channel="stable")["path"]
        intermediate_step = find_path_with_start_version(paths=intermediate_paths, start_version=current_version)

        if intermediate_step:
            non_eus_images = build_version_images(
                versions=intermediate_step["versions"],
                target_version=intermediate_version,
                target_cnv_image_url=intermediate_iib,
            )
        else:
            non_eus_images = {intermediate_version: {"cnv_image_url": intermediate_iib, "channel": "stable"}}

        return non_eus_images, target_step

    raise AssertionError(f"No valid intermediate in {intermediate_minor} for upgrade to {target_version}")


def build_eus_upgrade_path_dict(
    current_cnv_version: str,
    target_cnv_version: str,
    target_channel: str = "stable",
    target_cnv_image_url: str | None = None,
) -> dict[str, dict[str, dict[str, str]]]:
    """Build the EUS-to-EUS upgrade path with IIB images for each phase.

    Args:
        current_cnv_version: Currently installed CNV version (e.g., "4.20.15").
        target_cnv_version: EUS target CNV version (e.g., "4.22.0").
        target_channel: Channel for the target GetUpgradePath query (default "stable").
        target_cnv_image_url: CNV image URL for the EUS target (from --cnv-image CLI arg).

    Returns:
        Dict with "non-eus" and "eus" keys, each mapping version string
        to a dict with "cnv_image_url" and "channel" keys.
    """
    assert target_cnv_image_url, "target_cnv_image_url is required for EUS upgrade path"
    non_eus_images, target_step = find_intermediate_cnv_versions(
        current_version=current_cnv_version,
        target_version=target_cnv_version,
        target_channel=target_channel,
    )
    eus_images = build_version_images(
        versions=target_step["versions"],
        target_version=target_cnv_version,
        target_cnv_image_url=target_cnv_image_url,
        channel=target_channel,
    )
    upgrade_path = {"non-eus": non_eus_images, EUS: eus_images}
    LOGGER.info(f"Upgrade path for EUS-to-EUS upgrade: {upgrade_path}")
    return upgrade_path


def get_build_info_by_version(version: str, channel: str = "stable") -> dict[str, Any]:
    """Get successful builds for a CNV version from the version explorer, filtered by channel."""
    return wait_for_version_explorer_response(
        api_end_point="GetSuccessfulBuildsByVersion",
        query_string=f"version={version}&channel={channel}",
    )


def update_mcp_paused_spec(mcp: list[MachineConfigPool], paused: bool = True) -> None:
    for _mcp in mcp:
        ResourceEditor(patches={_mcp: {"spec": {"paused": paused}}}).update()


def set_workload_update_methods_hco(hyperconverged_resource: HyperConverged, workload_update_method: list[str]) -> None:
    ResourceEditorValidateHCOReconcile(
        patches={
            hyperconverged_resource: {
                "spec": {WORKLOAD_UPDATE_STRATEGY_KEY_NAME: {WORKLOADUPDATEMETHODS: workload_update_method}}
            }
        },
        list_resource_reconcile=[KubeVirt],
        wait_for_reconcile_post_update=True,
    ).update()


def perform_cnv_upgrade(
    admin_client: DynamicClient,
    cnv_image_url: str,
    cr_name: str,
    hco_namespace: Namespace,
    cnv_target_version: str,
    subscription: Subscription | None = None,
    subscription_source: str | None = None,
    subscription_channel: str | None = None,
) -> None:
    hco_target_csv_name = get_hco_csv_name_by_version(cnv_target_version=cnv_target_version)

    if subscription or subscription_source or subscription_channel:
        assert subscription and subscription_source and subscription_channel, (
            "subscription, subscription_source, and subscription_channel must all be provided together"
        )
        update_subscription_source(
            subscription=subscription,
            subscription_source=subscription_source,
            subscription_channel=subscription_channel,
        )

    LOGGER.info("Updating image in CatalogSource")
    update_image_in_catalog_source(
        client=admin_client,
        image=cnv_image_url,
        catalog_source_name=HCO_CATALOG_SOURCE,
        cr_name=cr_name,
    )
    LOGGER.info("Approving CNV InstallPlan")
    approve_cnv_upgrade_install_plan(
        client=admin_client,
        hco_namespace=hco_namespace.name,
        hco_target_csv_name=hco_target_csv_name,
        is_production_source=False,
    )
    LOGGER.info("Waiting for target CSV")
    target_csv = wait_for_hco_csv_creation(
        admin_client=admin_client, hco_namespace=hco_namespace.name, hco_target_csv_name=hco_target_csv_name
    )
    LOGGER.info("Waiting for CSV status to be SUCCEEDED")
    target_csv.wait_for_status(
        status=target_csv.Status.SUCCEEDED,
        timeout=TIMEOUT_10MIN,
        stop_status="fakestatus",  # to bypass intermittent FAILED status that is not permanent.
    )
    LOGGER.info(f"Wait for HCO version to be updated to {cnv_target_version}.")
    wait_for_hco_upgrade(client=admin_client, hco_namespace=hco_namespace, cnv_target_version=cnv_target_version)


def wait_for_hco_csv_creation(admin_client: DynamicClient, hco_namespace: str, hco_target_csv_name: str) -> Any:
    LOGGER.info(f"Wait for new CSV {hco_target_csv_name} to be created")
    csv_sampler = TimeoutSampler(
        wait_timeout=TIMEOUT_10MIN,
        sleep=TIMEOUT_5SEC,
        func=get_csv_by_name,
        admin_client=admin_client,
        namespace=hco_namespace,
        csv_name=hco_target_csv_name,
    )
    try:
        for csv in csv_sampler:
            if csv:
                return csv
    except TimeoutExpiredError:
        LOGGER.error(f"timeout waiting for target cluster service version: {hco_target_csv_name}")
        raise


def wait_for_odf_update(target_version: str, admin_client: DynamicClient) -> None:
    def _get_updated_odf_csv(_target_version: str, _admin_client: DynamicClient) -> list[str]:
        csv_list = []
        for csv in ClusterServiceVersion.get(client=_admin_client, namespace=NamespacesNames.OPENSHIFT_STORAGE):
            if any(
                csv_name in csv.name
                for csv_name in [
                    "mcg-operator",
                    "ocs-operator",
                    "odf-csi-addons-operator",
                    "odf-operator",
                ]
            ):
                csv_instance = csv.instance
                phase = csv_instance.status.phase
                current_version = csv_instance.spec.version
                if phase != csv.Status.SUCCEEDED or _target_version not in current_version:
                    csv_list.append(f"{csv.name} with status: {phase}, version: {csv_instance.spec.version}")
        return csv_list

    upgrade_sampler = TimeoutSampler(
        wait_timeout=TIMEOUT_20MIN,
        sleep=TIMEOUT_30SEC,
        func=_get_updated_odf_csv,
        _target_version=target_version,
        _admin_client=admin_client,
    )

    for sample in upgrade_sampler:
        if not sample:
            return
        LOGGER.info(f"Following odf csvs are not updated: {','.join(sample)}")

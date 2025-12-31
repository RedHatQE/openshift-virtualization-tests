from __future__ import annotations

import json
import logging
import re
from pprint import pformat
from threading import Thread
from typing import Any

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
from ocp_resources.subscription import Subscription
from packaging.version import Version
from pyhelper_utils.shell import run_command
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.install_upgrade_operators.constants import WORKLOAD_UPDATE_STRATEGY_KEY_NAME, WORKLOADUPDATEMETHODS
from tests.install_upgrade_operators.utils import wait_for_install_plan
from utilities.constants import (
    BASE_EXCEPTIONS_DICT,
    BREW_REGISTERY_SOURCE,
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
    wait_for_consistent_resource_conditions,
    wait_for_version_explorer_response,
)
from utilities.operator import (
    approve_install_plan,
    get_hco_csv_name_by_version,
    update_image_in_catalog_source,
    wait_for_mcp_update_completion,
)

LOGGER = logging.getLogger(__name__)
TIER_2_PODS_TYPE = "tier-2"

# list of whitelisted alerts
WHITELIST_ALERTS_UPGRADE_LIST = ["OutdatedVirtualMachineInstanceWorkloads"]


def wait_for_pod_replacement(dyn_client, hco_namespace, pod_name, related_images, status_dict):
    """
    Wait for a new pod to be created and running


    Args:
        dyn_client (DynamicClient): OCP Client to use
        hco_namespace (Namespace): HCO namespace
        pod_name (str): Pod name
        related_images (dict): "image" and "strategy" information

    Raises:
        TimeoutExpiredError: if a pod with the expected image is not created or if the pod is not running.
    """

    def _is_expected_pod_image(_dyn_client, _pod_name, _hco_namespace, _related_images):
        _pods = get_pod_by_name_prefix(
            dyn_client=_dyn_client,
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
        _dyn_client=dyn_client,
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


def wait_for_pods_replacement_by_type(dyn_client, hco_namespace, related_images, pod_list):
    LOGGER.info("Wait for pod replacement.")
    threads = []
    status_dict = {}

    for pod_name in pod_list:
        sub_thread = Thread(
            name=pod_name,
            target=wait_for_pod_replacement,
            kwargs={
                "dyn_client": dyn_client,
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
    dyn_client,
    hco_namespace,
    expected_images,
):
    """
    Verifies that only pods with expected images (taken from target CSV) exist.

    Args:
        dyn_client (DynamicClient): OCP Client to use
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
        dyn_client=dyn_client,
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


def get_pods_with_mismatch_image(dyn_client, hco_namespace, expected_images):
    cnv_pods = get_pods(dyn_client=dyn_client, namespace=hco_namespace)
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


def wait_for_hco_upgrade(dyn_client: DynamicClient, hco_namespace: Namespace, cnv_target_version: str) -> None:
    LOGGER.info(f"Wait for HCO version to be updated to {cnv_target_version}.")
    wait_for_hco_version(
        client=dyn_client,
        hco_ns_name=hco_namespace.name,
        cnv_version=cnv_target_version,
    )
    LOGGER.info("Wait for HCO stable conditions after upgrade")
    wait_for_hco_conditions(
        admin_client=dyn_client,
        hco_namespace=hco_namespace,
        wait_timeout=TIMEOUT_20MIN,
    )


def wait_for_post_upgrade_deployments_replicas(dyn_client, hco_namespace):
    LOGGER.info("Wait for deployments replicas.")
    for deployment in get_deployments(admin_client=dyn_client, namespace=hco_namespace.name):
        deployment.wait_for_replicas(timeout=TIMEOUT_10MIN)


def verify_upgrade_cnv(dyn_client, hco_namespace, expected_images):
    wait_for_post_upgrade_deployments_replicas(dyn_client=dyn_client, hco_namespace=hco_namespace)

    wait_for_expected_pods_exist(
        dyn_client=dyn_client,
        hco_namespace=hco_namespace,
        expected_images=expected_images,
    )


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
        cluster_version=get_clusterversion(dyn_client=admin_client),
        target_ocp_version=target_ocp_version,
    )
    wait_for_mcp_update_completion(
        machine_config_pools_list=machine_config_pools_list,
        initial_mcp_conditions=initial_mcp_conditions,
        nodes=nodes,
    )

    wait_for_cluster_version_stable_conditions(
        admin_client=admin_client,
    )


def get_all_cnv_alerts(prometheus, file_name, base_directory):
    cnv_alerts = []
    alerts_fired = prometheus.alerts()
    for alert in alerts_fired["data"].get("alerts"):
        if (
            alert["labels"].get("kubernetes_operator_part_of")
            and alert["labels"]["kubernetes_operator_part_of"] == "kubevirt"
        ):
            alert_name = alert["labels"]["alertname"]
            if alert_name in WHITELIST_ALERTS_UPGRADE_LIST:
                LOGGER.info(f"Whitelist alert {alert_name}")
                continue
            cnv_alerts.append(alert)

    write_to_file(
        base_directory=base_directory,
        file_name=file_name,
        content=json.dumps(cnv_alerts),
    )
    return cnv_alerts


def get_alerts_fired_during_upgrade(prometheus, before_upgrade_alerts, base_directory):
    after_upgrade_alerts = get_all_cnv_alerts(
        prometheus=prometheus,
        file_name="after_upgrade_alerts.json",
        base_directory=base_directory,
    )
    before_upgrade_alert_names = [alert["labels"]["alertname"] for alert in before_upgrade_alerts]
    fired_during_upgrade = []
    for alert in after_upgrade_alerts:
        alert_name = alert["labels"]["alertname"]
        if alert_name in before_upgrade_alert_names:
            continue
        LOGGER.info(f"Alert {alert_name}, state: {alert['state']} fired during upgrade.")
        fired_during_upgrade.append(alert)
    return fired_during_upgrade


def process_alerts_fired_during_upgrade(prometheus, fired_alerts_during_upgrade):
    pending_alerts = []
    for alert in fired_alerts_during_upgrade:
        if alert["state"] == "pending":
            pending_alerts.append(alert["labels"]["alertname"])

    LOGGER.info(f"Pending alerts: {pending_alerts}")
    if pending_alerts:
        # wait for the pending alerts to be fired within 10 minutes, since pending alerts would be part of alerts fired
        # during upgrade, we don't need to fail, if pending alerts did not fire.
        wait_for_pending_alerts_to_fire(prometheus=prometheus, pending_alerts=pending_alerts)


def wait_for_pending_alerts_to_fire(pending_alerts, prometheus):
    def _get_fired_alerts(_prometheus, _alert_list):
        _all_alerts = _prometheus.alerts()
        current_firing_alerts = []
        current_pending_alerts = []
        for _alert in _all_alerts["data"].get("alerts"):
            if (
                not _alert["labels"].get("kubernetes_operator_part_of")
                or _alert["labels"]["kubernetes_operator_part_of"] != "kubevirt"
            ):
                continue
            _alert_name = _alert["labels"]["alertname"]
            if _alert["state"] == FIRING_STATE:
                current_firing_alerts.append(_alert_name)
            elif _alert["state"] == "pending":
                current_pending_alerts.append(_alert_name)

        not_fired = [_alert for _alert in _alert_list if _alert not in current_firing_alerts]
        LOGGER.warning(f"Out of {_alert_list}, following alerts are still not fired: {not_fired}")
        return not_fired

    _pending_alerts = pending_alerts
    sampler = TimeoutSampler(
        wait_timeout=TIMEOUT_10MIN,
        sleep=2,
        func=_get_fired_alerts,
        _prometheus=prometheus,
        _alert_list=_pending_alerts,
    )
    try:
        for sample in sampler:
            if not sample:
                return
            _pending_alerts = sample
            LOGGER.warning(f"Waiting on alerts: {_pending_alerts}")
    except TimeoutExpiredError:
        LOGGER.error(f"Out of {pending_alerts}, following alerts did not get to {FIRING_STATE}: {_pending_alerts}")


def get_upgrade_path(target_version: str) -> dict[str, list[dict[str, str | list[str]]]]:
    return wait_for_version_explorer_response(
        api_end_point="GetUpgradePath", query_string=f"targetVersion={target_version}"
    )


def get_shortest_upgrade_path(target_version: str) -> dict[str, str | list[str]]:
    """
    Get the shortest upgrade path to a given CNV target version(latest z stream)

    Args:
        target_version (str): The target version of the upgrade path.

    Returns:
        dict: The shortest upgrade path to the target version.
    """
    upgrade_paths = get_upgrade_path(target_version=target_version)["path"]
    assert upgrade_paths, f"Couldn't find upgrade path for {target_version} version"
    upgrade_path = max(
        upgrade_paths,
        key=lambda path: Version(version="0")
        if "-hotfix" in path["startVersion"]
        else Version(version=str(path["startVersion"])),
    )
    return upgrade_path


def get_iib_images_of_cnv_versions(versions: list[str], errata_status: str = "true") -> dict[str, str]:
    version_images = {}
    for version in versions:
        iib = get_successful_fbc_build_iib(
            build_info=get_build_info_by_version(version=version, errata_status=errata_status)["successful_builds"]
        )
        version_images[version] = f"{BREW_REGISTERY_SOURCE}/rh-osbs/iib:{iib}"
    return version_images


def get_successful_fbc_build_iib(build_info: list[dict[str, str]]) -> str:
    LOGGER.info(f"Build info found: {build_info}")
    for build in build_info:
        if build["pipeline"] == "RHTAP FBC":
            return build["iib"]
    raise AssertionError("Should have a fbc build")


def get_build_info_by_version(version: str, errata_status: str = "true") -> dict[str, Any]:
    query_string = f"version={version}"
    if errata_status:
        query_string = f"{query_string}&errata_status={errata_status}"
    return wait_for_version_explorer_response(
        api_end_point="GetSuccessfulBuildsByVersion",
        query_string=query_string,
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
    cnv_subscription: Subscription,
) -> None:
    hco_target_csv_name = get_hco_csv_name_by_version(cnv_target_version=cnv_target_version)

    LOGGER.info("Updating image in CatalogSource")
    update_image_in_catalog_source(
        dyn_client=admin_client,
        image=cnv_image_url,
        catalog_source_name=HCO_CATALOG_SOURCE,
        cr_name=cr_name,
    )

    wait_for_install_plan(
        dyn_client=admin_client,
        hco_namespace=hco_namespace.name,
        hco_target_csv_name=hco_target_csv_name,
        is_production_source=False,
        cnv_subscription=cnv_subscription,
    )
    LOGGER.info("Approving CNV InstallPlan")
    approve_install_plan(hco_target_csv_name=hco_target_csv_name, hco_namespace=hco_namespace.name)
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
    wait_for_hco_upgrade(dyn_client=admin_client, hco_namespace=hco_namespace, cnv_target_version=cnv_target_version)


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


def wait_for_odf_update(target_version: str) -> None:
    def _get_updated_odf_csv(_target_version: str) -> list[str]:
        csv_list = []
        for csv in ClusterServiceVersion.get(namespace=NamespacesNames.OPENSHIFT_STORAGE):
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
    )

    for sample in upgrade_sampler:
        if not sample:
            return
        LOGGER.info(f"Following odf csvs are not updated: {','.join(sample)}")

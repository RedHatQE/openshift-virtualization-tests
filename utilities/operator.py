# TODO: Remove ### unused_code: ignore ### from function docstring once it's used.

import logging
import os
import shlex
from contextlib import contextmanager
from datetime import datetime
from pprint import pformat

import yaml
from kubernetes.dynamic.exceptions import ResourceNotFoundError
from ocp_resources.catalog_source import CatalogSource
from ocp_resources.cluster_operator import ClusterOperator
from ocp_resources.cluster_service_version import ClusterServiceVersion
from ocp_resources.image_content_source_policy import ImageContentSourcePolicy
from ocp_resources.image_digest_mirror_set import ImageDigestMirrorSet
from ocp_resources.machine_config_pool import MachineConfigPool
from ocp_resources.namespace import Namespace
from ocp_resources.node import Node
from ocp_resources.operator_group import OperatorGroup
from ocp_resources.operator_hub import OperatorHub
from ocp_resources.pod import Pod
from ocp_resources.resource import Resource, ResourceEditor
from ocp_resources.subscription import Subscription
from pyhelper_utils.shell import run_command
from pytest_testconfig import config as py_config
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

import utilities.infra
from utilities.constants import (
    BASE_EXCEPTIONS_DICT,
    BREW_REGISTERY_SOURCE,
    DEFAULT_RESOURCE_CONDITIONS,
    ICSP_FILE,
    IDMS_FILE,
    TIMEOUT_5MIN,
    TIMEOUT_5SEC,
    TIMEOUT_10MIN,
    TIMEOUT_10SEC,
    TIMEOUT_15MIN,
    TIMEOUT_20MIN,
    TIMEOUT_75MIN,
)
from utilities.data_collector import collect_ocp_must_gather

LOGGER = logging.getLogger(__name__)


def create_icsp_idms_command(image, source_url, folder_name, pull_secret=None, filter_options=""):
    """
        Create ImageContentSourcePolicy command.

    Args:
        image (str): name of image to be mirrored.
        source_url (str): source url of image registry to which contents mirror.
        folder_name (str): local path to store manifests.
        pull_secret (str): Path to your registry credentials, default set to None(until passed)
        filter_options (str): when filter passed it will choose image from multiple variants.

    Returns:
        str: base command to create icsp in the cluster.
    """
    base_command = (
        f"oc adm catalog mirror {image} {source_url} --manifests-only --to-manifests {folder_name} {filter_options}"
    )
    if pull_secret:
        base_command = f"{base_command} --registry-config={pull_secret}"

    return base_command


def generate_icsp_idms_file(folder_name, command, is_idms_file, cnv_version=None):
    rc, _, _ = run_command(
        command=shlex.split(command),
        verify_stderr=False,
        check=False,
    )
    assert rc
    file_name = IDMS_FILE if is_idms_file else ICSP_FILE

    absolute_file_name = os.path.join(folder_name, file_name)
    assert os.path.isfile(absolute_file_name), f"file does not exist in path {absolute_file_name}"
    if cnv_version:
        absolute_file_name = generate_unique_icsp_idms_file(
            file_name=absolute_file_name,
            version_string=cnv_version.lstrip("v").replace(".", ""),
        )
    return absolute_file_name


def generate_unique_icsp_idms_file(file_name, version_string):
    # update the metadata.name value to generate unique ICSP/IDMS
    with open(file_name) as fd:
        file_yaml = yaml.safe_load(fd.read())
    file_yaml["metadata"]["name"] = f"iib-{version_string}"
    with open(file_name, "w") as current_mirror_file:
        yaml.dump(file_yaml, current_mirror_file)
    new_file_name = file_name.replace(file_name, f"{file_name.replace('.yaml', '')}{version_string}.yaml")
    os.rename(file_name, new_file_name)
    return new_file_name


def create_icsp_idms_from_file(file_path):
    LOGGER.info(f"Creating icsp/idms using file: {file_path}")
    rc, _, _ = run_command(
        command=shlex.split(f"oc create -f {file_path}"),
        verify_stderr=False,
        check=False,
    )
    assert rc


def delete_existing_icsp_idms(name, is_idms_file):
    resource_class = ImageDigestMirrorSet if is_idms_file else ImageContentSourcePolicy
    LOGGER.info(f"Deleting {resource_class}.")
    for resource_obj in resource_class.get():
        object_name = resource_obj.name
        if object_name.startswith(name):
            LOGGER.info(f"Deleting {resource_class} {object_name}.")
            resource_obj.delete(wait=True)


def get_mcps_with_different_transition_times(condition_type, machine_config_pools_list, initial_transition_times):
    """
    Return a set of machine config pool (MCP) names with different transition times.

    Filters a list of MCPs based on a given condition type and returns a set of names
    of the MCPs that have a different last transition time compared to the corresponding
    initial_transition_times entry.

    Args:
        condition_type (str): The condition type to match against.
        machine_config_pools_list (list): A list of machine config pools to filter.
        initial_transition_times (dict): A dictionary with MCP names as keys and
            initial transition times as values. Used to compare against the MCP's lastTransitionTime.

    Returns:
        set: A set of machine config pool names with different transition times.
    """
    date_format = "%Y-%m-%dT%H:%M:%SZ"
    return {
        mcp.name
        for mcp in machine_config_pools_list
        for condition in mcp.instance.status.conditions
        if (
            condition["type"] == condition_type
            and datetime.strptime(condition["lastTransitionTime"], date_format)
            > datetime.strptime(initial_transition_times[mcp.name], date_format)
        )
    }


def get_mcps_with_true_condition_status(condition_type, machine_config_pools_list):
    """
    Return a set of machine config pool (MCP) names with true status conditions.

    Filters a list of MCPs based on a given condition type and returns a set of names
    of the MCPs that have a true status condition.

    Args:
        condition_type (str): The condition type to match against.
        machine_config_pools_list (list): A list of machine config pools to filter.

    Returns:
        set: A set of machine config pool names with true status conditions.
    """
    return {
        mcp.name
        for mcp in machine_config_pools_list
        for condition in mcp.instance.status.conditions
        if (condition["type"] == condition_type and condition["status"] == Resource.Condition.Status.TRUE)
    }


def get_mcps_with_all_machines_ready(machine_config_pools_list):
    resulting_mcps = set()
    for mcp in machine_config_pools_list:
        mcp_instance_status = mcp.instance.status
        if (
            mcp_instance_status.readyMachineCount == mcp_instance_status.machineCount
            and mcp_instance_status.readyMachineCount == mcp_instance_status.updatedMachineCount
        ):
            resulting_mcps.add(mcp.name)

    return resulting_mcps


def wait_for_mcp_updated_condition_true(machine_config_pools_list, timeout=TIMEOUT_75MIN, sleep=TIMEOUT_5SEC):
    LOGGER.info(f"Waiting for MCPs to reach desired condition: {MachineConfigPool.Status.UPDATED}")
    sampler = TimeoutSampler(
        wait_timeout=timeout,
        sleep=sleep,
        func=get_mcps_with_true_condition_status,
        exceptions_dict=BASE_EXCEPTIONS_DICT,
        condition_type=MachineConfigPool.Status.UPDATED,
        machine_config_pools_list=machine_config_pools_list,
    )
    consecutive_checks_for_mcp_condition(mcp_sampler=sampler, machine_config_pools_list=machine_config_pools_list)


def wait_for_mcp_ready_machine_count(machine_config_pools_list):
    LOGGER.info("Waiting for MCPs to have all machines ready.")
    sampler = TimeoutSampler(
        wait_timeout=TIMEOUT_10MIN,
        sleep=TIMEOUT_5SEC,
        func=get_mcps_with_all_machines_ready,
        exceptions_dict=BASE_EXCEPTIONS_DICT,
        machine_config_pools_list=machine_config_pools_list,
    )
    consecutive_checks_for_mcp_condition(mcp_sampler=sampler, machine_config_pools_list=machine_config_pools_list)


def consecutive_checks_for_mcp_condition(mcp_sampler, machine_config_pools_list):
    mcps_to_check = {mcp.name for mcp in machine_config_pools_list}
    consecutive_check = 0
    not_matching_mcps = set()
    try:
        for sample in mcp_sampler:
            if sample:
                not_matching_mcps = {mcp for mcp in mcps_to_check if mcp not in sample}
                if not not_matching_mcps:
                    consecutive_check += 1
                else:
                    consecutive_check = 0
                if consecutive_check == 3:
                    return
    except TimeoutExpiredError:
        collect_mcp_data_on_update_timeout(
            machine_config_pools_list=machine_config_pools_list,
            not_matching_mcps=not_matching_mcps,
            condition_type=MachineConfigPool.Status.UPDATED,
            since_time=mcp_sampler.wait_timeout + TIMEOUT_5MIN,
        )
        raise


def wait_for_mcp_update_end(machine_config_pools_list, timeout=TIMEOUT_75MIN, sleep=TIMEOUT_5SEC):
    wait_for_mcp_updated_condition_true(
        machine_config_pools_list=machine_config_pools_list, timeout=timeout, sleep=sleep
    )
    wait_for_mcp_ready_machine_count(machine_config_pools_list=machine_config_pools_list)


def wait_for_mcp_update_start(machine_config_pools_list, initial_transition_times):
    updating_condition = MachineConfigPool.Status.UPDATING
    mcps_to_check = {mcp.name for mcp in machine_config_pools_list}
    LOGGER.info(
        "Waiting for MCP update to start. "
        f"Waiting for MCPs {mcps_to_check} to reach desired condition: {updating_condition}"
    )
    sampler = TimeoutSampler(
        wait_timeout=TIMEOUT_15MIN,
        sleep=TIMEOUT_10SEC,
        func=get_mcps_with_different_transition_times,
        exceptions_dict=BASE_EXCEPTIONS_DICT,
        condition_type=updating_condition,
        machine_config_pools_list=machine_config_pools_list,
        initial_transition_times=initial_transition_times,
    )
    not_matching_mcps = set()
    try:
        for sample in sampler:
            if sample:
                not_matching_mcps = {mcp for mcp in mcps_to_check if mcp not in sample}
                if not not_matching_mcps:
                    return
    except TimeoutExpiredError:
        collect_mcp_data_on_update_timeout(
            machine_config_pools_list=machine_config_pools_list,
            not_matching_mcps=not_matching_mcps,
            condition_type=updating_condition,
            since_time=sampler.wait_timeout + TIMEOUT_5MIN,
        )
        updated_condition = MachineConfigPool.Status.UPDATED
        updated_mcps = get_mcps_with_true_condition_status(
            condition_type=updated_condition,
            machine_config_pools_list=machine_config_pools_list,
        )
        if updated_mcps:
            LOGGER.warning(f"Some of the MCPs reached {updated_condition}: {updated_mcps}. Continuing with the test.")
        else:
            LOGGER.error(f"None of the MCPs reached {updated_condition}.")
            raise


def collect_mcp_data_on_update_timeout(machine_config_pools_list, not_matching_mcps, condition_type, since_time):
    mcps_to_check = {mcp.name for mcp in machine_config_pools_list}
    LOGGER.error(
        f"Out of MCPs {mcps_to_check}, following MCPs {not_matching_mcps} were not at desired "
        f"condition {condition_type} before timeout.\n"
        f"Current MCP status={str({mcp.name: mcp.instance.status.conditions for mcp in machine_config_pools_list})}"
    )
    collect_ocp_must_gather(since_time=since_time)


def get_machine_config_pool_by_name(mcp_name):
    mcp = MachineConfigPool(name=mcp_name)
    if mcp.exists:
        return mcp
    raise ResourceNotFoundError(f"OperatorHub {mcp_name} not found")


def get_machine_config_pools_conditions(machine_config_pools):
    return {mcp.name: mcp.instance.status.conditions for mcp in machine_config_pools}


def get_operator_hub():
    operator_hub_name = "cluster"
    operator_hub = OperatorHub(name=operator_hub_name)
    if operator_hub.exists:
        return operator_hub
    raise ResourceNotFoundError(f"OperatorHub {operator_hub_name} not found")


@contextmanager
def disable_default_sources_in_operatorhub(admin_client):
    operator_hub = get_operator_hub()
    LOGGER.info("Disable default sources in operatorhub.")
    with ResourceEditor(patches={operator_hub: {"spec": {"disableAllDefaultSources": True}}}) as edited_source:
        # wait for all the catalogsources to disappear:
        sources = operator_hub.instance.status.sources
        for catalog_source_name in [catalog_source["name"] for catalog_source in sources]:
            wait_for_catalog_source_disabled(catalog_name=catalog_source_name)
        yield edited_source


def get_catalog_source(catalog_name):
    market_place_namespace = py_config["marketplace_namespace"]
    catalog_source = CatalogSource(namespace=market_place_namespace, name=catalog_name)
    if catalog_source.exists:
        return catalog_source
    LOGGER.warning(f"CatalogSource {catalog_name} not found in namespace: {market_place_namespace}")


def wait_for_catalog_source_disabled(catalog_name):
    LOGGER.info(f"Wait for catalogsource {catalog_name} to be disabled.")
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_5MIN,
        sleep=10,
        func=get_catalog_source,
        catalog_name=catalog_name,
    )
    try:
        for catalog_source in samples:
            if not catalog_source:
                return
    except TimeoutExpiredError:
        LOGGER.error(f"Catalogsource {catalog_name} did not get disabled.")
        raise


def create_catalog_source(
    catalog_name,
    image,
    display_name="OpenShift Virtualization Index Image",
):
    LOGGER.info(f"Create catalog source {catalog_name}")
    with CatalogSource(
        name=catalog_name,
        namespace=py_config["marketplace_namespace"],
        display_name=display_name,
        source_type="grpc",
        image=image,
        publisher="Red Hat",
        teardown=False,
    ) as catalog_source:
        return catalog_source


def wait_for_catalogsource_ready(admin_client, catalog_name):
    """
    ### unused_code: ignore ###
    """
    LOGGER.info(f"Wait for pods associated with catalog source: {catalog_name} to get to 'Running' state")

    def _get_catalog_source_pods_not_running():
        not_running = [
            _pod.name
            for _pod in utilities.infra.get_pods(
                dyn_client=admin_client,
                namespace=Namespace(name=py_config["marketplace_namespace"]),
                label=f"olm.catalogSource={catalog_name}",
            )
            if _pod.instance.status.phase != Pod.Status.RUNNING
        ]
        LOGGER.info(f"Not running pods: {not_running}")
        return not_running

    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_5MIN,
        sleep=10,
        func=_get_catalog_source_pods_not_running,
    )
    not_running_pod = None
    try:
        for not_running_pod in samples:
            if not not_running_pod:
                return
    except TimeoutExpiredError:
        LOGGER.error(f"Pods {not_running_pod} associated with {catalog_name} did not go to running state.")
        raise


def create_operator_group(operator_group_name, namespace_name, target_namespaces=None):
    """
        Create specified Operator group.

    Args:
        operator_group_name (str): name of the operator group
        namespace_name (str): Namespace name in which operator group be created.
        target_namespaces (list): List of namespace names for which operator group can be a member. Default None.

    Returns:
        OperatorGroup: Operator group object.
    """
    LOGGER.info(f"Create operatorgroup {operator_group_name} in namespace {namespace_name}")
    with OperatorGroup(
        name=operator_group_name,
        namespace=namespace_name,
        target_namespaces=target_namespaces,
        teardown=False,
    ) as operator_group:
        return operator_group


def create_subscription(
    subscription_name,
    package_name,
    namespace_name,
    catalogsource_name,
    channel_name="stable",
    install_plan_approval="Automatic",
):
    """
    ### unused_code: ignore ###
    """
    LOGGER.info(f"Create subscription {subscription_name} on namespace {namespace_name}")
    with Subscription(
        name=subscription_name,
        package_name=package_name,
        namespace=namespace_name,
        channel=channel_name,
        install_plan_approval=install_plan_approval,
        source=catalogsource_name,
        source_namespace=py_config["marketplace_namespace"],
        teardown=False,
    ) as subscription:
        return subscription


def approve_install_plan(install_plan):
    ResourceEditor(patches={install_plan: {"spec": {"approved": True}}}).update()
    install_plan.wait_for_status(status=install_plan.Status.COMPLETE, timeout=TIMEOUT_20MIN)


def get_install_plan_from_subscription(subscription):
    LOGGER.info(f"Wait for install plan to be created in subscription {subscription.name}.")
    install_plan_sampler = TimeoutSampler(
        wait_timeout=TIMEOUT_5MIN,
        sleep=30,
        func=lambda: subscription.instance.status.installplan,
    )
    try:
        for install_plan in install_plan_sampler:
            if install_plan:
                LOGGER.info(f"Install plan found {install_plan}.")
                return install_plan["name"]
    except TimeoutExpiredError:
        LOGGER.error(
            f"Subscription: {subscription.name}, did not get updated with install plan: {pformat(subscription)}"
        )
        raise


def wait_for_csv_successful_state(admin_client, namespace_name, subscription_name):
    subscription = Subscription(name=subscription_name, namespace=namespace_name)
    if subscription.exists:
        csv = utilities.infra.get_csv_by_name(
            csv_name=subscription.instance.status.installedCSV,
            admin_client=admin_client,
            namespace=namespace_name,
        )
        csv.wait_for_status(status=ClusterServiceVersion.Status.SUCCEEDED, timeout=TIMEOUT_10MIN)
        return
    raise ResourceNotFoundError(f"Subscription {subscription_name} not found in namespace: {namespace_name}")


def wait_for_mcp_update_completion(machine_config_pools_list, initial_mcp_conditions, nodes):
    initial_updating_transition_times = get_mcp_updating_transition_times(mcp_conditions=initial_mcp_conditions)

    wait_for_mcp_update_start(
        machine_config_pools_list=machine_config_pools_list,
        initial_transition_times=initial_updating_transition_times,
    )
    wait_for_mcp_update_end(
        machine_config_pools_list=machine_config_pools_list,
    )
    wait_for_nodes_to_have_same_kubelet_version(nodes=nodes)
    wait_for_all_nodes_ready(nodes=nodes)


def wait_for_all_nodes_ready(nodes):
    nodes_not_ready = None
    sampler = TimeoutSampler(
        wait_timeout=TIMEOUT_5MIN,
        sleep=TIMEOUT_10SEC,
        func=get_nodes_not_ready,
        exceptions_dict=BASE_EXCEPTIONS_DICT,
        nodes=nodes,
    )
    consecutive_checks = 0
    try:
        for nodes_not_ready in sampler:
            if not nodes_not_ready:
                consecutive_checks += 1
            else:
                consecutive_checks = 0
            if consecutive_checks == 3:
                return
    except TimeoutExpiredError:
        if nodes_not_ready:
            LOGGER.error(f"Some nodes are not ready: {(node.name for node in nodes_not_ready)}")
        raise


def get_nodes_not_ready(nodes):
    return [node for node in nodes if not node.kubelet_ready]


def wait_for_nodes_to_have_same_kubelet_version(nodes):
    node_versions = None
    sampler = TimeoutSampler(
        wait_timeout=TIMEOUT_5MIN,
        sleep=TIMEOUT_10SEC,
        func=lambda: {node.name: node.instance.status.nodeInfo.kubeletVersion for node in nodes},
        exceptions_dict=BASE_EXCEPTIONS_DICT,
    )
    try:
        for node_versions in sampler:
            # Verify that all the node versions are equal
            if node_versions and len(set(node_versions.values())) == 1:
                return
    except TimeoutExpiredError:
        if node_versions:
            LOGGER.error(f"The kubelet version is not the same for all nodes: {node_versions}")
        raise


def get_mcp_updating_transition_times(mcp_conditions):
    """
    Extract the initial transition times for the Updating MCP condition
    """

    updating_transition_times = {}

    for role, conditions_list in mcp_conditions.items():
        for conditions in conditions_list:
            if conditions["type"] == MachineConfigPool.Status.UPDATING:
                updating_transition_times[role] = conditions["lastTransitionTime"]

    return updating_transition_times


def create_operator(operator_class, operator_name, namespace_name=None):
    """
    ### unused_code: ignore ###
    """
    if namespace_name:
        operator = operator_class(name=operator_name, namespace=namespace_name)
    else:
        operator = operator_class(name=operator_name)
    if operator.exists:
        LOGGER.warning(f"Operator: {operator_name} already exists in namespace: {namespace_name}")
        return
    LOGGER.info(f"Operator: {operator_name} is getting deployed in namespace: {namespace_name}")
    operator.deploy(wait=True)
    return operator


def wait_for_package_manifest_to_exist(dyn_client, cr_name, catalog_name):
    LOGGER.info(f"Wait for package manifest creation for {cr_name} associated with catalog source: {catalog_name}")
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_10MIN,
        sleep=10,
        func=utilities.infra.get_raw_package_manifest,
        admin_client=dyn_client,
        name=cr_name,
        catalog_source=catalog_name,
    )
    try:
        for sample in samples:
            if sample:
                return
    except TimeoutExpiredError:
        LOGGER.error(f"{cr_name} package associated with {catalog_name} did not get created")
        raise


def update_image_in_catalog_source(dyn_client, image, catalog_source_name, cr_name):
    catalog = get_catalog_source(catalog_name=catalog_source_name)
    if catalog:
        LOGGER.info(f"Updating {catalog_source_name} image to {image}")
        ResourceEditor(patches={catalog: {"spec": {"image": image}}}).update()
    else:
        LOGGER.info(f"Creating CatalogSource {catalog_source_name} with image {image}.")
        create_catalog_source(
            catalog_name=catalog_source_name,
            image=image,
        )
        LOGGER.info(f"Waiting for {cr_name} packagemanifest associated with {catalog_source_name} to appear")
        wait_for_package_manifest_to_exist(dyn_client=dyn_client, catalog_name=catalog_source_name, cr_name=cr_name)


def update_subscription_source(
    subscription: Subscription,
    subscription_source: str,
    subscription_channel: str,
) -> None:
    LOGGER.info(
        f"Update subscription {subscription.name} source to {subscription_source} on {subscription_channel} channel"
    )
    ResourceEditor({
        subscription: {
            "spec": {
                "channel": subscription_channel,
                "installPlanApproval": "Manual",
                "source": subscription_source,
            }
        }
    }).update()


def cluster_with_icsp():
    icsp_list = list(ImageContentSourcePolicy.get())
    return len(icsp_list) > 0


def get_cluster_operator_status_conditions(admin_client, operator_conditions=None):
    operator_conditions = operator_conditions or DEFAULT_RESOURCE_CONDITIONS
    cluster_operator_status = {}
    for cluster_operator in list(ClusterOperator.get(dyn_client=admin_client)):
        operator_name = cluster_operator.name
        cluster_operator_status[operator_name] = {}
        for condition in cluster_operator.instance.get("status", {}).get("conditions", []):
            if condition["type"] in operator_conditions:
                if (
                    operator_name == "console"
                    and condition["type"] == Resource.Condition.DEGRADED
                    and condition["status"]
                    and "ConsoleNotificationSyncDegraded" in condition["message"]
                ):
                    cluster_operator_status[operator_name][condition["type"]] = Resource.Condition.Status.FALSE
                else:
                    cluster_operator_status[operator_name][condition["type"]] = condition["status"]

    return cluster_operator_status


def get_failed_cluster_operator(admin_client):
    cluster_operators_status_conditions = get_cluster_operator_status_conditions(admin_client=admin_client)
    failed_operators = {}
    for cluster_operator in cluster_operators_status_conditions:
        if sorted(cluster_operators_status_conditions[cluster_operator].items()) != sorted(
            DEFAULT_RESOURCE_CONDITIONS.items()
        ):
            LOGGER.info(
                f"{cluster_operator} current status condition: {cluster_operators_status_conditions[cluster_operator]}"
            )
            failed_operators[cluster_operator] = cluster_operators_status_conditions[cluster_operator]
    return failed_operators


def wait_for_cluster_operator_stabilize(admin_client, wait_timeout=TIMEOUT_20MIN):
    sampler = TimeoutSampler(
        wait_timeout=wait_timeout,
        sleep=10,
        func=get_failed_cluster_operator,
        admin_client=admin_client,
    )
    consecutive_check = 0
    sample = None
    try:
        for sample in sampler:
            if not sample:
                LOGGER.info(f"Found stable cluster operator: {consecutive_check} time.")
                consecutive_check += 1
            else:
                LOGGER.info(f"Following cluster operators are not yet stable: {sample}.")
                consecutive_check = 0
            if consecutive_check == 3:
                return

    except TimeoutExpiredError:
        LOGGER.error(f"Following cluster operators failed to stabilize: {sample}")
        if sample:
            raise


def get_hco_csv_name_by_version(cnv_target_version: str) -> str:
    return f"kubevirt-hyperconverged-operator.v{cnv_target_version}"


def get_generated_icsp_idms(
    image_url: str,
    registry_source: str,
    generated_pulled_secret: str,
    pull_secret_directory: str,
    is_idms_cluster: bool,
    cnv_version: str | None = None,
    filter_options: str = "",
) -> str:
    pull_secret = None
    if image_url.startswith(tuple([BREW_REGISTERY_SOURCE, "quay.io"])):
        registry_source = BREW_REGISTERY_SOURCE
        pull_secret = generated_pulled_secret
    cnv_mirror_cmd = create_icsp_idms_command(
        image=image_url,
        source_url=registry_source,
        folder_name=pull_secret_directory,
        pull_secret=pull_secret,
        filter_options=filter_options,
    )
    icsp_file_path = generate_icsp_idms_file(
        folder_name=pull_secret_directory,
        command=cnv_mirror_cmd,
        is_idms_file=is_idms_cluster,
        cnv_version=cnv_version,
    )

    return icsp_file_path


def apply_icsp_idms(
    file_paths: list[str],
    machine_config_pools: list[MachineConfigPool],
    mcp_conditions: dict[str, list[dict[str, str]]],
    nodes: list[Node],
    is_idms_file: bool,
    delete_file: bool = False,
) -> None:
    LOGGER.info("pausing MCP updates while modifying ICSP/IDMS")
    with ResourceEditor(patches={mcp: {"spec": {"paused": True}} for mcp in machine_config_pools}):
        if delete_file:
            # Due to the amount of annotations in ICSP/IDMS yaml, `oc apply` may fail. Existing ICSP/IDMS is deleted.
            LOGGER.info("Deleting existing ICSP/IDMS.")
            delete_existing_icsp_idms(name="iib", is_idms_file=is_idms_file)
        LOGGER.info("Creating new ICSP/IDMS")
        for file_path in file_paths:
            create_icsp_idms_from_file(file_path=file_path)

    LOGGER.info("Wait for MCP update after ICSP/IDMS modification.")
    wait_for_mcp_update_completion(
        machine_config_pools_list=machine_config_pools,
        initial_mcp_conditions=mcp_conditions,
        nodes=nodes,
    )

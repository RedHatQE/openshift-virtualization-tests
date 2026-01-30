import logging
from collections import defaultdict

from kubernetes.dynamic import DynamicClient
from kubernetes.dynamic.exceptions import NotFoundError
from ocp_resources.pod import Pod
from ocp_resources.resource import ResourceEditor
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from utilities.constants import (
    BRIDGE_MARKER,
    CDI_APISERVER,
    CDI_DEPLOYMENT,
    CDI_OPERATOR,
    CDI_UPLOADPROXY,
    CLUSTER_NETWORK_ADDONS_OPERATOR,
    HCO_OPERATOR,
    HCO_WEBHOOK,
    HYPERCONVERGED_CLUSTER_CLI_DOWNLOAD,
    IMAGE_CRON_STR,
    KUBE_CNI_LINUX_BRIDGE_PLUGIN,
    KUBEMACPOOL_CERT_MANAGER,
    KUBEMACPOOL_MAC_CONTROLLER_MANAGER,
    KUBEVIRT_APISERVER_PROXY,
    KUBEVIRT_CONSOLE_PLUGIN,
    KUBEVIRT_IPAM_CONTROLLER_MANAGER,
    NODE_ROLE_KUBERNETES_IO,
    SSP_OPERATOR,
    TIMEOUT_4MIN,
    TIMEOUT_5MIN,
    TIMEOUT_5SEC,
    TIMEOUT_10MIN,
    TIMEOUT_30SEC,
    VIRT_API,
    VIRT_CONTROLLER,
    VIRT_EXPORTPROXY,
    VIRT_HANDLER,
    VIRT_OPERATOR,
    VIRT_TEMPLATE_VALIDATOR,
    WORKER_NODE_LABEL_KEY,
)
from utilities.hco import wait_for_hco_post_update_stable_state

LOGGER = logging.getLogger(__name__)

SELECTORS = [
    ("infra-comp", "infra1"),
    ("infra-comp", "infra2"),
    ("infra-comp", "infra3"),
    ("work-comp", "work1"),
    ("work-comp", "work2"),
    ("work-comp", "work3"),
    ("op-comp", "op1"),
    ("op-comp", "op2"),
    ("op-comp", "op3"),
]

INFRA_LABEL_1 = {"nodePlacement": {"nodeSelector": {"infra-comp": "infra1"}}}
INFRA_LABEL_2 = {"nodePlacement": {"nodeSelector": {"infra-comp": "infra2"}}}
INFRA_LABEL_3 = {"nodePlacement": {"nodeSelector": {"infra-comp": "infra3"}}}
WORK_LABEL_1 = {"nodePlacement": {"nodeSelector": {"work-comp": "work1"}}}
WORK_LABEL_2 = {"nodePlacement": {"nodeSelector": {"work-comp": "work2"}}}
WORK_LABEL_3 = {"nodePlacement": {"nodeSelector": {"work-comp": "work3"}}}

SUBSCRIPTION_NODE_SELCTOR_1 = {"op-comp": "op1"}
SUBSCRIPTION_NODE_SELCTOR_2 = {"op-comp": "op2"}
SUBSCRIPTION_NODE_SELCTOR_3 = {"op-comp": "op3"}
SUBSCRIPTION_TOLERATIONS = [
    {
        "effect": "NoSchedule",
        "key": f"{NODE_ROLE_KUBERNETES_IO}/master",
        "operator": "Exists",
    }
]


NODE_PLACEMENT_INFRA = {
    "nodePlacement": {
        "affinity": {
            "nodeAffinity": {
                "requiredDuringSchedulingIgnoredDuringExecution": {
                    "nodeSelectorTerms": [
                        {
                            "matchExpressions": [
                                {
                                    "key": "infra-comp",
                                    "operator": "In",
                                    "values": ["infra1", "infra2"],
                                }
                            ]
                        }
                    ]
                }
            }
        },
        "nodeSelector": {"infra-comp": "infra1"},
        "tolerations": [
            {
                "effect": "NoSchedule",
                "key": WORKER_NODE_LABEL_KEY,
                "operator": "Exists",
            }
        ],
    }
}

NODE_PLACEMENT_WORKLOADS = {
    "nodePlacement": {
        "affinity": {
            "nodeAffinity": {
                "preferredDuringSchedulingIgnoredDuringExecution": [
                    {
                        "preference": {
                            "matchExpressions": [
                                {
                                    "key": "work-comp",
                                    "operator": "In",
                                    "values": ["work1", "work2"],
                                }
                            ]
                        },
                        "weight": 1,
                    }
                ],
                "requiredDuringSchedulingIgnoredDuringExecution": {
                    "nodeSelectorTerms": [
                        {
                            "matchExpressions": [
                                {
                                    "key": "work-comp",
                                    "operator": "In",
                                    "values": ["work1", "work2"],
                                }
                            ]
                        }
                    ]
                },
            }
        },
        "nodeSelector": {"work-comp": "work2"},
        "tolerations": [
            {
                "effect": "NoSchedule",
                "key": WORKER_NODE_LABEL_KEY,
                "operator": "Exists",
            }
        ],
    }
}

# Below list consists of Infrastructure and Workloads pods based on Daemonset and Deployments.
CNV_INFRA_PODS_COMPONENTS = [
    VIRT_CONTROLLER,
    VIRT_TEMPLATE_VALIDATOR,
    VIRT_API,
    VIRT_EXPORTPROXY,
    KUBEMACPOOL_MAC_CONTROLLER_MANAGER,
    KUBEMACPOOL_CERT_MANAGER,
    CDI_APISERVER,
    CDI_DEPLOYMENT,
    CDI_UPLOADPROXY,
    KUBEVIRT_CONSOLE_PLUGIN,
    KUBEVIRT_APISERVER_PROXY,
    KUBEVIRT_IPAM_CONTROLLER_MANAGER,
]
CNV_WORKLOADS_PODS_COMPONENTS = [
    VIRT_HANDLER,
    BRIDGE_MARKER,
    KUBE_CNI_LINUX_BRIDGE_PLUGIN,
]

CNV_OPERATOR_PODS_COMPONENTS = [
    CDI_OPERATOR,
    CLUSTER_NETWORK_ADDONS_OPERATOR,
    HCO_OPERATOR,
    HCO_WEBHOOK,
    SSP_OPERATOR,
    VIRT_OPERATOR,
]


def find_components_on_node(component_list, node_name, admin_client, hco_namespace):
    """
    This function is used to check the Pod on given node. It breaks the loop once it finds Pod from the given list.

    Args:
        component_list (list): list of components to be matched
        node_name (str): Name of the node
        admin_client(DynamicClient): DynamicClient object
        hco_namespace(Namespace): Namespace object

    Returns:
        list, list: list of matched components, list of unmatched components for a given node
    """
    pods_on_node = get_pod_per_nodes(
        admin_client=admin_client,
        hco_namespace=hco_namespace,
        filter_pods_by_name=IMAGE_CRON_STR,
    )
    found_components = []
    missing_components = []
    if node_name not in pods_on_node:
        LOGGER.warning(f"Node: {node_name}, does not have any associated pods.")
        return found_components, missing_components
    for component_name in component_list:
        for pod_name in pods_on_node[node_name]:
            if pod_name.startswith(component_name):
                found_components.append(component_name)
                break
        else:
            missing_components.append(component_name)
    LOGGER.info(
        f"For node: {node_name}, found components: {found_components}, missing components: {missing_components}"
    )
    return found_components, missing_components


def verify_all_components_on_node(component_list, node_name, admin_client, hco_namespace):
    """
    This function validates that actual pods associated with a given node matches with the list of expected pods for
    same node

    Args:
        component_list (list): list of components to be matched
        node_name (str): Name of the node
        admin_client(DynamicClient): DynamicClient object
        hco_namespace(Namespace): Namespace object

    raise:
        TimeoutExpiredError: if a match is not found
    """
    LOGGER.info(f"Validating that following pod types: {component_list} are present for node: {node_name}")
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_5MIN,
        sleep=TIMEOUT_5SEC,
        func=find_components_on_node,
        component_list=component_list,
        node_name=node_name,
        admin_client=admin_client,
        hco_namespace=hco_namespace,
    )
    found_components = None
    missing_components = None

    try:
        for found_components, missing_components in samples:
            if not missing_components:
                return
    except TimeoutExpiredError:
        LOGGER.error(
            f"For Node:{node_name}, verified components {found_components}, failed components {missing_components}"
        )
        raise


def verify_no_components_on_nodes(
    component_list,
    node_names,
    admin_client,
    hco_namespace,
):
    """
    This function validates that a list of pods are not associated with any of node from a given list

    Args:
        component_list (list): list of components to be matched
        node_names (list): Name of the nodes
        admin_client(DynamicClient): DynamicClient object
        hco_namespace(Namespace): Namespace object

    raise:
        TimeoutExpiredError: if a match is found
    """
    LOGGER.info(f"Validating following pod types: {component_list} are not present on nodes: {node_names}")

    def _check_found_components_all_nodes():
        node_results = {}
        for node_name in node_names:
            found_components, missing_components = find_components_on_node(
                component_list=component_list,
                node_name=node_name,
                admin_client=admin_client,
                hco_namespace=hco_namespace,
            )
            node_results[node_name] = {
                "found": found_components,
                "missing": missing_components,
            }
            LOGGER.debug(f"On node: {node_name}, found: {found_components}, missing_components: {missing_components}")

        return {
            node_name: node_results[node_name]["found"] for node_name in node_names if node_results[node_name]["found"]
        }

    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_4MIN,
        sleep=TIMEOUT_5SEC,
        func=_check_found_components_all_nodes,
    )
    sample = None
    try:
        for sample in samples:
            if not sample:
                return
    except TimeoutExpiredError:
        LOGGER.error(f"Timed out waiting for no matching components on nodes:{node_names}, actual results {sample}")
        raise


def verify_components_exist_only_on_selected_node(
    hco_pods_per_nodes,
    component_list,
    selected_node,
    admin_client,
    hco_namespace,
):
    """
    This function validates only expected pods have been spin'ed up on a given node.

    Args:
        hco_pods_per_nodes(dict): dictionary with node names as keys and associated list of pod apps as values
        component_list (list): list of components to be matched
        selected_node (str): Name of the selected node
        admin_client(DynamicClient): DynamicClient object
        hco_namespace(Namespace): Namespace object
    """
    unselected_nodes = [node_name for node_name in hco_pods_per_nodes.keys() if node_name != selected_node]
    verify_all_components_on_node(
        component_list=component_list,
        node_name=selected_node,
        admin_client=admin_client,
        hco_namespace=hco_namespace,
    )
    verify_no_components_on_nodes(
        component_list=component_list,
        node_names=unselected_nodes,
        admin_client=admin_client,
        hco_namespace=hco_namespace,
    )


def get_pod_per_nodes(admin_client, hco_namespace, filter_pods_by_name=None):
    """
    This function creates a dictionary, with nodes as keys and associated list of pod apps as values

    Args:
        admin_client(DynamicClient): DynamicClient object
        hco_namespace(Namespace): Namespace object
        filter_pods_by_name(str): string to filter pod names by

    Returns:
        dict: a dictionary, with nodes as keys and associated list of pod apps as values
    """

    def _get_pods_per_nodes(_filter_pods_by_name):
        pods_per_nodes = defaultdict(list)
        for pod in Pod.get(
            client=admin_client,
            namespace=hco_namespace.name,
        ):
            if _filter_pods_by_name and _filter_pods_by_name in pod.name:
                LOGGER.warning(f"Ignoring pod: {pod.name} for placement")
                continue
            try:
                # field_selector="status.phase==Running" is not always reliable
                # to filter out terminating pods, see: https://github.com/kubernetes/kubectl/issues/450
                if pod.instance.metadata.get("deletionTimestamp") is None:
                    pods_per_nodes[pod.node.name].append(pod)
            except NotFoundError:
                LOGGER.warning(f"Ignoring pods that disappeared during the query. node={pod.node.name} pod={pod.name}")
        return pods_per_nodes

    pod_names_per_nodes = {}
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_5MIN,
        sleep=TIMEOUT_30SEC,
        func=_get_pods_per_nodes,
        _filter_pods_by_name=filter_pods_by_name,
        exceptions_dict={NotFoundError: []},
    )
    try:
        for sample in samples:
            if all(pod.exists and pod.status == Pod.Status.RUNNING for pods in sample.values() for pod in pods):
                pod_names_per_nodes = {node: [pod.name for pod in pods] for node, pods in sample.items()}
                return pod_names_per_nodes
    except TimeoutExpiredError:
        LOGGER.error(f"Timeout waiting for pods to be ready {pod_names_per_nodes}.")
        raise


def update_subscription_config(admin_client, hco_namespace, subscription, config):
    """
    Updates CNV subscription spec.config

    Args:
        admin_client(DynamicClient): DynamicClient object
        hco_namespace (Resource): hco_namespace
        subscription(Resource): subscription resource
        config(dict): config dict to be used for patch operation

    Raises:
        TimeoutExpiredError: if appropriate pods are not re-spinned
    """
    editor = ResourceEditor(
        patches={
            subscription: {
                "spec": {
                    "config": config,
                }
            }
        },
    )
    editor.update(backup_resources=False)

    LOGGER.info("Waiting for CNV HCO to be Ready.")

    wait_for_hco_post_update_stable_state(
        admin_client=admin_client,
        hco_namespace=hco_namespace,
        exclude_deployments=[HYPERCONVERGED_CLUSTER_CLI_DOWNLOAD],
    )


def pods_with_node_selector(namespace_name: str, node_selectors: set[str], admin_client: DynamicClient) -> list[str]:
    pods_with_labels = []
    for pod in list(Pod.get(namespace=namespace_name, client=admin_client)):
        node_selectors_from_pod = pod.instance.spec.get("nodeSelector", [])
        LOGGER.info(f"Node selector for pod {pod.name}: {node_selectors_from_pod}")
        if node_selectors_from_pod and (set(node_selectors_from_pod.keys()).intersection(node_selectors)):
            pods_with_labels.append(f"Pod: {pod.name} with labels: {node_selectors_from_pod} still exists")
    return pods_with_labels


def wait_for_pod_node_selector_clean_up(namespace_name: str, admin_client: DynamicClient) -> None:
    node_selectors = set(list(zip(*SELECTORS))[0])
    LOGGER.info(f"Looking for pods with nodeSelectors keys: {node_selectors}")
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_10MIN,
        sleep=TIMEOUT_30SEC,
        func=pods_with_node_selector,
        namespace_name=namespace_name,
        node_selectors=node_selectors,
        admin_client=admin_client,
        exceptions_dict={NotFoundError: []},
    )
    sample = None
    try:
        for sample in samples:
            if sample:
                LOGGER.info(f"Following pods still has labels: {sample}")
            else:
                return
    except TimeoutExpiredError:
        if sample:
            LOGGER.error(f"Following pods still has labels: {sample}")
            raise

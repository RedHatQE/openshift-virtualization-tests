import logging

import pytest
from ocp_resources.node import Node

from tests.install_upgrade_operators.node_component.utils import (
    SELECTORS,
    get_pod_per_nodes,
    update_subscription_config,
    wait_for_pod_node_selector_clean_up,
)
from tests.install_upgrade_operators.utils import get_network_addon_config
from utilities.constants import (
    BRIDGE_MARKER,
    CDI_APISERVER,
    CDI_DEPLOYMENT,
    CDI_UPLOADPROXY,
    HCO_SUBSCRIPTION,
    IMAGE_CRON_STR,
    KUBE_CNI_LINUX_BRIDGE_PLUGIN,
    KUBEMACPOOL_MAC_CONTROLLER_MANAGER,
    TIMEOUT_5MIN,
    VIRT_API,
    VIRT_CONTROLLER,
    VIRT_HANDLER,
    VIRT_TEMPLATE_VALIDATOR,
)
from utilities.hco import add_labels_to_nodes, apply_np_changes, wait_for_hco_conditions
from utilities.infra import (
    get_daemonset_by_name,
    get_deployment_by_name,
    get_node_selector_dict,
    get_subscription,
)
from utilities.virt import (
    VirtualMachineForTests,
    fedora_vm_body,
    wait_for_vm_interfaces,
)

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="class")
def node_placement_labels(
    admin_client,
    hco_namespace,
    control_plane_nodes,
    workers,
):
    """
    Set Infra and Workloads Labels on the worker nodes and
    Set Operators Labels on the control plane nodes.

    This would help with Installing CNV components on specific nodes.
    It yields a dictionary key is node and value is a dictionary of labels.
    """
    control_plane_labels = {"op-comp": "op"}
    worker_labels = {"infra-comp": "infra", "work-comp": "work"}
    worker_resources = add_labels_to_nodes(
        nodes=workers,
        node_labels=worker_labels,
    )
    control_plane_resources = add_labels_to_nodes(
        nodes=control_plane_nodes,
        node_labels=control_plane_labels,
    )
    label_dict = {}
    all_resources = []
    for key, value in worker_resources.items():
        label_dict.update({value["node"]: value["labels"]})
        all_resources.append(key)
    for key, value in control_plane_resources.items():
        all_resources.append(key)
        if label_dict.get(value["node"]):
            label_dict[value["node"]].update(value["labels"])
        else:
            label_dict.update({value["node"]: value["labels"]})

    yield label_dict

    for resource in all_resources:
        resource.restore()
    wait_for_hco_conditions(
        admin_client=admin_client,
        hco_namespace=hco_namespace,
        consecutive_checks_count=6,
    )
    wait_for_pod_node_selector_clean_up(namespace_name=hco_namespace.name)


def create_dict_by_label(values):
    nl = {}
    for selector, label in SELECTORS:
        nl[label] = [key for key, labels in values.items() if labels.get(selector) == label]
    return nl


@pytest.fixture(scope="class")
def expected_node_by_label(node_placement_labels):
    return create_dict_by_label(values=node_placement_labels)


@pytest.fixture(scope="class")
def np_nodes_labels_dict(admin_client):
    return {node.name: node.instance.metadata.labels for node in Node.get(dyn_client=admin_client)}


@pytest.fixture(scope="class")
def nodes_labeled(np_nodes_labels_dict):
    return create_dict_by_label(values=np_nodes_labels_dict)


@pytest.fixture()
def virt_template_validator_spec_nodeselector(admin_client, hco_namespace):
    virt_template_validator_spec = get_deployment_by_name(
        namespace_name=hco_namespace.name, deployment_name=VIRT_TEMPLATE_VALIDATOR
    ).instance.to_dict()["spec"]["template"]["spec"]
    return virt_template_validator_spec.get("nodeSelector")


@pytest.fixture()
def network_addon_config_spec_placement(admin_client):
    return get_network_addon_config(admin_client=admin_client).instance.to_dict()["spec"]["placementConfiguration"]


@pytest.fixture()
def network_deployment_placement(admin_client, hco_namespace):
    node_selector_deployments = {}
    nw_deployment = get_deployment_by_name(
        namespace_name=hco_namespace.name,
        deployment_name=KUBEMACPOOL_MAC_CONTROLLER_MANAGER,
    ).instance.to_dict()["spec"]["template"]["spec"]
    node_selector_deployments[KUBEMACPOOL_MAC_CONTROLLER_MANAGER] = nw_deployment.get("nodeSelector").get("infra-comp")
    return node_selector_deployments


@pytest.fixture()
def network_daemonsets_placement(admin_client, hco_namespace):
    node_selector_daemonset = {}
    for daemonset in [
        BRIDGE_MARKER,
        KUBE_CNI_LINUX_BRIDGE_PLUGIN,
    ]:
        nw_daemonset = get_daemonset_by_name(
            admin_client=admin_client,
            daemonset_name=daemonset,
            namespace_name=hco_namespace.name,
        ).instance.to_dict()["spec"]["template"]["spec"]
        node_selector_daemonset[daemonset] = nw_daemonset.get("nodeSelector").get("work-comp")
    return node_selector_daemonset


@pytest.fixture()
def virt_daemonset_nodeselector_comp(admin_client, hco_namespace):
    virt_daemonset = get_daemonset_by_name(
        admin_client=admin_client,
        daemonset_name=VIRT_HANDLER,
        namespace_name=hco_namespace.name,
    ).instance.to_dict()["spec"]["template"]["spec"]
    return virt_daemonset.get("nodeSelector").get("work-comp")


@pytest.fixture()
def virt_deployment_nodeselector_comp_list(admin_client, hco_namespace):
    nodeselector_lists = []
    virt_deployments = [VIRT_API, VIRT_CONTROLLER]
    for deployment in virt_deployments:
        virt_deployment = get_deployment_by_name(
            namespace_name=hco_namespace.name, deployment_name=deployment
        ).instance.to_dict()["spec"]["template"]["spec"]
        nodeselector_lists.append(virt_deployment.get("nodeSelector").get("infra-comp"))
    return nodeselector_lists


@pytest.fixture()
def cdi_deployment_nodeselector_list(admin_client, hco_namespace):
    nodeselector_lists = []
    cdi_deployments = [CDI_APISERVER, CDI_DEPLOYMENT, CDI_UPLOADPROXY]
    for deployment in cdi_deployments:
        cdi_deployment = get_deployment_by_name(
            namespace_name=hco_namespace.name, deployment_name=deployment
        ).instance.to_dict()["spec"]["template"]["spec"]
        nodeselector_lists.append(cdi_deployment.get("nodeSelector"))
    return nodeselector_lists


@pytest.fixture()
def hco_pods_per_nodes(admin_client, hco_namespace):
    return get_pod_per_nodes(
        admin_client=admin_client,
        hco_namespace=hco_namespace,
        filter_pods_by_name=IMAGE_CRON_STR,
    )


@pytest.fixture()
def hco_pods_per_nodes_after_altering_placement(admin_client, hco_namespace, alter_np_configuration):
    return get_pod_per_nodes(
        admin_client=admin_client,
        hco_namespace=hco_namespace,
        filter_pods_by_name=IMAGE_CRON_STR,
    )


@pytest.fixture(scope="class")
def hyperconverged_resource_before_np(admin_client, hco_namespace, hyperconverged_resource_scope_class):
    """
    Update HCO CR with infrastructure and workloads spec.
    """
    LOGGER.info("Fetching HCO to save its initial node placement configuration ")
    initial_infra = hyperconverged_resource_scope_class.instance.to_dict()["spec"].get("infra", {})
    initial_workloads = hyperconverged_resource_scope_class.instance.to_dict()["spec"].get("workloads", {})
    yield hyperconverged_resource_scope_class
    LOGGER.info("Revert to initial HCO node placement configuration ")
    apply_np_changes(
        admin_client=admin_client,
        hco=hyperconverged_resource_scope_class,
        hco_namespace=hco_namespace,
        infra_placement=initial_infra,
        workloads_placement=initial_workloads,
    )


@pytest.fixture()
def alter_np_configuration(
    request,
    admin_client,
    hco_namespace,
    hyperconverged_resource_scope_function,
):
    """
    Update HCO CR with infrastructure and workloads spec.
    By design, this fixture will not revert back the configuration
    of HCO CR to its initial configuration so that it can be used in
    subsequent tests.
    Passing a None "infra" or "workloads" will keep the existing correspondent value.
    """
    infra_placement = request.param.get("infra")
    workloads_placement = request.param.get("workloads")
    apply_np_changes(
        admin_client=admin_client,
        hco=hyperconverged_resource_scope_function,
        hco_namespace=hco_namespace,
        infra_placement=infra_placement,
        workloads_placement=workloads_placement,
    )
    yield


@pytest.fixture(scope="class")
def vm_placement_vm_work3(
    namespace,
    unprivileged_client,
    nodes_labeled,
):
    name = "vm-placement-sanity-tests-vm"
    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        node_selector=get_node_selector_dict(node_selector=nodes_labeled["work3"][0]),
        body=fedora_vm_body(name=name),
        client=unprivileged_client,
        teardown=False,
    ) as vm:
        vm.start(wait=True, timeout=TIMEOUT_5MIN)
        vm.vmi.wait_until_running()
        wait_for_vm_interfaces(vmi=vm.vmi)
        yield vm
    if vm.exists:
        vm.clean_up()


@pytest.fixture()
def delete_vm_after_placement(
    vm_placement_vm_work3,
):
    # Delete the VM created after checking it's placement on correct node.
    if vm_placement_vm_work3.exists:
        vm_placement_vm_work3.delete(wait=True)


@pytest.fixture(scope="class")
def cnv_subscription_scope_class(admin_client, hco_namespace):
    return get_subscription(
        admin_client=admin_client,
        namespace=hco_namespace.name,
        subscription_name=HCO_SUBSCRIPTION,
    )


@pytest.fixture()
def cnv_subscription_scope_function(admin_client, hco_namespace):
    """
    Retrieves the CNV subscription
    """
    return get_subscription(
        admin_client=admin_client,
        namespace=hco_namespace.name,
        subscription_name=HCO_SUBSCRIPTION,
    )


@pytest.fixture(scope="class")
def cnv_subscription_resource_before_np(admin_client, hco_namespace, cnv_subscription_scope_class):
    """
    Update HCO CR with infrastructure and workloads spec.
    """
    LOGGER.info("Fetching CNV Subscription to save its initial node placement configuration ")
    initial_config = cnv_subscription_scope_class.instance.to_dict()["spec"].get("config")
    yield cnv_subscription_scope_class
    LOGGER.info("Revert to initial HCO node placement configuration ")
    update_subscription_config(
        admin_client=admin_client,
        subscription=cnv_subscription_scope_class,
        hco_namespace=hco_namespace,
        config=initial_config,
    )


@pytest.fixture()
def alter_cnv_subscription_configuration(
    request,
    admin_client,
    hco_namespace,
    cnv_subscription_scope_function,
):
    """
    Update CNV subscription with node placement configurations.
    By design, this fixture will not revert back the configuration
    of CNV subscription to its initial configuration so that it can
    be used in subsequent tests.
    Passing a None "node_selector" or "tolerations" will keep the
    existing correspondent value.
    Note: cnv_subscription_resource_before_np must be used in conjunction with this fixture
    otherwise there will be configuration leftovers in the cluster
    """
    config = {}
    node_selector = request.param.get("node_selector")
    tolerations = request.param.get("tolerations")
    if node_selector:
        config["nodeSelector"] = node_selector
    if tolerations:
        config["tolerations"] = tolerations

    update_subscription_config(
        admin_client=admin_client,
        subscription=cnv_subscription_scope_function,
        hco_namespace=hco_namespace,
        config=config or None,
    )


@pytest.fixture()
def subscription_pods_per_nodes_after_altering_placement(
    admin_client,
    hco_namespace,
):
    return get_pod_per_nodes(
        admin_client=admin_client,
        hco_namespace=hco_namespace,
        filter_pods_by_name=IMAGE_CRON_STR,
    )

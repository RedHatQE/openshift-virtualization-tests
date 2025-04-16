import logging
from copy import deepcopy

import pytest
from ocp_resources.daemonset import DaemonSet
from ocp_resources.network_addons_config import NetworkAddonsConfig
from pytest_testconfig import config as py_config

from utilities.constants import (
    CLUSTER_NETWORK_ADDONS_OPERATOR,
    KMP_VM_ASSIGNMENT_LABEL,
    KUBE_CNI_LINUX_BRIDGE_PLUGIN,
    KUBEMACPOOL_MAC_CONTROLLER_MANAGER,
    LINUX_BRIDGE,
    NON_EXISTS_IMAGE,
    TIMEOUT_10MIN,
)
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.infra import (
    create_ns,
    get_node_selector_dict,
    get_pod_by_name_prefix,
    label_project,
    wait_for_pods_running,
)
from utilities.network import network_device, network_nad
from utilities.virt import VirtualMachineForTests, fedora_vm_body

DUPLICATE_MAC_STR = "duplicate-mac"
LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="class")
def updated_cnao_kubemacpool_with_bad_image_csv(
    admin_client,
    hco_namespace,
    csv_scope_class,
    updated_csv_dict_bad_kubemacpool_image,
):
    with ResourceEditorValidateHCOReconcile(patches={csv_scope_class: updated_csv_dict_bad_kubemacpool_image}):
        yield
    wait_for_pods_running(admin_client=admin_client, namespace=hco_namespace)


@pytest.fixture(scope="class")
def updated_csv_dict_bad_kubemacpool_image(csv_scope_class):
    operator_image = "KUBEMACPOOL_IMAGE"
    csv_dict = csv_scope_class.instance.to_dict()
    for deployment in csv_dict["spec"]["install"]["spec"]["deployments"]:
        if deployment["name"] == CLUSTER_NETWORK_ADDONS_OPERATOR:
            container_env = deployment["spec"]["template"]["spec"]["containers"][0]["env"]
            for env in container_env:
                if env["name"] == operator_image:
                    LOGGER.info(f"Replacing {operator_image} {env['value']} with {NON_EXISTS_IMAGE}")
                    env["value"] = NON_EXISTS_IMAGE
                    return csv_dict

    raise ValueError(f"{CLUSTER_NETWORK_ADDONS_OPERATOR} not found")


@pytest.fixture(scope="class")
def vms_mac(mac_pool):
    return mac_pool.get_mac_from_pool()


@pytest.fixture(scope="class")
def kmp_disabled_namespace(kmp_vm_label):
    kmp_vm_label[KMP_VM_ASSIGNMENT_LABEL] = "ignore"
    yield from create_ns(name="kmp-disabled", labels=kmp_vm_label)


@pytest.fixture(scope="class")
def updated_namespace_with_kmp(admin_client, kmp_vm_label, kmp_disabled_namespace):
    kmp_vm_label[KMP_VM_ASSIGNMENT_LABEL] = None
    label_project(name=kmp_disabled_namespace.name, label=kmp_vm_label, admin_client=admin_client)


@pytest.fixture(scope="class")
def restarted_kmp_controller(admin_client, kmp_deployment):
    get_pod_by_name_prefix(
        dyn_client=admin_client,
        pod_prefix=KUBEMACPOOL_MAC_CONTROLLER_MANAGER,
        namespace=py_config["hco_namespace"],
    ).delete(wait=True)
    kmp_deployment.wait_for_replicas()


@pytest.fixture(scope="class")
def bridge_device_duplicate_mac(worker_node1):
    with network_device(
        interface_type=LINUX_BRIDGE,
        nncp_name=f"{DUPLICATE_MAC_STR}-nncp",
        interface_name="bridge-dup-mac",
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
    ) as dev:
        yield dev


@pytest.fixture(scope="class")
def duplicate_mac_nad_vm1(namespace, bridge_device_duplicate_mac):
    with network_nad(
        nad_type=bridge_device_duplicate_mac.bridge_type,
        nad_name=f"{DUPLICATE_MAC_STR}-nad",
        namespace=namespace,
        interface_name=bridge_device_duplicate_mac.bridge_name,
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def duplicate_mac_nad_vm2(kmp_disabled_namespace, bridge_device_duplicate_mac):
    with network_nad(
        nad_type=bridge_device_duplicate_mac.bridge_type,
        nad_name=f"{DUPLICATE_MAC_STR}-nad",
        namespace=kmp_disabled_namespace,
        interface_name=bridge_device_duplicate_mac.bridge_name,
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def duplicate_mac_vm1(namespace, worker_node1, admin_client, vms_mac, duplicate_mac_nad_vm1):
    networks = {duplicate_mac_nad_vm1.name: duplicate_mac_nad_vm1.name}
    name = f"{DUPLICATE_MAC_STR}-vm1"
    with VirtualMachineForTests(
        client=admin_client,
        namespace=namespace.name,
        name=name,
        body=fedora_vm_body(name=name),
        networks=networks,
        interfaces=networks.keys(),
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
        macs={duplicate_mac_nad_vm1.name: vms_mac},
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="class")
def duplicate_mac_vm2(kmp_disabled_namespace, worker_node1, admin_client, vms_mac, duplicate_mac_nad_vm2):
    networks = {duplicate_mac_nad_vm2.name: duplicate_mac_nad_vm2.name}
    name = f"{DUPLICATE_MAC_STR}-vm2"
    with VirtualMachineForTests(
        client=admin_client,
        namespace=kmp_disabled_namespace.name,
        name=name,
        body=fedora_vm_body(name=name),
        networks=networks,
        interfaces=networks.keys(),
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
        macs={duplicate_mac_nad_vm2.name: vms_mac},
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="class")
def bad_cnao_operator(csv_scope_class):
    operator_image = "OPERATOR_IMAGE"
    csv_dict = deepcopy(csv_scope_class.instance.to_dict())
    for deployment in csv_dict["spec"]["install"]["spec"]["deployments"]:
        if deployment["name"] == CLUSTER_NETWORK_ADDONS_OPERATOR:
            containers = deployment["spec"]["template"]["spec"]["containers"][0]
            containers["image"] = NON_EXISTS_IMAGE
            deployment_env = containers["env"]
            for env in deployment_env:
                if env["name"] == operator_image:
                    LOGGER.info(f"Replacing {operator_image} {env['value']} with {NON_EXISTS_IMAGE}")
                    env["value"] = NON_EXISTS_IMAGE

    return csv_dict


@pytest.fixture(scope="class")
def invalid_cnao_operator(prometheus, admin_client, hco_namespace, csv_scope_class, bad_cnao_operator):
    with ResourceEditorValidateHCOReconcile(
        patches={csv_scope_class: bad_cnao_operator},
        list_resource_reconcile=[NetworkAddonsConfig],
    ):
        yield

    linux_bridge_pods = get_pod_by_name_prefix(
        dyn_client=admin_client,
        pod_prefix=KUBE_CNI_LINUX_BRIDGE_PLUGIN,
        namespace=hco_namespace.name,
        get_all=True,
    )

    [pod.delete() for pod in linux_bridge_pods]
    [pod.wait_deleted() for pod in linux_bridge_pods]

    linux_bridge_plugin_ds = DaemonSet(name=KUBE_CNI_LINUX_BRIDGE_PLUGIN, namespace=hco_namespace.name)
    linux_bridge_plugin_ds.wait_until_deployed(timeout=TIMEOUT_10MIN)

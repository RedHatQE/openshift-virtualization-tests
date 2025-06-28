import pytest
from ocp_resources.api_service import APIService
from ocp_resources.config_map import ConfigMap
from ocp_resources.custom_resource_definition import CustomResourceDefinition
from ocp_resources.daemonset import DaemonSet
from ocp_resources.deployment import Deployment
from ocp_resources.mutating_webhook_config import MutatingWebhookConfiguration
from ocp_resources.package_manifest import PackageManifest
from ocp_resources.pod import Pod
from ocp_resources.replica_set import ReplicaSet
from ocp_resources.role_binding import RoleBinding
from ocp_resources.secret import Secret
from ocp_resources.security_context_constraints import SecurityContextConstraints
from ocp_resources.service import Service
from ocp_resources.service_account import ServiceAccount
from ocp_resources.validating_webhook_config import ValidatingWebhookConfiguration

import utilities.network
from tests.network.constants import EXPECTED_CNAO_COMP_NAMES
from tests.network.libs.nodenetworkconfigurationpolicy import (
    STP,
    Bridge,
    BridgeOptions,
    DesiredState,
    Interface,
    IPv4,
    IPv6,
    NodeNetworkConfigurationPolicy,
)
from utilities.constants import CLUSTER_NETWORK_ADDONS_OPERATOR, LINUX_BRIDGE
from utilities.infra import get_node_selector_dict
from utilities.virt import VirtualMachineForTests, fedora_vm_body

pytestmark = pytest.mark.sno

RESOURCE_TYPES = [
    APIService,
    ConfigMap,
    CustomResourceDefinition,
    DaemonSet,
    Deployment,
    MutatingWebhookConfiguration,
    PackageManifest,
    Pod,
    ReplicaSet,
    RoleBinding,
    Secret,
    SecurityContextConstraints,
    Service,
    ServiceAccount,
    ValidatingWebhookConfiguration,
]
COMPONENTS_TO_IGNORE = [
    "selfSignConfiguration",
    "placementConfiguration",
]
EXPECTED_CNAO_COMP = [
    "multus",
    "cnao",
    "kubeMacPool",
    "linuxBridge",
    "ovs",
    "tlsSecurityProfile",
    "kubevirtIpamController",
]
MANAGED_BY = "managed-by"
COMP_LABELS = ["component", "version", "part-of", MANAGED_BY]
IGNORE_LIST = [
    "token",
    "metrics",
    "lock",
    "configmap/5",
    "lease",
    "dockercfg",
    "apiservice",
    "validatingwebhook",
    "packagemanifest",
    "serviceaccount/cluster-network-addons-operator",
]


class UnaccountedComponents(Exception):
    def __init__(self, components):
        self.components = components

    def __str__(self):
        return f"{self.components} are unaccounted CNAO components. Check if relevant. if so, modify test"


def get_all_network_resources(dyn_client, namespace):
    # Extract all related resources, iterating through each resource type
    network_resources = [
        resource
        for _type in RESOURCE_TYPES
        for resource in _type.get(dyn_client=dyn_client, namespace=namespace)
        if any(component in resource.name for component in EXPECTED_CNAO_COMP_NAMES)
    ]
    # Filter out old replicasets
    return [
        resource
        for resource in network_resources
        if resource.kind != ReplicaSet.kind or resource.instance.get("status", {}).get("replicas", 0) > 0
    ]


def filter_resources(resources, network_addons_config, is_post_cnv_upgrade_cluster):
    bad_rcs = []
    for resource in resources:
        resource_name = f"{resource.kind}/{resource.name}"
        if any(ignore in resource_name.lower() for ignore in IGNORE_LIST) or (
            "Secret" in resource.kind and is_post_cnv_upgrade_cluster
        ):
            continue

        try:
            for key in COMP_LABELS:
                label_key = f"{resource.ApiGroup.APP_KUBERNETES_IO}/{key}"
                if network_addons_config.labels[label_key] not in resource.labels[label_key]:
                    if MANAGED_BY in key:
                        if (
                            CLUSTER_NETWORK_ADDONS_OPERATOR in resource_name and resource.labels[label_key] == "olm"
                        ) or resource.labels[label_key] == "cnao-operator":
                            continue

                    bad_rcs.append(resource_name)
        except (KeyError, TypeError):
            bad_rcs.append(resource_name)

    return bad_rcs


def verify_cnao_labels(admin_client, namespace, network_addons_config, is_post_cnv_upgrade_cluster):
    cnao_resources = get_all_network_resources(dyn_client=admin_client, namespace=namespace)
    bad_rcs = filter_resources(
        resources=cnao_resources,
        network_addons_config=network_addons_config,
        is_post_cnv_upgrade_cluster=is_post_cnv_upgrade_cluster,
    )

    assert not bad_rcs, f"Unlabeled Resources - {bad_rcs}"


@pytest.fixture(scope="module")
def check_components(network_addons_config_scope_session):
    """
    Check that all CNAO components are accounted for.
    If a new cnao component is added, the test needs to be modified.
    It's name should be added to EXPECTED_CNAO_COMP and EXPECTED_CNAO_COMP_NAMES.
    """
    bad_components = []
    for component in network_addons_config_scope_session.instance.spec.keys():
        if component in COMPONENTS_TO_IGNORE:
            continue
        if component not in EXPECTED_CNAO_COMP:
            bad_components.append(component)
    if bad_components:
        raise UnaccountedComponents(components=bad_components)


@pytest.fixture(scope="module")
def net_add_op_bridge_device(worker_node1):
    desired_state = DesiredState(
        interfaces=[
            Interface(
                name="net-add-br",
                state=NodeNetworkConfigurationPolicy.Interface.State.UP,
                type=LINUX_BRIDGE,
                ipv4=IPv4(enabled=False),
                ipv6=IPv6(enabled=False),
                bridge=Bridge(BridgeOptions(STP(enabled=False))),
            )
        ]
    )
    with NodeNetworkConfigurationPolicy(
        name="test-network-operator",
        desired_state=desired_state,
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
    ) as nncp:
        nncp.wait_for_status_success()
        yield nncp


@pytest.fixture(scope="module")
def net_add_op_br1test_nad(namespace, net_add_op_bridge_device):
    bridge_name = next(
        (
            interface.name
            for interface in net_add_op_bridge_device.desired_state_spec.interfaces
            if interface.type == LINUX_BRIDGE
        ),
    )

    with utilities.network.network_nad(
        nad_type=LINUX_BRIDGE,
        nad_name=bridge_name,
        interface_name=bridge_name,
        namespace=namespace,
    ) as nad:
        yield nad


@pytest.fixture(scope="module")
def net_add_op_bridge_attached_vm(namespace, net_add_op_br1test_nad):
    name = "oper-test-vm"
    with VirtualMachineForTests(
        namespace=namespace.name,
        interfaces=[net_add_op_br1test_nad.name],
        networks={net_add_op_br1test_nad.name: net_add_op_br1test_nad.name},
        name=name,
        body=fedora_vm_body(name=name),
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.mark.gating
@pytest.mark.post_upgrade
@pytest.mark.single_nic
@pytest.mark.s390x
@pytest.mark.polarion("CNV-2520")
def test_component_installed_by_operator(network_addons_config_scope_session):
    """
    Verify that the network addons operator is supposed to install linuxBridge and kubeMacPool
    (a mandatory default components), by checking if the components appears in
    the operator CR.
    """
    component_name_in_cr_list = ["linuxBridge", "kubeMacPool"]
    components_missing_list = []

    for component_name in component_name_in_cr_list:
        if component_name not in network_addons_config_scope_session.instance.spec.keys():
            components_missing_list.append(component_name)
    assert not components_missing_list, (
        "One or more components are missing from the network operator CR."
        f"\nComponents missing: {components_missing_list}"
    )


@pytest.mark.post_upgrade
@pytest.mark.polarion("CNV-2296")
@pytest.mark.s390x
def test_linux_bridge_functionality(net_add_op_bridge_attached_vm):
    """
    Verify the linux-bridge component valid functionality.
    Start a VM and verify it starts successfully, as an indication of successful
    deployment of linux-bridge.
    """
    net_add_op_bridge_attached_vm.vmi.wait_until_running()


@pytest.mark.polarion("CNV-6754")
@pytest.mark.single_nic
@pytest.mark.s390x
def test_cnao_labels(
    admin_client,
    network_addons_config_scope_session,
    check_components,
    hco_namespace,
    is_post_cnv_upgrade_cluster,
):
    """
    Verify that all cnao components are labeled accordingly, first checking there are no unaccounted components,
    then checking each component's resources.
    """
    verify_cnao_labels(
        admin_client=admin_client,
        namespace=hco_namespace.name,
        network_addons_config=network_addons_config_scope_session,
        is_post_cnv_upgrade_cluster=is_post_cnv_upgrade_cluster,
    )

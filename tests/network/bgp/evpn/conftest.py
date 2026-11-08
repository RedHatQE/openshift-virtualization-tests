import ipaddress
import json
from collections.abc import Generator
from typing import Final

import ocp_resources.network_operator_openshift_io as openshift_no
import pytest
from kubernetes.dynamic import DynamicClient
from ocp_resources.cluster_operator import ClusterOperator
from ocp_resources.namespace import Namespace
from ocp_resources.node import Node
from ocp_resources.pod import Pod
from ocp_resources.resource import ResourceEditor
from ocp_resources.vtep import VTEP
from timeout_sampler import TimeoutExpiredError

from libs.net.ip import random_ipv4_address
from libs.net.traffic_generator import TcpServer
from libs.net.udn import UDN_BINDING_DEFAULT_PLUGIN_NAME, create_udn_namespace, udn_primary_network
from libs.vm.affinity import new_pod_anti_affinity
from libs.vm.factory import base_vmspec, fedora_vm
from libs.vm.spec import Devices, Metadata
from libs.vm.vm import BaseVirtualMachine
from tests.network.bgp.evpn.libevpn import (
    CUDN_EVPN_SUBNET_IPV6,
    EVPN_CUDN_NET_SEED,
    EndpointTcpClient,
    EvpnEndpoint,
    cudn_evpn_subnets,
    deploy_evpn_bridge,
    deploy_evpn_l2_endpoint,
    deploy_evpn_l3_endpoint,
    deploy_evpn_l3_vrf,
    evpn_workloads_active_connections,
    node_primary_ipv4_interface,
    teardown_evpn_bridge,
    teardown_evpn_l2_endpoint,
    teardown_evpn_l3_endpoint,
    teardown_evpn_l3_vrf,
)
from tests.network.bgp.evpn.utils import (
    L2VNI,
    L3VNI,
    OPENPE_PROVIDER_NODE_LABEL,
    OpenPERouterAttachment,
    OpenPERouterInfo,
    RawFRRConfig,
    Underlay,
    collect_openperouter_diagnostics,
    create_openperouter_l2_vni,
    create_openperouter_l3_vni,
    create_openperouter_raw_frr_config,
    create_openperouter_underlay,
    deploy_openperouter_helper_pod,
    deploy_stock_openperouter,
    openperouter_attachment_from_environment,
    openperouter_topology_cleanup,
    validate_openperouter_parent_interface,
    wait_for_openperouter_l2_vni,
    wait_for_openperouter_l3_vni,
    wait_for_openperouter_raw_frr_config,
    wait_for_openperouter_underlay,
)
from tests.network.libs import cluster_user_defined_network as libcudn
from tests.network.libs.bgp import (
    EXTERNAL_FRR_POD_LABEL,
    ExternalFrrPodInfo,
    create_cudn_route_advertisements,
    create_evpn_frr_configuration,
    wait_for_evpn_established,
)
from tests.network.libs.label_selector import LabelSelector
from tests.network.libs.vm_factory import udn_vm
from utilities.constants.hco import DEFAULT_RESOURCE_CONDITIONS
from utilities.infra import create_ns, label_nodes, wait_for_consistent_resource_conditions

EVPN_ADVERTISE_LABEL: Final[dict] = {"advertise": "evpn"}
APP_EVPN_CUDN_LABEL: Final[dict] = {**EVPN_ADVERTISE_LABEL, "app": "cudn-evpn"}
CUDN_EVPN_BGP_LABEL: Final[dict] = {"cudn-bgp": "evpn"}
EXTERNAL_L2_ENDPOINT_IPV4: Final[str] = str(random_ipv4_address(net_seed=EVPN_CUDN_NET_SEED, host_address=250))
EXTERNAL_L2_ENDPOINT_IPV6: Final[str] = f"{ipaddress.ip_network(CUDN_EVPN_SUBNET_IPV6, strict=False)[250]}/64"
EXTERNAL_L2_ENDPOINT_MAC: Final[str] = "02:00:05:00:fa:00"
EXTERNAL_L3_ENDPOINT_IPV4: Final[str] = "192.168.100.100/24"
EXTERNAL_L3_ENDPOINT_IPV6: Final[str] = "fd01:1234:5678::64/64"
EXTERNAL_L3_GATEWAY_IPV4: Final[str] = "192.168.100.1/24"
EXTERNAL_L3_GATEWAY_IPV6: Final[str] = "fd01:1234:5678::1/64"
EVPN_MAC_VRF_VNI: Final[int] = 10100
EVPN_IP_VRF_VNI: Final[int] = 20102


@pytest.fixture(scope="module")
def ovn_local_gateway_mode(
    admin_client: DynamicClient,
    network_operator: openshift_no.Network,
) -> Generator[None]:
    patch = {
        network_operator: {
            "spec": {
                "defaultNetwork": {
                    "ovnKubernetesConfig": {
                        "gatewayConfig": {"routingViaHost": True, "ipForwarding": "Global"},
                    }
                }
            }
        }
    }
    with ResourceEditor(patches=patch):
        wait_for_consistent_resource_conditions(
            dynamic_client=admin_client,
            resource_kind=ClusterOperator,
            resource_name="network",
            expected_conditions=DEFAULT_RESOURCE_CONDITIONS,
        )
        yield
    wait_for_consistent_resource_conditions(
        dynamic_client=admin_client,
        resource_kind=ClusterOperator,
        resource_name="network",
        expected_conditions=DEFAULT_RESOURCE_CONDITIONS,
    )


@pytest.fixture(scope="module")
def namespace_evpn(admin_client: DynamicClient) -> Generator[Namespace]:
    yield from create_udn_namespace(name="test-cudn-evpn-ns", client=admin_client, labels={**CUDN_EVPN_BGP_LABEL})


@pytest.fixture(scope="module")
def vtep(
    admin_client: DynamicClient,
    workers: list[Node],
) -> Generator[VTEP]:
    vtep_cidr = str(node_primary_ipv4_interface(workers[0]).network)
    with VTEP(
        name="evpn-vtep",
        cidrs=[vtep_cidr],
        mode=libcudn.VtepMode.UNMANAGED.value,
        client=admin_client,
    ) as vtep_resource:
        yield vtep_resource


@pytest.fixture(scope="module")
def cudn_evpn_layer2(
    admin_client: DynamicClient,
    namespace_evpn: Namespace,
    vtep: VTEP,
) -> Generator[libcudn.ClusterUserDefinedNetwork]:
    with libcudn.ClusterUserDefinedNetwork(
        name="l2-network-evpn",
        namespace_selector=LabelSelector(matchLabels=CUDN_EVPN_BGP_LABEL),
        network=libcudn.Network(
            topology=libcudn.Network.Topology.LAYER2.value,
            layer2=libcudn.Layer2(
                role=libcudn.Layer2.Role.PRIMARY.value,
                ipam=libcudn.Ipam(mode=libcudn.Ipam.Mode.ENABLED.value, lifecycle="Persistent"),
                subnets=cudn_evpn_subnets(),
            ),
            transport=libcudn.Transport.EVPN.value,
            evpn=libcudn.EvpnConfiguration(
                vtep=vtep.name,
                macVRF=libcudn.MacVRF(vni=EVPN_MAC_VRF_VNI),
                ipVRF=libcudn.IpVRF(vni=EVPN_IP_VRF_VNI),
            ),
        ),
        client=admin_client,
        label=APP_EVPN_CUDN_LABEL,
    ) as cudn:
        cudn.wait_for_status_success()
        yield cudn


@pytest.fixture(scope="module")
def cudn_evpn_route_advertisements(
    cudn_evpn_layer2: libcudn.ClusterUserDefinedNetwork,
    cluster_network_resource_ra_enabled: None,
    admin_client: DynamicClient,
) -> Generator[None]:
    with create_cudn_route_advertisements(
        name="evpn-route-advertisement",
        match_labels=APP_EVPN_CUDN_LABEL,
        client=admin_client,
        target_vrf="auto",
        frr_configuration_selector={"matchLabels": EVPN_ADVERTISE_LABEL},
    ):
        yield


@pytest.fixture(scope="module")
def frr_configuration_evpn(
    admin_client: DynamicClient,
    frr_external_pod: ExternalFrrPodInfo,
) -> Generator[None]:
    with create_evpn_frr_configuration(
        name="frr-configuration-evpn",
        frr_pod_ipv4=frr_external_pod.ipv4,
        client=admin_client,
        label=EVPN_ADVERTISE_LABEL,
    ):
        yield


@pytest.fixture(scope="module")
def evpn_setup_ready(
    ovn_local_gateway_mode: None,
    frr_external_pod: ExternalFrrPodInfo,
    cudn_evpn_route_advertisements: None,
    frr_configuration_evpn: None,
    workers: list[Node],
) -> None:
    node_names = [worker.name for worker in workers if worker.name != frr_external_pod.pod.instance.spec.nodeName]
    wait_for_evpn_established(frr_pod=frr_external_pod.pod, expected_neighbors=len(node_names))


@pytest.fixture(scope="module")
def vm_evpn_target(
    namespace_evpn: Namespace,
    cudn_evpn_layer2: libcudn.ClusterUserDefinedNetwork,
    admin_client: DynamicClient,
    frr_external_pod: ExternalFrrPodInfo,
) -> Generator[BaseVirtualMachine]:
    with udn_vm(
        namespace_name=namespace_evpn.name,
        name="vm-evpn-target",
        client=admin_client,
        binding=UDN_BINDING_DEFAULT_PLUGIN_NAME,
        template_labels=EXTERNAL_FRR_POD_LABEL,
        anti_affinity_namespaces=[frr_external_pod.pod.namespace, namespace_evpn.name],
    ) as vm:
        vm.start(wait=True)
        vm.wait_for_agent_connected()
        yield vm


@pytest.fixture()
def vm_evpn_reference(
    namespace_evpn: Namespace,
    cudn_evpn_layer2: libcudn.ClusterUserDefinedNetwork,
    admin_client: DynamicClient,
    frr_external_pod: ExternalFrrPodInfo,
) -> Generator[BaseVirtualMachine]:
    with udn_vm(
        namespace_name=namespace_evpn.name,
        name="vm-evpn-reference",
        client=admin_client,
        binding=UDN_BINDING_DEFAULT_PLUGIN_NAME,
        template_labels=EXTERNAL_FRR_POD_LABEL,
        anti_affinity_namespaces=[frr_external_pod.pod.namespace, namespace_evpn.name],
    ) as vm:
        vm.start(wait=True)
        vm.wait_for_agent_connected()
        yield vm


@pytest.fixture(scope="module")
def evpn_bridge(
    frr_external_pod: ExternalFrrPodInfo,
    workers: list[Node],
) -> Generator[None]:
    worker_ips = [str(node_primary_ipv4_interface(worker).ip) for worker in workers]

    deploy_evpn_bridge(
        pod=frr_external_pod.pod,
        local_vtep_ip=frr_external_pod.ipv4,
        remote_vtep_ips=worker_ips,
        l2_vni=EVPN_MAC_VRF_VNI,
        l3_vni=EVPN_IP_VRF_VNI,
    )
    yield
    teardown_evpn_bridge(pod=frr_external_pod.pod)


@pytest.fixture(scope="module")
def external_l2_endpoint(
    evpn_bridge: None,
    frr_external_pod: ExternalFrrPodInfo,
) -> Generator[EvpnEndpoint]:
    endpoint = deploy_evpn_l2_endpoint(
        pod=frr_external_pod.pod,
        endpoint_ips=[EXTERNAL_L2_ENDPOINT_IPV4, EXTERNAL_L2_ENDPOINT_IPV6],
        mac_address=EXTERNAL_L2_ENDPOINT_MAC,
    )
    yield endpoint
    teardown_evpn_l2_endpoint(endpoint=endpoint)


@pytest.fixture(scope="module")
def external_l3_vrf(
    evpn_bridge: None,
    frr_external_pod: ExternalFrrPodInfo,
) -> Generator[None]:
    deploy_evpn_l3_vrf(pod=frr_external_pod.pod, vni=EVPN_IP_VRF_VNI)
    yield
    teardown_evpn_l3_vrf(pod=frr_external_pod.pod)


@pytest.fixture(scope="module")
def external_l3_endpoint(
    external_l3_vrf: None,
    frr_external_pod: ExternalFrrPodInfo,
) -> Generator[EvpnEndpoint]:
    endpoint = deploy_evpn_l3_endpoint(
        pod=frr_external_pod.pod,
        endpoint_ips=[EXTERNAL_L3_ENDPOINT_IPV4, EXTERNAL_L3_ENDPOINT_IPV6],
        gateway_ips=[EXTERNAL_L3_GATEWAY_IPV4, EXTERNAL_L3_GATEWAY_IPV6],
    )
    yield endpoint
    teardown_evpn_l3_endpoint(endpoint=endpoint)


@pytest.fixture()
def evpn_stretched_l2_active_connections(
    external_l2_endpoint: EvpnEndpoint,
    vm_evpn_target: BaseVirtualMachine,
) -> Generator[list[tuple[EndpointTcpClient, TcpServer]]]:
    with evpn_workloads_active_connections(endpoint=external_l2_endpoint, vm=vm_evpn_target) as connections:
        yield connections


@pytest.fixture()
def evpn_routed_l3_active_connections(
    external_l3_endpoint: EvpnEndpoint,
    vm_evpn_target: BaseVirtualMachine,
) -> Generator[list[tuple[EndpointTcpClient, TcpServer]]]:
    with evpn_workloads_active_connections(endpoint=external_l3_endpoint, vm=vm_evpn_target) as connections:
        yield connections


@pytest.fixture()
def vm_source_provider(
    external_l2_endpoint: EvpnEndpoint,
    namespace_evpn: Namespace,
    cudn_evpn_layer2: libcudn.ClusterUserDefinedNetwork,
    admin_client: DynamicClient,
    frr_external_pod: ExternalFrrPodInfo,
) -> Generator[BaseVirtualMachine]:
    spec = base_vmspec()
    network_name = "udn-network"
    iface, network = udn_primary_network(name=network_name, binding=UDN_BINDING_DEFAULT_PLUGIN_NAME)
    iface.macAddress = external_l2_endpoint.mac_address
    spec.template.spec.domain.devices = Devices(interfaces=[iface])
    spec.template.spec.networks = [network]
    spec.template.metadata = Metadata(
        labels=EXTERNAL_FRR_POD_LABEL,
        annotations={"network.kubevirt.io/addresses": json.dumps({network_name: external_l2_endpoint.ip_addresses})},
    )
    label, *_ = EXTERNAL_FRR_POD_LABEL.items()
    spec.template.spec.affinity = new_pod_anti_affinity(
        label=label, namespaces=[frr_external_pod.pod.namespace, namespace_evpn.name]
    )

    with fedora_vm(namespace=namespace_evpn.name, name="vm-source-provider", client=admin_client, spec=spec) as vm:
        yield vm


EXTERNAL_L3_NET_SEED: Final[int] = EVPN_CUDN_NET_SEED + 1


EXTERNAL_L3_SUBNET_IPV4: Final[str] = str(random_ipv4_address(net_seed=EXTERNAL_L3_NET_SEED, host_address=0))


@pytest.fixture(scope="module")
def openperouter_attachment() -> OpenPERouterAttachment:
    return openperouter_attachment_from_environment()


@pytest.fixture(scope="module")
def openperouter_provider_nodes(worker_node1: Node) -> Generator[list[Node]]:
    yield from label_nodes(nodes=[worker_node1], labels=OPENPE_PROVIDER_NODE_LABEL)


@pytest.fixture(scope="module")
def openperouter_provider_node(openperouter_provider_nodes: list[Node]) -> Node:
    return openperouter_provider_nodes[0]


@pytest.fixture(scope="module")
def openperouter_namespace(admin_client: DynamicClient) -> Generator[Namespace]:
    yield from create_ns(name="test-openperouter-ns", admin_client=admin_client)


@pytest.fixture(scope="module")
def openperouter_installation(
    admin_client: DynamicClient,
    openperouter_namespace: Namespace,
    openperouter_provider_node: Node,
) -> Generator[OpenPERouterInfo]:
    with deploy_stock_openperouter(
        client=admin_client,
        namespace_name=openperouter_namespace.name,
        provider_node_name=openperouter_provider_node.name,
    ) as openperouter_info:
        yield openperouter_info


@pytest.fixture(scope="module")
def openperouter_diagnostics_pod(
    admin_client: DynamicClient,
    openperouter_installation: OpenPERouterInfo,
) -> Generator[Pod]:
    with deploy_openperouter_helper_pod(
        client=admin_client,
        namespace_name=openperouter_installation.namespace_name,
        node_name=openperouter_installation.provider_node_name,
        netns_read_only=True,
    ) as diagnostics_pod:
        yield diagnostics_pod


@pytest.fixture(scope="module")
def openperouter_underlay(
    admin_client: DynamicClient,
    openperouter_installation: OpenPERouterInfo,
    openperouter_attachment: OpenPERouterAttachment,
    openperouter_diagnostics_pod: Pod,
    openperouter_provider_node: Node,
    workers: list[Node],
) -> Generator[Underlay]:
    validate_openperouter_parent_interface(
        node=openperouter_provider_node,
        attachment=openperouter_attachment,
    )
    worker_ips = [
        str(node_primary_ipv4_interface(worker).ip)
        for worker in workers
        if worker.name != openperouter_provider_node.name
    ]
    with (
        openperouter_topology_cleanup(
            diagnostics_pod=openperouter_diagnostics_pod,
            vnis=[EVPN_MAC_VRF_VNI, EVPN_IP_VRF_VNI],
        ),
        create_openperouter_underlay(
            client=admin_client,
            namespace_name=openperouter_diagnostics_pod.namespace,
            attachment=openperouter_attachment,
            worker_ips=worker_ips,
        ) as underlay,
    ):
        try:
            wait_for_openperouter_underlay(
                diagnostics_pod=openperouter_diagnostics_pod,
                attachment=openperouter_attachment,
                worker_ips=worker_ips,
            )
        except TimeoutExpiredError:
            collect_openperouter_diagnostics(
                client=admin_client,
                namespace_name=openperouter_installation.namespace_name,
                router_pod=openperouter_installation.router_pod,
                diagnostics_pod=openperouter_diagnostics_pod,
            )
            raise
        yield underlay


@pytest.fixture(scope="module")
def openperouter_l2_vni(
    admin_client: DynamicClient,
    openperouter_installation: OpenPERouterInfo,
    openperouter_diagnostics_pod: Pod,
    openperouter_underlay: Underlay,
) -> Generator[L2VNI]:
    with create_openperouter_l2_vni(
        client=admin_client,
        namespace_name=openperouter_underlay.namespace,
        vni=EVPN_MAC_VRF_VNI,
    ) as l2_vni:
        try:
            wait_for_openperouter_l2_vni(diagnostics_pod=openperouter_diagnostics_pod, vni=EVPN_MAC_VRF_VNI)
        except TimeoutExpiredError:
            collect_openperouter_diagnostics(
                client=admin_client,
                namespace_name=openperouter_installation.namespace_name,
                router_pod=openperouter_installation.router_pod,
                diagnostics_pod=openperouter_diagnostics_pod,
            )
            raise
        yield l2_vni


@pytest.fixture(scope="module")
def openperouter_l3_vni(
    admin_client: DynamicClient,
    openperouter_installation: OpenPERouterInfo,
    openperouter_diagnostics_pod: Pod,
    openperouter_l2_vni: L2VNI,
) -> Generator[L3VNI]:
    with create_openperouter_l3_vni(
        client=admin_client,
        namespace_name=openperouter_l2_vni.namespace,
        vni=EVPN_IP_VRF_VNI,
    ) as l3_vni:
        try:
            wait_for_openperouter_l3_vni(diagnostics_pod=openperouter_diagnostics_pod)
        except TimeoutExpiredError:
            collect_openperouter_diagnostics(
                client=admin_client,
                namespace_name=openperouter_installation.namespace_name,
                router_pod=openperouter_installation.router_pod,
                diagnostics_pod=openperouter_diagnostics_pod,
            )
            raise
        yield l3_vni


@pytest.fixture(scope="module", autouse=True)
def openperouter_raw_frr_config(
    admin_client: DynamicClient,
    openperouter_installation: OpenPERouterInfo,
    openperouter_diagnostics_pod: Pod,
    openperouter_l3_vni: L3VNI,
    openperouter_provider_node: Node,
    workers: list[Node],
) -> Generator[RawFRRConfig]:
    worker_ips = [
        str(node_primary_ipv4_interface(worker).ip)
        for worker in workers
        if worker.name != openperouter_provider_node.name
    ]
    with create_openperouter_raw_frr_config(
        client=admin_client,
        namespace_name=openperouter_l3_vni.namespace,
        worker_ips=worker_ips,
        external_l3_subnet_ipv4=EXTERNAL_L3_SUBNET_IPV4,
    ) as raw_frr_config:
        try:
            wait_for_openperouter_raw_frr_config(diagnostics_pod=openperouter_diagnostics_pod)
        except TimeoutExpiredError:
            collect_openperouter_diagnostics(
                client=admin_client,
                namespace_name=openperouter_installation.namespace_name,
                router_pod=openperouter_installation.router_pod,
                diagnostics_pod=openperouter_diagnostics_pod,
            )
            raise
        yield raw_frr_config

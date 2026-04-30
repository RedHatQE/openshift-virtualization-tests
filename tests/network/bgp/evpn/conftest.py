import ipaddress
import json
from collections.abc import Generator
from typing import Final

import ocp_resources.network_operator_openshift_io as openshift_no
import pytest
from kubernetes.dynamic import DynamicClient
from ocp_resources.namespace import Namespace
from ocp_resources.node import Node
from ocp_resources.resource import ResourceEditor
from ocp_resources.vtep import VTEP

from libs.net.udn import UDN_BINDING_DEFAULT_PLUGIN_NAME, create_udn_namespace
from libs.vm.vm import BaseVirtualMachine
from tests.network.bgp.evpn.libevpn import cudn_evpn_subnets
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

EVPN_ADVERTISE_LABEL: Final[dict] = {"advertise": "evpn"}
APP_EVPN_CUDN_LABEL: Final[dict] = {**EVPN_ADVERTISE_LABEL, "app": "cudn-evpn"}
CUDN_EVPN_BGP_LABEL: Final[dict] = {"cudn-bgp": "evpn"}
EVPN_MAC_VRF_VNI: Final[int] = 10100
EVPN_IP_VRF_VNI: Final[int] = 20102


@pytest.fixture(scope="module")
def ovn_local_gateway_mode(
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
        yield


@pytest.fixture(scope="module")
def namespace_evpn(admin_client: DynamicClient) -> Generator[Namespace]:
    yield from create_udn_namespace(name="test-cudn-evpn-ns", client=admin_client, labels={**CUDN_EVPN_BGP_LABEL})


@pytest.fixture(scope="module")
def vtep(
    admin_client: DynamicClient,
    workers: list[Node],
) -> Generator[VTEP]:
    host_cidrs = json.loads(workers[0].instance.metadata.annotations["k8s.ovn.org/host-cidrs"])
    host_cidr = next(cidr for cidr in host_cidrs if "." in cidr)
    vtep_cidr = str(ipaddress.ip_network(host_cidr, strict=False))
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


@pytest.fixture(scope="module")
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

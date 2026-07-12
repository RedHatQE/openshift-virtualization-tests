from collections.abc import Generator, Iterator

import pytest
from kubernetes.dynamic import DynamicClient
from ocp_resources.namespace import Namespace

from libs.net import nodenetworkconfigurationpolicy as libnncp
from libs.net.netattachdef import CNIPluginBridgeConfig, NetConfig, NetworkAttachmentDefinition
from utilities.constants.cluster import WORKER_NODE_LABEL_KEY
from utilities.constants.networking import LINUX_BRIDGE


@pytest.fixture(scope="module")
def bridge_nncp(
    nmstate_dependent_placeholder: None,
    admin_client: DynamicClient,
    hosts_common_available_ports: list[str],
) -> Generator[libnncp.NodeNetworkConfigurationPolicy]:
    with libnncp.NodeNetworkConfigurationPolicy(
        client=admin_client,
        name="l2-bridge-test-nncp",
        desired_state=libnncp.DesiredState(
            interfaces=[
                libnncp.Interface(
                    name="br1-test",
                    type=LINUX_BRIDGE,
                    state=libnncp.Resource.Interface.State.UP,
                    bridge=libnncp.Bridge(
                        port=[libnncp.Port(name=hosts_common_available_ports[-1])],
                        options=libnncp.BridgeOptions(libnncp.STP(enabled=False)),
                    ),
                )
            ]
        ),
        node_selector={WORKER_NODE_LABEL_KEY: ""},
    ) as nncp_br:
        nncp_br.wait_for_status_success()
        yield nncp_br


@pytest.fixture(scope="module")
def bridge_nad_a(
    admin_client: DynamicClient,
    namespace: Namespace,
    bridge_nncp: libnncp.NodeNetworkConfigurationPolicy,
    cluster_vlan_ids: Iterator[int],
) -> Generator[NetworkAttachmentDefinition]:
    bridge = bridge_nncp.desired_state_spec.interfaces[0].name  # type: ignore
    with NetworkAttachmentDefinition(
        name="nad-vlan-a",
        namespace=namespace.name,
        config=NetConfig(
            name="nad-vlan-a", plugins=[CNIPluginBridgeConfig(bridge=bridge, vlan=next(cluster_vlan_ids))]
        ),
        client=admin_client,
    ) as nad:
        yield nad


@pytest.fixture(scope="module")
def bridge_nad_b(
    admin_client: DynamicClient,
    namespace: Namespace,
    bridge_nncp: libnncp.NodeNetworkConfigurationPolicy,
    cluster_vlan_ids: Iterator[int],
) -> Generator[NetworkAttachmentDefinition]:
    bridge = bridge_nncp.desired_state_spec.interfaces[0].name  # type: ignore[union-attr, index]
    with NetworkAttachmentDefinition(
        name="nad-vlan-b",
        namespace=namespace.name,
        config=NetConfig(
            name="nad-vlan-b", plugins=[CNIPluginBridgeConfig(bridge=bridge, vlan=next(cluster_vlan_ids))]
        ),
        client=admin_client,
    ) as nad:
        yield nad

import json
import os
import shlex
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Final

import ocp_resources.network_config_openshift_io as openshift_nc
import yaml
from kubernetes.dynamic import DynamicClient
from kubernetes.dynamic.exceptions import ResourceNotFoundError
from ocp_resources.bgp_session_state import BGPSessionState
from ocp_resources.cluster_operator import ClusterOperator
from ocp_resources.exceptions import ExecOnPodError
from ocp_resources.frr_configuration import FRRConfiguration
from ocp_resources.pod import Pod
from ocp_resources.resource import ResourceEditor
from ocp_resources.route_advertisements import RouteAdvertisements
from timeout_sampler import retry

from libs.net.vmspec import IpNotFound
from utilities.constants.hco import DEFAULT_RESOURCE_CONDITIONS
from utilities.constants.namespaces import NamespacesNames
from utilities.constants.networking import NET_UTIL_CONTAINER_IMAGE
from utilities.infra import get_resources_by_name_prefix, wait_for_consistent_resource_conditions

OPENPE_CONTAINER_NAME: Final[str] = "openpe"
OPENPE_IMAGE: Final[str] = os.environ.get(
    "CNV_EXTERNAL_OPENPE_IMAGE",
    "quay.io/ramlavi/openperouter@sha256:8f48574c97e3ab7ee7237482c070c9cec4f492ec59b06812a93b1c613a4ba5af",
)
EVPN_MAC_VRF_VNI: Final[int] = 10100
EVPN_IP_VRF_VNI: Final[int] = 20102
OPENPE_L3_VRF_NAME: Final[str] = "vrf-blue"
OPENPE_VTEP_POOL_IPV4: Final[str] = "100.64.0.0/24"
CLUSTER_FRR_ASN: Final[int] = 64512
EXTERNAL_FRR_ASN: Final[int] = 64000
POD_SECONDARY_IFACE_NAME: Final[str] = "net1"
NET_TOOLS_CONTAINER_NAME: Final[str] = "net-tools"
EXTERNAL_FRR_POD_LABEL: Final[dict] = {"role": "frr-external"}


@dataclass
class ExternalFrrPodInfo:
    pod: Pod
    ipv4: str


@contextmanager
def enable_route_advertisements_in_cluster(
    network_resource: openshift_nc.Network, client: DynamicClient
) -> Generator[None]:
    """Enables route advertisements in the cluster network resource and deploys FRR.

    Within the context, the cluster network resource is patched to enable
    additional routing capabilities with FRR and to enable route advertisements for OVN-Kubernetes.
    Waits for the network ClusterOperator to stabilize before proceeding.

    After the context is exited, the changes are reverted.

    Args:
        network_resource (openshift_nc.Network): The cluster network resource to be patched.
        client: DynamicClient: The Kubernetes dynamic client.

    Yields:
        None
    """
    patch = {
        network_resource: {
            "spec": {
                "additionalRoutingCapabilities": {"providers": ["FRR"]},
                "defaultNetwork": {"ovnKubernetesConfig": {"routeAdvertisements": "Enabled"}},
            }
        }
    }

    with ResourceEditor(patches=patch):
        wait_for_consistent_resource_conditions(
            dynamic_client=client,
            resource_kind=ClusterOperator,
            resource_name=network_resource.kind.lower(),
            expected_conditions=DEFAULT_RESOURCE_CONDITIONS,
        )
        yield


def create_cudn_route_advertisements(
    name: str,
    match_labels: dict,
    client: DynamicClient,
    target_vrf: str | None = None,
    frr_configuration_selector: dict | None = None,
) -> RouteAdvertisements:
    """Creates a RouteAdvertisements object for a ClusterUserDefinedNetwork (CUDN) based on the provided labels.

    Args:
        name: The name of the RouteAdvertisements object.
        match_labels: A dictionary of labels to match the CUDN.
        client: The Kubernetes dynamic client.
        target_vrf: The VRF to advertise routes in.
        frr_configuration_selector: Label selector for matching FRRConfiguration resources.

    Returns:
        RouteAdvertisements: The created RouteAdvertisements object.
    """
    network_selectors = [
        {
            "networkSelectionType": "ClusterUserDefinedNetworks",
            "clusterUserDefinedNetworkSelector": {"networkSelector": {"matchLabels": match_labels}},
        }
    ]

    return RouteAdvertisements(
        name=name,
        advertisements=["PodNetwork"],
        network_selectors=network_selectors,
        node_selector={},
        frr_configuration_selector=frr_configuration_selector or {},
        target_vrf=target_vrf,
        client=client,
    )


def create_frr_configuration(
    name: str, frr_pod_ipv4: str, external_subnet_ipv4: str, client: DynamicClient
) -> FRRConfiguration:
    """Creates a FRRConfiguration object for BGP setup.

    Args:
        name (str): The name of the FRRConfiguration object.
        frr_pod_ipv4 (str): The IPv4 address of the FRR pod to be configured as a BGP neighbor.
        external_subnet_ipv4 (str): The external IPv4 subnet to be advertised.
        client: DynamicClient: The Kubernetes dynamic client.

    Returns:
        FRRConfiguration: The created FRRConfiguration object.
    """
    bgp_config = {
        "routers": [
            {
                "asn": CLUSTER_FRR_ASN,
                "neighbors": [
                    {
                        "address": frr_pod_ipv4,
                        "asn": EXTERNAL_FRR_ASN,
                        "disableMP": True,
                        "toReceive": {"allowed": {"mode": "filtered", "prefixes": [{"prefix": external_subnet_ipv4}]}},
                    }
                ],
            }
        ]
    }

    return FRRConfiguration(name=name, namespace=NamespacesNames.OPENSHIFT_FRR_K8S, bgp=bgp_config, client=client)


def create_evpn_frr_configuration(
    name: str, frr_pod_ipv4: str, client: DynamicClient, label: dict[str, str] | None = None
) -> FRRConfiguration:
    """Creates a FRRConfiguration for BGP EVPN setup.

    Args:
        name: The name of the FRRConfiguration object.
        frr_pod_ipv4: The IPv4 address of the external FRR pod.
        client: The Kubernetes dynamic client.
        label: Labels for the FRRConfiguration.

    Returns:
        FRRConfiguration for EVPN peering.
    """
    bgp_config = {
        "routers": [
            {
                "asn": CLUSTER_FRR_ASN,
                "neighbors": [
                    {
                        "address": frr_pod_ipv4,
                        "asn": EXTERNAL_FRR_ASN,
                    }
                ],
            }
        ]
    }
    return FRRConfiguration(
        name=name, namespace=NamespacesNames.OPENSHIFT_FRR_K8S, bgp=bgp_config, label=label, client=client
    )


def openpe_l2_bridge_name(vni: int) -> str:
    """Returns the OpenPE managed L2 bridge name for the given VNI.

    Args:
        vni: MAC-VRF VNI.

    Returns:
        Managed Linux bridge name created by OpenPE.
    """
    return f"br-hs-{vni}"


def generate_openpe_yaml(
    worker_ipv4_list: list[str],
    external_subnet_ipv4: str,
    mac_vrf_vni: int = EVPN_MAC_VRF_VNI,
    ip_vrf_vni: int = EVPN_IP_VRF_VNI,
) -> str:
    """Generates OpenPE static configuration for the external ToR router.

    Args:
        worker_ipv4_list: IPv4 addresses of cluster workers to peer with.
        external_subnet_ipv4: External IPv4 subnet advertised to the cluster.
        mac_vrf_vni: MAC-VRF VNI for stretched L2 connectivity.
        ip_vrf_vni: IP-VRF VNI for routed L3 connectivity.

    Returns:
        OpenPE static configuration YAML.
    """
    if not worker_ipv4_list:
        raise ValueError("worker_ipv4_list cannot be empty")

    evpn_route_map = "evpn-to-ocp"
    raw_config_lines = [
        f"route-map {evpn_route_map} permit 10",
        " set ip next-hop unchanged",
        "!",
        f"router bgp {EXTERNAL_FRR_ASN}",
        " address-family l2vpn evpn",
    ]
    for worker_ipv4 in worker_ipv4_list:
        raw_config_lines.append(f"  neighbor {worker_ipv4} route-map {evpn_route_map} out")
    raw_config_lines.extend([
        " exit-address-family",
        "!",
        f"router bgp {EXTERNAL_FRR_ASN} vrf {OPENPE_L3_VRF_NAME}",
        " address-family ipv4 unicast",
        "  redistribute connected",
        " exit-address-family",
        " address-family ipv6 unicast",
        "  redistribute connected",
        " exit-address-family",
        "!",
        f"router bgp {EXTERNAL_FRR_ASN}",
        " address-family ipv4 unicast",
        f"  network {external_subnet_ipv4}",
    ])
    for worker_ipv4 in worker_ipv4_list:
        raw_config_lines.append(f"  neighbor {worker_ipv4} next-hop-self")

    openpe_config = {
        "underlays": [
            {
                "asn": EXTERNAL_FRR_ASN,
                "neighbors": [{"asn": CLUSTER_FRR_ASN, "address": worker_ipv4} for worker_ipv4 in worker_ipv4_list],
                "tunnelEndpoint": {"cidrs": [OPENPE_VTEP_POOL_IPV4]},
            }
        ],
        "l2vnis": [
            {
                "name": "mac-vrf",
                "vni": mac_vrf_vni,
                "hostMaster": {
                    "type": "LinuxBridge",
                    "linuxBridge": {"lifecycle": "Managed"},
                },
            }
        ],
        "l3vnis": [
            {
                "name": "ip-vrf",
                "vrf": OPENPE_L3_VRF_NAME,
                "vni": ip_vrf_vni,
            }
        ],
        "rawfrrconfigs": [{"rawConfig": "\n".join(raw_config_lines)}],
    }
    return yaml.dump(openpe_config, default_flow_style=False)


@contextmanager
def deploy_external_frr_pod(
    namespace_name: str,
    node_name: str,
    nad_name: str,
    openpe_configmap_name: str,
    client: DynamicClient,
) -> Generator[ExternalFrrPodInfo]:
    """Deploys an external OpenPE ToR pod in a specified namespace.

    On entering the context, this function creates a privileged pod with the OpenPE image,
    attaches it to a specified NetworkAttachmentDefinition (NAD), and mounts a ConfigMap for
    OpenPE static configuration. On exiting the context, the pod is automatically deleted.

    A net-tools sidecar is included for DHCP, interface setup, and connectivity testing.

    Args:
        namespace_name: The name of the namespace where the pod will be deployed.
        node_name: The name of the node where the pod will be scheduled.
        nad_name: The name of the NetworkAttachmentDefinition (NAD) to attach to the pod.
        openpe_configmap_name: The name of the ConfigMap containing OpenPE configuration.
        client: The Kubernetes dynamic client.

    Yields:
        ExternalFrrPodInfo: The info about deployed external ToR pod, including its IPv4 address.
    """
    annotations = {
        f"{Pod.ApiGroup.K8S_V1_CNI_CNCF_IO}/networks": json.dumps([
            {"name": nad_name, "interface": POD_SECONDARY_IFACE_NAME},
        ]),
    }
    containers = [
        {
            "name": OPENPE_CONTAINER_NAME,
            "image": OPENPE_IMAGE,
            "securityContext": {"privileged": True, "capabilities": {"add": ["NET_ADMIN"]}},
            "volumeMounts": [
                {
                    "name": openpe_configmap_name,
                    "mountPath": "/etc/openperouter/node-config.yaml",
                    "subPath": "node-config.yaml",
                },
                {
                    "name": openpe_configmap_name,
                    "mountPath": "/etc/openperouter/configs/openpe_tor.yaml",
                    "subPath": "openpe_tor.yaml",
                },
            ],
        },
        {
            "name": NET_TOOLS_CONTAINER_NAME,
            "image": NET_UTIL_CONTAINER_IMAGE,
            "securityContext": {"privileged": True, "capabilities": {"add": ["NET_ADMIN"]}},
            "command": ["sleep", "infinity"],
        },
    ]
    volumes = [{"name": openpe_configmap_name, "configMap": {"name": openpe_configmap_name}}]

    with Pod(
        name="frr-external",
        namespace=namespace_name,
        annotations=annotations,
        node_name=node_name,
        containers=containers,
        volumes=volumes,
        client=client,
        label=EXTERNAL_FRR_POD_LABEL,
    ) as pod:
        pod.wait_for_status(status=Pod.Status.RUNNING)
        ipv4 = _acquire_dhcp_ipv4(pod=pod, iface_name=POD_SECONDARY_IFACE_NAME)

        yield ExternalFrrPodInfo(pod=pod, ipv4=ipv4)


def _acquire_dhcp_ipv4(pod: Pod, iface_name: str) -> str:
    pod.execute(command=shlex.split(f"dhclient {iface_name}"), container=NET_TOOLS_CONTAINER_NAME)

    iface_info = json.loads(
        pod.execute(command=shlex.split(f"ip -j -4 addr show {iface_name}"), container=NET_TOOLS_CONTAINER_NAME)
    )
    if iface_info and "addr_info" in iface_info[0]:
        for addr in iface_info[0]["addr_info"]:
            if addr["family"] == "inet":
                return addr["local"]

    raise IpNotFound(f"IP address not found for interface {iface_name}")


def wait_for_bgp_connection_established(node_names: list) -> None:
    """Waits for BGP sessions to be established.

    Args:
        node_names (list): A list of node names to check for BGP session establishment.

    Raises:
        ResourceNotFoundError: If the BGPSessionState resource is not found for any of the nodes.
    """
    for node_name in node_names:
        _get_bgp_session_state(node_name=node_name).wait_for_session_established()


@retry(
    wait_timeout=300,
    sleep=10,
    exceptions_dict={RuntimeError: []},
)
def wait_for_evpn_established(frr_pod: Pod, expected_neighbors: int) -> bool:
    """Waits for all expected EVPN neighbors to have received at least one prefix.

    Args:
        frr_pod: The external FRR pod to query.
        expected_neighbors: Number of neighbors expected to have received EVPN prefixes.
    """
    output = frr_pod.execute(
        command=shlex.split('vtysh -c "show bgp l2vpn evpn summary json"'),
        container=OPENPE_CONTAINER_NAME,
    )
    summary = json.loads(output)
    peers = summary.get("peers", {})
    active_count = sum(1 for peer_info in peers.values() if peer_info.get("pfxRcd", 0) > 0)
    if active_count < expected_neighbors:
        raise RuntimeError(f"EVPN not fully established: {active_count}/{expected_neighbors} neighbors active")
    return True


@retry(
    wait_timeout=60,
    sleep=5,
    exceptions_dict={ResourceNotFoundError: []},
)
def _get_bgp_session_state(node_name: str) -> BGPSessionState:
    bgp_session_state = get_resources_by_name_prefix(
        prefix=node_name, namespace=NamespacesNames.OPENSHIFT_FRR_K8S, api_resource_name=BGPSessionState
    )  # type: ignore[no-untyped-call]
    if bgp_session_state:
        return bgp_session_state[0]

    raise ResourceNotFoundError(
        f"BGPSessionState for node '{node_name}' not found in namespace '{NamespacesNames.OPENSHIFT_FRR_K8S}'"
    )


@retry(
    wait_timeout=120,
    sleep=5,
    exceptions_dict={ExecOnPodError: []},
)
def wait_for_openpe_interface(pod: Pod, iface_name: str) -> bool:
    """Waits for an OpenPE-managed interface to exist in the external ToR pod.

    Args:
        pod: The external OpenPE pod.
        iface_name: Interface name to wait for.

    Returns:
        True when the interface exists.
    """
    pod.execute(
        command=shlex.split(f"ip link show dev {iface_name}"),
        container=NET_TOOLS_CONTAINER_NAME,
    )
    return True

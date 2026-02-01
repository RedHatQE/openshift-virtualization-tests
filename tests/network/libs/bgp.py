import json
import shlex
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Final

import ocp_resources.network_config_openshift_io as openshift_nc
from kubernetes.dynamic import DynamicClient
from kubernetes.dynamic.exceptions import ResourceNotFoundError
from ocp_resources.bgp_session_state import BGPSessionState
from ocp_resources.deployment import Deployment
from ocp_resources.frr_configuration import FRRConfiguration
from ocp_resources.namespace import Namespace
from ocp_resources.pod import Pod
from ocp_resources.resource import ResourceEditor
from ocp_resources.route_advertisements import RouteAdvertisements
from timeout_sampler import retry

from libs.net.vmspec import IpNotFound
from utilities.constants import NET_UTIL_CONTAINER_IMAGE, NamespacesNames
from utilities.infra import get_resources_by_name_prefix

_CLUSTER_FRR_ASN: Final[int] = 64512
_EXTERNAL_FRR_ASN: Final[int] = 64000
_EXTERNAL_FRR_IMAGE: Final[str] = "quay.io/frrouting/frr:9.1.2"
_FRR_DEPLOYMENT_NAME: Final[str] = "frr-k8s-statuscleaner"
POD_SECONDARY_IFACE_NAME: Final[str] = "net1"
EXTERNAL_FRR_POD_LABEL: Final[dict] = {"role": "frr-external"}


@dataclass
class ExternalFrrPodInfo:
    pod: Pod
    ipv4: str


@contextmanager
def enable_route_advertisements_in_cluster(
    network_resource: openshift_nc.Network, client: DynamicClient
) -> Generator[None]:
    """Enables route advertisements in the cluster network resource and deploys the FRR deployment.

    Within the context, the cluster network resource is patched to enable
    additional routing capabilities with FRR and to enable route advertisements for OVN-Kubernetes.
    The FRR deployment is then created in the designated namespace and waits for its replicas to be ready.

    After the context is exited, the changes are reverted and the FRR namespace is cleaned up.
    The cleanup is expected by the un-patching of the changes (ResourceEditor cleanup).
    However, it has been observed that the NS is not removed
    and therefore an explicit delete on the NS is performed.

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
        deployment = Deployment(name=_FRR_DEPLOYMENT_NAME, namespace=NamespacesNames.OPENSHIFT_FRR_K8S, client=client)
        deployment.wait_for_replicas()

        yield

    Namespace(name=NamespacesNames.OPENSHIFT_FRR_K8S, client=client).clean_up()


def create_cudn_route_advertisements(name: str, match_labels: dict, client: DynamicClient) -> RouteAdvertisements:
    """Creates a RouteAdvertisements object for a ClusterUserDefinedNetwork (CUDN) based on the provided labels.

    Args:
        name (str): The name of the RouteAdvertisements object.
        match_labels (dict): A dictionary of labels to match the CUDN.
        client (DynamicClient): The Kubernetes dynamic client.

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
        frr_configuration_selector={},
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
                "asn": _CLUSTER_FRR_ASN,
                "neighbors": [
                    {
                        "address": frr_pod_ipv4,
                        "asn": _EXTERNAL_FRR_ASN,
                        "disableMP": True,
                        "toReceive": {"allowed": {"mode": "filtered", "prefixes": [{"prefix": external_subnet_ipv4}]}},
                    }
                ],
            }
        ]
    }

    return FRRConfiguration(name=name, namespace=NamespacesNames.OPENSHIFT_FRR_K8S, bgp=bgp_config, client=client)


def generate_frr_conf(
    external_subnet_ipv4: str,
    nodes_ipv4_list: list[str],
) -> str:
    """Generates a FRR configuration for the external FRR router.

    Args:
        external_subnet_ipv4 (str): The external IPv4 subnet to be advertised.
        nodes_ipv4_list (list[str]): IPv4 addresses of the cluster nodes to be configured as BGP neighbors.

    Returns:
        str: The generated FRR configuration as a string.
    """
    if not nodes_ipv4_list:
        raise ValueError("nodes_ipv4_list cannot be empty")

    lines = [
        f"router bgp {_EXTERNAL_FRR_ASN}",
        " no bgp ebgp-requires-policy",
        " no bgp default ipv4-unicast",
        " no bgp network import-check",
        "",
    ]

    lines.extend([f" neighbor {ip} remote-as {_CLUSTER_FRR_ASN}" for ip in nodes_ipv4_list])
    lines.append("")

    lines.extend([
        " address-family ipv4 unicast",
        f"  network {external_subnet_ipv4}",
    ])

    for ip in nodes_ipv4_list:
        lines.extend([
            f"  neighbor {ip} activate",
            f"  neighbor {ip} next-hop-self",
            f"  neighbor {ip} route-reflector-client",
        ])

    lines.append(" exit-address-family")

    return "\n".join(lines)


@contextmanager
def deploy_external_frr_pod(
    namespace_name: str,
    node_name: str,
    nad_name: str,
    frr_configmap_name: str,
    client: DynamicClient,
) -> Generator[ExternalFrrPodInfo]:
    """Deploys an external FRR (Free Range Routing) pod in a specified namespace.

    On entering the context, this function creates a privileged pod with the FRR image,
    attaches it to a specified NetworkAttachmentDefinition (NAD), and mounts a ConfigMap for FRR
    configuration. On exiting the context, the pod is automatically deleted.

    Also contains an iperf3 container to be used for connectivity testing. The process namespace
    of the iperf3 container is shared with the frr container for the sake of process management
    (due to the minimal capabilities of the iperf3 container).

    Args:
        namespace_name (str): The name of the namespace where the pod will be deployed.
        node_name (str): The name of the node where the pod will be scheduled.
        nad_name (str): The name of the NetworkAttachmentDefinition (NAD) to attach to the pod.
        frr_configmap_name (str): The name of the ConfigMap containing FRR configuration.
        client (DynamicClient): The Kubernetes dynamic client.

    Yields:
        ExternalFrrPodInfo: The info about deployed external FRR pod, including its IPv4 address.
    """
    annotations = {
        f"{Pod.ApiGroup.K8S_V1_CNI_CNCF_IO}/networks": json.dumps([
            {"name": nad_name, "interface": POD_SECONDARY_IFACE_NAME},
        ]),
    }
    containers = [
        {
            "name": "frr",
            "image": _EXTERNAL_FRR_IMAGE,
            "securityContext": {"privileged": True, "capabilities": {"add": ["NET_ADMIN"]}},
            "volumeMounts": [{"name": frr_configmap_name, "mountPath": "/etc/frr"}],
        },
        {
            "name": "iperf3",
            "image": NET_UTIL_CONTAINER_IMAGE,
            "securityContext": {"privileged": True, "capabilities": {"add": ["NET_ADMIN"]}},
            "command": ["sleep", "infinity"],
        },
    ]
    volumes = [{"name": frr_configmap_name, "configMap": {"name": frr_configmap_name}}]

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
    pod.execute(command=shlex.split(f"dhclient {iface_name}"), container="iperf3")

    iface_info = json.loads(pod.execute(command=shlex.split(f"ip -j -4 addr show {iface_name}")))
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

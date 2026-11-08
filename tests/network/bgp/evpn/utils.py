from contextlib import contextmanager
from dataclasses import dataclass
from ipaddress import ip_interface, ip_network
from json import JSONDecodeError, loads
from logging import getLogger
from os import environ
from typing import TYPE_CHECKING, Any, Final

from ocp_resources.cluster_service_version import ClusterServiceVersion
from ocp_resources.exceptions import ExecOnPodError
from ocp_resources.node import Node
from ocp_resources.node_network_state import NodeNetworkState
from ocp_resources.operator_group import OperatorGroup
from ocp_resources.package_manifest import PackageManifest
from ocp_resources.pod import Pod
from ocp_resources.resource import NamespacedResource
from ocp_resources.subscription import Subscription
from ocp_resources.validating_webhook_config import ValidatingWebhookConfiguration
from timeout_sampler import TimeoutExpiredError, TimeoutSampler, retry

from tests.network.libs.bgp import CLUSTER_FRR_ASN, EXTERNAL_FRR_ASN, NET_TOOLS_CONTAINER_NAME
from utilities.constants.networking import NET_UTIL_CONTAINER_IMAGE

if TYPE_CHECKING:
    from collections.abc import Generator

    from kubernetes.dynamic import DynamicClient


LOGGER = getLogger(name=__name__)

OPENPE_API_GROUP: Final[str] = "network.openperouter.io"
OPENPE_API_VERSION: Final[str] = "v1alpha1"
OPENPE_OPERATOR_PACKAGE: Final[str] = "openperouter-operator"
OPENPE_OPERATOR_CHANNEL: Final[str] = "5.0"
OPENPE_MARKETPLACE_NAMESPACE: Final[str] = "openshift-marketplace"
OPENPE_WEBHOOK_NAME: Final[str] = "openpe-validating-webhook-configuration"
OPENPE_PROVIDER_NODE_LABEL: Final[dict[str, str]] = {"cnv-qe/openpe-evpn-provider": "true"}
OPENPE_TEST_RESOURCE_LABEL: Final[dict[str, str]] = {"cnv-qe/openpe-evpn-test": "true"}
OPENPE_HELPER_LABEL: Final[dict[str, str]] = {"cnv-qe/openpe-helper": "true"}
OPENPE_UNDERLAY_PARENT_ENV: Final[str] = "OPENPE_UNDERLAY_PARENT"
OPENPE_PROVIDER_IPV4_ENV: Final[str] = "OPENPE_PROVIDER_IPV4"
OPENPE_VTEP_CIDR_ENV: Final[str] = "OPENPE_VTEP_CIDR"
OPENPE_ROUTER_NAMESPACE: Final[str] = "perouter"
OPENPE_UNDERLAY_INTERFACE_NAME: Final[str] = "net1"
OPENPE_L3_VRF_NAME: Final[str] = "vrf-blue"


@dataclass(frozen=True)
class OpenPERouterAttachment:
    """Validated provider-side underlay attachment values."""

    parent_interface: str
    provider_ipv4: str
    vtep_cidr: str


@dataclass(frozen=True)
class OpenPERouterInfo:
    """Stock OpenPERouter deployment information."""

    namespace_name: str
    provider_node_name: str
    router_pod: Pod


class OpenPERouter(NamespacedResource):
    """Operator-managed stock OpenPERouter deployment."""

    api_group = OPENPE_API_GROUP
    api_version = OPENPE_API_VERSION

    def __init__(self, client: DynamicClient, namespace: str, node_selector: dict[str, str]) -> None:
        super().__init__(client=client, name="openperouter", namespace=namespace)
        self.node_selector = node_selector

    def to_dict(self) -> None:
        super().to_dict()
        self.res["spec"] = {"logLevel": "info", "nodeSelector": self.node_selector}


class Underlay(NamespacedResource):
    """OpenPERouter Underlay custom resource."""

    api_group = OPENPE_API_GROUP
    api_version = OPENPE_API_VERSION


class L2VNI(NamespacedResource):
    """OpenPERouter L2VNI custom resource."""

    api_group = OPENPE_API_GROUP
    api_version = OPENPE_API_VERSION


class L3VNI(NamespacedResource):
    """OpenPERouter L3VNI custom resource."""

    api_group = OPENPE_API_GROUP
    api_version = OPENPE_API_VERSION


class RawFRRConfig(NamespacedResource):
    """OpenPERouter RawFRRConfig custom resource."""

    api_group = OPENPE_API_GROUP
    api_version = OPENPE_API_VERSION


def openperouter_attachment_from_environment() -> OpenPERouterAttachment:
    """Reads and validates the required OpenPERouter underlay attachment.

    Returns:
        The validated parent interface, provider IPv4 address, and VTEP CIDR.

    Raises:
        ValueError: If a required value is missing or is not a usable IPv4 host
            address, or if the VTEP pool is not a routable IPv4 /32.
    """
    parent_interface = _required_environment_variable(name=OPENPE_UNDERLAY_PARENT_ENV)
    provider_ipv4 = _required_environment_variable(name=OPENPE_PROVIDER_IPV4_ENV)
    vtep_cidr = _required_environment_variable(name=OPENPE_VTEP_CIDR_ENV)

    provider_interface = ip_interface(address=provider_ipv4)
    if provider_interface.version != 4:
        raise ValueError(f"{OPENPE_PROVIDER_IPV4_ENV} must be an IPv4 address with prefix: {provider_ipv4}")

    provider_network = provider_interface.network
    if provider_network.prefixlen < 31 and provider_interface.ip in (
        provider_network.network_address,
        provider_network.broadcast_address,
    ):
        raise ValueError(f"{OPENPE_PROVIDER_IPV4_ENV} must be a usable host address: {provider_ipv4}")

    vtep_network = ip_network(address=vtep_cidr, strict=True)
    if vtep_network.version != 4 or vtep_network.prefixlen != 32:
        raise ValueError(f"{OPENPE_VTEP_CIDR_ENV} must be a routable IPv4 /32: {vtep_cidr}")

    return OpenPERouterAttachment(
        parent_interface=parent_interface,
        provider_ipv4=provider_ipv4,
        vtep_cidr=vtep_cidr,
    )


def validate_openperouter_parent_interface(node: Node, attachment: OpenPERouterAttachment) -> None:
    """Validates that the configured parent interface exists on the provider node.

    Args:
        node: The node that will host OpenPERouter.
        attachment: The validated underlay attachment.

    Raises:
        ValueError: If the configured parent interface is not present in the
            node's reported network state.
    """
    interface_names = [
        interface["name"] for interface in NodeNetworkState(name=node.name, client=node.client).interfaces
    ]
    if attachment.parent_interface not in interface_names:
        raise ValueError(
            f"OpenPERouter parent interface {attachment.parent_interface} does not exist on node {node.name}. "
            f"Existing interfaces: {interface_names}"
        )


@contextmanager
def deploy_stock_openperouter(
    client: DynamicClient,
    namespace_name: str,
    provider_node_name: str,
) -> Generator[OpenPERouterInfo]:
    """Installs stock OpenPERouter through the downstream OLM catalog.

    Args:
        client: Kubernetes dynamic client.
        namespace_name: Test-owned namespace for the operator and router.
        provider_node_name: Node selected for the OpenPERouter provider.

    Yields:
        Information about the deployed stock OpenPERouter.
    """
    _ensure_no_existing_openperouter_installation(client=client)
    catalog_source = _openperouter_catalog_source(client=client)

    provider_node_label_key, provider_node_label_value = next(iter(OPENPE_PROVIDER_NODE_LABEL.items()))
    provider_node_label_selector = f"{provider_node_label_key}={provider_node_label_value}"
    provider_node_names = [
        labelled_node.name for labelled_node in Node.get(client=client, label_selector=provider_node_label_selector)
    ]
    if provider_node_names != [provider_node_name]:
        raise RuntimeError(
            f"OpenPERouter provider label must select exactly {provider_node_name}; it selected {provider_node_names}"
        )

    with OperatorGroup(client=client, name="openperouter", namespace=namespace_name):
        try:
            with Subscription(
                client=client,
                name=OPENPE_OPERATOR_PACKAGE,
                namespace=namespace_name,
                package_name=OPENPE_OPERATOR_PACKAGE,
                channel=OPENPE_OPERATOR_CHANNEL,
                source=catalog_source,
                source_namespace=OPENPE_MARKETPLACE_NAMESPACE,
                install_plan_approval="Automatic",
            ) as subscription:
                for csv_name in TimeoutSampler(
                    wait_timeout=600,
                    sleep=5,
                    func=lambda: subscription.instance.get("status", {}).get("installedCSV"),
                ):
                    if csv_name:
                        break
                csv = ClusterServiceVersion(client=client, namespace=namespace_name, name=csv_name)
                csv.wait_for_status(status=ClusterServiceVersion.Status.SUCCEEDED, timeout=600)
                with OpenPERouter(
                    client=client,
                    namespace=namespace_name,
                    node_selector=OPENPE_PROVIDER_NODE_LABEL,
                ):
                    try:
                        _wait_for_openperouter_pods(client=client, namespace_name=namespace_name)
                        router_pod = _get_single_pod(
                            client=client,
                            namespace_name=namespace_name,
                            label_selector="app=router",
                        )
                        if router_pod.instance.spec.nodeName != provider_node_name:
                            raise RuntimeError(
                                f"OpenPERouter router is on {router_pod.instance.spec.nodeName}; "
                                f"expected provider node {provider_node_name}"
                            )
                        yield OpenPERouterInfo(
                            namespace_name=namespace_name,
                            provider_node_name=provider_node_name,
                            router_pod=router_pod,
                        )
                    except TimeoutExpiredError:
                        _collect_openperouter_pod_logs(client=client, namespace_name=namespace_name)
                        raise
        finally:
            try:
                for pods in TimeoutSampler(
                    wait_timeout=300,
                    sleep=5,
                    func=lambda: list(
                        Pod.get(
                            client=client,
                            namespace=namespace_name,
                            label_selector="app in (controller,router,nodemarker)",
                        )
                    ),
                ):
                    if not pods:
                        break
            finally:
                for csv in ClusterServiceVersion.get(client=client, namespace=namespace_name):
                    if csv.name.startswith(f"{OPENPE_OPERATOR_PACKAGE}."):
                        if not csv.clean_up():
                            raise RuntimeError(f"Failed to remove OpenPERouter CSV {csv.namespace}/{csv.name}")


@contextmanager
def deploy_openperouter_helper_pod(
    client: DynamicClient,
    namespace_name: str,
    node_name: str,
    netns_read_only: bool,
) -> Generator[Pod]:
    """Deploys a node-pinned helper for OpenPERouter diagnostics or endpoints.

    Args:
        client: Kubernetes dynamic client.
        namespace_name: Test-owned OpenPERouter namespace.
        node_name: Provider node selected for OpenPERouter.
        netns_read_only: Whether the host network-namespace directory is mounted
            read-only for diagnostics. Endpoint creation requires a writable
            mount with bidirectional propagation.

    Yields:
        The helper pod.
    """
    netns_mount = {
        "name": "host-netns",
        "mountPath": "/var/run/netns",
        "readOnly": netns_read_only,
        "mountPropagation": "HostToContainer" if netns_read_only else "Bidirectional",
    }
    with Pod(
        client=client,
        name="openpe-endpoint-helper" if not netns_read_only else "openpe-diagnostics",
        namespace=namespace_name,
        node_name=node_name,
        host_network=netns_read_only,
        label=OPENPE_HELPER_LABEL,
        service_account_name="perouter",
        automount_service_account_token=False,
        containers=[
            {
                "name": NET_TOOLS_CONTAINER_NAME,
                "image": NET_UTIL_CONTAINER_IMAGE,
                "command": ["sleep", "infinity"],
                "securityContext": {"privileged": True},
                "volumeMounts": [
                    netns_mount,
                    *(
                        [
                            {
                                "name": "host-frr-config",
                                "mountPath": "/etc/perouter/frr",
                                "readOnly": True,
                                "mountPropagation": "HostToContainer",
                            }
                        ]
                        if netns_read_only
                        else []
                    ),
                ],
            }
        ],
        volumes=[
            {
                "name": "host-netns",
                "hostPath": {"path": "/var/run/netns", "type": "Directory"},
            },
            *(
                [{"name": "host-frr-config", "hostPath": {"path": "/etc/perouter/frr", "type": "Directory"}}]
                if netns_read_only
                else []
            ),
        ],
    ) as helper_pod:
        helper_pod.wait_for_status(status=Pod.Status.RUNNING)
        yield helper_pod


@contextmanager
def openperouter_topology_cleanup(diagnostics_pod: Pod, vnis: list[int]) -> Generator[None]:
    """Waits for datapath cleanup after the enclosed topology CRs are deleted.

    Args:
        diagnostics_pod: Host-networked diagnostic pod on the provider worker.
        vnis: Test-owned VNIs whose host bridges and veths must disappear.

    Yields:
        Control to the topology resource context managers.
    """
    try:
        yield
    finally:
        LOGGER.info(f"Waiting for OpenPERouter datapath cleanup on node {diagnostics_pod.node_name}")
        for remaining in TimeoutSampler(
            wait_timeout=300,
            sleep=5,
            func=_remaining_openperouter_interfaces,
            diagnostics_pod=diagnostics_pod,
            vnis=vnis,
        ):
            if not remaining:
                break


def _remaining_openperouter_interfaces(diagnostics_pod: Pod, vnis: list[int]) -> list[str]:
    router_names = network_interface_names(pod=diagnostics_pod, netns_name=OPENPE_ROUTER_NAMESPACE)
    host_names = network_interface_names(pod=diagnostics_pod)
    loopback = loads(
        s=diagnostics_pod.execute(
            command=["ip", "netns", "exec", OPENPE_ROUTER_NAMESPACE, "ip", "-j", "addr", "show", "dev", "lo"],
            container=NET_TOOLS_CONTAINER_NAME,
        )
    )
    managed_host_names = {name for vni in vnis for name in (f"br-hs-{vni}", f"host-e-{vni}")}
    return [
        *(f"{OPENPE_ROUTER_NAMESPACE}/{name}" for name in sorted(router_names - {"lo"})),
        *(f"host/{name}" for name in sorted(host_names & managed_host_names)),
        *(
            f"{OPENPE_ROUTER_NAMESPACE}/lo/{address['local']}"
            for interface in loopback
            for address in interface["addr_info"]
            if address["scope"] == "global"
        ),
    ]


def network_interface_names(pod: Pod, netns_name: str | None = None) -> set[str]:
    """Lists interfaces without treating a failed command as an absent device.

    Args:
        pod: Helper pod in which to run the command.
        netns_name: Named network namespace, or the pod's namespace when omitted.

    Returns:
        The interface names reported by iproute2.
    """
    prefix = ["ip", "netns", "exec", netns_name] if netns_name else []
    output = pod.execute(
        command=[*prefix, "ip", "-j", "link", "show"],
        container=NET_TOOLS_CONTAINER_NAME,
    )
    return {link["ifname"] for link in loads(s=output)}


def create_openperouter_underlay(
    client: DynamicClient,
    namespace_name: str,
    attachment: OpenPERouterAttachment,
    worker_ips: list[str],
) -> Underlay:
    """Creates an OpenPERouter Underlay attached through a CNI macvlan.

    Args:
        client: Kubernetes dynamic client.
        namespace_name: Test-owned OpenPERouter namespace.
        attachment: Validated provider underlay attachment.
        worker_ips: IPv4 addresses of the worker FRR peers.

    Returns:
        The uncreated Underlay resource; enter its context manager to deploy it.
    """
    spec = {
        "asn": EXTERNAL_FRR_ASN,
        "nodeSelector": {"matchLabels": OPENPE_PROVIDER_NODE_LABEL},
        "neighbors": [{"asn": CLUSTER_FRR_ASN, "address": worker_ip} for worker_ip in worker_ips],
        "tunnelEndpoint": {"cidrs": [attachment.vtep_cidr]},
        "interfaces": [
            {
                "type": "CNIDevice",
                "cniDevice": {
                    "type": "RawConfig",
                    "interfaceName": OPENPE_UNDERLAY_INTERFACE_NAME,
                    "rawConfig": {
                        "cniVersion": "1.0.0",
                        "name": "ovt-openpe-provider",
                        "plugins": [
                            {
                                "type": "macvlan",
                                "master": attachment.parent_interface,
                                "mode": "bridge",
                                "ipam": {
                                    "type": "static",
                                    "addresses": [{"address": attachment.provider_ipv4}],
                                },
                            }
                        ],
                    },
                },
            }
        ],
    }
    return Underlay(
        client=client,
        kind_dict=_openpe_resource_dict(
            kind="Underlay",
            name="ovt-openpe-underlay",
            namespace_name=namespace_name,
            spec=spec,
        ),
    )


def create_openperouter_l2_vni(
    client: DynamicClient,
    namespace_name: str,
    vni: int,
) -> L2VNI:
    """Creates an OpenPERouter L2VNI backed by a managed Linux bridge.

    Args:
        client: Kubernetes dynamic client.
        namespace_name: Test-owned OpenPERouter namespace.
        vni: MAC-VRF VNI.

    Returns:
        The uncreated L2VNI resource; enter its context manager to deploy it.
    """
    spec = {
        "vni": vni,
        "nodeSelector": {"matchLabels": OPENPE_PROVIDER_NODE_LABEL},
        "hostMaster": {
            "type": "LinuxBridge",
            "linuxBridge": {"lifecycle": "Managed"},
        },
    }
    return L2VNI(
        client=client,
        kind_dict=_openpe_resource_dict(
            kind="L2VNI",
            name="ovt-openpe-mac-vrf",
            namespace_name=namespace_name,
            spec=spec,
        ),
    )


def create_openperouter_l3_vni(
    client: DynamicClient,
    namespace_name: str,
    vni: int,
) -> L3VNI:
    """Creates an OpenPERouter L3VNI for the routed EVPN domain.

    Args:
        client: Kubernetes dynamic client.
        namespace_name: Test-owned OpenPERouter namespace.
        vni: IP-VRF VNI.

    Returns:
        The uncreated L3VNI resource; enter its context manager to deploy it.
    """
    spec = {
        "vni": vni,
        "vrf": OPENPE_L3_VRF_NAME,
        "nodeSelector": {"matchLabels": OPENPE_PROVIDER_NODE_LABEL},
    }
    return L3VNI(
        client=client,
        kind_dict=_openpe_resource_dict(
            kind="L3VNI",
            name="ovt-openpe-ip-vrf",
            namespace_name=namespace_name,
            spec=spec,
        ),
    )


def create_openperouter_raw_frr_config(
    client: DynamicClient,
    namespace_name: str,
    worker_ips: list[str],
    external_l3_subnet_ipv4: str,
) -> RawFRRConfig:
    """Creates the provider-scoped OpenPERouter raw FRR configuration.

    Args:
        client: Kubernetes dynamic client.
        namespace_name: Test-owned OpenPERouter namespace.
        worker_ips: IPv4 addresses of the worker FRR peers.
        external_l3_subnet_ipv4: Test-owned routed-L3 endpoint subnet.

    Returns:
        The uncreated RawFRRConfig resource; enter its context manager to deploy it.
    """
    spec = {
        "nodeSelector": {"matchLabels": OPENPE_PROVIDER_NODE_LABEL},
        "rawConfig": generate_openperouter_raw_frr_config(
            worker_ips=worker_ips,
            external_l3_subnet_ipv4=external_l3_subnet_ipv4,
        ),
    }
    return RawFRRConfig(
        client=client,
        kind_dict=_openpe_resource_dict(
            kind="RawFRRConfig",
            name="ovt-openpe-evpn",
            namespace_name=namespace_name,
            spec=spec,
        ),
    )


def generate_openperouter_raw_frr_config(worker_ips: list[str], external_l3_subnet_ipv4: str) -> str:
    """Generates the EVPN relay and routed-L3 FRR behavior.

    Args:
        worker_ips: IPv4 addresses of the worker FRR peers.
        external_l3_subnet_ipv4: Test-owned routed-L3 endpoint subnet.

    Returns:
        Raw FRR configuration accepted by OpenPERouter.
    """
    if not worker_ips:
        raise ValueError("worker_ips cannot be empty")

    config_lines = [
        "route-map evpn-to-ocp permit 10",
        f" set as-path exclude {CLUSTER_FRR_ASN}",
        " set ip next-hop unchanged",
        "!",
        f"router bgp {EXTERNAL_FRR_ASN}",
        " address-family l2vpn evpn",
    ]
    config_lines.extend(
        command
        for worker_ip in worker_ips
        for command in (
            f"  neighbor {worker_ip} route-map evpn-to-ocp out",
            f"  no neighbor {worker_ip} allowas-in",
        )
    )
    config_lines.extend([
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
        f"  network {external_l3_subnet_ipv4}",
    ])
    config_lines.extend(f"  neighbor {worker_ip} next-hop-self" for worker_ip in worker_ips)
    config_lines.append(" exit-address-family")
    return "\n".join(config_lines)


@retry(wait_timeout=300, sleep=5, exceptions_dict={ExecOnPodError: [], RuntimeError: []})
def wait_for_openperouter_underlay(
    diagnostics_pod: Pod,
    attachment: OpenPERouterAttachment,
    worker_ips: list[str],
) -> str:
    """Waits for the CNI underlay address and worker reachability.

    Args:
        diagnostics_pod: Node-pinned diagnostic helper pod.
        attachment: Validated provider underlay attachment.
        worker_ips: IPv4 addresses that must be reachable from OpenPERouter.

    Returns:
        The configured OpenPERouter provider IPv4 address.
    """
    output = diagnostics_pod.execute(
        command=[
            "ip",
            "netns",
            "exec",
            OPENPE_ROUTER_NAMESPACE,
            "ip",
            "-j",
            "-4",
            "addr",
            "show",
            OPENPE_UNDERLAY_INTERFACE_NAME,
        ],
        container=NET_TOOLS_CONTAINER_NAME,
    )
    try:
        interface_data = loads(s=output)
    except JSONDecodeError as error:
        raise RuntimeError(f"Invalid OpenPERouter underlay address output: {output}") from error

    addresses = [
        address_info["local"]
        for interface_info in interface_data
        for address_info in interface_info.get("addr_info", [])
        if address_info.get("family") == "inet"
    ]
    expected_address = str(ip_interface(address=attachment.provider_ipv4).ip)
    if expected_address not in addresses:
        raise RuntimeError(
            f"OpenPERouter underlay interface {OPENPE_UNDERLAY_INTERFACE_NAME} has {addresses}; "
            f"expected {expected_address}"
        )

    for worker_ip in worker_ips:
        diagnostics_pod.execute(
            command=[
                "ip",
                "netns",
                "exec",
                OPENPE_ROUTER_NAMESPACE,
                "ping",
                "-c",
                "1",
                "-W",
                "2",
                worker_ip,
            ],
            container=NET_TOOLS_CONTAINER_NAME,
        )

    return expected_address


@retry(wait_timeout=300, sleep=5, exceptions_dict={ExecOnPodError: []})
def wait_for_openperouter_l2_vni(diagnostics_pod: Pod, vni: int) -> None:
    """Waits for OpenPERouter to create the Linux bridge for an L2VNI.

    Args:
        diagnostics_pod: Node-pinned diagnostic helper pod.
        vni: MAC-VRF VNI.
    """
    diagnostics_pod.execute(
        command=[
            "ip",
            "netns",
            "exec",
            OPENPE_ROUTER_NAMESPACE,
            "ip",
            "link",
            "show",
            f"br-pe-{vni}",
        ],
        container=NET_TOOLS_CONTAINER_NAME,
    )


@retry(wait_timeout=300, sleep=5, exceptions_dict={ExecOnPodError: []})
def wait_for_openperouter_l3_vni(diagnostics_pod: Pod) -> None:
    """Waits for OpenPERouter to create the routed-L3 VRF.

    Args:
        diagnostics_pod: Node-pinned diagnostic helper pod.
    """
    diagnostics_pod.execute(
        command=[
            "ip",
            "netns",
            "exec",
            OPENPE_ROUTER_NAMESPACE,
            "ip",
            "link",
            "show",
            OPENPE_L3_VRF_NAME,
        ],
        container=NET_TOOLS_CONTAINER_NAME,
    )


@retry(wait_timeout=300, sleep=5, exceptions_dict={ExecOnPodError: [], RuntimeError: []})
def wait_for_openperouter_raw_frr_config(diagnostics_pod: Pod) -> None:
    """Waits for OpenPERouter to render the raw EVPN FRR configuration.

    Args:
        diagnostics_pod: Node-pinned diagnostic helper pod.
    """
    output = diagnostics_pod.execute(
        command=["cat", "/etc/perouter/frr/frr.conf"],
        container=NET_TOOLS_CONTAINER_NAME,
    )
    if "route-map evpn-to-ocp permit 10" not in output:
        raise RuntimeError(f"OpenPERouter raw FRR configuration is not rendered; got: {output}")


def collect_openperouter_diagnostics(
    client: DynamicClient,
    namespace_name: str,
    router_pod: Pod,
    diagnostics_pod: Pod,
) -> None:
    """Collects OpenPERouter control-plane and data-plane failure artifacts.

    Args:
        client: Kubernetes dynamic client.
        namespace_name: Test-owned OpenPERouter namespace.
        router_pod: Stock OpenPERouter pod.
        diagnostics_pod: Node-pinned diagnostic helper pod.
    """
    helper_commands = [
        ("router links", ["ip", "netns", "exec", OPENPE_ROUTER_NAMESPACE, "ip", "-br", "link"]),
        ("router addresses", ["ip", "netns", "exec", OPENPE_ROUTER_NAMESPACE, "ip", "-br", "addr"]),
        ("router IPv4 routes", ["ip", "netns", "exec", OPENPE_ROUTER_NAMESPACE, "ip", "route", "show"]),
        ("router IPv6 routes", ["ip", "netns", "exec", OPENPE_ROUTER_NAMESPACE, "ip", "-6", "route", "show"]),
        ("router VRFs", ["ip", "netns", "exec", OPENPE_ROUTER_NAMESPACE, "ip", "vrf"]),
        ("router bridge links", ["ip", "netns", "exec", OPENPE_ROUTER_NAMESPACE, "bridge", "link"]),
        ("router bridge FDB", ["ip", "netns", "exec", OPENPE_ROUTER_NAMESPACE, "bridge", "fdb", "show"]),
        ("router neighbors", ["ip", "netns", "exec", OPENPE_ROUTER_NAMESPACE, "ip", "neigh", "show"]),
        ("generated FRR config", ["cat", "/etc/perouter/frr/frr.conf"]),
    ]
    for description, command in helper_commands:
        output = diagnostics_pod.execute(
            command=command,
            container=NET_TOOLS_CONTAINER_NAME,
            ignore_rc=True,
        )
        LOGGER.info(f"OpenPERouter {description}:\n{output}")

    router_commands = [
        ("BGP summary", ["vtysh", "-c", "show bgp summary"]),
        ("EVPN summary", ["vtysh", "-c", "show bgp l2vpn evpn summary"]),
        ("EVPN VNIs", ["vtysh", "-c", "show evpn vni"]),
    ]
    for description, command in router_commands:
        output = router_pod.execute(
            command=command,
            container="frr",
            ignore_rc=True,
        )
        LOGGER.info(f"OpenPERouter {description}:\n{output}")

    _collect_openperouter_pod_logs(client=client, namespace_name=namespace_name)


def _required_environment_variable(name: str) -> str:
    value = environ.get(name)
    if not value:
        raise ValueError(f"Required environment variable {name} is not set")
    return value


def _openperouter_catalog_source(client: DynamicClient) -> str:
    manifests = [
        manifest
        for manifest in PackageManifest.get(
            client=client,
            namespace=OPENPE_MARKETPLACE_NAMESPACE,
            field_selector=f"metadata.name={OPENPE_OPERATOR_PACKAGE}",
            raw=True,
        )
        if any(channel.name == OPENPE_OPERATOR_CHANNEL for channel in manifest.status.channels)
    ]
    if len(manifests) != 1:
        raise RuntimeError(
            f"Expected one {OPENPE_OPERATOR_PACKAGE} package providing channel {OPENPE_OPERATOR_CHANNEL} "
            f"in {OPENPE_MARKETPLACE_NAMESPACE}; found {len(manifests)}. "
            "Make the downstream OpenPERouter catalog available before running EVPN tests."
        )
    return manifests[0].status.catalogSource


def _ensure_no_existing_openperouter_installation(client: DynamicClient) -> None:
    existing_subscriptions = [
        f"{subscription.namespace}/{subscription.name}"
        for subscription in Subscription.get(client=client)
        if subscription.instance.spec.name == OPENPE_OPERATOR_PACKAGE
    ]
    if existing_subscriptions:
        raise RuntimeError(
            f"OpenPERouter subscriptions already exist: {existing_subscriptions}; refusing to modify them"
        )
    existing_csvs = [
        f"{csv.namespace}/{csv.name}"
        for csv in ClusterServiceVersion.get(client=client)
        if csv.name.startswith(f"{OPENPE_OPERATOR_PACKAGE}.")
    ]
    if existing_csvs:
        raise RuntimeError(f"OpenPERouter is already installed: {existing_csvs}; refusing to modify it")
    webhook = ValidatingWebhookConfiguration(
        client=client,
        name=OPENPE_WEBHOOK_NAME,
    )
    if webhook.exists:
        raise RuntimeError(
            f"A pre-existing OpenPERouter installation was detected through {OPENPE_WEBHOOK_NAME}; "
            "refusing to modify or delete it"
        )


def _openpe_resource_dict(
    kind: str,
    name: str,
    namespace_name: str,
    spec: dict[str, Any],
) -> dict[str, Any]:
    return {
        "apiVersion": f"{OPENPE_API_GROUP}/{OPENPE_API_VERSION}",
        "kind": kind,
        "metadata": {
            "name": name,
            "namespace": namespace_name,
            "labels": OPENPE_TEST_RESOURCE_LABEL,
        },
        "spec": spec,
    }


def _get_ready_pods(
    client: DynamicClient,
    namespace_name: str,
    label_selector: str,
) -> list[Pod]:
    pods = list(
        Pod.get(
            client=client,
            namespace=namespace_name,
            label_selector=label_selector,
        )
    )
    if not pods or not all(_pod_is_ready(pod=pod) for pod in pods):
        return []
    return pods


def _pod_is_ready(pod: Pod) -> bool:
    conditions = pod.instance.status.get("conditions", [])
    return any(condition.get("type") == "Ready" and condition.get("status") == "True" for condition in conditions)


def _wait_for_openperouter_pods(client: DynamicClient, namespace_name: str) -> None:
    for component_name in ("controller", "router", "nodemarker"):
        for pods in TimeoutSampler(
            wait_timeout=600,
            sleep=5,
            func=_get_ready_pods,
            client=client,
            namespace_name=namespace_name,
            label_selector=f"app={component_name}",
        ):
            if pods:
                break


def _get_single_pod(
    client: DynamicClient,
    namespace_name: str,
    label_selector: str,
) -> Pod:
    pods = list(
        Pod.get(
            client=client,
            namespace=namespace_name,
            label_selector=label_selector,
        )
    )
    if len(pods) != 1:
        raise RuntimeError(f"Expected one pod with {label_selector} in {namespace_name}, found {len(pods)}")
    return pods[0]


def _collect_openperouter_pod_logs(client: DynamicClient, namespace_name: str) -> None:
    component_containers = {
        "controller": ("controller",),
        "router": ("frr", "reloader"),
        "nodemarker": ("nodemarker",),
    }
    for component_name, container_names in component_containers.items():
        pods = list(
            Pod.get(
                client=client,
                namespace=namespace_name,
                label_selector=f"app={component_name}",
            )
        )
        for pod in pods:
            for container_name in container_names:
                pod_logs = pod.log(container=container_name)
                LOGGER.info(
                    f"OpenPERouter {component_name} pod {pod.name} container {container_name} logs:\n{pod_logs}"
                )

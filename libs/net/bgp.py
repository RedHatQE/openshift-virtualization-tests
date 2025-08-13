import json
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from kubernetes.dynamic import DynamicClient
from ocp_resources.daemonset import DaemonSet
from ocp_resources.deployment import Deployment
from ocp_resources.frr_configuration import FRRConfiguration
from ocp_resources.namespace import Namespace
from ocp_resources.network_config_openshift_io import Network
from ocp_resources.pod import Pod
from ocp_resources.resource import ResourceEditor, ResourceNotFoundError
from ocp_resources.route_advertisements import RouteAdvertisements
from timeout_sampler import retry

BGP_ASN = 64512
EXTERNAL_FRR_IMAGE = "quay.io/frrouting/frr:9.1.2"
FRR_DEPLOYMENT_NAME = "frr-k8s-webhook-server"
FRR_DS_NAME = "frr-k8s"
FRR_NS_NAME = "openshift-frr-k8s"
FRR_RESOURCES_AVAILABILITY_TIMEOUT = 120
FRR_RESOURCES_AVAILABILITY_SLEEP = 5


def wait_for_frr_namespace_created() -> Namespace:
    ns = Namespace(name=FRR_NS_NAME)

    @retry(
        wait_timeout=FRR_RESOURCES_AVAILABILITY_TIMEOUT,
        sleep=FRR_RESOURCES_AVAILABILITY_SLEEP,
        exceptions_dict={ResourceNotFoundError: []},
    )
    def _check_namespace_exists() -> Namespace:
        if ns.exists and ns.status == Namespace.Status.ACTIVE:
            return ns
        raise ResourceNotFoundError(f"Namespace {FRR_NS_NAME} was not created or is not active.")

    return _check_namespace_exists()


def wait_for_frr_daemonset_ready() -> bool:
    ds = DaemonSet(name=FRR_DS_NAME, namespace=FRR_NS_NAME)

    @retry(
        wait_timeout=FRR_RESOURCES_AVAILABILITY_TIMEOUT,
        sleep=FRR_RESOURCES_AVAILABILITY_SLEEP,
        exceptions_dict={ResourceNotFoundError: []},
    )
    def _check_daemonset_exists() -> bool:
        if ds.exists:
            ds.wait_until_deployed(timeout=FRR_RESOURCES_AVAILABILITY_TIMEOUT)
            return True
        raise ResourceNotFoundError(f"DaemonSet {FRR_NS_NAME} was not created.")

    return _check_daemonset_exists()


def wait_for_frr_deployment_available() -> None:
    deployment = Deployment(name=FRR_DEPLOYMENT_NAME, namespace=FRR_NS_NAME)
    deployment.wait_for_replicas(timeout=FRR_RESOURCES_AVAILABILITY_TIMEOUT)


@contextmanager
def enable_ra_in_network_operator(network_operator: Network) -> Generator[None]:
    patch = {
        network_operator: {
            "spec": {
                "additionalRoutingCapabilities": {"providers": ["FRR"]},
                "defaultNetwork": {"ovnKubernetesConfig": {"routeAdvertisements": "Enabled"}},
            }
        }
    }

    with ResourceEditor(patches=patch):
        frr_ns = wait_for_frr_namespace_created()
        wait_for_frr_daemonset_ready()
        wait_for_frr_deployment_available()

        yield

    frr_ns.delete(wait=True)


@contextmanager
def create_cudn_route_advertisements(
    name: str, match_labels: dict, client: DynamicClient = None
) -> Generator[RouteAdvertisements]:
    network_selectors = [
        {
            "networkSelectionType": "ClusterUserDefinedNetworks",
            "clusterUserDefinedNetworkSelector": {"networkSelector": {"matchLabels": match_labels}},
        }
    ]

    with RouteAdvertisements(
        name=name,
        advertisements=["PodNetwork"],
        network_selectors=network_selectors,
        node_selector={},
        frr_configuration_selector={},
        client=client,
    ) as ra:
        yield ra


@contextmanager
def create_frr_configuration(
    name: str, frr_pod_ipv4: str, external_subnet_ipv4: str, client: DynamicClient = None
) -> Generator[FRRConfiguration]:
    bgp_config = {
        "routers": [
            {
                "asn": BGP_ASN,
                "neighbors": [
                    {
                        "address": frr_pod_ipv4,
                        "asn": BGP_ASN,
                        "disableMP": True,
                        "toReceive": {"allowed": {"mode": "filtered", "prefixes": [{"prefix": external_subnet_ipv4}]}},
                    }
                ],
            }
        ]
    }

    with FRRConfiguration(name=name, namespace=FRR_NS_NAME, bgp=bgp_config, client=client) as frr_config:
        yield frr_config


def generate_frr_conf(
    output_file: Path,
    external_subnet_ipv4: str,
    nodes_ipv4_list: list[str],
) -> None:
    if not output_file.parent.exists():
        raise FileNotFoundError(f"Output directory {output_file.parent} does not exist.")

    with open(output_file, "w") as f:
        f.write(f"router bgp {BGP_ASN}\n")
        f.write(" no bgp default ipv4-unicast\n")
        f.write(" no bgp network import-check\n\n")

        for ip in nodes_ipv4_list:
            f.write(f" neighbor {ip} remote-as {BGP_ASN}\n\n")

        f.write(" address-family ipv4 unicast\n")
        f.write(f"  network {external_subnet_ipv4}\n")

        for ip in nodes_ipv4_list:
            f.write(f"  neighbor {ip} activate\n")
            f.write(f"  neighbor {ip} next-hop-self\n")
            f.write(f"  neighbor {ip} route-reflector-client\n")
        f.write(" exit-address-family\n\n")


@contextmanager
def deploy_external_frr_pod(
    namespace_name: str,
    node_name: str,
    nad_name: str,
    frr_configmap_name: str,
    default_route: str,
    client: DynamicClient = None,
) -> Generator[Pod]:
    """
    Deploys an external FRR (Free Range Routing) pod in a specified namespace.

    This function creates a privileged pod with the FRR image, attaches it to a
    specified NetworkAttachmentDefinition (NAD), and mounts a ConfigMap for FRR
    configuration.

    Args:
        namespace_name (str): The name of the namespace where the pod will be deployed.
        node_name (str): The name of the node where the pod will be scheduled.
        nad_name (str): The name of the NetworkAttachmentDefinition (NAD) to attach to the pod.
        frr_configmap_name (str): The name of the ConfigMap containing FRR configuration.
        default_route (str): The default route to be used by the pod.
        client (DynamicClient, optional): A Kubernetes dynamic client for resource management.

    Yields:
        Pod: The deployed FRR pod object.

    Raises:
        ResourceNotFoundError: If the pod fails to reach the RUNNING state.
    """
    annotations = {
        "k8s.v1.cni.cncf.io/networks": json.dumps([
            {"name": nad_name, "interface": "net1", "default-route": [default_route]}
        ]),
        "k8s.v1.cni.cncf.io/default-network": "none",
    }
    containers = [
        {
            "name": "frr",
            "image": EXTERNAL_FRR_IMAGE,
            "securityContext": {"privileged": True, "capabilities": {"add": ["NET_ADMIN"]}},
            "volumeMounts": [{"name": frr_configmap_name, "mountPath": "/etc/frr"}],
        }
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
    ) as pod:
        pod.wait_for_status(status=Pod.Status.RUNNING)
        yield pod

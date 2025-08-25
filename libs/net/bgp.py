import json
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Final

import ocp_resources.network_config_openshift_io as openshift_nc
from ocp_resources.deployment import Deployment
from ocp_resources.frr_configuration import FRRConfiguration
from ocp_resources.namespace import Namespace
from ocp_resources.pod import Pod
from ocp_resources.resource import ResourceEditor
from ocp_resources.route_advertisements import RouteAdvertisements

from utilities.infra import cache_admin_client

_BGP_ASN: Final[int] = 64512
_EXTERNAL_FRR_IMAGE: Final[str] = "quay.io/frrouting/frr:9.1.2"
_FRR_DEPLOYMENT_NAME: Final[str] = "frr-k8s-webhook-server"
_FRR_NS_NAME: Final[str] = "openshift-frr-k8s"
_FRR_RESOURCES_AVAILABILITY_TIMEOUT_SEC: Final[int] = 120
_FRR_RESOURCES_AVAILABILITY_SLEEP_SEC: Final[int] = 5


def wait_for_frr_deployment_available() -> None:
    deployment = Deployment(name=_FRR_DEPLOYMENT_NAME, namespace=_FRR_NS_NAME)
    deployment.wait_for_replicas(timeout=_FRR_RESOURCES_AVAILABILITY_TIMEOUT_SEC)


@contextmanager
def enable_ra_in_cluster_network_resource(network_resource: openshift_nc.Network) -> Generator[None]:
    patch = {
        network_resource: {
            "spec": {
                "additionalRoutingCapabilities": {"providers": ["FRR"]},
                "defaultNetwork": {"ovnKubernetesConfig": {"routeAdvertisements": "Enabled"}},
            }
        }
    }

    with ResourceEditor(patches=patch):
        wait_for_frr_deployment_available()

        yield

    # Cleanup: revert the changes made to the Network resource
    Namespace(name=_FRR_NS_NAME, client=cache_admin_client()).delete(wait=True)


def create_cudn_route_advertisements(name: str, match_labels: dict) -> RouteAdvertisements:
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
        client=cache_admin_client(),
    )


def create_frr_configuration(name: str, frr_pod_ipv4: str, external_subnet_ipv4: str) -> FRRConfiguration:
    bgp_config = {
        "routers": [
            {
                "asn": _BGP_ASN,
                "neighbors": [
                    {
                        "address": frr_pod_ipv4,
                        "asn": _BGP_ASN,
                        "disableMP": True,
                        "toReceive": {"allowed": {"mode": "filtered", "prefixes": [{"prefix": external_subnet_ipv4}]}},
                    }
                ],
            }
        ]
    }

    return FRRConfiguration(name=name, namespace=_FRR_NS_NAME, bgp=bgp_config, client=cache_admin_client())


def generate_frr_conf(
    output_file: Path,
    external_subnet_ipv4: str,
    nodes_ipv4_list: list[str],
) -> None:
    if not nodes_ipv4_list:
        raise ValueError("nodes_ipv4_list cannot be empty")

    with open(output_file, "w") as f:
        f.write(f"router bgp {_BGP_ASN}\n")
        f.write(" no bgp default ipv4-unicast\n")
        f.write(" no bgp network import-check\n\n")

        for ip in nodes_ipv4_list:
            f.write(f" neighbor {ip} remote-as {_BGP_ASN}\n\n")

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
) -> Generator[Pod]:
    """
    Deploys an external FRR (Free Range Routing) pod in a specified namespace.

    On entering the context, this function creates a privileged pod with the FRR image,
    attaches it to a specified NetworkAttachmentDefinition (NAD), and mounts a ConfigMap for FRR
    configuration. On exiting the context, the pod is automatically deleted.

    Args:
        namespace_name (str): The name of the namespace where the pod will be deployed.
        node_name (str): The name of the node where the pod will be scheduled.
        nad_name (str): The name of the NetworkAttachmentDefinition (NAD) to attach to the pod.
        frr_configmap_name (str): The name of the ConfigMap containing FRR configuration.
        default_route (str): The default route to be used by the pod.

    Yields:
        Pod: The deployed FRR pod object.

    Raises:
        ResourceNotFoundError: If the pod fails to reach the RUNNING state.
    """
    annotations = {
        f"{Pod.ApiGroup.K8S_V1_CNI_CNCF_IO}/networks": json.dumps([
            {"name": nad_name, "interface": "net1", "default-route": [default_route]}
        ]),
        f"{Pod.ApiGroup.K8S_V1_CNI_CNCF_IO}/default-network": "none",
    }
    containers = [
        {
            "name": "frr",
            "image": _EXTERNAL_FRR_IMAGE,
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
        client=cache_admin_client(),
    ) as pod:
        pod.wait_for_status(status=Pod.Status.RUNNING)
        yield pod

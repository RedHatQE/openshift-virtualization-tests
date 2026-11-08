from contextlib import contextmanager
from dataclasses import dataclass
from logging import getLogger
from typing import TYPE_CHECKING, Final

from ocp_resources.cluster_service_version import ClusterServiceVersion
from ocp_resources.node import Node
from ocp_resources.operator_group import OperatorGroup
from ocp_resources.package_manifest import PackageManifest
from ocp_resources.pod import Pod
from ocp_resources.resource import NamespacedResource
from ocp_resources.subscription import Subscription
from ocp_resources.validating_webhook_config import ValidatingWebhookConfiguration
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

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

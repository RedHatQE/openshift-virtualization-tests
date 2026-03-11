from typing import Any

from _pytest.fixtures import FixtureRequest
from kubernetes.client import ApiException
from kubernetes.dynamic import DynamicClient
from kubernetes.dynamic.exceptions import ResourceNotFoundError
from ocp_resources.endpoints import Endpoints
from ocp_resources.mutating_webhook_config import MutatingWebhookConfiguration
from ocp_resources.namespace import Namespace
from ocp_resources.node import Node
from ocp_resources.validating_webhook_config import ValidatingWebhookConfiguration
from ocp_resources.virtual_machine import VirtualMachine
from ocp_utilities.exceptions import NodeNotReadyError, NodeUnschedulableError
from ocp_utilities.infra import assert_nodes_in_healthy_condition, assert_nodes_schedulable
from pytest_testconfig import config as py_config
from timeout_sampler import TimeoutExpiredError

from utilities.constants import IMAGE_CRON_STR, KUBELET_READY_CONDITION
from utilities.exceptions import ClusterSanityError, StorageSanityError
from utilities.hco import wait_for_hco_conditions
from utilities.infra import LOGGER, wait_for_pods_running
from utilities.pytest_utils import exit_pytest_execution


def storage_sanity_check(cluster_storage_classes_names: list[str]) -> bool:
    """
    Verify cluster has all expected storage classes from pytest configuration.

    Compares storage classes defined in the pytest configuration's storage_class_matrix
    against storage classes available on the cluster. The order of storage classes is
    ignored during comparison.

    Args:
        cluster_storage_classes_names: List of storage class names currently available on the cluster.

    Returns:
        True if all expected storage classes from configuration exist on the cluster,
        False otherwise.
    """
    config_sc = list([[*csc][0] for csc in py_config["storage_class_matrix"]])
    exists_sc = [scn for scn in config_sc if scn in cluster_storage_classes_names]
    if sorted(config_sc) != sorted(exists_sc):
        LOGGER.error(f"Expected {config_sc}, On cluster {exists_sc}")
        return False
    return True


def _discover_webhook_services(admin_client: DynamicClient, namespace: Namespace) -> set[str]:
    """
    Discover all webhook services in the HCO namespace.

    Scans all MutatingWebhookConfiguration and ValidatingWebhookConfiguration resources
    and extracts service names that point to the namespace.

    Args:
        admin_client: Kubernetes dynamic client with admin privileges for cluster operations.
        namespace: Namespace resource.

    Returns:
        Set of service names that are referenced by webhook configurations in the namespace.
    """
    webhook_services: set[str] = set()

    for webhook_kind in [MutatingWebhookConfiguration, ValidatingWebhookConfiguration]:
        LOGGER.info(f"Scanning {webhook_kind.kind} resources for webhook services")
        for webhook in webhook_kind.get(client=admin_client):
            webhook_items = webhook.instance.webhooks or []
            if not webhook_items:
                LOGGER.warning(f"Webhook configuration {webhook.name} has no webhooks")
                continue

            for webhook_item in webhook_items:
                service_config = webhook_item.get("clientConfig", {}).get("service")
                # Skip URL-based webhooks (they don't use a service)
                if not service_config:
                    continue

                if service_config["namespace"] == namespace.name:
                    webhook_services.add(service_config["name"])

    return webhook_services


def check_webhook_endpoints_health(admin_client: DynamicClient, namespace: Namespace) -> None:
    """
    Check that all webhook services in the HCO namespace have available endpoints.

    Verify that each discovered service has at least one ready endpoint address.

    Args:
        admin_client: Kubernetes dynamic client with admin privileges for cluster operations.
        namespace: Namespace resource.

    Raises:
        ClusterSanityError: When any webhook service has no ready endpoint addresses.
    """
    LOGGER.info(f"Checking webhook endpoints health for services in namespace: {namespace.name}")

    webhook_services = _discover_webhook_services(admin_client=admin_client, namespace=namespace)

    if not webhook_services:
        LOGGER.warning(f"No webhook services discovered in namespace {namespace.name}")
        return

    services_without_endpoints = []

    for service_name in sorted(webhook_services):
        LOGGER.info(f"Checking endpoints for service: {service_name}")
        try:
            endpoint = Endpoints(
                name=service_name,
                namespace=namespace.name,
                client=admin_client,
                ensure_exists=True,
            )

            subsets = endpoint.instance.subsets
            if not subsets:
                LOGGER.error(f"No subsets found in endpoints for service: {service_name}")
                services_without_endpoints.append(service_name)
                continue

            for subset in subsets:
                if addresses := getattr(subset, "addresses", None):
                    LOGGER.info(f"Service {service_name} has {len(addresses)} ready endpoint address(es)")
                    break
            else:
                LOGGER.error(f"No ready addresses found in endpoints for service: {service_name}")
                services_without_endpoints.append(service_name)

        except ResourceNotFoundError:
            LOGGER.error(f"Endpoints resource not found for service: {service_name}")
            services_without_endpoints.append(service_name)

        except ApiException as ex:
            LOGGER.error(f"API error checking endpoints for service {service_name}: {ex}")
            services_without_endpoints.append(service_name)

    if services_without_endpoints:
        raise ClusterSanityError(
            err_str=f"Webhook services have no available endpoints: {', '.join(services_without_endpoints)}. "
            "Check that the corresponding pods are running."
        )

    LOGGER.info("All discovered webhook services have available endpoints")


def check_vm_creation_capability(admin_client: DynamicClient, namespace: str) -> None:
    """
    Verify VM creation capability by performing a dry-run VM creation.

    Args:
        admin_client: Kubernetes dynamic client with admin privileges for cluster operations.
        namespace: str

    Raises:
        ClusterSanityError: When dry-run VM creation fails.
    """
    LOGGER.info(f"Checking VM creation capability via dry-run in namespace: {namespace}")

    try:
        vm = VirtualMachine(
            name="sanity-check-dry-run-vm",
            namespace=namespace,
            client=admin_client,
            body={
                "spec": {
                    "running": False,
                    "template": {
                        "spec": {
                            "domain": {
                                "devices": {},
                                "resources": {
                                    "requests": {
                                        "memory": "64Mi",
                                    },
                                },
                            },
                        },
                    },
                },
            },
            dry_run=True,
        )
        vm.create()
        LOGGER.info("Dry-run VM creation succeeded")

    except ApiException as ex:
        raise ClusterSanityError(
            err_str=f"Dry-run VM creation failed: {ex}. This may indicate webhook or API server issues."
        ) from ex

    except (ConnectionError, TimeoutError) as ex:
        raise ClusterSanityError(
            err_str=f"Connection error during dry-run VM creation: {ex}. Check cluster connectivity and webhook health."
        ) from ex

    except Exception as ex:
        raise ClusterSanityError(
            err_str=f"Unexpected error during dry-run VM creation: {ex}. Check cluster state and webhook configuration."
        ) from ex


def cluster_sanity(
    request: FixtureRequest,
    admin_client: DynamicClient,
    cluster_storage_classes_names: list[str],
    nodes: list[Node],
    hco_namespace: Namespace,
    junitxml_property: Any | None = None,
) -> None:
    """
    Perform comprehensive cluster sanity checks before running tests.

    Validates cluster health by checking storage classes, node status, pod status,
    and HyperConverged Operator conditions. Can be configured to skip specific checks
    via pytest command-line options.

    The function checks:
    1. Storage classes: Verifies all required storage classes from pytest configuration
       are present on the cluster.
    2. Nodes: Ensures all nodes are in ready and schedulable state.
    3. Pods: Validates all CNV pods in the HCO namespace are running.
    4. HCO conditions: Waits for HyperConverged Operator to reach healthy state.

    Args:
        request: Pytest fixture request object providing access to test configuration
            and command-line options.
        admin_client: Kubernetes dynamic client with admin privileges for cluster operations.
        cluster_storage_classes_names: List of storage class names available on the cluster.
        nodes: List of Node resources representing all cluster nodes.
        hco_namespace: Namespace resource where HyperConverged Operator is deployed.
        junitxml_property: Optional pytest plugin function for recording test suite properties
            in JUnit XML output. Used to record exit codes on failure.

    Raises:
        ClusterSanityError: When cluster is not in healthy state (pods not running, HCO unhealthy).
        StorageSanityError: When cluster is missing required storage classes.
        NodeUnschedulableError: When one or more nodes are unschedulable.
        NodeNotReadyError: When one or more nodes are not in ready state.

    Note:
        The function will exit pytest execution on any sanity check failure.
        Specific checks can be skipped using pytest options:
        - --cluster-sanity-skip-check: Skip all sanity checks
        - --cluster-sanity-skip-storage-check: Skip storage class validation
        - --cluster-sanity-skip-nodes-check: Skip node health validation
        - --cluster-sanity-skip-webhook-check: Skip webhook health validation
        - -m cluster_health_check: Skip sanity when running cluster health tests
    """
    if "cluster_health_check" in request.config.getoption("-m"):
        LOGGER.warning("Skipping cluster sanity test, got -m cluster_health_check")
        return

    skip_cluster_sanity_check = "--cluster-sanity-skip-check"
    skip_storage_classes_check = "--cluster-sanity-skip-storage-check"
    skip_nodes_check = "--cluster-sanity-skip-nodes-check"
    skip_webhook_check = "--cluster-sanity-skip-webhook-check"
    exceptions_filename = "cluster_sanity_failure.txt"
    try:
        if request.session.config.getoption(skip_cluster_sanity_check):
            LOGGER.warning(f"Skipping cluster sanity check, got {skip_cluster_sanity_check}")
            return
        LOGGER.info(
            f"Running cluster sanity. (To skip cluster sanity check pass {skip_cluster_sanity_check} to pytest)"
        )
        # Check storage class only if --cluster-sanity-skip-storage-check not passed to pytest.
        if request.session.config.getoption(skip_storage_classes_check):
            LOGGER.warning(f"Skipping storage classes check, got {skip_storage_classes_check}")
        else:
            LOGGER.info(
                f"Check storage classes sanity. (To skip storage class sanity check pass {skip_storage_classes_check} "
                f"to pytest)"
            )
            if not storage_sanity_check(cluster_storage_classes_names=cluster_storage_classes_names):
                raise StorageSanityError(
                    err_str=f"Cluster is missing storage class.\n"
                    f"either run with '--storage-class-matrix' or with '{skip_storage_classes_check}'"
                )

        # Check nodes only if --cluster-sanity-skip-nodes-check not passed to pytest.
        if request.session.config.getoption(skip_nodes_check):
            LOGGER.warning(f"Skipping nodes check, got {skip_nodes_check}")

        else:
            # validate that all the nodes are ready and schedulable and CNV pods are running
            LOGGER.info(f"Check nodes sanity. (To skip nodes sanity check pass {skip_nodes_check} to pytest)")
            assert_nodes_in_healthy_condition(nodes=nodes, healthy_node_condition_type=KUBELET_READY_CONDITION)
            assert_nodes_schedulable(nodes=nodes)

            try:
                wait_for_pods_running(
                    admin_client=admin_client,
                    namespace=hco_namespace,
                    filter_pods_by_name=IMAGE_CRON_STR,
                )
            except TimeoutExpiredError as timeout_error:
                LOGGER.error(timeout_error)
                raise ClusterSanityError(
                    err_str=f"Timed out waiting for all pods in namespace {hco_namespace.name} to get to running state."
                )

        # Check webhook endpoints only if --cluster-sanity-skip-webhook-check not passed to pytest.
        if request.session.config.getoption(skip_webhook_check):
            LOGGER.warning(f"Skipping webhook health check, got {skip_webhook_check}")
        else:
            LOGGER.info(f"Check webhook endpoints health. (To skip webhook check pass {skip_webhook_check} to pytest)")
            check_webhook_endpoints_health(admin_client=admin_client, namespace=hco_namespace)
            check_vm_creation_capability(admin_client=admin_client, namespace="default")

        # Wait for hco to be healthy
        wait_for_hco_conditions(
            admin_client=admin_client,
            hco_namespace=hco_namespace,
        )

    except (ClusterSanityError, NodeUnschedulableError, NodeNotReadyError, StorageSanityError) as ex:
        exit_pytest_execution(
            filename=exceptions_filename,
            log_message=str(ex),
            junitxml_property=junitxml_property,
            message="Cluster sanity checks failed.",
            admin_client=admin_client,
        )

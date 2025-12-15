from typing import Any, List

from _pytest.fixtures import FixtureRequest
from kubernetes.dynamic import DynamicClient
from ocp_resources.namespace import Namespace
from ocp_resources.node import Node
from ocp_utilities.exceptions import NodeNotReadyError, NodeUnschedulableError
from ocp_utilities.infra import assert_nodes_in_healthy_condition, assert_nodes_schedulable
from pytest_testconfig import config as py_config
from timeout_sampler import TimeoutExpiredError

from utilities.constants import IMAGE_CRON_STR, KUBELET_READY_CONDITION
from utilities.exceptions import ClusterSanityError, StorageSanityError
from utilities.hco import wait_for_hco_conditions
from utilities.infra import LOGGER, wait_for_pods_running
from utilities.pytest_utils import exit_pytest_execution


def storage_sanity_check(cluster_storage_classes_names: List[str]) -> bool:
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


def cluster_sanity(
    request: FixtureRequest,
    admin_client: DynamicClient,
    cluster_storage_classes_names: List[str],
    nodes: List[Node],
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
        - -m cluster_health_check: Skip sanity when running cluster health tests
    """
    if "cluster_health_check" in request.config.getoption("-m"):
        LOGGER.warning("Skipping cluster sanity test, got -m cluster_health_check")
        return

    skip_cluster_sanity_check = "--cluster-sanity-skip-check"
    skip_storage_classes_check = "--cluster-sanity-skip-storage-check"
    skip_nodes_check = "--cluster-sanity-skip-nodes-check"
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

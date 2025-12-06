import logging

from kubernetes.dynamic import DynamicClient
from ocp_resources.node import Node
from ocp_resources.sriov_network_node_policy import SriovNetworkNodePolicy
from ocp_resources.sriov_network_node_state import SriovNetworkNodeState
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from utilities.exceptions import ResourceMismatch

LOGGER = logging.getLogger(__name__)


def wait_for_ready_sriov_nodes(
    snns_list: list[SriovNetworkNodeState],
    admin_client: DynamicClient,
    policy: SriovNetworkNodePolicy | None = None,
    nic_selector: dict[str, list[str]] | None = None,
) -> None:
    """Wait for SR-IOV nodes to be ready and verify interface configuration.

    Usage:
    1. Policy creation: Waits for SUCCEEDED status and verifies config matches policy.
    2. Policy teardown: Verifies VFs are removed from specified interfaces.

    Args:
        snns_list: List of SriovNetworkNodeState objects.
        admin_client: Kubernetes admin client for Node access.
        policy: SriovNetworkNodePolicy for verification. None during teardown.
        nic_selector: NIC selector dict with pfNames/rootDevices for teardown verification.

    Raises:
        TimeoutExpiredError: If sync status doesn't reach SUCCEEDED or verification times out.
        ResourceMismatch: If interface config doesn't match policy spec.
    """
    for sriov_node_network_state in snns_list:
        status_msg = f"to be {SriovNetworkNodePolicy.Status.SUCCEEDED}"
        if policy:
            status_msg += f" and configured per policy {policy.name}"
        elif nic_selector:
            status_msg += " with VFs removed"
        LOGGER.info(f"Waiting for node {sriov_node_network_state.name} SriovNetworkNodeState {status_msg}")

        sampler = TimeoutSampler(
            wait_timeout=1000,
            sleep=5,
            func=_check_sriov_node_ready_and_configured,
            sriov_node_network_state=sriov_node_network_state,
            policy=policy,
            admin_client=admin_client,
            nic_selector=nic_selector,
            exceptions_dict={ResourceMismatch: []} if (policy or nic_selector) else {},
        )
        try:
            for sample in sampler:
                if sample:
                    success_msg = (
                        f"Node {sriov_node_network_state.name} SriovNetworkNodeState is"
                        f" {SriovNetworkNodePolicy.Status.SUCCEEDED}"
                    )
                    if policy:
                        success_msg += " and configuration verified"
                    LOGGER.info(success_msg)
                    break
        except TimeoutExpiredError:
            current_status = sriov_node_network_state.instance.status.syncStatus
            if current_status == SriovNetworkNodePolicy.Status.SUCCEEDED:
                LOGGER.error(
                    f"Timeout waiting for SR-IOV configuration to match policy on node {sriov_node_network_state.name}"
                )
            else:
                LOGGER.error(
                    f"Timeout waiting for node {sriov_node_network_state.name} "
                    f"SriovNetworkNodeState to reach SUCCEEDED status. "
                    f"Current status: {current_status}"
                )
            raise


def _check_sriov_node_ready_and_configured(
    sriov_node_network_state: SriovNetworkNodeState,
    policy: SriovNetworkNodePolicy | None,
    admin_client: DynamicClient,
    nic_selector: dict[str, list[str]] | None = None,
) -> bool:
    """Check if SR-IOV node status is SUCCEEDED and verify configuration.

    Performs two checks:
    1. Verifies syncStatus reached SUCCEEDED.
    2. Verifies interface config matches policy.

    Args:
        sriov_node_network_state: SriovNetworkNodeState object.
        policy: SriovNetworkNodePolicy for verification. None during teardown.
        admin_client: Kubernetes admin client for Node access.
        nic_selector: NIC selector dict with pfNames/rootDevices for teardown verification.

    Returns:
        True if SUCCEEDED and config matches, False if not SUCCEEDED yet.

    Raises:
        ResourceMismatch: If config doesn't match policy spec. Retried by TimeoutSampler.
    """
    current_status = sriov_node_network_state.instance.status.syncStatus
    if current_status != SriovNetworkNodePolicy.Status.SUCCEEDED:
        return False

    _verify_sriov_interface_config(
        sriov_node_network_state=sriov_node_network_state,
        policy=policy,
        admin_client=admin_client,
        nic_selector=nic_selector,
    )

    return True


def _verify_sriov_interface_config(
    sriov_node_network_state: SriovNetworkNodeState,
    policy: SriovNetworkNodePolicy | None,
    admin_client: DynamicClient,
    nic_selector: dict[str, list[str]] | None = None,
) -> None:
    """Verify SR-IOV interfaces match policy config or are cleaned up.

    Usage:
    1. Setup: Verifies interfaces matching nicSelector have correct VFs and MTU.
    2. Teardown: Verifies VFs are removed from specified interfaces.

    Args:
        sriov_node_network_state: SriovNetworkNodeState object.
        policy: SriovNetworkNodePolicy with desired config. None during teardown.
        admin_client: Kubernetes admin client for Node access.
        nic_selector: NIC selector dict with pfNames/rootDevices for teardown verification.

    Raises:
        ResourceMismatch: If config doesn't match policy spec or VFs not removed.
    """
    node = Node(client=admin_client, name=sriov_node_network_state.name)

    if policy and not _node_matches_policy_selector(node=node, policy=policy):
        LOGGER.info(f"Skipping verification for node {node.name} - does not match policy {policy.name} nodeSelector")
        return

    if policy:
        policy_spec = policy.instance.spec
        pf_names = policy_spec.nicSelector.get("pfNames", [])
        root_devices = policy_spec.nicSelector.get("rootDevices", [])
        expected_num_vfs = policy_spec.numVfs
        expected_mtu = policy_spec.get("mtu")

        matching_interfaces = []
        for iface in sriov_node_network_state.instance.status.interfaces:
            if iface.name in pf_names or iface.pciAddress in root_devices:
                matching_interfaces.append(iface)

        if not matching_interfaces:
            raise ResourceMismatch(
                f"Node {sriov_node_network_state.name} matches policy {policy.name} nodeSelector "
                f"but has no interfaces matching pfNames={pf_names}, rootDevices={root_devices})."
            )

        for iface in matching_interfaces:
            LOGGER.info(
                f"Verifying interface {iface.name} on node {sriov_node_network_state.name}: "
                f"numVfs={iface.numVfs} (expected: {expected_num_vfs})"
            )

            if iface.numVfs != expected_num_vfs:
                raise ResourceMismatch(
                    f"SR-IOV interface {iface.name} on node {sriov_node_network_state.name}: "
                    f"numVfs mismatch - got {iface.numVfs}, expected {expected_num_vfs}"
                )

            if expected_mtu:
                iface_mtu = getattr(iface, "mtu", None)
                if iface_mtu and iface_mtu != expected_mtu:
                    raise ResourceMismatch(
                        f"SR-IOV interface {iface.name} on node {sriov_node_network_state.name}: "
                        f"MTU mismatch - got {iface_mtu}, expected {expected_mtu}"
                    )

            LOGGER.info(f"Interface {iface.name} configuration verified successfully")

    elif nic_selector:
        pf_names = nic_selector.get("pfNames", [])
        root_devices = nic_selector.get("rootDevices", [])

        for iface in sriov_node_network_state.instance.status.interfaces:
            if iface.name in pf_names or iface.pciAddress in root_devices:
                if iface.numVfs:
                    raise ResourceMismatch(
                        f"SR-IOV interface {iface.name} on node {sriov_node_network_state.name} still has "
                        f"numVfs={iface.numVfs} after policy deletion. Expected numVfs=0 or None"
                    )
                LOGGER.info(
                    f"Verified interface {iface.name} on node {sriov_node_network_state.name}: "
                    f"numVfs={iface.numVfs} (VFs removed)"
                )


def _node_matches_policy_selector(node: Node, policy: SriovNetworkNodePolicy) -> bool:
    """Check if a node matches the policy's nodeSelector.

    Args:
        node: Node object.
        policy: SriovNetworkNodePolicy with nodeSelector.

    Returns:
        bool: True if all nodeSelector labels match node labels, False otherwise.
    """
    policy_spec = policy.instance.spec
    node_selector = policy_spec.nodeSelector

    node_labels = node.instance.metadata.labels
    for key, value in node_selector.items():
        if node_labels.get(key) != value:
            return False

    return True

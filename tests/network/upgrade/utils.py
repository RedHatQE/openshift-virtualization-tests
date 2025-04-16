import logging

from ocp_resources.node_network_state import NodeNetworkState
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from utilities.constants import TIMEOUT_1MIN, TIMEOUT_5SEC
from utilities.infra import get_node_selector_name

LOGGER = logging.getLogger(__name__)


def assert_bridge_and_vms_on_same_node(vm_a, vm_b, bridge):
    for vm in [vm_a, vm_b]:
        assert vm.vmi.node.name == get_node_selector_name(node_selector=bridge.node_selector)


def assert_node_is_marked_by_bridge(bridge_nad, vm):
    for bridge_annotation in bridge_nad.instance.metadata.annotations.values():
        assert bridge_annotation in vm.privileged_vmi.node.instance.status.capacity.keys()
        assert bridge_annotation in vm.privileged_vmi.node.instance.status.allocatable.keys()


def assert_nmstate_bridge_creation(bridge):
    bridge_name = bridge.bridge_name

    # Although the bridge interface was already created, the NodeNetworkState resource takes some time to be updated.
    sampler = TimeoutSampler(
        wait_timeout=TIMEOUT_1MIN,
        sleep=TIMEOUT_5SEC,
        func=lambda: NodeNetworkState(name=get_node_selector_name(node_selector=bridge.node_selector)).get_interface(
            name=bridge_name
        ),
    )
    try:
        for sample in sampler:
            if sample:
                break
    except TimeoutExpiredError:
        LOGGER.error(f"Bridge {bridge_name} not found in NNS.")
        raise


def assert_label_in_namespace(labeled_namespace, label_key, expected_label_value):
    namespace_labels = labeled_namespace.labels
    assert namespace_labels[label_key] == expected_label_value, (
        f"Namespace {labeled_namespace.name} should have label {label_key} "
        f"set to {expected_label_value}. Actual labels:\n{labeled_namespace.labels}."
    )

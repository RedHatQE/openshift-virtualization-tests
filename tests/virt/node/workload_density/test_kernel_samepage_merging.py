import logging

import pytest
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.resource import Resource, ResourceEditor
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.utils import create_vms
from utilities.constants import TIMEOUT_5MIN, TIMEOUT_30SEC
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.infra import ExecCommandOnPod, label_nodes
from utilities.virt import migrate_vm_and_verify, running_vm

LOGGER = logging.getLogger(__name__)


KERNEL_SAMEPAGE_MERGING_TEST = "kernel-samepage-merging-test"
KERNEL_SAMEPAGE_MERGING_TEST_LABEL = {KERNEL_SAMEPAGE_MERGING_TEST: ""}

KSM_ENABLED = "ksm-enabled"
KSM_HANDLER_MANAGED = "ksm-handler-managed"

RUN_FILE = "run"
PAGES_TO_SCAN_FILE = "pages_to_scan"

PAGES_TO_SCAN_MAX_LIMIT = 1000


def get_ksm_data_from_node(utility_pods, node, file_name):
    return int(
        ExecCommandOnPod(utility_pods=utility_pods, node=node).exec(command=f"cat /sys/kernel/mm/ksm/{file_name}")
    )


def wait_for_ksm_state_on_node(utility_pods, node, expected_state):
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_5MIN,
        sleep=TIMEOUT_30SEC,
        func=get_ksm_data_from_node,
        utility_pods=utility_pods,
        node=node,
        file_name=RUN_FILE,
    )
    sample = None
    try:
        for sample in samples:
            if sample == expected_state:
                return
    except TimeoutExpiredError:
        LOGGER.error(f"KSM state not correct, the value in {RUN_FILE} file: {sample}, expected: {expected_state}")
        raise


def assert_label_on_node(node_metadata, expected_value):
    LOGGER.info("Checking labels on the node")
    assert node_metadata.labels.get(f"{Resource.ApiGroup.KUBEVIRT_IO}/{KSM_ENABLED}") == expected_value, (
        f"Label {KSM_ENABLED} was not updated, expected: {expected_value}"
    )


def assert_annotation_on_node(node_metadata, expected_value):
    LOGGER.info("Checking annotations on the node")
    assert node_metadata.annotations.get(f"{Resource.ApiGroup.KUBEVIRT_IO}/{KSM_HANDLER_MANAGED}") == expected_value, (
        f"Annotation {KSM_HANDLER_MANAGED} was not updated, expected: {expected_value}"
    )


def wait_for_pages_to_scan_value_to_grow(utility_pods, node, initial_value):
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_5MIN,
        sleep=TIMEOUT_30SEC,
        func=get_ksm_data_from_node,
        utility_pods=utility_pods,
        node=node,
        file_name=PAGES_TO_SCAN_FILE,
    )
    sample = None
    try:
        for sample in samples:
            if sample > initial_value:
                return
            elif sample >= PAGES_TO_SCAN_MAX_LIMIT:
                LOGGER.warning(f"{PAGES_TO_SCAN_FILE} file reached the limit: {sample}")
                return
    except TimeoutExpiredError:
        LOGGER.error(f"The value in {PAGES_TO_SCAN_FILE} file does not grow, current value: {sample}")
        raise


@pytest.fixture(scope="class")
def ksm_enabled_in_hco(hyperconverged_resource_scope_class):
    with ResourceEditorValidateHCOReconcile(
        patches={
            hyperconverged_resource_scope_class: {
                "spec": {"ksmConfiguration": {"nodeLabelSelector": {"matchLabels": KERNEL_SAMEPAGE_MERGING_TEST_LABEL}}}
            }
        },
        list_resource_reconcile=[KubeVirt],
        wait_for_reconcile_post_update=True,
    ):
        yield


@pytest.fixture(scope="class")
def ksm_label_added_to_worker1(worker_node1):
    yield from label_nodes(nodes=[worker_node1], labels=KERNEL_SAMEPAGE_MERGING_TEST_LABEL)


@pytest.fixture()
def ksm_label_added_to_worker2(worker_node2):
    # Add label to the second worker for successful migration
    yield from label_nodes(nodes=[worker_node2], labels=KERNEL_SAMEPAGE_MERGING_TEST_LABEL)


@pytest.fixture()
def ksm_label_removed_from_worker1(worker_node1):
    with ResourceEditor(patches={worker_node1: {"metadata": {"labels": {KERNEL_SAMEPAGE_MERGING_TEST: None}}}}):
        yield


@pytest.fixture(scope="class")
def ksm_override_annotation_added_to_worker1(worker_node1):
    # Set the free memory value needed for triggering KSM
    with ResourceEditor(
        patches={
            worker_node1: {
                "metadata": {"annotations": {f"{worker_node1.ApiGroup.KUBEVIRT_IO}/ksm-free-percent-override": "1.0"}}
            }
        }
    ):
        yield


@pytest.fixture()
def ksm_activated_on_node(worker_node1, workers_utility_pods):
    LOGGER.info("Wait when KSM activated on the node")
    wait_for_ksm_state_on_node(node=worker_node1, utility_pods=workers_utility_pods, expected_state=1)


@pytest.fixture()
def ksm_deactivated_on_node(worker_node1, workers_utility_pods):
    LOGGER.info("Wait when KSM deactivated on the node")
    wait_for_ksm_state_on_node(node=worker_node1, utility_pods=workers_utility_pods, expected_state=0)


@pytest.fixture(scope="class")
def vms_for_ksm_test(namespace):
    # We need several VMs for sharing memory
    vms_list = create_vms(
        name_prefix="ksm-test-vm",
        namespace_name=namespace.name,
        node_selector_labels=KERNEL_SAMEPAGE_MERGING_TEST_LABEL,
    )
    for vm in vms_list:
        running_vm(vm=vm)
    yield vms_list
    for vm in vms_list:
        vm.clean_up()


@pytest.fixture()
def pages_to_scan_initial_value(worker_node1, workers_utility_pods):
    return get_ksm_data_from_node(
        node=worker_node1,
        utility_pods=workers_utility_pods,
        file_name=PAGES_TO_SCAN_FILE,
    )


@pytest.mark.usefixtures(
    "ksm_enabled_in_hco",
    "ksm_label_added_to_worker1",
    "cluster_cpu_model_scope_class",
    "vms_for_ksm_test",
    "ksm_override_annotation_added_to_worker1",
)
class TestKernelSamepageMerging:
    @pytest.mark.polarion("CNV-10522")
    @pytest.mark.dependency(name="test_ksm_activated_when_node_under_pressure")
    def test_ksm_activated_when_node_under_pressure(self, worker_node1, ksm_activated_on_node):
        node_metadata = worker_node1.instance.metadata
        assert_label_on_node(node_metadata=node_metadata, expected_value="true")
        assert_annotation_on_node(node_metadata=node_metadata, expected_value="true")

    @pytest.mark.polarion("CNV-10732")
    @pytest.mark.dependency(depends=["test_ksm_activated_when_node_under_pressure"])
    def test_pages_to_scan_grows_when_ksm_active(self, worker_node1, workers_utility_pods, pages_to_scan_initial_value):
        wait_for_pages_to_scan_value_to_grow(
            node=worker_node1,
            utility_pods=workers_utility_pods,
            initial_value=pages_to_scan_initial_value,
        )

    @pytest.mark.polarion("CNV-10523")
    @pytest.mark.dependency(depends=["test_ksm_activated_when_node_under_pressure"])
    def test_migrate_vm_when_ksm_active(
        self,
        skip_if_no_common_cpu,
        skip_access_mode_rwo_scope_function,
        ksm_label_added_to_worker2,
        vms_for_ksm_test,
    ):
        migrate_vm_and_verify(vm=vms_for_ksm_test[0])

    @pytest.mark.polarion("CNV-10524")
    @pytest.mark.dependency(depends=["test_ksm_activated_when_node_under_pressure"])
    def test_ksm_not_active_on_non_managed_node(
        self, worker_node1, ksm_label_removed_from_worker1, ksm_deactivated_on_node
    ):
        node_metadata = worker_node1.instance.metadata
        assert_label_on_node(node_metadata=node_metadata, expected_value="false")
        assert_annotation_on_node(node_metadata=node_metadata, expected_value="false")

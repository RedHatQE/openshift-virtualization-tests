import logging

import pytest
from ocp_resources.resource import ResourceEditor
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from utilities.constants import CPU_MODEL_LABEL_PREFIX, TIMEOUT_5SEC, TIMEOUT_10MIN
from utilities.exceptions import ResourceValueError
from utilities.infra import raise_multiple_exceptions

LOGGER = logging.getLogger(__name__)
DISABLED_CPU_LABEL_VALUE = "false"
ENABLED_CPU_LABEL_VALUE = "true"
RECONCILE_TIMEOUT = TIMEOUT_10MIN
TESTS_CLASS_NAME = "TestNodeLabellerSkipAnnotation"


@pytest.fixture()
def worker1_skip_node_annotated(worker_node1):
    with ResourceEditor(
        patches={
            worker_node1: {
                "metadata": {"annotations": {f"{worker_node1.ApiGroup.NODE_LABELLER_KUBEVIRT_IO}/skip-node": "true"}}
            }
        }
    ):
        yield


@pytest.fixture(scope="class")
def worker1_supported_cpu_models_labels(worker_node1):
    node_cpu_models_labels = [
        label_name
        for label_name, label_value in worker_node1.labels.items()
        if label_name.startswith(CPU_MODEL_LABEL_PREFIX) and label_value == ENABLED_CPU_LABEL_VALUE
    ]
    assert node_cpu_models_labels, (
        f"Node {worker_node1.name} does not have labels starting with {CPU_MODEL_LABEL_PREFIX}"
    )
    return node_cpu_models_labels


@pytest.fixture(scope="class")
def labelled_worker_node1(worker1_supported_cpu_models_labels, worker_node1):
    updated_label = worker1_supported_cpu_models_labels[0]
    LOGGER.info(f"Updating node {worker_node1.name} label {updated_label}")
    with ResourceEditor(patches={worker_node1: {"metadata": {"labels": {updated_label: DISABLED_CPU_LABEL_VALUE}}}}):
        yield {worker_node1: updated_label}


@pytest.mark.s390x
class TestNodeLabellerSkipAnnotation:
    @pytest.mark.polarion("CNV-7744")
    @pytest.mark.dependency(name=f"{TESTS_CLASS_NAME}::test_node_labeller_added_skip_node_annotation")
    def test_node_labeller_added_skip_node_annotation(self, worker1_skip_node_annotated, labelled_worker_node1):
        ((node, label),) = labelled_worker_node1.items()
        LOGGER.info(f"Verify {label} on {node.name} is not reconciled after {int(RECONCILE_TIMEOUT / 60)} minutes.")
        try:
            for sample in TimeoutSampler(
                wait_timeout=RECONCILE_TIMEOUT,
                sleep=TIMEOUT_5SEC,
                func=lambda: node.labels[label] != DISABLED_CPU_LABEL_VALUE,
            ):
                if sample:
                    raise ResourceValueError(f"Node {node.name} label {label} was reconciled")
        except TimeoutExpiredError:
            return

    @pytest.mark.polarion("CNV-7745")
    @pytest.mark.dependency(depends=[f"{TESTS_CLASS_NAME}::test_node_labeller_added_skip_node_annotation"])
    def test_node_labeller_removed_skip_node_annotation(self, labelled_worker_node1):
        ((node, label),) = labelled_worker_node1.items()
        LOGGER.info(f"Verify {label} on {node.name} is reconciled")
        try:
            for sample in TimeoutSampler(
                wait_timeout=RECONCILE_TIMEOUT,
                sleep=TIMEOUT_5SEC,
                func=lambda: node.labels[label] == ENABLED_CPU_LABEL_VALUE,
            ):
                if sample:
                    return
        except TimeoutExpiredError as exp:
            raise_multiple_exceptions(
                exceptions=[
                    ResourceValueError(f"Node {node.name} label {label} was not reconciled"),
                    exp,
                ]
            )

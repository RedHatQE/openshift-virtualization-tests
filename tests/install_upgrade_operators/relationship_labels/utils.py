import json
import logging

from tests.install_upgrade_operators.relationship_labels.constants import (
    HPP_POOL,
    KUBEVIRT_APISERVER_PROXY,
    VIRITO_WIN_STORAGE,
)
from utilities.constants import POD_STR, ROLEBINDING_STR, VIRTIO_WIN

LOGGER = logging.getLogger(__name__)


def verify_component_labels_by_resource(component, expected_component_labels):
    """
    extract the expected & actual labels and call for comparison function expected against actual

    Args:
        component (obj) : cnv deployment / related object
        expected_component_labels (dict) :

    deployment name that start with hpp_pool  is considered as hpp_pool
    related_object name that is VIRTIO_WIN and kind ROLEBINDING is considered VIRITO_WIN_STORAGE

    """
    actual_labels = component.instance.metadata.labels
    assert actual_labels, f"For {component.name} no metadata.labels exists"

    if component.name.startswith(HPP_POOL):
        expected_labels = expected_component_labels.get(HPP_POOL)
    elif component.name.startswith(KUBEVIRT_APISERVER_PROXY):
        expected_labels = expected_component_labels.get(KUBEVIRT_APISERVER_PROXY)
    elif component.name == VIRTIO_WIN and component.kind == ROLEBINDING_STR:
        expected_labels = expected_component_labels.get(VIRITO_WIN_STORAGE)
    elif component.kind == POD_STR:
        expected_labels = next(
            labels
            for component_name, labels in expected_component_labels.items()
            if component.name.startswith(component_name)
        )
    else:
        expected_labels = expected_component_labels.get(component.name)

    assert expected_labels, f"Missing component {component.name} in {expected_component_labels}"

    assert_expected_vs_actual_labels_and_values_get_mismatches(
        actual_labels=actual_labels,
        expected_labels=expected_labels,
        related_object_name=component.name,
    )


def assert_expected_vs_actual_labels_and_values_get_mismatches(
    actual_labels,
    expected_labels,
    related_object_name,
):
    """
    Compare label actual value against the expected value and update the mismatch results dict

    Args:
        actual_labels (dict): actual labels-values pairs from the cluster
        expected_labels (dict): expected labels-values pairs
        related_object_name (str): the name of component


    assert: expected_label_value equal to actual_labels

    """
    results = {
        expected_label_key: {
            "expected": expected_label_value,
            "actual": actual_labels[expected_label_key],
        }
        for expected_label_key, expected_label_value in expected_labels.items()
        if expected_label_value != actual_labels[expected_label_key]
    }
    assert not results, (
        f"{related_object_name}\nFound mismatch in label values:  mismatch_results=\n{json.dumps(results, indent=4)}"
    )

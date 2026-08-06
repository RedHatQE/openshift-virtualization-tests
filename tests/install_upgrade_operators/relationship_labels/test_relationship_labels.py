import copy
import logging

import pytest

from tests.install_upgrade_operators.relationship_labels.constants import (
    EXPECTED_VIRT_DAEMONSETS_LABELS_DICT_MAP,
    EXPECTED_VIRT_DEPLOYMENTS_LABELS_DICT_MAP,
    EXPECTED_VIRT_PODS_LABELS_DICT_MAP,
)
from tests.install_upgrade_operators.relationship_labels.utils import (
    verify_component_labels_by_resource,
)
from utilities.constants.cluster import VERSION_LABEL_KEY

pytestmark = [
    pytest.mark.post_upgrade,
    pytest.mark.sno,
    pytest.mark.gating,
    pytest.mark.arm64,
    pytest.mark.s390x,
    pytest.mark.conformance,
    pytest.mark.skip_must_gather_collection,
]
LOGGER = logging.getLogger(__name__)


def _build_expected_labels(labels_dict_map: dict, hco_version: str) -> dict:
    """Build expected labels dict with the current HCO version filled in.

    Args:
        labels_dict_map: Static expected labels map with VERSION_LABEL_KEY set to None.
        hco_version: Current HCO version string.

    Returns:
        dict: Deep copy with VERSION_LABEL_KEY populated.
    """
    updated = copy.deepcopy(labels_dict_map)
    for component_labels in updated.values():
        component_labels[VERSION_LABEL_KEY] = hco_version
    return updated


class TestRelationshipLabels:
    @pytest.mark.polarion("CNV-7190")
    def test_verify_mismatch_relationship_labels_deployments(
        self, subtests, discovered_cnv_deployments, hco_version_scope_class
    ):
        expected_labels = _build_expected_labels(
            labels_dict_map=EXPECTED_VIRT_DEPLOYMENTS_LABELS_DICT_MAP,
            hco_version=hco_version_scope_class,
        )
        for deployment in discovered_cnv_deployments:
            with subtests.test(msg=deployment.name):
                verify_component_labels_by_resource(
                    component=deployment,
                    expected_component_labels=expected_labels,
                )

    @pytest.mark.polarion("CNV-7269")
    def test_verify_mismatch_relationship_labels_daemonsets(
        self, subtests, discovered_cnv_daemonsets, hco_version_scope_class
    ):
        expected_labels = _build_expected_labels(
            labels_dict_map=EXPECTED_VIRT_DAEMONSETS_LABELS_DICT_MAP,
            hco_version=hco_version_scope_class,
        )
        for daemonset in discovered_cnv_daemonsets:
            with subtests.test(msg=daemonset.name):
                verify_component_labels_by_resource(
                    component=daemonset,
                    expected_component_labels=expected_labels,
                )

    @pytest.mark.polarion("CNV-10307")
    def test_verify_mismatch_relationship_labels_pods(self, subtests, discovered_cnv_pods, hco_version_scope_class):
        expected_labels = _build_expected_labels(
            labels_dict_map=EXPECTED_VIRT_PODS_LABELS_DICT_MAP,
            hco_version=hco_version_scope_class,
        )
        for pod in discovered_cnv_pods:
            with subtests.test(msg=pod.name):
                verify_component_labels_by_resource(
                    component=pod,
                    expected_component_labels=expected_labels,
                )

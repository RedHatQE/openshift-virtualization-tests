import copy
import logging

import pytest

from tests.install_upgrade_operators.relationship_labels.constants import (
    EXPECTED_RELATED_OBJECTS_LABELS_DICT_MAP,
    EXPECTED_VIRT_DAEMONSETS_LABELS_DICT_MAP,
    EXPECTED_VIRT_DEPLOYMENTS_LABELS_DICT_MAP,
    EXPECTED_VIRT_PODS_LABELS_DICT_MAP,
)
from tests.install_upgrade_operators.relationship_labels.utils import (
    verify_component_labels_by_resource,
)
from utilities.constants import VERSION_LABEL_KEY

pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno, pytest.mark.gating, pytest.mark.arm64]
LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="class")
def expected_label_dictionary(hco_version_scope_class, request):
    """
    Populate each labels dict (RELATED_OBJECTS_LABELS_DICT_MAP / COMPONENT_LABELS_DICT_MAP)
    with updates cnv current version, deepcopy and return  updated expected labels dict
    """
    expected_labels_dict = request.param["expected_labels_dict"]
    updated_expected_labels_dict = copy.deepcopy(expected_labels_dict)
    for deployment_labels in updated_expected_labels_dict.values():
        deployment_labels[VERSION_LABEL_KEY] = hco_version_scope_class
    return updated_expected_labels_dict


class TestRelationshipLabels:
    @pytest.mark.parametrize(
        "expected_label_dictionary",
        [
            pytest.param(
                {"expected_labels_dict": EXPECTED_VIRT_DEPLOYMENTS_LABELS_DICT_MAP},
                marks=pytest.mark.polarion("CNV-7190"),
            ),
        ],
        indirect=True,
    )
    @pytest.mark.s390x
    def test_verify_mismatch_relationship_labels_deployments(self, expected_label_dictionary, cnv_deployment_by_name):
        verify_component_labels_by_resource(
            component=cnv_deployment_by_name,
            expected_component_labels=expected_label_dictionary,
        )

    @pytest.mark.parametrize(
        "expected_label_dictionary",
        [
            pytest.param(
                {"expected_labels_dict": EXPECTED_VIRT_DAEMONSETS_LABELS_DICT_MAP},
                marks=pytest.mark.polarion("CNV-7269"),
            ),
        ],
        indirect=True,
    )
    @pytest.mark.s390x
    def test_verify_mismatch_relationship_labels_daemonsets(self, expected_label_dictionary, cnv_daemonset_by_name):
        verify_component_labels_by_resource(
            component=cnv_daemonset_by_name,
            expected_component_labels=expected_label_dictionary,
        )

    @pytest.mark.parametrize(
        "expected_label_dictionary",
        [
            pytest.param(
                {"expected_labels_dict": EXPECTED_VIRT_PODS_LABELS_DICT_MAP},
                marks=pytest.mark.polarion("CNV-10307"),
            ),
        ],
        indirect=True,
    )
    @pytest.mark.s390x
    def test_verify_mismatch_relationship_labels_pods(self, expected_label_dictionary, cnv_pod_by_name):
        verify_component_labels_by_resource(
            component=cnv_pod_by_name,
            expected_component_labels=expected_label_dictionary,
        )

    @pytest.mark.parametrize(
        "expected_label_dictionary",
        [
            pytest.param(
                {"expected_labels_dict": EXPECTED_RELATED_OBJECTS_LABELS_DICT_MAP},
                marks=pytest.mark.polarion("CNV-7189"),
            ),
        ],
        indirect=True,
    )
    @pytest.mark.s390x
    def test_verify_relationship_labels_hco_components(
        self,
        expected_label_dictionary,
        ocp_resource_by_name,
    ):
        verify_component_labels_by_resource(
            component=ocp_resource_by_name,
            expected_component_labels=expected_label_dictionary,
        )

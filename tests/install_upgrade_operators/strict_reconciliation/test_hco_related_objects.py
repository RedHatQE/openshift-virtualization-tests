import pytest
from deepdiff import DeepDiff

from tests.install_upgrade_operators.strict_reconciliation.utils import (
    validate_related_objects,
)
from tests.install_upgrade_operators.utils import is_rhel10_beta_resource_and_63351_bug_open
from utilities.constants import ALL_HCO_RELATED_OBJECTS

pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno, pytest.mark.arm64]


class TestRelatedObjects:
    @pytest.mark.polarion("CNV-9843")
    @pytest.mark.s390x
    def test_no_new_hco_related_objects(self, hco_status_related_objects):
        actual_related_objects = {
            related_object["name"]: related_object["kind"]
            for related_object in hco_status_related_objects
            if not is_rhel10_beta_resource_and_63351_bug_open(resource_name=related_object["name"])
        }
        expected_related_objects = {
            object_name: object_kind
            for related_object in ALL_HCO_RELATED_OBJECTS
            for object_name, object_kind in related_object.items()
        }

        new_related_objects = DeepDiff(t1=expected_related_objects, t2=actual_related_objects, verbose_level=2)
        assert not new_related_objects, f"There are new HCO related objects:\n {new_related_objects.to_json(indent=2)}"

    @pytest.mark.polarion("CNV-7267")
    @pytest.mark.s390x
    def test_hco_related_objects(
        self,
        admin_client,
        hco_namespace,
        skip_if_hco_bearer_token_bug_open,
        ocp_resource_by_name,
        pre_update_resource_version,
        updated_resource_labels,
    ):
        validate_related_objects(
            admin_client=admin_client,
            hco_namespace=hco_namespace,
            resource=ocp_resource_by_name,
            pre_update_resource_version=pre_update_resource_version,
        )

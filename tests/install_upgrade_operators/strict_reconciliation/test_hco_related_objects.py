import pytest

from tests.install_upgrade_operators.strict_reconciliation.utils import (
    validate_related_objects,
)
from utilities.constants import ALL_HCO_RELATED_OBJECTS

pytestmark = [
    pytest.mark.post_upgrade,
    pytest.mark.sno,
    pytest.mark.arm64,
    pytest.mark.s390x,
    pytest.mark.skip_must_gather_collection,
]


class TestRelatedObjects:
    @pytest.mark.polarion("CNV-9843")
    def test_no_new_hco_related_objects(self, hco_status_related_objects):
        actual_related_objects = {
            (related_object["name"], related_object["kind"]) for related_object in hco_status_related_objects
        }
        expected_related_objects = {
            (object_name, object_kind)
            for related_object in ALL_HCO_RELATED_OBJECTS
            for object_name, object_kind in related_object.items()
        }

        missing_objects = expected_related_objects - actual_related_objects
        new_objects = actual_related_objects - expected_related_objects
        assert not missing_objects and not new_objects, (
            f"HCO related objects mismatch:\n"
            f"  Missing (expected but not found): {missing_objects}\n"
            f"  New (found but not expected): {new_objects}"
        )

    @pytest.mark.polarion("CNV-7267")
    def test_hco_related_objects(
        self,
        admin_client,
        hco_namespace,
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

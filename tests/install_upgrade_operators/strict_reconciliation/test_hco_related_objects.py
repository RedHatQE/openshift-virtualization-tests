import pytest

from tests.install_upgrade_operators.strict_reconciliation.utils import (
    validate_related_objects,
)
from utilities.constants import ALL_HCO_RELATED_OBJECTS

pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno]


class TestRelatedObjects:
    @pytest.mark.polarion("CNV-9843")
    def test_no_new_hco_related_objects(self, hco_status_related_objects):
        assert len(hco_status_related_objects) == len(ALL_HCO_RELATED_OBJECTS), (
            f"Expected related objects: {ALL_HCO_RELATED_OBJECTS}, actual: {hco_status_related_objects}"
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

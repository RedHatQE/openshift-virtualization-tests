import pytest

from tests.install_upgrade_operators.strict_reconciliation.utils import (
    validate_related_objects,
)

pytestmark = [
    pytest.mark.post_upgrade,
    pytest.mark.sno,
    pytest.mark.arm64,
    pytest.mark.s390x,
    pytest.mark.skip_must_gather_collection,
]


class TestRelatedObjects:
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

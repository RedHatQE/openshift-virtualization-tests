import logging

import pytest
from ocp_resources.resource import ResourceEditor

from tests.install_upgrade_operators.strict_reconciliation.utils import (
    validate_related_objects,
)
from tests.install_upgrade_operators.utils import get_resource_from_module_name
from tests.utils import wait_for_cr_labels_change
from utilities.constants.cluster import VERSION_LABEL_KEY
from utilities.constants.timeouts import TIMEOUT_1MIN

pytestmark = [
    pytest.mark.post_upgrade,
    pytest.mark.sno,
    pytest.mark.arm64,
    pytest.mark.s390x,
    pytest.mark.skip_must_gather_collection,
]

LOGGER = logging.getLogger(__name__)


class TestRelatedObjects:
    @pytest.mark.polarion("CNV-7267")
    def test_hco_related_objects(
        self,
        subtests,
        admin_client,
        hco_namespace,
        hco_status_related_objects,
        ocp_resources_submodule_list,
    ):
        for related_object in hco_status_related_objects:
            object_name = related_object.name
            with subtests.test(msg=f"{object_name}-{related_object.kind}"):
                ocp_resource = get_resource_from_module_name(
                    related_obj=related_object,
                    ocp_resources_submodule_list=ocp_resources_submodule_list,
                    admin_client=admin_client,
                )
                pre_update_resource_version = related_object["resourceVersion"]

                expected_labels = ocp_resource.labels
                expected_labels.custom_label = ocp_resource.name
                with ResourceEditor(
                    patches={
                        ocp_resource: {
                            "metadata": {
                                "labels": {VERSION_LABEL_KEY: None, "custom_label": ocp_resource.name},
                            }
                        }
                    }
                ):
                    wait_for_cr_labels_change(
                        expected_value=expected_labels,
                        component=ocp_resource,
                        timeout=TIMEOUT_1MIN,
                    )
                    validate_related_objects(
                        admin_client=admin_client,
                        hco_namespace=hco_namespace,
                        resource=ocp_resource,
                        pre_update_resource_version=pre_update_resource_version,
                    )

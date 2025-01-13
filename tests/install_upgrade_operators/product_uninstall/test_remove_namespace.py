import logging
from http import HTTPStatus

import pytest
from kubernetes.client.rest import ApiException

from tests.install_upgrade_operators.product_uninstall.constants import BLOCK_REMOVAL_TEST_NODE_ID
from utilities.constants import TIMEOUT_10MIN

LOGGER = logging.getLogger(__name__)

DELETION_ERROR_MESSAGE = (
    r"denied the request.*"
    r"HyperConverged CR is still present.*"
    r"please remove it before deleting the containing hcoNamespace"
)


@pytest.fixture()
def remove_hyperconverged_resource(hyperconverged_resource_scope_function):
    hyperconverged_resource_scope_function.delete(wait=True, timeout=TIMEOUT_10MIN)


@pytest.mark.install
class TestRemoveNamespace:
    @pytest.mark.polarion("CNV-5846")
    def test_block_namespace_removal(
        self,
        hyperconverged_resource_scope_function,
        hco_namespace,
    ):
        """
        testcase to verify that HCO namespace deletion is blocked while the HyperConverged
        resource still exists.

        test plan:

            1. delete HCO namespace
            2. verify that the deletion failed with a proper error message
        """

        LOGGER.info("Attempting to delete HCO namespace")

        with pytest.raises(
            ApiException,
            match=DELETION_ERROR_MESSAGE,
        ) as excinfo:
            hco_namespace.delete()

        assert excinfo.value.status == HTTPStatus.FORBIDDEN, (
            f"Unexpected HTTP status {excinfo.value.status} when deleting HCO namespace"
        )

        assert hco_namespace.exists, "HCO namespace does not exist"

        assert hyperconverged_resource_scope_function.instance.metadata.get("deletionTimestamp") is None, (
            "deletionTimestamp is set on HCO namespace"
        )

    @pytest.mark.polarion("CNV-5847")
    @pytest.mark.dependency(depends=[BLOCK_REMOVAL_TEST_NODE_ID], scope="package")
    def test_unblock_namespace_removal(
        self,
        remove_hyperconverged_resource,
        hco_namespace,
    ):
        """
        testcase to verify that HCO namespace deletion is unblocked when the HyperConverged
        resource does not exist.

        test plan:

            1. delete HCO CR (via a fixture)
            2. delete HCO namespace
            3. verify that HCO namespace is now removed
        """

        hco_namespace.delete(wait=True)

        assert not hco_namespace.exists, "HCO namespace still exists"

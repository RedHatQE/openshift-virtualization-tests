import logging

import pytest

from tests.install_upgrade_operators.resource_params.utils import (
    assert_observed_generation,
    assert_status_condition,
)
from utilities.hco import wait_for_hco_conditions
from utilities.infra import get_hyperconverged_resource

pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno, pytest.mark.gating, pytest.mark.arm64]
LOGGER = logging.getLogger(__name__)


@pytest.mark.parametrize(
    "expected_condition_fields",
    [
        pytest.param(
            {"LastHeartbeatTime": False, "observedGeneration": True},
            marks=(pytest.mark.polarion("CNV-6985")),
            id="test_hco_status_conditions",
        ),
    ],
)
@pytest.mark.s390x
def test_hco_status_conditions(admin_client, hco_namespace, expected_condition_fields):
    """Validates hco status conditions contains expected field"""
    LOGGER.info("Check for hco to be in stable condition:")
    wait_for_hco_conditions(
        admin_client=admin_client,
        hco_namespace=hco_namespace,
    )
    hyperconverged_resource = get_hyperconverged_resource(client=admin_client, hco_ns_name=hco_namespace.name)
    LOGGER.info(f"Validate presence and absense of right fields in status.conditions: {expected_condition_fields}")
    assert_status_condition(
        conditions=hyperconverged_resource.instance.status.conditions,
        field_dict=expected_condition_fields,
    )
    assert_observed_generation(hyperconverged_resource=hyperconverged_resource.instance)

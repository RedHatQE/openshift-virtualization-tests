import logging

import pytest

from tests.upgrade_params import IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID

LOGGER = logging.getLogger(__name__)


@pytest.mark.upgrade
@pytest.mark.eus_upgrade
class TestEUSToEUSUpgrade:
    @pytest.mark.polarion("CNV-9509")
    @pytest.mark.dependency(name=IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID)
    def test_eus_upgrade_process(self):
        pass

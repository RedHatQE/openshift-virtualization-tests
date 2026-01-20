import logging

import pytest

from tests.observability.utils import validate_metrics_value

pytestmark = [pytest.mark.usefixtures("skip_if_hpp_not_exist", "hpp_condition_available_scope_module")]

LOGGER = logging.getLogger(__name__)


class TestKubevirtHPPPoolPathSharedWithOS:
    @pytest.mark.polarion("CNV-11221")
    @pytest.mark.s390x
    def test_kubevirt_hpp_pool_path_shared_path_metric(self, prometheus, hpp_pod_sharing_pool_path):
        validate_metrics_value(
            prometheus=prometheus,
            metric_name="kubevirt_hpp_pool_path_shared_with_os",
            expected_value="1",
        )


class TestHPPCrReady:
    @pytest.mark.polarion("CNV-11022")
    @pytest.mark.s390x
    def test_kubevirt_hpp_cr_ready_metric(self, prometheus, modified_hpp_non_exist_node_selector):
        validate_metrics_value(
            prometheus=prometheus,
            metric_name="kubevirt_hpp_cr_ready",
            expected_value="0",
        )

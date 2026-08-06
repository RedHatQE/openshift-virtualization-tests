import logging

import pytest

from tests.observability.runbook_url.utils import validate_downstream_runbook_url

LOGGER = logging.getLogger(__name__)


class TestRunbookUrlsAndPrometheusRules:
    @pytest.mark.polarion("CNV-10084")
    def test_runbook_downstream_urls(self, available_runbook_urls, cnv_prometheus_rule_alerts, subtests):
        validate_downstream_runbook_url(
            cnv_prometheus_rule_alerts=cnv_prometheus_rule_alerts,
            available_runbook_urls=available_runbook_urls,
            subtests=subtests,
        )

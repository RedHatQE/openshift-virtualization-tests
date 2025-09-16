import logging

import pytest
from ocp_resources.prometheus_rule import PrometheusRule
from pytest_testconfig import config as py_config

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def cnv_prometheus_rules_names(hco_namespace):
    return [prometheus_rule.name for prometheus_rule in PrometheusRule.get(namespace=hco_namespace.name)]


@pytest.fixture()
def cnv_alerts_runbook_urls_from_prometheus_rule(cnv_prometheus_rules_matrix__function__):
    cnv_prometheus_rule_by_name = PrometheusRule(
        namespace=py_config["hco_namespace"],
        name=cnv_prometheus_rules_matrix__function__,
    )
    LOGGER.info(f"Checking rule: {cnv_prometheus_rule_by_name.name}")
    return {
        alert.get("alert"): alert.get("annotations").get("runbook_url")
        for group in cnv_prometheus_rule_by_name.instance.spec.groups
        for alert in group["rules"]
        if alert.get("alert")
    }

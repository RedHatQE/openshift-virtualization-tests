import logging

import pytest
import requests
from ocp_resources.prometheus_rule import PrometheusRule
from pytest_testconfig import config as py_config
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from utilities.constants.components import CNV_PROMETHEUS_RULES, KUBEMACPOOL_PROMETHEUS_RULE
from utilities.constants.timeouts import (
    TIMEOUT_1MIN,
    TIMEOUT_10SEC,
)
from utilities.jira import is_jira_open

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def cnv_prometheus_rules_names(hco_namespace):
    return [prometheus_rule.name for prometheus_rule in PrometheusRule.get(namespace=hco_namespace.name)]


@pytest.fixture(scope="module")
def cnv_prometheus_rule_alerts(hpp_cr_installed):
    """All alert-to-runbook-URL mappings per CNV prometheus rule.

    Returns:
        dict[str, dict[str, str]]: Mapping of rule name to {alert_name: runbook_url}.
    """
    rules_to_check = CNV_PROMETHEUS_RULES.copy()
    if not hpp_cr_installed:
        rules_to_check.remove("prometheus-hpp-rules")

    result: dict[str, dict[str, str]] = {}
    for rule_name in rules_to_check:
        prometheus_rule = PrometheusRule(
            namespace=py_config["hco_namespace"],
            name=rule_name,
        )
        LOGGER.info(f"Loading alerts from rule: {rule_name}")
        result[rule_name] = {
            alert.get("alert"): (alert.get("annotations") or {}).get("runbook_url")
            for group in prometheus_rule.instance.spec.groups
            for alert in group["rules"]
            if alert.get("alert")
        }
    return result


@pytest.fixture()
def cnv_alerts_runbook_urls_from_prometheus_rule(
    cnv_prometheus_rules_matrix__function__, hpp_cr_installed, cnv_prometheus_rule_alerts
):
    rule_name = cnv_prometheus_rules_matrix__function__
    if rule_name == "prometheus-hpp-rules" and not hpp_cr_installed:
        pytest.xfail(f"Rule {rule_name} should not be present if HPP CR is not installed")
    if rule_name == KUBEMACPOOL_PROMETHEUS_RULE and is_jira_open(jira_id="CNV-81829"):
        pytest.xfail(f"{KUBEMACPOOL_PROMETHEUS_RULE} missing runbook URLs: CNV-81829")

    return cnv_prometheus_rule_alerts.get(rule_name, {})


@pytest.fixture(scope="module")
def available_runbook_urls(cnv_prometheus_rule_alerts):
    """Fetch available runbook URLs from the openshift/runbooks GitHub repository.

    Returns:
        set[str]: Set of runbook URLs that are reachable via HTTP HEAD.
    """
    unique_urls: set[str] = set()
    for alerts in cnv_prometheus_rule_alerts.values():
        for runbook_url in alerts.values():
            if runbook_url:
                unique_urls.add(runbook_url)

    LOGGER.info(f"Validating {len(unique_urls)} unique runbook URLs")

    available_urls: set[str] = set()
    session = requests.Session()
    try:
        for runbook_url in sorted(unique_urls):
            raw_url = runbook_url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
            sample = None
            try:
                for sample in TimeoutSampler(
                    wait_timeout=TIMEOUT_1MIN,
                    sleep=TIMEOUT_10SEC,
                    func=session.head,
                    exceptions_dict={
                        requests.exceptions.ConnectionError: [],
                        requests.exceptions.Timeout: [],
                    },
                    url=raw_url,
                    timeout=TIMEOUT_10SEC,
                ):
                    if sample.status_code == requests.codes.ok:
                        available_urls.add(runbook_url)
                        LOGGER.info(f"Runbook URL reachable: {raw_url}")
                        break
            except TimeoutExpiredError:
                LOGGER.error(
                    f"Runbook URL unreachable after retries: {raw_url}, "
                    f"status: {sample.status_code if sample else 'no response'}"
                )
    finally:
        session.close()

    return available_urls

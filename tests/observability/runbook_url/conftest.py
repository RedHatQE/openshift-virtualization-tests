import logging

import pytest
import requests
from ocp_resources.prometheus_rule import PrometheusRule
from pytest_testconfig import config as py_config
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from utilities.constants import KUBEMACPOOL_PROMETHEUS_RULE, TIMEOUT_10SEC, TIMEOUT_30SEC
from utilities.jira import is_jira_open

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def cnv_prometheus_rules_names(hco_namespace):
    return [prometheus_rule.name for prometheus_rule in PrometheusRule.get(namespace=hco_namespace.name)]


@pytest.fixture()
def cnv_alerts_runbook_urls_from_prometheus_rule(cnv_prometheus_rules_matrix__function__, hpp_cr_installed):
    rule_name = cnv_prometheus_rules_matrix__function__
    if rule_name == "prometheus-hpp-rules" and not hpp_cr_installed:
        pytest.xfail(f"Rule {rule_name} should not be present if HPP CR is not installed")
    if rule_name == KUBEMACPOOL_PROMETHEUS_RULE and is_jira_open(jira_id="CNV-81829"):
        pytest.xfail(f"{KUBEMACPOOL_PROMETHEUS_RULE} missing runbook URLs: CNV-81829")

    cnv_prometheus_rule_by_name = PrometheusRule(
        namespace=py_config["hco_namespace"],
        name=rule_name,
    )
    LOGGER.info(f"Checking rule: {cnv_prometheus_rule_by_name.name}")
    return {
        alert.get("alert"): alert.get("annotations").get("runbook_url")
        for group in cnv_prometheus_rule_by_name.instance.spec.groups
        for alert in group["rules"]
        if alert.get("alert")
    }


@pytest.fixture(scope="module")
def available_runbook_urls():
    """Fetch available runbook URLs from the openshift/runbooks GitHub repository.

    Returns:
        Set of runbook HTML URLs available in the repository.
    """
    runbooks_api_url = (
        "https://api.github.com/repos/openshift/runbooks/contents/alerts/openshift-virtualization-operator"
    )
    sample = None
    try:
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_30SEC,
            sleep=TIMEOUT_10SEC,
            func=requests.get,
            url=runbooks_api_url,
            timeout=TIMEOUT_10SEC,
        ):
            if sample.status_code == requests.codes.ok:
                return {entry["html_url"] for entry in sample.json()}
    except TimeoutExpiredError:
        LOGGER.error(
            f"Failed to fetch runbooks directory listing from '{runbooks_api_url}', "
            f"status: {sample.status_code if sample else 'no response'} "
        )
        raise

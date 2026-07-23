import logging

import pytest
import requests
from ocp_resources.prometheus_rule import PrometheusRule
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.observability.runbook_url.utils import github_blob_url_to_raw
from utilities.constants.timeouts import TIMEOUT_1MIN, TIMEOUT_10SEC

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def cnv_prometheus_rule_alerts(hco_namespace):
    """All alert-to-runbook-URL mappings per CNV prometheus rule.

    Returns:
        dict[str, dict[str, str]]: Mapping of rule name to {alert_name: runbook_url}.
    """
    result: dict[str, dict[str, str]] = {}
    for prometheus_rule in PrometheusRule.get(namespace=hco_namespace.name):
        LOGGER.info(f"Loading alerts from rule: {prometheus_rule.name}")
        result[prometheus_rule.name] = {
            alert.get("alert"): alert.get("annotations").get("runbook_url")
            for group in prometheus_rule.instance.spec.groups
            for alert in group["rules"]
            if alert.get("alert")
        }
    return result


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
    with requests.Session() as session:
        for runbook_url in sorted(unique_urls):
            raw_url = github_blob_url_to_raw(blob_url=runbook_url)
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

    return available_urls

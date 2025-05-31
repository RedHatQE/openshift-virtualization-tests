# -*- coding: utf-8 -*-
"""
Test to verify all HCO deployments have 'openshift.io/required-scc' annotation.
"""

import pytest
from ocp_resources.deployment import Deployment

from utilities.constants import ALL_CNV_DEPLOYMENTS_NO_HPP_POOL, VIRT_EXPORTPROXY
from utilities.infra import is_jira_open

REQUIRED_SCC_ANNOTATION = "openshift.io/required-scc"
REQUIRED_SCC_VALUE = "restricted-v2"


@pytest.fixture(scope="module")
def all_hco_deployments(hco_namespace):
    return [Deployment(name=dep_name, namespace=hco_namespace.name) for dep_name in ALL_CNV_DEPLOYMENTS_NO_HPP_POOL]


@pytest.fixture(scope="module")
def required_scc_deployment_check(all_hco_deployments):
    missing_required_scc_annotation = []
    incorrect_required_scc_annotation_value = []

    for dp in all_hco_deployments:
        if is_jira_open(jira_id="CNV-62807") and dp.name in VIRT_EXPORTPROXY:
            continue

        scc = dp.instance.spec.template.metadata.annotations.get(REQUIRED_SCC_ANNOTATION)

        if scc != REQUIRED_SCC_VALUE:
            if scc is None:
                missing_required_scc_annotation.append(dp.name)
            incorrect_required_scc_annotation_value.append(dp.name)

    return {
        "missing_required_scc_annotation": sorted(missing_required_scc_annotation),
        "incorrect_required_scc_annotation_value": sorted(incorrect_required_scc_annotation_value),
    }


@pytest.mark.polarion("CNV-11964")
def test_deployments_missing_required_scc_annotation(required_scc_deployment_check):
    assert not required_scc_deployment_check["missing_required_scc_annotation"], (
        f"Deployments missing {REQUIRED_SCC_ANNOTATION} annotation: "
        f"{required_scc_deployment_check['missing_required_scc_annotation']}"
    )


@pytest.mark.polarion("CNV-11965")
def test_deployments_with_incorrect_required_scc(required_scc_deployment_check):
    assert not required_scc_deployment_check["incorrect_required_scc_annotation_value"], (
        f"Deployments incorrect {REQUIRED_SCC_ANNOTATION} annotation: "
        f"{required_scc_deployment_check['incorrect_required_scc_annotation_value']}"
    )

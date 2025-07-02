# -*- coding: utf-8 -*-
"""
Test to verify all HCO deployments have 'openshift.io/required-scc' annotation.
"""

import pytest
from ocp_resources.deployment import Deployment

from utilities.constants import ALL_CNV_DEPLOYMENTS_NO_HPP_POOL

REQUIRED_SCC_ANNOTATION = "openshift.io/required-scc"
REQUIRED_SCC_VALUE = "restricted-v2"


@pytest.fixture(scope="module")
def required_scc_deployment_check(admin_client, hco_namespace):
    missing_required_scc_annotation = []
    incorrect_required_scc_annotation_value = {}

    for dp in (
        Deployment(client=admin_client, name=name, namespace=hco_namespace.name)
        for name in ALL_CNV_DEPLOYMENTS_NO_HPP_POOL
    ):
        scc = dp.instance.spec.template.metadata.annotations.get(REQUIRED_SCC_ANNOTATION)

        if scc is None:
            missing_required_scc_annotation.append(dp.name)
        elif scc != REQUIRED_SCC_VALUE:
            incorrect_required_scc_annotation_value[dp.name] = scc

    return {
        "missing_required_scc_annotation": missing_required_scc_annotation,
        "incorrect_required_scc_annotation_value": incorrect_required_scc_annotation_value,
    }


@pytest.mark.polarion("CNV-11964")
@pytest.mark.s390x
def test_deployments_missing_required_scc_annotation(required_scc_deployment_check):
    assert not required_scc_deployment_check["missing_required_scc_annotation"], (
        f"Deployments missing {REQUIRED_SCC_ANNOTATION} annotation: "
        f"{required_scc_deployment_check['missing_required_scc_annotation']}"
    )


@pytest.mark.polarion("CNV-11965")
@pytest.mark.s390x
def test_deployments_with_incorrect_required_scc(required_scc_deployment_check):
    assert not required_scc_deployment_check["incorrect_required_scc_annotation_value"], (
        f"Deployments incorrect {REQUIRED_SCC_ANNOTATION} annotation : "
        f"{required_scc_deployment_check['incorrect_required_scc_annotation_value']}"
    )

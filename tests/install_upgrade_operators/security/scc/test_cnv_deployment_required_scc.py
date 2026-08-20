"""
Test to verify all HCO deployments have 'openshift.io/required-scc' annotation.
"""

import pytest

from utilities.constants.components import HPP_POOL
from utilities.jira import is_jira_open

REQUIRED_SCC_ANNOTATION = "openshift.io/required-scc"
REQUIRED_SCC_VALUE = "restricted-v2"
VIRT_TEMPLATE_PREFIXES = ("virt-template-apiserver", "virt-template-controller")

pytestmark = [pytest.mark.s390x, pytest.mark.skip_must_gather_collection]


@pytest.mark.polarion("CNV-11964")
def test_deployment_required_scc(subtests, discovered_cnv_deployments):
    assert discovered_cnv_deployments, "No CNV deployments were discovered in the HCO namespace"
    for deployment in discovered_cnv_deployments:
        with subtests.test(msg=deployment.name):
            if deployment.name.startswith(HPP_POOL):
                continue
            if deployment.name.startswith(VIRT_TEMPLATE_PREFIXES) and is_jira_open(jira_id="CNV-94717"):
                pytest.xfail(f"{deployment.name} missing required-scc annotation (CNV-94717)")
            scc = deployment.instance.spec.template.metadata.annotations.get(REQUIRED_SCC_ANNOTATION)
            assert scc, f"Deployment {deployment.name} missing {REQUIRED_SCC_ANNOTATION} annotation"
            assert scc == REQUIRED_SCC_VALUE, (
                f"Deployment {deployment.name}: {REQUIRED_SCC_ANNOTATION}={scc}, expected: {REQUIRED_SCC_VALUE}"
            )

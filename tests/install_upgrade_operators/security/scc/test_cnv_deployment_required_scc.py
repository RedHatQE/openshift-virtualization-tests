"""
Test to verify all HCO deployments have 'openshift.io/required-scc' annotation.
"""

import pytest

from utilities.constants.components import HPP_POOL

REQUIRED_SCC_ANNOTATION = "openshift.io/required-scc"
REQUIRED_SCC_VALUE = "restricted-v2"

pytestmark = [pytest.mark.s390x, pytest.mark.skip_must_gather_collection]


@pytest.mark.polarion("CNV-11964")
def test_deployment_required_scc(subtests, discovered_cnv_deployments):
    assert discovered_cnv_deployments, "No CNV deployments were discovered in the HCO namespace"
    for deployment in discovered_cnv_deployments:
        with subtests.test(msg=deployment.name):
            if deployment.name.startswith(HPP_POOL):
                continue
            annotations = deployment.instance.spec.template.metadata.annotations or {}
            scc = annotations.get(REQUIRED_SCC_ANNOTATION)
            assert scc, f"Deployment {deployment.name} missing {REQUIRED_SCC_ANNOTATION} annotation"
            assert scc == REQUIRED_SCC_VALUE, (
                f"Deployment {deployment.name}: {REQUIRED_SCC_ANNOTATION}={scc}, expected: {REQUIRED_SCC_VALUE}"
            )

import pytest

from utilities.constants.components import (
    HCO_OPERATOR,
    HPP_POOL,
    KUBEVIRT_MIGRATION_CONTROLLER,
)
from utilities.hco import get_hco_version
from utilities.infra import get_deployment_by_name, get_deployments
from utilities.jira import is_jira_open


@pytest.fixture()
def deployment_by_name(request, admin_client, hco_namespace):
    """
    Gets a deployment object by name.
    """
    deployment_name = request.param["deployment_name"]
    yield get_deployment_by_name(
        namespace_name=hco_namespace.name, deployment_name=deployment_name, admin_client=admin_client
    )


@pytest.fixture(scope="module")
def cnv_deployments_excluding_hpp_pool(admin_client, hco_namespace):
    return [
        deployment
        for deployment in get_deployments(admin_client=admin_client, namespace=hco_namespace.name)
        if not deployment.name.startswith(HPP_POOL)
    ]


@pytest.fixture(scope="session")
def hco_current_version(admin_client, hco_namespace):
    return get_hco_version(client=admin_client, hco_ns_name=hco_namespace.name)


@pytest.fixture()
def xfail_if_sriov_conforma_jira_open_and_hco_operator(hco_current_version, cnv_deployment_by_name):
    if cnv_deployment_by_name.name != HCO_OPERATOR:
        return
    if hco_current_version.startswith("4.23") and is_jira_open(jira_id="CNV-92888"):
        pytest.xfail(
            "hco-operator image check xfailed: nightly sriov-dp-admission-controller triggers upstream registry violation (CNV-92888)"
        )
    if hco_current_version.startswith("5.0") and is_jira_open(jira_id="CNV-92889"):
        pytest.xfail(
            "hco-operator image check xfailed: nightly sriov-dp-admission-controller triggers upstream registry violation (CNV-92889)"
        )


@pytest.fixture()
def xfail_if_jira_76659_open_and_migration_controller_deployment(jira_76659_open, cnv_deployment_by_name):
    if cnv_deployment_by_name.name == KUBEVIRT_MIGRATION_CONTROLLER and jira_76659_open:
        pytest.xfail(f"{KUBEVIRT_MIGRATION_CONTROLLER} deployment is not running due to CNV-76659 bug")

import importlib
import logging
import pkgutil
import re

import pytest
from ocp_resources.cdi import CDI
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.network_addons_config import NetworkAddonsConfig
from ocp_resources.pod import Pod
from pytest_testconfig import py_config

from tests.install_upgrade_operators.constants import (
    RESOURCE_NAME_STR,
    RESOURCE_NAMESPACE_STR,
    RESOURCE_TYPE_STR,
)
from tests.install_upgrade_operators.utils import (
    get_network_addon_config,
    get_resource_by_name,
)
from utilities.hco import ResourceEditorValidateHCOReconcile, get_hco_version
from utilities.infra import (
    get_daemonsets,
    get_deployments,
    wait_for_version_explorer_response,
)
from utilities.jira import is_jira_open
from utilities.operator import (
    disable_default_sources_in_operatorhub,
    get_machine_config_pools_conditions,
)
from utilities.pytest_utils import exit_pytest_execution
from utilities.storage import get_hyperconverged_cdi
from utilities.virt import get_hyperconverged_kubevirt

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def discovered_cnv_deployments(admin_client, hco_namespace):
    """Discover all CNV deployments from the cluster."""
    return get_deployments(admin_client=admin_client, namespace=hco_namespace.name)


@pytest.fixture(scope="session")
def discovered_cnv_pods(admin_client, hco_namespace):
    """Discover all CNV pods from the cluster."""
    return list(Pod.get(client=admin_client, namespace=hco_namespace.name))


@pytest.fixture(scope="session")
def discovered_cnv_daemonsets(admin_client, hco_namespace):
    """Discover all CNV daemonsets from the cluster."""
    return get_daemonsets(admin_client=admin_client, namespace=hco_namespace.name)


@pytest.fixture(scope="session")
def iib_build_info(cnv_source, cnv_image_url, admin_client):
    """Queries Version Explorer for IIB build info.

    Returns:
        Build info dict for osbs/fbc sources, empty dict for other sources.
    """
    if cnv_source in ("osbs", "fbc"):
        iib_format_match = re.search(r"/iib:(\d+)$", cnv_image_url)
        assert iib_format_match, f"Cannot extract IIB number from: {cnv_image_url} (expected format: .../iib:<number>)"
        iib_number = iib_format_match.group(1)

        if build_info := wait_for_version_explorer_response(
            api_end_point="GetBuildByIIB",
            query_string=f"iib_number={iib_number}",
        ):
            return build_info
        exit_pytest_execution(
            admin_client=admin_client,
            log_message=f"Version Explorer returned empty response for IIB {iib_number}.",
        )
    return {}


@pytest.fixture(scope="session")
def ocp_resources_submodule_list():
    """
    Gets the list of submodules in ocp_resources. This list is needed to make get and patch call to the right resource
    """
    path = importlib.util.find_spec("ocp_resources").submodule_search_locations
    return [module.name for module in pkgutil.iter_modules(path)]


@pytest.fixture(scope="session")
def cnv_registry_source(cnv_source):
    return py_config["cnv_registry_sources"][cnv_source]


@pytest.fixture()
def kubevirt_resource(admin_client, hco_namespace):
    return get_hyperconverged_kubevirt(admin_client=admin_client, hco_namespace=hco_namespace)


@pytest.fixture()
def cdi_resource_scope_function(admin_client):
    return get_hyperconverged_cdi(admin_client=admin_client)


@pytest.fixture()
def cdi_feature_gates(cdi_resource_scope_function):
    return cdi_resource_scope_function.instance.spec.config.get("featureGates")


@pytest.fixture()
def cnao_resource(admin_client):
    return get_network_addon_config(admin_client=admin_client)


@pytest.fixture()
def cnao_spec(cnao_resource):
    return cnao_resource.instance.to_dict()["spec"]


@pytest.fixture()
def updated_hco_cr(request, hyperconverged_resource_scope_function, admin_client, hco_namespace):
    """
    This fixture updates HCO CR with values specified via request.param
    """
    with ResourceEditorValidateHCOReconcile(
        patches={hyperconverged_resource_scope_function: request.param["patch"]},
        list_resource_reconcile=request.param.get("list_resource_reconcile", [NetworkAddonsConfig, CDI, KubeVirt]),
        wait_for_reconcile_post_update=True,
    ):
        yield


@pytest.fixture()
def updated_kubevirt_cr(request, kubevirt_resource, admin_client, hco_namespace):
    """
    Attempts to update kubevirt CR
    """
    with ResourceEditorValidateHCOReconcile(
        patches={kubevirt_resource: request.param["patch"]},
        list_resource_reconcile=[KubeVirt],
        wait_for_reconcile_post_update=True,
    ):
        yield


@pytest.fixture()
def ssp_cr_spec(ssp_resource_scope_function):
    return ssp_resource_scope_function.instance.to_dict()["spec"]


@pytest.fixture(scope="module")
def hco_spec_scope_module(hyperconverged_resource_scope_module):
    return hyperconverged_resource_scope_module.instance.to_dict()["spec"]


@pytest.fixture(scope="class")
def hco_version_scope_class(admin_client, hco_namespace):
    return get_hco_version(client=admin_client, hco_ns_name=hco_namespace.name)


@pytest.fixture()
def disabled_default_sources_in_operatorhub(admin_client, installing_cnv):
    if installing_cnv:
        yield
    else:
        with disable_default_sources_in_operatorhub(admin_client=admin_client):
            yield


@pytest.fixture(scope="session")
def cnv_image_url(pytestconfig):
    return pytestconfig.option.cnv_image


@pytest.fixture(scope="module")
def machine_config_pools_conditions_scope_module(machine_config_pools):
    return get_machine_config_pools_conditions(machine_config_pools=machine_config_pools)


@pytest.fixture()
def updated_resource(
    request,
    admin_client,
):
    cr_kind = request.param.get(RESOURCE_TYPE_STR)
    cr = get_resource_by_name(
        resource_kind=cr_kind,
        name=request.param.get(RESOURCE_NAME_STR),
        admin_client=admin_client,
        namespace=request.param.get(RESOURCE_NAMESPACE_STR),
    )
    with ResourceEditorValidateHCOReconcile(
        patches={cr: request.param["patch"]},
        action="replace",
        list_resource_reconcile=request.param.get("list_resource_reconcile", [cr_kind]),
        wait_for_reconcile_post_update=True,
    ):
        yield cr


@pytest.fixture(scope="session")
def jira_76659_open():
    return is_jira_open(jira_id="CNV-76659")

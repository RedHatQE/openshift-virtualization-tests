import logging
from copy import deepcopy

import pytest
from ocp_resources.network_addons_config import NetworkAddonsConfig

from utilities.constants import (
    CLUSTER_NETWORK_ADDONS_OPERATOR,
    NON_EXISTS_IMAGE,
)
from utilities.hco import ResourceEditorValidateHCOReconcile

LOGGER = logging.getLogger(__name__)


@pytest.fixture()
def bad_cnao_deployment_linux_bridge(csv_scope_function):
    linux_bridge_image = "LINUX_BRIDGE_IMAGE"
    csv_dict = deepcopy(csv_scope_function.instance.to_dict())
    for deployment in csv_dict["spec"]["install"]["spec"]["deployments"]:
        if deployment["name"] == CLUSTER_NETWORK_ADDONS_OPERATOR:
            deployment_env = deployment["spec"]["template"]["spec"]["containers"][0]["env"]
            for env in deployment_env:
                if env["name"] == linux_bridge_image:
                    LOGGER.info(f"Replacing {linux_bridge_image} {env['value']} with {NON_EXISTS_IMAGE}")
                    env["value"] = NON_EXISTS_IMAGE

    return csv_dict


@pytest.fixture()
def invalid_cnao_linux_bridge(bad_cnao_deployment_linux_bridge, csv_scope_function):
    with ResourceEditorValidateHCOReconcile(
        patches={csv_scope_function: bad_cnao_deployment_linux_bridge},
        list_resource_reconcile=[NetworkAddonsConfig],
    ):
        yield

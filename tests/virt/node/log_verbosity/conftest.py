import pytest
from ocp_resources.kubevirt import KubeVirt

from tests.virt.node.log_verbosity.constants import VIRT_LOG_VERBOSITY_LEVEL_6
from utilities.hco import ResourceEditorValidateHCOReconcile

# Predefined log verbosity configuration for level 6
LOG_VERBOSITY_LEVEL_6_CONFIG = {
    "component": {
        "kubevirt": {
            "virtHandler": VIRT_LOG_VERBOSITY_LEVEL_6,
            "virtController": VIRT_LOG_VERBOSITY_LEVEL_6,
            "virtAPI": VIRT_LOG_VERBOSITY_LEVEL_6,
            "virtLauncher": VIRT_LOG_VERBOSITY_LEVEL_6,
        }
    }
}


@pytest.fixture(scope="class")
def updated_log_verbosity_config(
    request,
    worker_node1,
    hyperconverged_resource_scope_class,
):
    """
    Fixture to update log verbosity configuration for KubeVirt components and nodes.
    Applies the configuration and yields control for test execution.
    """
    node_verbosity_config = {"node": {"kubevirt": {"nodeVerbosity": {worker_node1.name: VIRT_LOG_VERBOSITY_LEVEL_6}}}}

    # Merge component and node configs based on request.param
    config_map = {
        "component": LOG_VERBOSITY_LEVEL_6_CONFIG,
        "node": node_verbosity_config,
    }
    selected_config = config_map[request.param]

    with ResourceEditorValidateHCOReconcile(
        patches={hyperconverged_resource_scope_class: {"spec": {"logVerbosityConfig": selected_config}}},
        list_resource_reconcile=[KubeVirt],
        wait_for_reconcile_post_update=True,
    ):
        yield

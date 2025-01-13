import pytest
from ocp_resources.kubevirt import KubeVirt

from tests.virt.node.log_verbosity.constants import (
    VIRT_LOG_VERBOSITY_LEVEL_6,
)
from utilities.hco import ResourceEditorValidateHCOReconcile


@pytest.fixture(scope="class")
def updated_log_verbosity_config(
    request,
    worker_node1,
    hyperconverged_resource_scope_class,
):
    log_verbosity_level_six_config_dict = {
        "component": {
            "kubevirt": {
                "virtHandler": VIRT_LOG_VERBOSITY_LEVEL_6,
                "virtController": VIRT_LOG_VERBOSITY_LEVEL_6,
                "virtAPI": VIRT_LOG_VERBOSITY_LEVEL_6,
                "virtLauncher": VIRT_LOG_VERBOSITY_LEVEL_6,
            }
        },
        "node": {"kubevirt": {"nodeVerbosity": {worker_node1.name: VIRT_LOG_VERBOSITY_LEVEL_6}}},
    }
    with ResourceEditorValidateHCOReconcile(
        patches={
            hyperconverged_resource_scope_class: {
                "spec": {"logVerbosityConfig": log_verbosity_level_six_config_dict[request.param]}
            }
        },
        list_resource_reconcile=[KubeVirt],
        wait_for_reconcile_post_update=True,
    ):
        yield

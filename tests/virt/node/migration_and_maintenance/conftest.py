import pytest
from ocp_resources.kubevirt import KubeVirt

from tests.virt.node.log_verbosity.constants import (
    VIRT_LOG_VERBOSITY_LEVEL_6,
)
from utilities.hco import ResourceEditorValidateHCOReconcile


@pytest.fixture(scope="class")
def updated_multifd_vm_log_verbosity_config(
    hyperconverged_resource_scope_class,
):
    with ResourceEditorValidateHCOReconcile(
        patches={
            hyperconverged_resource_scope_class: {
                "spec": {
                    "logVerbosityConfig": {"component": {"kubevirt": {"virtLauncher": VIRT_LOG_VERBOSITY_LEVEL_6}}}
                }
            }
        },
        list_resource_reconcile=[KubeVirt],
        wait_for_reconcile_post_update=True,
    ):
        yield

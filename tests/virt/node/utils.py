from ocp_resources.kubevirt import KubeVirt

from utilities.hco import ResourceEditorValidateHCOReconcile


def update_log_verbosity_in_hco(hco, log_verbosity_config):
    return ResourceEditorValidateHCOReconcile(
        patches={hco: {"spec": {"logVerbosityConfig": log_verbosity_config}}},
        list_resource_reconcile=[KubeVirt],
        wait_for_reconcile_post_update=True,
    )

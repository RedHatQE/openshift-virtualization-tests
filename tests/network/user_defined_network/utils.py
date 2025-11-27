from contextlib import contextmanager

from ocp_resources.kubevirt import KubeVirt

from utilities.hco import ResourceEditorValidateHCOReconcile, wait_for_ds
from utilities.infra import get_daemonset_by_name
from utilities.virt import wait_for_updated_kv_value

PASST_BINDING_CNI = "passt-binding-cni"

@contextmanager
def register_passt_and_wait_for_sync(admin_client, hco_namespace, hco_resource):
    with ResourceEditorValidateHCOReconcile(
        patches={hco_resource: {"metadata": {"annotations": {"hco.kubevirt.io/deployPasstNetworkBinding": "true"}}}},
        list_resource_reconcile=[KubeVirt],
        wait_for_reconcile_post_update=True,
    ):
        wait_for_updated_kv_value(
            admin_client=admin_client,
            hco_namespace=hco_namespace,
            path=["network", "binding", "passt"],
            value=None,
            timeout=30,
            check_path_exists=True,
        )

        cni_ds = get_daemonset_by_name(
            admin_client=admin_client, daemonset_name=PASST_BINDING_CNI, namespace_name=hco_namespace.name
        )
        wait_for_ds(ds=cni_ds)
        yield
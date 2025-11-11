from typing import Generator

from kubernetes.dynamic import DynamicClient
from ocp_resources.hyperconverged import HyperConverged
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.namespace import Namespace
from ocp_resources.network_attachment_definition import NetworkAttachmentDefinition

from utilities.constants import VIRT_HANDLER
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.infra import get_daemonset_by_name
from utilities.virt import wait_for_virt_handler_pods_network_updated


def enable_feature_gate_and_configure_hco_live_migration_network(
    hyperconverged_resource: HyperConverged,
    client: DynamicClient,
    network_for_live_migration: NetworkAttachmentDefinition,
    hco_namespace: Namespace,
) -> Generator[None, None, None]:
    """
    Enable decentralized live migration feature gate and configure HCO live migration network.

    Args:
        hyperconverged_resource: The HyperConverged resource to patch
        client: The DynamicClient for the cluster
        network_for_live_migration: The NetworkAttachmentDefinition for live migration
        hco_namespace: The HCO namespace

    Yields:
        None
    """
    virt_handler_daemonset = get_daemonset_by_name(
        admin_client=client,
        daemonset_name=VIRT_HANDLER,
        namespace_name=hco_namespace.name,
    )

    with ResourceEditorValidateHCOReconcile(
        patches={
            hyperconverged_resource: {
                "spec": {
                    "featureGates": {"decentralizedLiveMigration": True},
                    "liveMigrationConfig": {"network": network_for_live_migration.name},
                }
            }
        },
        list_resource_reconcile=[KubeVirt],
        wait_for_reconcile_post_update=True,
        admin_client=client,
    ):
        wait_for_virt_handler_pods_network_updated(
            client=client,
            namespace=hco_namespace,
            network_name=network_for_live_migration.name,
            virt_handler_daemonset=virt_handler_daemonset,
        )
        yield

    wait_for_virt_handler_pods_network_updated(
        client=client,
        namespace=hco_namespace,
        network_name=network_for_live_migration.name,
        virt_handler_daemonset=virt_handler_daemonset,
        migration_network=False,
    )

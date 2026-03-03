import logging
from typing import Generator

from kubernetes.dynamic import DynamicClient
from ocp_resources.hyperconverged import HyperConverged
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.namespace import Namespace
from ocp_resources.network_attachment_definition import NetworkAttachmentDefinition

from utilities.constants import VIRT_HANDLER
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.infra import get_daemonset_by_name
from utilities.virt import VirtualMachineForTests, migrate_vm_and_verify, wait_for_virt_handler_pods_network_updated

LOGGER = logging.getLogger(__name__)


def enable_feature_gate_and_configure_hco_live_migration_network(
    hyperconverged_resource: HyperConverged,
    client: DynamicClient,
    hco_namespace: Namespace,
    network_for_live_migration: NetworkAttachmentDefinition | None = None,
) -> Generator[None, None, None]:
    """
    Enable decentralized live migration feature gate and optionally configure HCO live migration network.

    Args:
        hyperconverged_resource: The HyperConverged resource to patch
        client: The DynamicClient for the cluster
        hco_namespace: The HCO namespace
        network_for_live_migration: The NetworkAttachmentDefinition for live migration,
            or None to skip network configuration

    Yields:
        None
    """
    spec_patch = {"featureGates": {"decentralizedLiveMigration": True}}

    # Only configure network if provided
    virt_handler_daemonset = None
    if network_for_live_migration:
        LOGGER.info("Adding live migration network configuration to HCO spec patch")
        spec_patch["liveMigrationConfig"] = {"network": network_for_live_migration.name}

        virt_handler_daemonset = get_daemonset_by_name(
            admin_client=client,
            daemonset_name=VIRT_HANDLER,
            namespace_name=hco_namespace.name,
        )

    with ResourceEditorValidateHCOReconcile(
        patches={hyperconverged_resource: {"spec": spec_patch}},
        list_resource_reconcile=[KubeVirt],
        wait_for_reconcile_post_update=True,
        admin_client=client,
    ):
        if network_for_live_migration and virt_handler_daemonset:
            wait_for_virt_handler_pods_network_updated(
                client=client,
                namespace=hco_namespace,
                network_name=network_for_live_migration.name,
                virt_handler_daemonset=virt_handler_daemonset,
            )
        yield

    if network_for_live_migration and virt_handler_daemonset:
        wait_for_virt_handler_pods_network_updated(
            client=client,
            namespace=hco_namespace,
            network_name=network_for_live_migration.name,
            virt_handler_daemonset=virt_handler_daemonset,
            migration_network=False,
        )


def verify_compute_live_migration_after_cclm(
    client: DynamicClient, namespace: Namespace, vms_list: list[VirtualMachineForTests]
) -> None:
    """
    Verify compute live migration for VMs after Cross-Cluster Live Migration (CCLM).

    This function creates local VM references for each VM that was migrated from the remote cluster,
    preserves their credentials, and attempts to perform compute live migration on each VM.

    Args:
        client: DynamicClient
        namespace: The namespace where the VMs are located in the target cluster
        vms_list: List of VirtualMachineForTests objects to be migrated

    Raises:
        AssertionError: If any VM migration fails, with details of all failed migrations
    """
    vms_failed_migration = {}
    for vm in vms_list:
        local_vm = VirtualMachineForTests(
            name=vm.name, namespace=namespace.name, client=client, generate_unique_name=False
        )
        local_vm.username = vm.username
        local_vm.password = vm.password
        try:
            migrate_vm_and_verify(vm=local_vm, check_ssh_connectivity=True)
        except Exception as migration_exception:
            vms_failed_migration[local_vm.name] = migration_exception
    assert not vms_failed_migration, f"Failed VM migrations: {vms_failed_migration}"

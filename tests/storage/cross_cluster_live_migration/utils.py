import logging
import re
from typing import Generator

from kubernetes.dynamic import DynamicClient
from ocp_resources.hyperconverged import HyperConverged
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.namespace import Namespace
from ocp_resources.network_attachment_definition import NetworkAttachmentDefinition

from utilities import console
from utilities.constants import VIRT_HANDLER
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.infra import get_daemonset_by_name
from utilities.virt import (
    VirtualMachineForTests,
    migrate_vm_and_verify,
    wait_for_virt_handler_pods_network_updated,
)

LOGGER = logging.getLogger(__name__)


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


def get_vm_boot_time_via_console(
    vm: VirtualMachineForTests, kubeconfig: str | None = None, username: str | None = None, password: str | None = None
) -> str:
    """
    Returns the boot time string, e.g., "system boot  2026-01-08 11:17"
    """
    with console.Console(vm=vm, kubeconfig=kubeconfig, username=username, password=password) as vm_console:
        vm_console.sendline("who -b")

        # Wait for the prompt to return
        vm_console.expect([r"#", r"\$"])
        raw_output = vm_console.before

        # Decode if bytes
        if isinstance(raw_output, bytes):
            output = raw_output.decode("utf-8", errors="ignore")
        else:
            output = str(raw_output)

        # Remove ANSI escape sequences and control characters
        output = re.sub(r"\x1b\[\?[0-9]+[hl]", "", output)  # Remove bracketed paste mode
        output = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", output)  # Remove ANSI sequences
        output = output.replace("\r", "")  # Remove carriage returns

        lines = output.strip().split("\n")
        for line in lines:
            if "system boot" in line:
                # Extract and return just the date/time part
                # Format: "         system boot  2026-01-08 11:17"
                boot_info = line.strip()
                # Remove extra spaces
                boot_info = re.sub(r"\s+", " ", boot_info)
                LOGGER.info(f"Boot time: {boot_info}")
                return boot_info

        raise ValueError(f"Could not determine boot time from output: {raw_output}")


def verify_vms_boot_time_after_migration(
    client: DynamicClient,
    namespace: Namespace,
    vms_list: list[VirtualMachineForTests],
    initial_boot_time: dict[str, str],
) -> None:
    """
    Verify that VMs have not rebooted after storage migration.

    Args:
        vms_list: List of VMs to check
        initial_boot_time: Dictionary mapping VM names to their initial boot times

    Raises:
        AssertionError: If any VM has rebooted (boot time changed)
    """
    rebooted_vms = {}
    for vm in vms_list:
        local_vm = VirtualMachineForTests(
            name=vm.name, namespace=namespace.name, client=client, generate_unique_name=False
        )
        # local_vm.username = vm.username
        # local_vm.password = vm.password
        current_boot_time = get_vm_boot_time_via_console(vm=local_vm, username=vm.username, password=vm.password)
        if initial_boot_time[local_vm.name] != current_boot_time:
            rebooted_vms[local_vm.name] = {"initial": initial_boot_time[local_vm.name], "current": current_boot_time}
    assert not rebooted_vms, f"Boot time changed for VMs:\n {rebooted_vms}"

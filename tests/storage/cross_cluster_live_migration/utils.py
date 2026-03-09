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


def verify_compute_live_migration_after_cclm(local_vms: list[VirtualMachineForTests]) -> None:
    """
    Verify compute live migration for VMs after Cross-Cluster Live Migration (CCLM).

    Args:
        local_vms: List of VirtualMachineForTests objects in the local cluster

    Raises:
        AssertionError: If any VM migration fails, with details of all failed migrations
    """
    vms_failed_migration = {}
    for vm in local_vms:
        try:
            migrate_vm_and_verify(vm=vm, check_ssh_connectivity=True)
        except Exception as migration_exception:
            vms_failed_migration[vm.name] = migration_exception
    assert not vms_failed_migration, f"Failed VM migrations: {vms_failed_migration}"


def parse_boot_time_from_console_output(raw_output: str | bytes) -> str:
    """
    Parse system boot time from console output.

    Args:
        raw_output: Raw console output

    Returns:
        Cleaned boot time string, e.g., "system boot  2026-01-08 11:17"

    Raises:
        ValueError: If boot time cannot be determined from output
    """
    if isinstance(raw_output, bytes):
        output = raw_output.decode("utf-8", errors="ignore")
    else:
        output = str(raw_output)

    # Matches "system boot" followed by date/time in format "2026-01-08 11:17"
    match = re.search(r"(system boot\s+\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})", output)
    if match:
        boot_time = match.group(1)
        LOGGER.info(f"Boot time: '{boot_time}'")
        return boot_time
    raise ValueError(f"Could not determine boot time from output: {output}")


def get_vm_boot_time_via_console(
    vm: VirtualMachineForTests, kubeconfig: str | None = None, username: str | None = None, password: str | None = None
) -> str:
    """
    Returns the boot time string, e.g., "system boot 2026-01-08 11:17"
    """
    with console.Console(vm=vm, kubeconfig=kubeconfig, username=username, password=password) as vm_console:
        vm_console.sendline("who -b")
        vm_console.expect([r"#", r"\$"])
        raw_output = vm_console.before
        return parse_boot_time_from_console_output(raw_output=raw_output)


def verify_vms_boot_time_after_migration(
    local_vms: list[VirtualMachineForTests],
    initial_boot_time: dict[str, str],
) -> None:
    """
    Verify that VMs have not rebooted after storage migration.

    Args:
        local_vms: List of VirtualMachineForTests objects in the local cluster
        initial_boot_time: Dictionary mapping VM names to their initial boot times

    Raises:
        AssertionError: If any VM has rebooted (boot time changed)
    """
    rebooted_vms = {}
    for vm in local_vms:
        current_boot_time = get_vm_boot_time_via_console(vm=vm, username=vm.username, password=vm.password)
        if initial_boot_time[vm.name] != current_boot_time:
            rebooted_vms[vm.name] = {"initial": initial_boot_time[vm.name], "current": current_boot_time}
    assert not rebooted_vms, f"Boot time changed for VMs:\n {rebooted_vms}"


def assert_vms_are_stopped(vms: list[VirtualMachineForTests]) -> None:
    not_stopped_vms = {}
    for vm in vms:
        vm_status = vm.printable_status
        if vm_status != vm.Status.STOPPED:
            not_stopped_vms[vm.name] = vm_status
    assert not not_stopped_vms, f"Source VMs are not stopped: {not_stopped_vms}"


def assert_vms_can_be_deleted(vms: list[VirtualMachineForTests]) -> None:
    vms_failed_cleanup = {}
    for vm in vms:
        try:
            assert vm.clean_up(), f"Failed to clean up source VM {vm.name}"
        except Exception as cleanup_exception:
            vms_failed_cleanup[vm.name] = cleanup_exception
    assert not vms_failed_cleanup, f"Failed to clean up source VMs: {vms_failed_cleanup}"

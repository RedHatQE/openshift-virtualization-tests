import logging
from collections.abc import Generator

from kubernetes.dynamic import DynamicClient
from ocp_resources.hyperconverged import HyperConverged
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.namespace import Namespace
from ocp_resources.network_attachment_definition import NetworkAttachmentDefinition
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from utilities import console
from utilities.constants import TIMEOUT_3MIN, TIMEOUT_5SEC, VIRT_HANDLER
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.infra import get_daemonset_by_name
from utilities.virt import VirtualMachineForTests, migrate_vm_and_verify, wait_for_virt_handler_pods_network_updated

LOGGER = logging.getLogger(__name__)


def configure_hco_live_migration_network(
    hyperconverged_resource: HyperConverged,
    client: DynamicClient,
    hco_namespace: Namespace,
    network_for_live_migration: NetworkAttachmentDefinition | None = None,
) -> Generator[None]:
    """
    Configure HCO live migration network.

    Args:
        hyperconverged_resource: The HyperConverged resource to patch
        client: The DynamicClient for the cluster
        hco_namespace: The HCO namespace
        network_for_live_migration: The NetworkAttachmentDefinition for live migration,
            or None to skip network configuration

    Yields:
        None
    """
    # Only configure network if provided
    if not network_for_live_migration:
        LOGGER.info("No live migration network provided; skipping HCO network configuration")
        yield
        return

    LOGGER.info("Adding live migration network configuration to HCO spec patch")
    spec_patch = {"liveMigrationConfig": {"network": network_for_live_migration.name}}

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


def get_vm_boot_id_via_console(
    vm: VirtualMachineForTests, kubeconfig: str | None = None, username: str | None = None, password: str | None = None
) -> str:
    with console.Console(vm=vm, kubeconfig=kubeconfig, username=username, password=password) as vm_console:
        vm_console.sendline("cat /proc/sys/kernel/random/boot_id")
        vm_console.expect([r"#", r"\$"])
        raw_output = vm_console.before
        LOGGER.info(f"Boot ID from VM console (raw output): '{raw_output}'")
        return raw_output


def verify_vms_boot_id_after_cross_cluster_live_migration(
    local_vms: list[VirtualMachineForTests],
    initial_boot_id: dict[str, str],
) -> None:
    """
    Verify that VMs have not rebooted after cross-cluster live migration.

    Args:
        local_vms: List of VirtualMachineForTests objects in the local cluster
        initial_boot_id: Dictionary mapping VM names to their initial boot IDs

    Raises:
        AssertionError: If any VM has rebooted (boot ID changed)
    """
    rebooted_vms = {}
    for vm in local_vms:
        current_boot_id = get_vm_boot_id_via_console(vm=vm, username=vm.username, password=vm.password)
        if initial_boot_id[vm.name] != current_boot_id:
            rebooted_vms[vm.name] = {"initial": initial_boot_id[vm.name], "current": current_boot_id}
    assert not rebooted_vms, f"Boot id changed for VMs:\n {rebooted_vms}"


def get_not_stopped_vms(vms: list[VirtualMachineForTests]) -> dict[str, str]:
    not_stopped_vms = {}
    for vm in vms:
        vm_status = vm.printable_status
        if vm_status != vm.Status.STOPPED:
            not_stopped_vms[vm.name] = vm_status
    if not_stopped_vms:
        LOGGER.info(f"VMs are not stopped: {not_stopped_vms}")
    return not_stopped_vms


def assert_vms_are_stopped(vms: list[VirtualMachineForTests]) -> None:
    not_stopped_vms = get_not_stopped_vms(vms=vms)
    assert not not_stopped_vms, f"VMs are not stopped: {not_stopped_vms}"


def wait_for_vms_to_be_stopped(vms: list[VirtualMachineForTests]) -> None:
    LOGGER.info("Waiting for VMs to stop")
    not_stopped_vms = {}
    try:
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_3MIN,
            sleep=TIMEOUT_5SEC,
            func=get_not_stopped_vms,
            vms=vms,
        ):
            not_stopped_vms = sample
            if not not_stopped_vms:
                LOGGER.info("All VMs are stopped")
                return
            LOGGER.info(f"Waiting for VMs to stop: {not_stopped_vms}")
    except TimeoutExpiredError:
        raise AssertionError(f"VMs did not stop within timeout: {not_stopped_vms}")


def assert_vms_can_be_deleted(vms: list[VirtualMachineForTests]) -> None:
    vms_failed_cleanup = {}
    for vm in vms:
        try:
            cleanup_result = vm.clean_up()
            if cleanup_result is not True:
                vms_failed_cleanup[vm.name] = f"vm.clean_up() returned {cleanup_result}"
        except Exception as cleanup_exception:
            vms_failed_cleanup[vm.name] = str(cleanup_exception)
    assert not vms_failed_cleanup, f"Failed to clean up source VMs: {vms_failed_cleanup}"

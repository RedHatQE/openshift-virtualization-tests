# -*- coding: utf-8 -*-

"""
Network Migration - masquerade connectivity after migration
"""

import logging

import pytest
from timeout_sampler import TimeoutSampler

from utilities.virt import (
    VirtualMachineForTests,
    fedora_vm_body,
    migrate_vm_and_verify,
    vm_console_run_commands,
)

LOGGER = logging.getLogger(__name__)


def ping_via_console(src_vm, dst_vm):
    """Ping between VMs via console.

    Pings from a source VM to a destination VM over the primary interface's IP.
    This method verifies console-based network connectivity by checking for a
    successful (zero) exit status of the ping command, avoiding SSH-related masking issues.

    Args:
        src_vm (VirtualMachineForTests | BaseVirtualMachine): Source virtual machine
            used to execute the ping.
        dst_vm (VirtualMachineForTests | BaseVirtualMachine): Destination virtual machine
            whose primary interface IP is pinged.

    Raises:
        CommandExecFailed: If the ping command fails, times out, or the
            console session ends unexpectedly.
    """
    dst_ip = dst_vm.vmi.interfaces[0]["ipAddress"]

    vm_console_run_commands(
        vm=src_vm,
        commands=[f"ping {dst_ip} -c 10 -w 10"],
        timeout=10,
    )


@pytest.fixture(scope="module")
def running_vm_static(
    unprivileged_client,
    namespace,
):
    name = "vm-static"
    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        body=fedora_vm_body(name=name),
        client=unprivileged_client,
    ) as vm:
        vm.start(wait=True)
        vm.wait_for_agent_connected()
        yield vm


@pytest.fixture(scope="module")
def running_vm_for_migration(
    unprivileged_client,
    cpu_for_migration,
    namespace,
):
    name = "vm-for-migration"
    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        body=fedora_vm_body(name=name),
        client=unprivileged_client,
        cpu_model=cpu_for_migration,
    ) as vm:
        vm.start(wait=True)
        vm.wait_for_agent_connected()
        yield vm


@pytest.fixture()
def migrated_vmi(running_vm_for_migration):
    LOGGER.info(f"Migrating {running_vm_for_migration.name}. Current node: {running_vm_for_migration.vmi.node.name}")

    ip_before = running_vm_for_migration.vmi.interfaces[0]["ipAddress"]
    migrated_vmi = migrate_vm_and_verify(vm=running_vm_for_migration, wait_for_migration_success=False)

    for sample in TimeoutSampler(
        wait_timeout=60,
        sleep=1,
        func=lambda: ip_before != running_vm_for_migration.vmi.interfaces[0]["ipAddress"],
    ):
        if sample:
            break

    yield
    migrated_vmi.clean_up()


@pytest.mark.gating
@pytest.mark.polarion("CNV-6733")
@pytest.mark.s390x
@pytest.mark.single_nic
def test_connectivity_after_migration(
    namespace,
    running_vm_static,
    running_vm_for_migration,
    migrated_vmi,
):
    """
    Validate connectivity after migrating a VM that uses masquerade.
    - Uses the VM console (not SSH) to ping from the migrated VM to a static VM to avoid masking issues.
    - Once the VM IP changes and console connectivity is available, run ping immediately to catch
      short‑lived post‑migration connectivity gaps.
    """
    LOGGER.info(f"Pinging from migrated {running_vm_for_migration.name} to {running_vm_static.name}")

    ping_via_console(src_vm=running_vm_for_migration, dst_vm=running_vm_static)

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
    wait_for_console,
)

LOGGER = logging.getLogger(__name__)


def ping_via_console(src_vm, dst_vm):
    """
    Ping from src_vm to dst_vm via VM console to avoid SSH masking issues.
    Uses '-c 10 -w 10' so that any packet loss causes a non‑zero exit status.
    """
    dst_ip = dst_vm.vmi.interfaces[0]["ipAddress"]
    console_command_timeout_seconds = 10

    vm_console_run_commands(
        vm=src_vm,
        commands=[f"ping {dst_ip} -c 10 -w 10"],
        timeout=console_command_timeout_seconds,
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


@pytest.fixture(scope="module")
def vm_console_connection_ready(running_vm_for_migration):
    wait_for_console(
        vm=running_vm_for_migration,
    )


@pytest.fixture()
def inter_vm_connectivity_exists(
    running_vm_static,
    running_vm_for_migration,
    vm_console_connection_ready,
):
    ping_via_console(src_vm=running_vm_for_migration, dst_vm=running_vm_static)


@pytest.fixture()
def migrated_vmi(
    running_vm_for_migration,
    inter_vm_connectivity_exists,
):
    LOGGER.info(f"Migrating {running_vm_for_migration.name}. Current node: {running_vm_for_migration.vmi.node.name}")

    ip_before = running_vm_for_migration.vmi.interfaces[0]["ipAddress"]
    migrated_vmi = migrate_vm_and_verify(vm=running_vm_for_migration, wait_for_migration_success=False)
    ip_change_timeout_seconds = 60

    for sample in TimeoutSampler(
        wait_timeout=ip_change_timeout_seconds,
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
    vm_console_connection_ready,
):
    """
    Validate connectivity after migrating a VM that uses masquerade.

    - Uses the VM console (not SSH) to ping from the migrated VM to a static VM to avoid masking issues.
    - Run the ping right after the VM migration (once the VM IP changes) to detect a bug that appears
      only immediately after migration; waiting may hide it.
    """
    LOGGER.info(f"Pinging from migrated {running_vm_for_migration.name} to {running_vm_static.name}")
    ping_via_console(src_vm=running_vm_for_migration, dst_vm=running_vm_static)

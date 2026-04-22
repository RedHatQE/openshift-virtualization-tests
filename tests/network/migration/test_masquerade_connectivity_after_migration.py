import logging

import pytest
from timeout_sampler import TimeoutSampler

from libs.net.vmspec import lookup_iface_status
from tests.network.libs.connectivity import build_ping_command
from utilities.virt import (
    VirtualMachineForTests,
    fedora_vm_body,
    migrate_vm_and_verify,
    vm_console_run_commands,
    wait_for_console,
)

LOGGER = logging.getLogger(__name__)


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

    iface_name = running_vm_for_migration.vmi.interfaces[0].name
    ip_addresses_before = lookup_iface_status(vm=running_vm_for_migration, iface_name=iface_name)["ipAddresses"]
    migrated_vmi = migrate_vm_and_verify(vm=running_vm_for_migration, wait_for_migration_success=False)

    for sample in TimeoutSampler(
        wait_timeout=60,
        sleep=1,
        func=lambda: (
            ip_addresses_before
            != lookup_iface_status(vm=running_vm_for_migration, iface_name=iface_name)["ipAddresses"]
        ),
    ):
        if sample:
            break

    yield
    migrated_vmi.clean_up()


@pytest.fixture(scope="module")
def vm_console_connection_ready(running_vm_for_migration):
    wait_for_console(
        vm=running_vm_for_migration,
    )


@pytest.mark.gating
@pytest.mark.polarion("CNV-6733")
@pytest.mark.s390x
@pytest.mark.single_nic
# conformance candidate
def test_connectivity_after_migration(
    subtests,
    namespace,
    running_vm_static,
    running_vm_for_migration,
    migrated_vmi,
    vm_console_connection_ready,
):
    """
    test for connectivity of a migrated vm with masquerade.
    Tests all available IP families (IPv4 and IPv6 if configured).
    Using console to ping from migrated_vmi to running_vm_static.
    It is important to connect using console and not ssh because connecting
    through ssh hides the bug.
    The ping should take place right after running_vm_for_migration is migrated to
    the new node.
    the ping command include '-c 10 -w 10' so that in case there is a packet
    loss the exit code will be 1 and not 0.
    """
    target_vm_iface_name = running_vm_static.vmi.interfaces[0].name
    target_vm_ip_addresses = lookup_iface_status(vm=running_vm_static, iface_name=target_vm_iface_name)["ipAddresses"]
    for target_vm_ip in target_vm_ip_addresses:
        with subtests.test(
            msg=f"Testing connectivity from migrated {running_vm_for_migration.name} "
            f"to {running_vm_static.name} IP address: {target_vm_ip}"
        ):
            vm_console_run_commands(
                vm=running_vm_for_migration,
                commands=[build_ping_command(dst_ip=target_vm_ip, count=10, timeout=10)],
                timeout=20,
            )

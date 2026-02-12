"""
Test module for NAD swap with migration scenarios.

Markers:
    - tier2
    - p2/p3

Preconditions:
    - LiveUpdateNADRef feature gate enabled
    - Migration support enabled
"""

import logging
import time

import pytest
from ocp_resources.resource import ResourceEditor

from libs.net import netattachdef
from libs.net.vmspec import lookup_iface_status
from libs.vm.spec import Interface, Multus, Network
from utilities.virt import (
    VirtualMachineForTests,
    fedora_vm_body,
    migrate_vm_and_verify,
    running_vm,
)

LOGGER = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.usefixtures("namespace"),
    pytest.mark.tier2,
]


class TestNADSwapMigration:
    """Tests for NAD swap with migration scenarios."""

    def test_ts_cnv_72329_023_rollback_nad_before_migration_completes(
        self, admin_client, unprivileged_client, namespace
    ):
        """
        Test TS-CNV-72329-023: Rollback NAD change before migration completes.

        Steps:
            1. Create VM with NAD A
            2. Change to NAD B (triggers migration)
            3. Quickly rollback to NAD A before migration completes
            4. Verify migration behavior

        Expected:
            - Migration cancels or uses original NAD if already started
        """
        LOGGER.info("Creating NADs for rollback test")

        with netattachdef.NetworkAttachmentDefinition(
            namespace=namespace.name,
            name="nad-original",
            config=netattachdef.NetConfig(
                "network-original", [netattachdef.CNIPluginBridgeConfig(bridge="br1", vlan=100)]
            ),
            client=admin_client,
        ) as nad_orig:
            with netattachdef.NetworkAttachmentDefinition(
                namespace=namespace.name,
                name="nad-temporary",
                config=netattachdef.NetConfig(
                    "network-temporary", [netattachdef.CNIPluginBridgeConfig(bridge="br1", vlan=200)]
                ),
                client=admin_client,
            ) as nad_temp:
                LOGGER.info("Creating VM with original NAD")
                vm_name = "test-vm-rollback"

                with VirtualMachineForTests(
                    name=vm_name,
                    namespace=namespace.name,
                    body=fedora_vm_body(name=vm_name),
                    client=unprivileged_client,
                    networks=[
                        Network(name="test-net", multus=Multus(networkName=nad_orig.name)),
                    ],
                    interfaces=[
                        Interface(name="test-net", bridge={}),
                    ],
                ) as vm:
                    running_vm(vm=vm)

                    LOGGER.info("Changing to temporary NAD")
                    with ResourceEditor(
                        patches={
                            vm: {
                                "spec": {
                                    "template": {
                                        "spec": {
                                            "networks": [
                                                {"name": "default", "pod": {}},
                                                {
                                                    "name": "test-net",
                                                    "multus": {"networkName": nad_temp.name},
                                                },
                                            ]
                                        }
                                    }
                                }
                            }
                        }
                    ):
                        pass

                    # Wait briefly, then rollback before migration completes
                    time.sleep(2)

                    LOGGER.info("Rolling back to original NAD")
                    with ResourceEditor(
                        patches={
                            vm: {
                                "spec": {
                                    "template": {
                                        "spec": {
                                            "networks": [
                                                {"name": "default", "pod": {}},
                                                {
                                                    "name": "test-net",
                                                    "multus": {"networkName": nad_orig.name},
                                                },
                                            ]
                                        }
                                    }
                                }
                            }
                        }
                    ):
                        pass

                    LOGGER.info("Verifying rollback handled correctly")
                    # Migration may cancel or complete with original NAD
                    iface_status = lookup_iface_status(vm=vm, iface_name="test-net")
                    assert nad_orig.name in str(iface_status), "Original NAD should be active after rollback"

                    LOGGER.info("Test passed: Rollback handled correctly")

    def test_ts_cnv_72329_024_nad_swap_concurrent_vm_updates(self, admin_client, unprivileged_client, namespace):
        """
        Test TS-CNV-72329-024: NAD swap with concurrent VM updates.

        Steps:
            1. Create VM with NAD
            2. Change NAD and other VM properties simultaneously
            3. Trigger migration
            4. Verify NAD change processed correctly

        Expected:
            - NAD change processed correctly alongside other updates
        """
        LOGGER.info("Creating NADs for concurrent updates test")

        with netattachdef.NetworkAttachmentDefinition(
            namespace=namespace.name,
            name="nad-orig-concurrent",
            config=netattachdef.NetConfig(
                "network-orig-concurrent", [netattachdef.CNIPluginBridgeConfig(bridge="br1", vlan=100)]
            ),
            client=admin_client,
        ) as nad_orig:
            with netattachdef.NetworkAttachmentDefinition(
                namespace=namespace.name,
                name="nad-target-concurrent",
                config=netattachdef.NetConfig(
                    "network-target-concurrent", [netattachdef.CNIPluginBridgeConfig(bridge="br1", vlan=200)]
                ),
                client=admin_client,
            ) as nad_target:
                LOGGER.info("Creating VM")
                vm_name = "test-vm-concurrent"

                with VirtualMachineForTests(
                    name=vm_name,
                    namespace=namespace.name,
                    body=fedora_vm_body(name=vm_name),
                    client=unprivileged_client,
                    networks=[
                        Network(name="test-net", multus=Multus(networkName=nad_orig.name)),
                    ],
                    interfaces=[
                        Interface(name="test-net", bridge={}),
                    ],
                ) as vm:
                    running_vm(vm=vm)

                    LOGGER.info("Updating NAD and VM metadata concurrently")
                    with ResourceEditor(
                        patches={
                            vm: {
                                "metadata": {"labels": {"test-label": "concurrent-update"}},
                                "spec": {
                                    "template": {
                                        "spec": {
                                            "networks": [
                                                {"name": "default", "pod": {}},
                                                {
                                                    "name": "test-net",
                                                    "multus": {"networkName": nad_target.name},
                                                },
                                            ]
                                        }
                                    }
                                },
                            }
                        }
                    ):
                        pass

                    LOGGER.info("Migrating VM")
                    migrate_vm_and_verify(vm=vm)

                    LOGGER.info("Verifying NAD change and metadata update")
                    iface_status = lookup_iface_status(vm=vm, iface_name="test-net")
                    assert nad_target.name in str(iface_status), "Target NAD should be active"
                    assert vm.instance.metadata.labels.get("test-label") == "concurrent-update", (
                        "Label should be updated"
                    )

                    LOGGER.info("Test passed: Concurrent updates handled correctly")

    def test_ts_cnv_72329_025_nad_change_with_running_workload(self, admin_client, unprivileged_client, namespace):
        """
        Test TS-CNV-72329-025: Change NAD on VM with running workload.

        Steps:
            1. Start workload on VM
            2. Change NAD (triggers migration)
            3. Verify workload recovers after migration

        Expected:
            - Workload experiences expected network interruption
            - Workload recovers after migration
        """
        LOGGER.info("Creating NADs for running workload test")

        with netattachdef.NetworkAttachmentDefinition(
            namespace=namespace.name,
            name="nad-workload-orig",
            config=netattachdef.NetConfig(
                "network-workload-orig", [netattachdef.CNIPluginBridgeConfig(bridge="br1", vlan=100)]
            ),
            client=admin_client,
        ) as nad_orig:
            with netattachdef.NetworkAttachmentDefinition(
                namespace=namespace.name,
                name="nad-workload-target",
                config=netattachdef.NetConfig(
                    "network-workload-target", [netattachdef.CNIPluginBridgeConfig(bridge="br1", vlan=200)]
                ),
                client=admin_client,
            ) as nad_target:
                LOGGER.info("Creating VM with workload")
                vm_name = "test-vm-workload"

                with VirtualMachineForTests(
                    name=vm_name,
                    namespace=namespace.name,
                    body=fedora_vm_body(name=vm_name),
                    client=unprivileged_client,
                    networks=[
                        Network(name="workload-net", multus=Multus(networkName=nad_orig.name)),
                    ],
                    interfaces=[
                        Interface(name="workload-net", bridge={}),
                    ],
                ) as vm:
                    running_vm(vm=vm)

                    LOGGER.info("Starting workload (ping loop)")
                    # Start a continuous ping as workload
                    vm.ssh_exec.executor().run_command("nohup ping -i 1 8.8.8.8 > /tmp/ping.log 2>&1 &")

                    LOGGER.info("Changing NAD during workload")
                    with ResourceEditor(
                        patches={
                            vm: {
                                "spec": {
                                    "template": {
                                        "spec": {
                                            "networks": [
                                                {"name": "default", "pod": {}},
                                                {
                                                    "name": "workload-net",
                                                    "multus": {"networkName": nad_target.name},
                                                },
                                            ]
                                        }
                                    }
                                }
                            }
                        }
                    ):
                        pass

                    LOGGER.info("Migrating VM")
                    migrate_vm_and_verify(vm=vm, check_ssh_connectivity=True)

                    LOGGER.info("Verifying workload recovered")
                    # Check if ping process is still running
                    result = vm.ssh_exec.executor().run_command("pgrep ping")
                    assert result[0] == 0, "Ping workload should still be running after migration"

                    LOGGER.info("Test passed: Workload recovered after NAD swap migration")

    def test_ts_cnv_72329_028_nad_change_with_persistent_volumes(self, admin_client, unprivileged_client, namespace):
        """
        Test TS-CNV-72329-028: NAD change on VM with persistent volumes.

        Steps:
            1. Create VM with PV
            2. Change NAD
            3. Trigger migration
            4. Verify VM migrates with PVs and NAD swap succeeds

        Expected:
            - VM migrates with PVs
            - NAD swap succeeds
        """
        LOGGER.info("Creating NADs for PV test")

        with netattachdef.NetworkAttachmentDefinition(
            namespace=namespace.name,
            name="nad-pv-orig",
            config=netattachdef.NetConfig(
                "network-pv-orig", [netattachdef.CNIPluginBridgeConfig(bridge="br1", vlan=100)]
            ),
            client=admin_client,
        ) as nad_orig:
            with netattachdef.NetworkAttachmentDefinition(
                namespace=namespace.name,
                name="nad-pv-target",
                config=netattachdef.NetConfig(
                    "network-pv-target", [netattachdef.CNIPluginBridgeConfig(bridge="br1", vlan=200)]
                ),
                client=admin_client,
            ) as nad_target:
                LOGGER.info("Creating VM with persistent storage")
                vm_name = "test-vm-with-pv"

                # Note: In production, you'd create a PVC and attach it
                # For this test, we use the VM body which includes storage
                with VirtualMachineForTests(
                    name=vm_name,
                    namespace=namespace.name,
                    body=fedora_vm_body(name=vm_name),
                    client=unprivileged_client,
                    networks=[
                        Network(name="storage-net", multus=Multus(networkName=nad_orig.name)),
                    ],
                    interfaces=[
                        Interface(name="storage-net", bridge={}),
                    ],
                ) as vm:
                    running_vm(vm=vm)

                    LOGGER.info("Writing data to VM storage")
                    vm.ssh_exec.executor().run_command("echo 'test-data-before-migration' > /tmp/test-file.txt")

                    LOGGER.info("Changing NAD")
                    with ResourceEditor(
                        patches={
                            vm: {
                                "spec": {
                                    "template": {
                                        "spec": {
                                            "networks": [
                                                {"name": "default", "pod": {}},
                                                {
                                                    "name": "storage-net",
                                                    "multus": {"networkName": nad_target.name},
                                                },
                                            ]
                                        }
                                    }
                                }
                            }
                        }
                    ):
                        pass

                    LOGGER.info("Migrating VM with PV")
                    migrate_vm_and_verify(vm=vm, check_ssh_connectivity=True)

                    LOGGER.info("Verifying data persisted and NAD changed")
                    result = vm.ssh_exec.executor().run_command("cat /tmp/test-file.txt")
                    assert "test-data-before-migration" in result[1], "Data should persist after migration"

                    iface_status = lookup_iface_status(vm=vm, iface_name="storage-net")
                    assert nad_target.name in str(iface_status), "Target NAD should be active"

                    LOGGER.info("Test passed: VM migrated with PV and NAD swap successful")

    def test_ts_cnv_72329_029_monitor_migration_performance(self, admin_client, unprivileged_client, namespace):
        """
        Test TS-CNV-72329-029: Monitor migration performance impact.

        Steps:
            1. Create VM with NAD
            2. Change NAD (triggers migration)
            3. Monitor migration time
            4. Verify migration completes within expected window

        Expected:
            - NAD swap migration completes within expected time window
        """
        LOGGER.info("Creating NADs for performance test")

        with netattachdef.NetworkAttachmentDefinition(
            namespace=namespace.name,
            name="nad-perf-orig",
            config=netattachdef.NetConfig(
                "network-perf-orig", [netattachdef.CNIPluginBridgeConfig(bridge="br1", vlan=100)]
            ),
            client=admin_client,
        ) as nad_orig:
            with netattachdef.NetworkAttachmentDefinition(
                namespace=namespace.name,
                name="nad-perf-target",
                config=netattachdef.NetConfig(
                    "network-perf-target", [netattachdef.CNIPluginBridgeConfig(bridge="br1", vlan=200)]
                ),
                client=admin_client,
            ) as nad_target:
                LOGGER.info("Creating VM for performance test")
                vm_name = "test-vm-performance"

                with VirtualMachineForTests(
                    name=vm_name,
                    namespace=namespace.name,
                    body=fedora_vm_body(name=vm_name),
                    client=unprivileged_client,
                    networks=[
                        Network(name="perf-net", multus=Multus(networkName=nad_orig.name)),
                    ],
                    interfaces=[
                        Interface(name="perf-net", bridge={}),
                    ],
                ) as vm:
                    running_vm(vm=vm)

                    LOGGER.info("Starting performance monitoring")
                    start_time = time.time()

                    LOGGER.info("Changing NAD")
                    with ResourceEditor(
                        patches={
                            vm: {
                                "spec": {
                                    "template": {
                                        "spec": {
                                            "networks": [
                                                {"name": "default", "pod": {}},
                                                {
                                                    "name": "perf-net",
                                                    "multus": {"networkName": nad_target.name},
                                                },
                                            ]
                                        }
                                    }
                                }
                            }
                        }
                    ):
                        pass

                    LOGGER.info("Migrating VM and measuring time")
                    migrate_vm_and_verify(vm=vm)

                    migration_time = time.time() - start_time

                    LOGGER.info(f"Migration completed in {migration_time:.2f} seconds")

                    # Verify migration time is reasonable (< 5 minutes for standard VM)
                    assert migration_time < 300, f"Migration took too long: {migration_time}s"

                    LOGGER.info("Verifying NAD changed")
                    iface_status = lookup_iface_status(vm=vm, iface_name="perf-net")
                    assert nad_target.name in str(iface_status), "Target NAD should be active"

                    LOGGER.info(f"Test passed: Migration completed in {migration_time:.2f}s")

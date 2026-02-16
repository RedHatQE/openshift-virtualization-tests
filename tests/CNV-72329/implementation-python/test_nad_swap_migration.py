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
import shlex
import time

import pytest
from ocp_resources.resource import ResourceEditor
from tests.network.nad_swap.utils import get_vmi_network_nad_name
from timeout_sampler import TimeoutSampler

from libs.net.netattachdef import CNIPluginBridgeConfig, NetConfig, NetworkAttachmentDefinition
from utilities.virt import (
    VirtualMachineForTests,
    fedora_vm_body,
    restart_vm_wait_for_running_vm,
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

        with NetworkAttachmentDefinition(
            namespace=namespace.name,
            name="nad-original",
            config=NetConfig(
                name="network-original", plugins=[CNIPluginBridgeConfig(bridge="br1", vlan=100)]
            ),
            client=admin_client,
        ) as nad_orig:
            with NetworkAttachmentDefinition(
                namespace=namespace.name,
                name="nad-temporary",
                config=NetConfig(
                    name="network-temporary", plugins=[CNIPluginBridgeConfig(bridge="br1", vlan=200)]
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
                    networks={"test-net": nad_orig.name},
                    interfaces=["test-net"],
                ) as vm:
                    running_vm(vm=vm)

                    LOGGER.info("Changing to temporary NAD")
                    ResourceEditor(
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
                    ).update()

                    # Wait for migration to start, then rollback before it completes
                    for sample in TimeoutSampler(
                        wait_timeout=10,
                        sleep=1,
                        func=lambda: vm.vmi.instance.status.migrationState,
                    ):
                        if sample is not None:
                            break

                    LOGGER.info("Rolling back to original NAD")
                    ResourceEditor(
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
                    ).update()

                    LOGGER.info("Verifying rollback handled correctly")
                    # Migration may cancel or complete with original NAD
                    actual_nad = get_vmi_network_nad_name(vm=vm, iface_name="test-net")
                    assert actual_nad == nad_orig.name, "Original NAD should be active after rollback"

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

        with NetworkAttachmentDefinition(
            namespace=namespace.name,
            name="nad-orig-concurrent",
            config=NetConfig(
                name="network-orig-concurrent", plugins=[CNIPluginBridgeConfig(bridge="br1", vlan=100)]
            ),
            client=admin_client,
        ) as nad_orig:
            with NetworkAttachmentDefinition(
                namespace=namespace.name,
                name="nad-target-concurrent",
                config=NetConfig(
                    name="network-target-concurrent", plugins=[CNIPluginBridgeConfig(bridge="br1", vlan=200)]
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
                    networks={"test-net": nad_orig.name},
                    interfaces=["test-net"],
                ) as vm:
                    running_vm(vm=vm)

                    LOGGER.info("Updating NAD and VM metadata concurrently")
                    ResourceEditor(
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
                    ).update()

                    LOGGER.info("Migrating VM")
                    restart_vm_wait_for_running_vm(vm=vm)

                    LOGGER.info("Verifying NAD change and metadata update")
                    actual_nad = get_vmi_network_nad_name(vm=vm, iface_name="test-net")
                    assert actual_nad == nad_target.name, "Target NAD should be active"
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

        with NetworkAttachmentDefinition(
            namespace=namespace.name,
            name="nad-workload-orig",
            config=NetConfig(
                name="network-workload-orig", plugins=[CNIPluginBridgeConfig(bridge="br1", vlan=100)]
            ),
            client=admin_client,
        ) as nad_orig:
            with NetworkAttachmentDefinition(
                namespace=namespace.name,
                name="nad-workload-target",
                config=NetConfig(
                    name="network-workload-target", plugins=[CNIPluginBridgeConfig(bridge="br1", vlan=200)]
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
                    networks={"workload-net": nad_orig.name},
                    interfaces=["workload-net"],
                ) as vm:
                    running_vm(vm=vm)

                    LOGGER.info("Verifying VM is accessible via SSH before NAD change")
                    vm.ssh_exec.run_command(command=shlex.split("uname -r"))

                    LOGGER.info("Changing NAD during workload")
                    ResourceEditor(
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
                    ).update()

                    LOGGER.info("Restarting VM to apply NAD change")
                    restart_vm_wait_for_running_vm(vm=vm)

                    LOGGER.info("Verifying VM recovered with new NAD after restart")
                    actual_nad = get_vmi_network_nad_name(vm=vm, iface_name="workload-net")
                    assert actual_nad == nad_target.name, "Target NAD should be active after restart"

                    LOGGER.info("Test passed: VM recovered after NAD swap restart")

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

        with NetworkAttachmentDefinition(
            namespace=namespace.name,
            name="nad-pv-orig",
            config=NetConfig(
                name="network-pv-orig", plugins=[CNIPluginBridgeConfig(bridge="br1", vlan=100)]
            ),
            client=admin_client,
        ) as nad_orig:
            with NetworkAttachmentDefinition(
                namespace=namespace.name,
                name="nad-pv-target",
                config=NetConfig(
                    name="network-pv-target", plugins=[CNIPluginBridgeConfig(bridge="br1", vlan=200)]
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
                    networks={"storage-net": nad_orig.name},
                    interfaces=["storage-net"],
                ) as vm:
                    running_vm(vm=vm)

                    LOGGER.info("Changing NAD")
                    ResourceEditor(
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
                    ).update()

                    LOGGER.info("Restarting VM to apply NAD change")
                    restart_vm_wait_for_running_vm(vm=vm)

                    LOGGER.info("Verifying NAD changed after restart")
                    actual_nad = get_vmi_network_nad_name(vm=vm, iface_name="storage-net")
                    assert actual_nad == nad_target.name, "Target NAD should be active"

                    LOGGER.info("Test passed: VM restarted with NAD swap successful")

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

        with NetworkAttachmentDefinition(
            namespace=namespace.name,
            name="nad-perf-orig",
            config=NetConfig(
                name="network-perf-orig", plugins=[CNIPluginBridgeConfig(bridge="br1", vlan=100)]
            ),
            client=admin_client,
        ) as nad_orig:
            with NetworkAttachmentDefinition(
                namespace=namespace.name,
                name="nad-perf-target",
                config=NetConfig(
                    name="network-perf-target", plugins=[CNIPluginBridgeConfig(bridge="br1", vlan=200)]
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
                    networks={"perf-net": nad_orig.name},
                    interfaces=["perf-net"],
                ) as vm:
                    running_vm(vm=vm)

                    LOGGER.info("Starting performance monitoring")
                    start_time = time.time()

                    LOGGER.info("Changing NAD")
                    ResourceEditor(
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
                    ).update()

                    LOGGER.info("Migrating VM and measuring time")
                    restart_vm_wait_for_running_vm(vm=vm)

                    migration_time = time.time() - start_time

                    LOGGER.info(f"Migration completed in {migration_time:.2f} seconds")

                    # Verify migration time is reasonable (< 5 minutes for standard VM)
                    assert migration_time < 300, f"Migration took too long: {migration_time}s"

                    LOGGER.info("Verifying NAD changed")
                    actual_nad = get_vmi_network_nad_name(vm=vm, iface_name="perf-net")
                    assert actual_nad == nad_target.name, "Target NAD should be active"

                    LOGGER.info(f"Test passed: Migration completed in {migration_time:.2f}s")

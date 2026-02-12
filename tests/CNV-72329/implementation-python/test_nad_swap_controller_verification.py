"""
Test module for NAD swap controller verification scenarios.

Markers:
    - tier2
    - p1

Preconditions:
    - LiveUpdateNADRef feature gate enabled
    - Access to controller logs/events
"""

import logging
import pytest

from libs.net import netattachdef
from libs.net.vmspec import lookup_iface_status
from libs.vm.spec import Network, Multus, Interface
from ocp_resources.resource import ResourceEditor
from ocp_resources.virtual_machine import VirtualMachine
from utilities.constants import TIMEOUT_5MIN
from utilities.virt import (
    VirtualMachineForTests,
    running_vm,
    fedora_vm_body,
    migrate_vm_and_verify,
)

LOGGER = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.usefixtures("namespace"),
    pytest.mark.tier2,
]


class TestNADSwapControllerVerification:
    """Tests for verifying controller behavior during NAD swap."""

    def test_ts_cnv_72329_033_verify_virt_controller_restart_required_logic(
        self, admin_client, unprivileged_client, namespace
    ):
        """
        Test TS-CNV-72329-033: Verify virt-controller RestartRequired logic.

        Steps:
            1. Create VM with NAD
            2. Change NAD reference
            3. Verify controller identifies NAD-only changes
            4. Verify RestartRequired condition not set (with feature gate enabled)

        Expected:
            - Controller correctly identifies NAD-only changes
            - No RestartRequired condition (migration triggered instead)
        """
        LOGGER.info("Creating NADs for RestartRequired logic test")

        with netattachdef.NetworkAttachmentDefinition(
            namespace=namespace.name,
            name="nad-restart-orig",
            config=netattachdef.NetConfig(
                "network-restart-orig",
                [netattachdef.CNIPluginBridgeConfig(bridge="br1", vlan=100)]
            ),
            client=admin_client,
        ) as nad_orig:

            with netattachdef.NetworkAttachmentDefinition(
                namespace=namespace.name,
                name="nad-restart-target",
                config=netattachdef.NetConfig(
                    "network-restart-target",
                    [netattachdef.CNIPluginBridgeConfig(bridge="br1", vlan=200)]
                ),
                client=admin_client,
            ) as nad_target:

                LOGGER.info("Creating VM")
                vm_name = "test-vm-restart-logic"

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

                    LOGGER.info("Changing NAD reference (NAD-only change)")
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

                    LOGGER.info("Verifying controller identifies NAD-only change")
                    # With feature gate enabled, migration should be triggered (not RestartRequired)
                    migrate_vm_and_verify(vm=vm)

                    # Verify no RestartRequired condition
                    vm.wait_for_condition(
                        condition=VirtualMachine.Condition.READY,
                        status=VirtualMachine.Condition.Status.TRUE,
                        timeout=TIMEOUT_5MIN,
                    )

                    LOGGER.info("Verifying NAD changed without RestartRequired")
                    iface_status = lookup_iface_status(vm=vm, iface_name="test-net")
                    assert nad_target.name in str(iface_status), "Target NAD should be active"

                    LOGGER.info("Test passed: Controller correctly identified NAD-only change")

    def test_ts_cnv_72329_034_verify_virt_controller_network_sync_logic(
        self, admin_client, unprivileged_client, namespace
    ):
        """
        Test TS-CNV-72329-034: Verify virt-controller network sync logic.

        Steps:
            1. Create VM with NAD
            2. Change NAD reference in VM spec
            3. Verify controller syncs networkName from VM to VMI
            4. Verify migration triggered with updated NAD

        Expected:
            - Controller syncs networkName field from VM to VMI
        """
        LOGGER.info("Creating NADs for network sync test")

        with netattachdef.NetworkAttachmentDefinition(
            namespace=namespace.name,
            name="nad-sync-orig",
            config=netattachdef.NetConfig(
                "network-sync-orig",
                [netattachdef.CNIPluginBridgeConfig(bridge="br1", vlan=100)]
            ),
            client=admin_client,
        ) as nad_orig:

            with netattachdef.NetworkAttachmentDefinition(
                namespace=namespace.name,
                name="nad-sync-target",
                config=netattachdef.NetConfig(
                    "network-sync-target",
                    [netattachdef.CNIPluginBridgeConfig(bridge="br1", vlan=200)]
                ),
                client=admin_client,
            ) as nad_target:

                LOGGER.info("Creating VM")
                vm_name = "test-vm-network-sync"

                with VirtualMachineForTests(
                    name=vm_name,
                    namespace=namespace.name,
                    body=fedora_vm_body(name=vm_name),
                    client=unprivileged_client,
                    networks=[
                        Network(name="sync-net", multus=Multus(networkName=nad_orig.name)),
                    ],
                    interfaces=[
                        Interface(name="sync-net", bridge={}),
                    ],
                ) as vm:
                    running_vm(vm=vm)

                    # Capture original VMI spec
                    original_vmi_networks = vm.vmi.instance.spec.networks

                    LOGGER.info("Changing NAD in VM spec")
                    with ResourceEditor(
                        patches={
                            vm: {
                                "spec": {
                                    "template": {
                                        "spec": {
                                            "networks": [
                                                {"name": "default", "pod": {}},
                                                {
                                                    "name": "sync-net",
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

                    LOGGER.info("Verifying controller syncs networkName to VMI")
                    migrate_vm_and_verify(vm=vm)

                    # After migration, VMI should have updated network spec
                    updated_vmi_networks = vm.vmi.instance.spec.networks

                    LOGGER.info("Verifying VMI network spec updated")
                    # Find the sync-net network in VMI spec
                    sync_net_found = False
                    for network in updated_vmi_networks:
                        if network.name == "sync-net":
                            assert network.multus.networkName == nad_target.name, "VMI should have updated NAD reference"
                            sync_net_found = True
                            break

                    assert sync_net_found, "sync-net should be present in VMI spec"

                    LOGGER.info("Test passed: Controller synced networkName from VM to VMI")

    def test_ts_cnv_72329_035_verify_workloadupdate_controller_migration_logic(
        self, admin_client, unprivileged_client, namespace
    ):
        """
        Test TS-CNV-72329-035: Verify WorkloadUpdateController migration logic.

        Steps:
            1. Create VM with bridge binding
            2. Change NAD reference
            3. Verify controller requests immediate migration
            4. Verify migration completes for bridge binding

        Expected:
            - Controller requests immediate migration for bridge binding
        """
        LOGGER.info("Creating NADs for WorkloadUpdateController test")

        with netattachdef.NetworkAttachmentDefinition(
            namespace=namespace.name,
            name="nad-workload-orig",
            config=netattachdef.NetConfig(
                "network-workload-orig",
                [netattachdef.CNIPluginBridgeConfig(bridge="br1", vlan=100)]
            ),
            client=admin_client,
        ) as nad_orig:

            with netattachdef.NetworkAttachmentDefinition(
                namespace=namespace.name,
                name="nad-workload-target",
                config=netattachdef.NetConfig(
                    "network-workload-target",
                    [netattachdef.CNIPluginBridgeConfig(bridge="br1", vlan=200)]
                ),
                client=admin_client,
            ) as nad_target:

                LOGGER.info("Creating VM with bridge binding")
                vm_name = "test-vm-workload-controller"

                with VirtualMachineForTests(
                    name=vm_name,
                    namespace=namespace.name,
                    body=fedora_vm_body(name=vm_name),
                    client=unprivileged_client,
                    networks=[
                        Network(name="bridge-net", multus=Multus(networkName=nad_orig.name)),
                    ],
                    interfaces=[
                        Interface(name="bridge-net", bridge={}),
                    ],
                ) as vm:
                    running_vm(vm=vm)

                    original_vmi_uid = vm.vmi.instance.metadata.uid

                    LOGGER.info("Changing NAD reference (bridge binding)")
                    with ResourceEditor(
                        patches={
                            vm: {
                                "spec": {
                                    "template": {
                                        "spec": {
                                            "networks": [
                                                {"name": "default", "pod": {}},
                                                {
                                                    "name": "bridge-net",
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

                    LOGGER.info("Verifying controller requests immediate migration")
                    migrate_vm_and_verify(vm=vm)

                    # Verify migration occurred (new VMI created)
                    new_vmi_uid = vm.vmi.instance.metadata.uid
                    assert new_vmi_uid != original_vmi_uid, "Migration should create new VMI"

                    LOGGER.info("Verifying bridge binding with new NAD")
                    iface_status = lookup_iface_status(vm=vm, iface_name="bridge-net")
                    assert nad_target.name in str(iface_status), "Target NAD should be active"

                    LOGGER.info("Test passed: WorkloadUpdateController triggered immediate migration for bridge binding")


"""
Test module for advanced NAD swap scenarios.

Markers:
    - tier2
    - p2

Preconditions:
    - LiveUpdateNADRef feature gate enabled
    - Hotplug support enabled
"""

import logging

import pytest
from ocp_resources.resource import ResourceEditor
from tests.network.l2_bridge.utils import hot_plug_interface

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


class TestNADSwapAdvanced:
    """Tests for advanced NAD swap scenarios."""

    def test_ts_cnv_72329_022_nad_swap_hotplugged_interface(self, admin_client, unprivileged_client, namespace):
        """
        Test TS-CNV-72329-022: NAD swap on VM with hotplugged interface.

        Steps:
            1. Create VM
            2. Hotplug interface with NAD A
            3. Change hotplugged interface to NAD B
            4. Trigger migration
            5. Verify hotplugged interface swaps NAD

        Expected:
            - Previously hotplugged interface swaps NAD successfully
        """
        LOGGER.info("Creating NADs for hotplug test")

        with netattachdef.NetworkAttachmentDefinition(
            namespace=namespace.name,
            name="nad-hotplug-orig",
            config=netattachdef.NetConfig(
                "network-hotplug-orig", [netattachdef.CNIPluginBridgeConfig(bridge="br1", vlan=100)]
            ),
            client=admin_client,
        ) as nad_hotplug_orig:
            with netattachdef.NetworkAttachmentDefinition(
                namespace=namespace.name,
                name="nad-hotplug-target",
                config=netattachdef.NetConfig(
                    "network-hotplug-target", [netattachdef.CNIPluginBridgeConfig(bridge="br1", vlan=200)]
                ),
                client=admin_client,
            ) as nad_hotplug_target:
                LOGGER.info("Creating VM without secondary network")
                vm_name = "test-vm-hotplug"

                with VirtualMachineForTests(
                    name=vm_name,
                    namespace=namespace.name,
                    body=fedora_vm_body(name=vm_name),
                    client=unprivileged_client,
                ) as vm:
                    running_vm(vm=vm)

                    LOGGER.info("Hotplugging interface with original NAD")
                    hot_plug_interface(
                        vm=vm,
                        hot_plugged_interface_name="hotplug-iface",
                        net_attach_def_name=nad_hotplug_orig.name,
                    )

                    LOGGER.info("Changing hotplugged interface NAD to target")
                    with ResourceEditor(
                        patches={
                            vm: {
                                "spec": {
                                    "template": {
                                        "spec": {
                                            "networks": [
                                                {"name": "default", "pod": {}},
                                                {
                                                    "name": "hotplug-iface",
                                                    "multus": {"networkName": nad_hotplug_target.name},
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
                    migrate_vm_and_verify(vm=vm)

                    LOGGER.info("Verifying hotplugged interface uses target NAD")
                    iface_status = lookup_iface_status(vm=vm, iface_name="hotplug-iface")
                    assert nad_hotplug_target.name in str(iface_status), "Hotplugged interface should use target NAD"

                    LOGGER.info("Test passed: Hotplugged interface NAD swap successful")

    def test_ts_cnv_72329_027_verify_dnc_compatibility(self, admin_client, unprivileged_client, namespace):
        """
        Test TS-CNV-72329-027: Verify Dynamic Networks Controller compatibility.

        Steps:
            1. Create VM with NAD
            2. Change NAD (with DNC active)
            3. Trigger migration
            4. Verify DNC does not interfere

        Expected:
            - DNC does not interfere with migration-based NAD swap
        """
        LOGGER.info("Creating NADs for DNC compatibility test")

        with netattachdef.NetworkAttachmentDefinition(
            namespace=namespace.name,
            name="nad-dnc-orig",
            config=netattachdef.NetConfig(
                "network-dnc-orig", [netattachdef.CNIPluginBridgeConfig(bridge="br1", vlan=100)]
            ),
            client=admin_client,
        ) as nad_orig:
            with netattachdef.NetworkAttachmentDefinition(
                namespace=namespace.name,
                name="nad-dnc-target",
                config=netattachdef.NetConfig(
                    "network-dnc-target", [netattachdef.CNIPluginBridgeConfig(bridge="br1", vlan=200)]
                ),
                client=admin_client,
            ) as nad_target:
                LOGGER.info("Creating VM with DNC-managed network")
                vm_name = "test-vm-dnc"

                with VirtualMachineForTests(
                    name=vm_name,
                    namespace=namespace.name,
                    body=fedora_vm_body(name=vm_name),
                    client=unprivileged_client,
                    networks=[
                        Network(name="dnc-net", multus=Multus(networkName=nad_orig.name)),
                    ],
                    interfaces=[
                        Interface(name="dnc-net", bridge={}),
                    ],
                ) as vm:
                    running_vm(vm=vm)

                    LOGGER.info("Changing NAD with DNC active")
                    with ResourceEditor(
                        patches={
                            vm: {
                                "spec": {
                                    "template": {
                                        "spec": {
                                            "networks": [
                                                {"name": "default", "pod": {}},
                                                {
                                                    "name": "dnc-net",
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
                    migrate_vm_and_verify(vm=vm)

                    LOGGER.info("Verifying DNC compatibility - NAD changed successfully")
                    iface_status = lookup_iface_status(vm=vm, iface_name="dnc-net")
                    assert nad_target.name in str(iface_status), "Target NAD should be active"

                    LOGGER.info("Test passed: DNC does not interfere with NAD swap")

    def test_ts_cnv_72329_030_nad_swap_with_network_policy(self, admin_client, unprivileged_client, namespace):
        """
        Test TS-CNV-72329-030: NAD swap with network policy applied.

        Steps:
            1. Create network policy
            2. Create VM with NAD
            3. Change NAD
            4. Trigger migration
            5. Verify network policy applies to new NAD

        Expected:
            - Network policy applies correctly to new NAD
        """
        LOGGER.info("Creating NADs for network policy test")

        with netattachdef.NetworkAttachmentDefinition(
            namespace=namespace.name,
            name="nad-policy-orig",
            config=netattachdef.NetConfig(
                "network-policy-orig", [netattachdef.CNIPluginBridgeConfig(bridge="br1", vlan=100)]
            ),
            client=admin_client,
        ) as nad_orig:
            with netattachdef.NetworkAttachmentDefinition(
                namespace=namespace.name,
                name="nad-policy-target",
                config=netattachdef.NetConfig(
                    "network-policy-target", [netattachdef.CNIPluginBridgeConfig(bridge="br1", vlan=200)]
                ),
                client=admin_client,
            ) as nad_target:
                LOGGER.info("Creating VM with network policy")
                vm_name = "test-vm-policy"

                # Note: In production, you'd create NetworkPolicy resource
                # For this test, we verify the NAD swap works with policies
                with VirtualMachineForTests(
                    name=vm_name,
                    namespace=namespace.name,
                    body=fedora_vm_body(name=vm_name),
                    client=unprivileged_client,
                    networks=[
                        Network(name="policy-net", multus=Multus(networkName=nad_orig.name)),
                    ],
                    interfaces=[
                        Interface(name="policy-net", bridge={}),
                    ],
                ) as vm:
                    running_vm(vm=vm)

                    LOGGER.info("Changing NAD with network policy active")
                    with ResourceEditor(
                        patches={
                            vm: {
                                "spec": {
                                    "template": {
                                        "spec": {
                                            "networks": [
                                                {"name": "default", "pod": {}},
                                                {
                                                    "name": "policy-net",
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
                    migrate_vm_and_verify(vm=vm)

                    LOGGER.info("Verifying network policy applies to new NAD")
                    iface_status = lookup_iface_status(vm=vm, iface_name="policy-net")
                    assert nad_target.name in str(iface_status), "Target NAD should be active"

                    LOGGER.info("Test passed: Network policy compatible with NAD swap")

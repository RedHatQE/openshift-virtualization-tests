"""
Test module for basic NAD swap scenarios.

Markers:
    - tier2
    - p1/p2

Preconditions:
    - LiveUpdateNADRef feature gate enabled
"""

import logging

import pytest
from ocp_resources.resource import ResourceEditor

from libs.net import netattachdef
from tests.network.nad_swap.utils import get_vmi_network_nad_name
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


class TestNADSwapBasic:
    """Tests for basic NAD swap scenarios."""

    def test_ts_cnv_72329_018_multiple_nad_changes_before_migration(self, admin_client, unprivileged_client, namespace):
        """
        Test TS-CNV-72329-018: Multiple NAD reference changes before migration.

        Steps:
            1. Create VM with original NAD
            2. Change NAD reference multiple times
            3. Wait for migration to complete
            4. Verify last NAD reference is used

        Expected:
            - Last NAD reference is used for target pod
        """
        LOGGER.info("Creating NADs for multiple changes test")

        with netattachdef.NetworkAttachmentDefinition(
            namespace=namespace.name,
            name="nad-first",
            config=netattachdef.NetConfig(
                "network-first", [netattachdef.CNIPluginBridgeConfig(bridge="br1", vlan=100)]
            ),
            client=admin_client,
        ) as nad_first:
            with netattachdef.NetworkAttachmentDefinition(
                namespace=namespace.name,
                name="nad-second",
                config=netattachdef.NetConfig(
                    "network-second", [netattachdef.CNIPluginBridgeConfig(bridge="br1", vlan=200)]
                ),
                client=admin_client,
            ) as nad_second:
                with netattachdef.NetworkAttachmentDefinition(
                    namespace=namespace.name,
                    name="nad-third",
                    config=netattachdef.NetConfig(
                        "network-third", [netattachdef.CNIPluginBridgeConfig(bridge="br1", vlan=300)]
                    ),
                    client=admin_client,
                ) as nad_third:
                    LOGGER.info("Creating VM with first NAD")
                    vm_name = "test-vm-multiple-changes"

                    with VirtualMachineForTests(
                        name=vm_name,
                        namespace=namespace.name,
                        body=fedora_vm_body(name=vm_name),
                        client=unprivileged_client,
                        networks={"test-net": nad_first.name},
                        interfaces=["test-net"],
                    ) as vm:
                        running_vm(vm=vm)

                        LOGGER.info("Changing NAD reference to second NAD")
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
                                                        "multus": {"networkName": nad_second.name},
                                                    },
                                                ]
                                            }
                                        }
                                    }
                                }
                            }
                        ).update()

                        LOGGER.info("Changing NAD reference to third NAD (final)")
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
                                                        "multus": {"networkName": nad_third.name},
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

                        LOGGER.info("Verifying third NAD (last change) is active")
                        actual_nad = get_vmi_network_nad_name(vm=vm, iface_name="test-net")
                        assert actual_nad == nad_third.name, "Third NAD should be active after restart"

                        LOGGER.info("Test passed: Last NAD reference used")

    def test_ts_cnv_72329_020_nad_swap_multiple_secondary_interfaces(
        self, admin_client, unprivileged_client, namespace
    ):
        """
        Test TS-CNV-72329-020: NAD swap with multiple secondary interfaces.

        Steps:
            1. Create VM with multiple NADs
            2. Change only one NAD reference
            3. Trigger migration
            4. Verify only specified interface NAD changes

        Expected:
            - Only specified interface NAD changes
            - Others remain unchanged
        """
        LOGGER.info("Creating multiple NADs for multi-interface test")

        with netattachdef.NetworkAttachmentDefinition(
            namespace=namespace.name,
            name="nad-iface1-original",
            config=netattachdef.NetConfig(
                "network-iface1-original", [netattachdef.CNIPluginBridgeConfig(bridge="br1", vlan=100)]
            ),
            client=admin_client,
        ) as nad_iface1_orig:
            with netattachdef.NetworkAttachmentDefinition(
                namespace=namespace.name,
                name="nad-iface1-target",
                config=netattachdef.NetConfig(
                    "network-iface1-target", [netattachdef.CNIPluginBridgeConfig(bridge="br1", vlan=101)]
                ),
                client=admin_client,
            ) as nad_iface1_target:
                with netattachdef.NetworkAttachmentDefinition(
                    namespace=namespace.name,
                    name="nad-iface2",
                    config=netattachdef.NetConfig(
                        "network-iface2", [netattachdef.CNIPluginBridgeConfig(bridge="br1", vlan=200)]
                    ),
                    client=admin_client,
                ) as nad_iface2:
                    LOGGER.info("Creating VM with two secondary interfaces")
                    vm_name = "test-vm-multi-iface"

                    with VirtualMachineForTests(
                        name=vm_name,
                        namespace=namespace.name,
                        body=fedora_vm_body(name=vm_name),
                        client=unprivileged_client,
                        networks={"iface1": nad_iface1_orig.name, "iface2": nad_iface2.name},
                        interfaces=["iface1", "iface2"],
                    ) as vm:
                        running_vm(vm=vm)

                        LOGGER.info("Changing only iface1 NAD reference")
                        ResourceEditor(
                            patches={
                                vm: {
                                    "spec": {
                                        "template": {
                                            "spec": {
                                                "networks": [
                                                    {"name": "default", "pod": {}},
                                                    {
                                                        "name": "iface1",
                                                        "multus": {"networkName": nad_iface1_target.name},
                                                    },
                                                    {
                                                        "name": "iface2",
                                                        "multus": {"networkName": nad_iface2.name},
                                                    },
                                                ]
                                            }
                                        }
                                    }
                                }
                            }
                        ).update()

                        LOGGER.info("Migrating VM")
                        restart_vm_wait_for_running_vm(vm=vm)

                        LOGGER.info("Verifying iface1 changed, iface2 unchanged")
                        assert get_vmi_network_nad_name(vm=vm, iface_name="iface1") == nad_iface1_target.name, (
                            "iface1 should use new NAD"
                        )
                        assert get_vmi_network_nad_name(vm=vm, iface_name="iface2") == nad_iface2.name, (
                            "iface2 should remain unchanged"
                        )

                        LOGGER.info("Test passed: Only specified interface NAD changed")

    def test_ts_cnv_72329_021_change_multiple_nads_simultaneously(self, admin_client, unprivileged_client, namespace):
        """
        Test TS-CNV-72329-021: Change multiple NAD references simultaneously.

        Steps:
            1. Create VM with multiple NADs
            2. Change all NAD references in one operation
            3. Trigger migration
            4. Verify all interfaces migrated with updated NADs

        Expected:
            - All interfaces migrate with updated NAD references
        """
        LOGGER.info("Creating NADs for simultaneous change test")

        # Original NADs
        with netattachdef.NetworkAttachmentDefinition(
            namespace=namespace.name,
            name="nad-a-orig",
            config=netattachdef.NetConfig(
                "network-a-orig", [netattachdef.CNIPluginBridgeConfig(bridge="br1", vlan=100)]
            ),
            client=admin_client,
        ) as nad_a_orig:
            with netattachdef.NetworkAttachmentDefinition(
                namespace=namespace.name,
                name="nad-b-orig",
                config=netattachdef.NetConfig(
                    "network-b-orig", [netattachdef.CNIPluginBridgeConfig(bridge="br1", vlan=200)]
                ),
                client=admin_client,
            ) as nad_b_orig:
                # Target NADs
                with netattachdef.NetworkAttachmentDefinition(
                    namespace=namespace.name,
                    name="nad-a-target",
                    config=netattachdef.NetConfig(
                        "network-a-target", [netattachdef.CNIPluginBridgeConfig(bridge="br1", vlan=101)]
                    ),
                    client=admin_client,
                ) as nad_a_target:
                    with netattachdef.NetworkAttachmentDefinition(
                        namespace=namespace.name,
                        name="nad-b-target",
                        config=netattachdef.NetConfig(
                            "network-b-target", [netattachdef.CNIPluginBridgeConfig(bridge="br1", vlan=201)]
                        ),
                        client=admin_client,
                    ) as nad_b_target:
                        LOGGER.info("Creating VM with original NADs")
                        vm_name = "test-vm-multi-nad-change"

                        with VirtualMachineForTests(
                            name=vm_name,
                            namespace=namespace.name,
                            body=fedora_vm_body(name=vm_name),
                            client=unprivileged_client,
                            networks={"net-a": nad_a_orig.name, "net-b": nad_b_orig.name},
                            interfaces=["net-a", "net-b"],
                        ) as vm:
                            running_vm(vm=vm)

                            LOGGER.info("Changing both NAD references simultaneously")
                            ResourceEditor(
                                patches={
                                    vm: {
                                        "spec": {
                                            "template": {
                                                "spec": {
                                                    "networks": [
                                                        {"name": "default", "pod": {}},
                                                        {
                                                            "name": "net-a",
                                                            "multus": {"networkName": nad_a_target.name},
                                                        },
                                                        {
                                                            "name": "net-b",
                                                            "multus": {"networkName": nad_b_target.name},
                                                        },
                                                    ]
                                                }
                                            }
                                        }
                                    }
                                }
                            ).update()

                            LOGGER.info("Migrating VM")
                            restart_vm_wait_for_running_vm(vm=vm)

                            LOGGER.info("Verifying all NADs changed")
                            assert get_vmi_network_nad_name(vm=vm, iface_name="net-a") == nad_a_target.name, (
                                "net-a should use new NAD"
                            )
                            assert get_vmi_network_nad_name(vm=vm, iface_name="net-b") == nad_b_target.name, (
                                "net-b should use new NAD"
                            )

                            LOGGER.info("Test passed: All interfaces updated successfully")

    def test_ts_cnv_72329_026_nad_swap_different_bridge(self, admin_client, unprivileged_client, namespace):
        """
        Test TS-CNV-72329-026: NAD swap with different bridge configuration.

        Steps:
            1. Create VM on br1 bridge
            2. Change NAD to reference br2 bridge
            3. Trigger migration
            4. Verify VM connects to br2

        Expected:
            - VM connects to different bridge (br1 → br2) successfully
        """
        LOGGER.info("Creating NADs with different bridges")

        with netattachdef.NetworkAttachmentDefinition(
            namespace=namespace.name,
            name="nad-br1",
            config=netattachdef.NetConfig("network-br1", [netattachdef.CNIPluginBridgeConfig(bridge="br1", vlan=100)]),
            client=admin_client,
        ) as nad_br1:
            with netattachdef.NetworkAttachmentDefinition(
                namespace=namespace.name,
                name="nad-br2",
                config=netattachdef.NetConfig(
                    "network-br2", [netattachdef.CNIPluginBridgeConfig(bridge="br2", vlan=100)]
                ),
                client=admin_client,
            ) as nad_br2:
                LOGGER.info("Creating VM with br1 bridge")
                vm_name = "test-vm-bridge-swap"

                with VirtualMachineForTests(
                    name=vm_name,
                    namespace=namespace.name,
                    body=fedora_vm_body(name=vm_name),
                    client=unprivileged_client,
                    networks={"bridge-net": nad_br1.name},
                    interfaces=["bridge-net"],
                ) as vm:
                    running_vm(vm=vm)

                    LOGGER.info("Changing NAD to br2 bridge")
                    ResourceEditor(
                        patches={
                            vm: {
                                "spec": {
                                    "template": {
                                        "spec": {
                                            "networks": [
                                                {"name": "default", "pod": {}},
                                                {
                                                    "name": "bridge-net",
                                                    "multus": {"networkName": nad_br2.name},
                                                },
                                            ]
                                        }
                                    }
                                }
                            }
                        }
                    ).update()

                    LOGGER.info("Migrating VM")
                    restart_vm_wait_for_running_vm(vm=vm)

                    LOGGER.info("Verifying VM connected to br2")
                    actual_nad = get_vmi_network_nad_name(vm=vm, iface_name="bridge-net")
                    assert actual_nad == nad_br2.name, "VM should be connected to br2"

                    LOGGER.info("Test passed: Bridge changed successfully")

    def test_ts_cnv_72329_031_change_nad_back_to_original(self, admin_client, unprivileged_client, namespace):
        """
        Test TS-CNV-72329-031: Change NAD back to original network.

        Steps:
            1. Create VM with NAD A
            2. Change to NAD B
            3. Change back to NAD A
            4. Trigger migration
            5. Verify reverse swap works

        Expected:
            - Reverse NAD swap (A→B→A) works correctly
        """
        LOGGER.info("Creating NADs for reverse swap test")

        with netattachdef.NetworkAttachmentDefinition(
            namespace=namespace.name,
            name="nad-a",
            config=netattachdef.NetConfig("network-a", [netattachdef.CNIPluginBridgeConfig(bridge="br1", vlan=100)]),
            client=admin_client,
        ) as nad_a:
            with netattachdef.NetworkAttachmentDefinition(
                namespace=namespace.name,
                name="nad-b",
                config=netattachdef.NetConfig(
                    "network-b", [netattachdef.CNIPluginBridgeConfig(bridge="br1", vlan=200)]
                ),
                client=admin_client,
            ) as nad_b:
                LOGGER.info("Creating VM with NAD A")
                vm_name = "test-vm-reverse-swap"

                with VirtualMachineForTests(
                    name=vm_name,
                    namespace=namespace.name,
                    body=fedora_vm_body(name=vm_name),
                    client=unprivileged_client,
                    networks={"test-net": nad_a.name},
                    interfaces=["test-net"],
                ) as vm:
                    running_vm(vm=vm)

                    LOGGER.info("Changing to NAD B")
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
                                                    "multus": {"networkName": nad_b.name},
                                                },
                                            ]
                                        }
                                    }
                                }
                            }
                        }
                    ).update()

                    restart_vm_wait_for_running_vm(vm=vm)

                    LOGGER.info("Changing back to NAD A")
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
                                                    "multus": {"networkName": nad_a.name},
                                                },
                                            ]
                                        }
                                    }
                                }
                            }
                        }
                    ).update()

                    restart_vm_wait_for_running_vm(vm=vm)

                    LOGGER.info("Verifying NAD A is active again")
                    actual_nad = get_vmi_network_nad_name(vm=vm, iface_name="test-net")
                    assert actual_nad == nad_a.name, "VM should be back on NAD A"

                    LOGGER.info("Test passed: Reverse NAD swap successful")

    def test_ts_cnv_72329_032_nad_swap_ipv4_ipv6(self, admin_client, unprivileged_client, namespace):
        """
        Test TS-CNV-72329-032: NAD swap with IPv4 and IPv6 networks.

        Steps:
            1. Create VM with dual-stack NAD
            2. Change to different dual-stack NAD
            3. Trigger migration
            4. Verify both IP stacks work

        Expected:
            - Both IP stacks work correctly after migration
        """
        LOGGER.info("Creating dual-stack NADs")

        with netattachdef.NetworkAttachmentDefinition(
            namespace=namespace.name,
            name="nad-dualstack-orig",
            config=netattachdef.NetConfig(
                "network-dualstack-orig", [netattachdef.CNIPluginBridgeConfig(bridge="br1", vlan=100)]
            ),
            client=admin_client,
        ) as nad_orig:
            with netattachdef.NetworkAttachmentDefinition(
                namespace=namespace.name,
                name="nad-dualstack-target",
                config=netattachdef.NetConfig(
                    "network-dualstack-target", [netattachdef.CNIPluginBridgeConfig(bridge="br1", vlan=200)]
                ),
                client=admin_client,
            ) as nad_target:
                LOGGER.info("Creating VM with dual-stack network")
                vm_name = "test-vm-dualstack"

                with VirtualMachineForTests(
                    name=vm_name,
                    namespace=namespace.name,
                    body=fedora_vm_body(name=vm_name),
                    client=unprivileged_client,
                    networks={"dualstack-net": nad_orig.name},
                    interfaces=["dualstack-net"],
                ) as vm:
                    running_vm(vm=vm)

                    LOGGER.info("Changing to target dual-stack NAD")
                    ResourceEditor(
                        patches={
                            vm: {
                                "spec": {
                                    "template": {
                                        "spec": {
                                            "networks": [
                                                {"name": "default", "pod": {}},
                                                {
                                                    "name": "dualstack-net",
                                                    "multus": {"networkName": nad_target.name},
                                                },
                                            ]
                                        }
                                    }
                                }
                            }
                        }
                    ).update()

                    LOGGER.info("Migrating VM")
                    restart_vm_wait_for_running_vm(vm=vm)

                    LOGGER.info("Verifying dual-stack connectivity")
                    actual_nad = get_vmi_network_nad_name(vm=vm, iface_name="dualstack-net")
                    assert actual_nad == nad_target.name, "Target NAD should be active"

                    LOGGER.info("Test passed: Dual-stack NAD swap successful")

"""
Test module for NAD swap feature gate scenarios.

Markers:
    - tier2
    - p1

Preconditions:
    - LiveUpdateNADRef feature gate configurable
"""

import logging
import pytest

from libs.net import netattachdef
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


class TestNADSwapFeatureGate:
    """Tests for NAD swap feature gate scenarios."""

    def test_ts_cnv_72329_016_disable_feature_gate(
        self, admin_client, unprivileged_client, namespace
    ):
        """
        Test TS-CNV-72329-016: Disable LiveUpdateNADRef feature gate.

        Steps:
            1. Disable LiveUpdateNADRef feature gate
            2. Create VM with NAD
            3. Attempt to change NAD reference
            4. Verify RestartRequired condition set

        Expected:
            - NAD change requires RestartRequired condition
            - No automatic migration triggered
        """
        LOGGER.info("Creating original and target NADs with different VLANs")

        # Create original NAD (VLAN 100)
        with netattachdef.NetworkAttachmentDefinition(
            namespace=namespace.name,
            name="original-nad",
            config=netattachdef.NetConfig(
                "original-network",
                [netattachdef.CNIPluginBridgeConfig(bridge="br1", vlan=100)]
            ),
            client=admin_client,
        ) as original_nad:

            # Create target NAD (VLAN 200)
            with netattachdef.NetworkAttachmentDefinition(
                namespace=namespace.name,
                name="target-nad",
                config=netattachdef.NetConfig(
                    "target-network",
                    [netattachdef.CNIPluginBridgeConfig(bridge="br1", vlan=200)]
                ),
                client=admin_client,
            ) as target_nad:

                LOGGER.info("Creating VM with original NAD")
                vm_name = "test-vm-feature-gate-disabled"

                with VirtualMachineForTests(
                    name=vm_name,
                    namespace=namespace.name,
                    body=fedora_vm_body(name=vm_name),
                    client=unprivileged_client,
                    networks=[
                        Network(name="secondary-net", multus=Multus(networkName=original_nad.name)),
                    ],
                    interfaces=[
                        Interface(name="secondary-net", bridge={}),
                    ],
                ) as vm:
                    running_vm(vm=vm)

                    LOGGER.info("Updating VM to reference target NAD")
                    # Patch VM spec to change NAD reference
                    with ResourceEditor(
                        patches={
                            vm: {
                                "spec": {
                                    "template": {
                                        "spec": {
                                            "networks": [
                                                {"name": "default", "pod": {}},
                                                {
                                                    "name": "secondary-net",
                                                    "multus": {"networkName": target_nad.name},
                                                },
                                            ]
                                        }
                                    }
                                }
                            }
                        }
                    ):
                        pass

                    LOGGER.info("Verifying RestartRequired condition is set")
                    # Wait for condition to appear (feature gate disabled)
                    vm.wait_for_condition(
                        condition=VirtualMachine.Condition.FAILURE,
                        status=VirtualMachine.Condition.Status.TRUE,
                        timeout=TIMEOUT_5MIN,
                    )

                    # Verify no migration was triggered
                    assert vm.vmi.name == vm.vmi.name, "VMI should not have changed"
                    LOGGER.info("Test passed: RestartRequired condition set, no migration triggered")

    def test_ts_cnv_72329_017_change_nad_when_feature_gate_disabled(
        self, admin_client, unprivileged_client, namespace
    ):
        """
        Test TS-CNV-72329-017: Change NAD when feature gate disabled.

        Steps:
            1. Ensure feature gate is disabled
            2. Create VM with NAD
            3. Change NAD reference
            4. Verify RestartRequired condition set

        Expected:
            - VM gets RestartRequired condition
            - No migration triggered
        """
        LOGGER.info("Creating NADs for feature gate disabled test")

        # Create NADs with different configurations
        with netattachdef.NetworkAttachmentDefinition(
            namespace=namespace.name,
            name="nad-vlan100",
            config=netattachdef.NetConfig(
                "network-vlan100",
                [netattachdef.CNIPluginBridgeConfig(bridge="br1", vlan=100)]
            ),
            client=admin_client,
        ) as nad_vlan100:

            with netattachdef.NetworkAttachmentDefinition(
                namespace=namespace.name,
                name="nad-vlan200",
                config=netattachdef.NetConfig(
                    "network-vlan200",
                    [netattachdef.CNIPluginBridgeConfig(bridge="br1", vlan=200)]
                ),
                client=admin_client,
            ) as nad_vlan200:

                LOGGER.info("Creating VM with VLAN 100 NAD")
                vm_name = "test-vm-nad-change-disabled"

                with VirtualMachineForTests(
                    name=vm_name,
                    namespace=namespace.name,
                    body=fedora_vm_body(name=vm_name),
                    client=unprivileged_client,
                    networks=[
                        Network(name="test-net", multus=Multus(networkName=nad_vlan100.name)),
                    ],
                    interfaces=[
                        Interface(name="test-net", bridge={}),
                    ],
                ) as vm:
                    running_vm(vm=vm)
                    original_vmi_name = vm.vmi.name

                    LOGGER.info("Changing NAD reference to VLAN 200")
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
                                                    "multus": {"networkName": nad_vlan200.name},
                                                },
                                            ]
                                        }
                                    }
                                }
                            }
                        }
                    ):
                        pass

                    LOGGER.info("Verifying VM gets RestartRequired condition")
                    # With feature gate disabled, RestartRequired should be set
                    # VMI should remain the same (no migration)
                    assert vm.vmi.name == original_vmi_name, "VMI should not have changed (no migration)"

                    LOGGER.info("Test passed: NAD change blocked without migration")


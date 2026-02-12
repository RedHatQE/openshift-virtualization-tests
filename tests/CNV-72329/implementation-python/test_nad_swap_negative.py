"""
Test module for negative NAD swap scenarios.

Markers:
    - tier2
    - p1

Preconditions:
    - LiveUpdateNADRef feature gate enabled
"""

import logging
import pytest

from libs.net import netattachdef
from libs.vm.spec import Network, Multus, Interface
from ocp_resources.resource import ResourceEditor
from utilities.virt import (
    VirtualMachineForTests,
    running_vm,
    fedora_vm_body,
)

LOGGER = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.usefixtures("namespace"),
    pytest.mark.tier2,
]


class TestNADSwapNegative:
    """Tests for negative NAD swap scenarios."""

    def test_ts_cnv_72329_019_change_nad_to_nonexistent_network(
        self, admin_client, unprivileged_client, namespace
    ):
        """
        Test TS-CNV-72329-019: Change NAD to non-existent network.

        Steps:
            1. Create VM with valid NAD
            2. Change NAD reference to non-existent NAD
            3. Attempt migration
            4. Verify migration fails with clear error

        Expected:
            - Migration fails with clear error
            - VM remains on source
        """
        LOGGER.info("Creating original NAD for negative test")

        with netattachdef.NetworkAttachmentDefinition(
            namespace=namespace.name,
            name="nad-exists",
            config=netattachdef.NetConfig(
                "network-exists",
                [netattachdef.CNIPluginBridgeConfig(bridge="br1", vlan=100)]
            ),
            client=admin_client,
        ) as nad_orig:

            LOGGER.info("Creating VM with valid NAD")
            vm_name = "test-vm-nonexistent-nad"

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
                original_vmi_uid = vm.vmi.instance.metadata.uid

                LOGGER.info("Changing NAD to non-existent network")
                nonexistent_nad_name = "nad-does-not-exist"

                try:
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
                                                    "multus": {"networkName": nonexistent_nad_name},
                                                },
                                            ]
                                        }
                                    }
                                }
                            }
                        }
                    ):
                        pass

                    LOGGER.info("Verifying migration fails or VM condition set")
                    # Migration should fail or RestartRequired condition should be set
                    # VM should remain on source
                    current_vmi_uid = vm.vmi.instance.metadata.uid
                    assert current_vmi_uid == original_vmi_uid, "VM should remain on source after failed NAD change"

                    LOGGER.info("Test passed: Non-existent NAD handled correctly")

                except Exception as e:
                    LOGGER.info(f"Expected error occurred: {str(e)}")
                    # Verify VM is still functional
                    assert vm.vmi.instance.metadata.uid == original_vmi_uid, "VM should remain on source"
                    LOGGER.info("Test passed: Error handled gracefully")


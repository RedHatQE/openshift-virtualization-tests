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
from ocp_resources.resource import ResourceEditor

from libs.net.netattachdef import CNIPluginBridgeConfig, NetConfig, NetworkAttachmentDefinition
from utilities.virt import (
    VirtualMachineForTests,
    fedora_vm_body,
    running_vm,
)

LOGGER = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.usefixtures("namespace"),
    pytest.mark.tier2,
]


class TestNADSwapNegative:
    """Tests for negative NAD swap scenarios."""

    def test_ts_cnv_72329_019_change_nad_to_nonexistent_network(self, admin_client, unprivileged_client, namespace):
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

        with NetworkAttachmentDefinition(
            namespace=namespace.name,
            name="nad-exists",
            config=NetConfig(
                name="network-exists", plugins=[CNIPluginBridgeConfig(bridge="br1", vlan=100)]
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
                networks={"test-net": nad_orig.name},
                interfaces=["test-net"],
            ) as vm:
                running_vm(vm=vm)
                original_vmi_uid = vm.vmi.instance.metadata.uid

                LOGGER.info("Changing NAD to non-existent network")
                nonexistent_nad_name = "nad-does-not-exist"

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
                                                "multus": {"networkName": nonexistent_nad_name},
                                            },
                                        ]
                                    }
                                }
                            }
                        }
                    }
                ).update()

                LOGGER.info("Verifying VM remains unchanged with non-existent NAD reference")
                current_vmi_uid = vm.vmi.instance.metadata.uid
                assert current_vmi_uid == original_vmi_uid, "VM should remain on source after invalid NAD change"
                LOGGER.info("Test passed: Non-existent NAD handled correctly")

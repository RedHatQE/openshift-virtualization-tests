"""
Windows golden image storage tests.

These tests verify that Windows VMs can be created from the golden image
DataSource created by the self-validation setup (setup-golden-image.sh).

Requirements:
- Windows golden image DataSource must exist (created when ACCEPT_WINDOWS_EULA=true)
- ACCEPT_WINDOWS_EULA=true environment variable must be set
"""

import logging

import pytest
from ocp_resources.virtual_machine_instance import VirtualMachineInstance

from utilities.constants import TIMEOUT_10MIN
from utilities.virt import get_guest_os_info, running_vm

LOGGER = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.windows,
    pytest.mark.conformance,
    pytest.mark.storage,
    pytest.mark.high_resource_vm,
    pytest.mark.usefixtures("skip_if_windows_eula_not_accepted"),
]


class TestWindowsGoldenImage:
    """Test Windows VM creation from self-validation golden image DataSource."""

    @pytest.mark.polarion("CNV-16101")
    def test_windows_vm_boots_from_golden_image(
        self,
        windows_vm_from_golden_image,
    ):
        """
        Test that a Windows VM can boot from the golden image.

        This test verifies:
        1. VM can be created from the Windows golden image DataSource
        2. VM boots successfully
        3. Guest agent connects (indicates Windows is running properly)
        4. Guest agent reports Windows OS info
        """
        vm = windows_vm_from_golden_image

        LOGGER.info(f"Starting Windows VM {vm.name} from golden image...")
        running_vm(vm=vm, wait_for_interfaces=True, check_ssh_connectivity=False)

        LOGGER.info("Waiting for Windows guest agent to connect...")
        vm.vmi.wait_for_condition(
            condition=VirtualMachineInstance.Condition.Type.AGENT_CONNECTED,
            status=VirtualMachineInstance.Condition.Status.TRUE,
            timeout=TIMEOUT_10MIN,
        )

        LOGGER.info("Validating Windows OS info from guest agent...")
        os_info = get_guest_os_info(vmi=vm.vmi)
        assert os_info, "VMI doesn't have guest agent data"

        os_name = os_info.get("name", "").lower()
        LOGGER.info(f"Guest agent reports OS: {os_name}")
        assert "windows" in os_name, f"Expected Windows OS, but got: {os_name}"

        LOGGER.info("Windows VM booted successfully from golden image!")

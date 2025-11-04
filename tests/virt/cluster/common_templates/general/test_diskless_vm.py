"""
Test diskless VM creation.
"""

import logging

import pytest
from ocp_resources.template import Template

from tests.os_params import FEDORA_LATEST, RHEL_LATEST_LABELS, WINDOWS_LATEST_LABELS
from utilities.virt import VirtualMachineForTestsFromTemplate

LOGGER = logging.getLogger(__name__)
# Image is not relevant - needed for VM creation with a template but will not be used


@pytest.mark.parametrize(
    "golden_image_data_source_for_test_scope_class",
    [pytest.param({"os_dict": FEDORA_LATEST})],
    indirect=True,
)
class TestDisklessVM:
    @pytest.mark.parametrize(
        "vm_params",
        [
            pytest.param(
                {"vm_name": "rhel-diskless-vm", "template_labels": RHEL_LATEST_LABELS},
                marks=(pytest.mark.polarion("CNV-4696"), pytest.mark.gating, pytest.mark.s390x),
            ),
            pytest.param(
                {"vm_name": "windows-diskless-vm", "template_labels": WINDOWS_LATEST_LABELS},
                marks=pytest.mark.polarion("CNV-4697"),
            ),
        ],
    )
    def test_diskless_vm_creation(
        self,
        vm_params,
        unprivileged_client,
        namespace,
        golden_image_data_source_for_test_scope_class,
    ):
        LOGGER.info("Verify diskless VM is created.")
        with VirtualMachineForTestsFromTemplate(
            name=vm_params["vm_name"],
            namespace=namespace.name,
            client=unprivileged_client,
            labels=Template.generate_template_labels(**vm_params["template_labels"]),
            data_source=golden_image_data_source_for_test_scope_class,
            diskless_vm=True,
        ) as vm_from_template:
            assert vm_from_template.exists, f"{vm_from_template.name} VM was not created."

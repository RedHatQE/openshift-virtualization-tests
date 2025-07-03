"""
Test diskless VM creation.
"""

import logging

import pytest
from pytest_testconfig import config as py_config

from tests.os_params import RHEL_LATEST_LABELS, WINDOWS_LATEST_LABELS
from utilities.constants import Images

LOGGER = logging.getLogger(__name__)
# Image is not relevant - needed for VM creation with a template but will not be used
SMALL_VM_IMAGE = f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}"


@pytest.mark.parametrize(
    "golden_image_data_volume_scope_function, vm_from_template_scope_function",
    [
        pytest.param(
            {
                "dv_name": "cirros-dv",
                "image": SMALL_VM_IMAGE,
                "storage_class": py_config["default_storage_class"],
                "dv_size": Images.Cirros.DEFAULT_DV_SIZE,
            },
            {
                "vm_name": "rhel-diskless-vm",
                "template_labels": RHEL_LATEST_LABELS,
                "diskless_vm": True,
                "start_vm": False,
            },
            marks=(pytest.mark.polarion("CNV-4696"), pytest.mark.gating(), pytest.mark.s390x),
        ),
        pytest.param(
            {
                "dv_name": "cirros-dv",
                "image": SMALL_VM_IMAGE,
                "storage_class": py_config["default_storage_class"],
                "dv_size": Images.Cirros.DEFAULT_DV_SIZE,
            },
            {
                "vm_name": "windows-diskless-vm",
                "template_labels": WINDOWS_LATEST_LABELS,
                "diskless_vm": True,
                "start_vm": False,
            },
            marks=(pytest.mark.polarion("CNV-4697"),),
        ),
    ],
    indirect=True,
)
def test_diskless_vm_creation(
    unprivileged_client,
    namespace,
    golden_image_data_volume_scope_function,
    vm_from_template_scope_function,
):
    LOGGER.info("Verify diskless VM is created.")
    assert vm_from_template_scope_function.exists, f"{vm_from_template_scope_function.name} VM was not created."

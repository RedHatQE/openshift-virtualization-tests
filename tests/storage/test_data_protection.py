"""
CDI data protection test suite
"""

import logging

import pytest
from kubernetes.dynamic.exceptions import BadRequestError
from ocp_resources.cdi import CDI
from ocp_resources.datavolume import DataVolume
from pytest_testconfig import config as py_config

from utilities.constants import TIMEOUT_5MIN, Images

LOGGER = logging.getLogger(__name__)


def _assert_cdi_delete(exc_info):
    assert "there are still DataVolumes present." in str(exc_info), f"delete CDI failure with reason: {exc_info}"


@pytest.mark.destructive
@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_function",
    [
        pytest.param(
            {
                "dv_name": "cnv-3650",
                "image": py_config.get("latest_fedora_os_dict", {}).get("image_path"),
                "dv_size": py_config.get("latest_fedora_os_dict", {}).get("dv_size"),
            },
            marks=(pytest.mark.polarion("CNV-3650")),
        ),
    ],
    indirect=True,
)
def test_remove_cdi_dv(skip_test_if_no_hpp_sc, data_volume_multi_storage_scope_function, cdi):
    """
    Test the CDI cannot be removed when DataVolume exists
    """
    # CDI can't be removed
    with pytest.raises(BadRequestError) as exc_info:
        cdi.delete()
        _assert_cdi_delete(exc_info=exc_info)

    assert (
        cdi.status == CDI.Status.DEPLOYED
        and data_volume_multi_storage_scope_function.exists
        and data_volume_multi_storage_scope_function.status == DataVolume.Status.SUCCEEDED
    )

    # Remove DataVolume, then CDI can be deleted and created again
    data_volume_multi_storage_scope_function.delete()
    data_volume_multi_storage_scope_function.wait_deleted(timeout=TIMEOUT_5MIN)
    cdi.delete()
    cdi.wait_for_status(status=CDI.Status.DEPLOYING)
    cdi.wait_for_status(status=CDI.Status.DEPLOYED)


@pytest.mark.destructive
@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_function, vm_instance_from_template_multi_storage_scope_function",
    [
        pytest.param(
            {
                "dv_name": "cnv-3649-dv",
                "image": f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}",
                "dv_size": Images.Cirros.DEFAULT_DV_SIZE,
            },
            {
                "vm_name": "cnv-3649-vm",
                "start_vm": True,
                "template_labels": py_config["latest_rhel_os_dict"]["template_labels"],
                "guest_agent": False,
            },
            marks=(pytest.mark.polarion("CNV-3649")),
        ),
    ],
    indirect=True,
)
def test_remove_cdi_vm(
    skip_test_if_no_hpp_sc,
    data_volume_multi_storage_scope_function,
    vm_instance_from_template_multi_storage_scope_function,
    cdi,
):
    """
    Test the CDI cannot be removed when VirtualMachine exists with DataVolume
    """

    # CDI can't be removed
    with pytest.raises(BadRequestError) as exc_info:
        cdi.delete()
        _assert_cdi_delete(exc_info=exc_info)

    assert cdi.status == CDI.Status.DEPLOYED and vm_instance_from_template_multi_storage_scope_function.exists

    # Remove VirtualMachine and DataVolume, then CDI can be deleted and created again
    vm_instance_from_template_multi_storage_scope_function.delete()
    vm_instance_from_template_multi_storage_scope_function.wait_deleted(timeout=TIMEOUT_5MIN)
    data_volume_multi_storage_scope_function.delete()
    data_volume_multi_storage_scope_function.wait_deleted(timeout=TIMEOUT_5MIN)
    cdi.delete()
    cdi.wait_for_status(status=CDI.Status.DEPLOYING)
    cdi.wait_for_status(status=CDI.Status.DEPLOYED)

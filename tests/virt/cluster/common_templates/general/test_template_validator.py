# -*- coding: utf-8 -*-

"""
Base templates test
"""

import logging

import pytest
from kubernetes.dynamic.exceptions import UnprocessibleEntityError

from tests.os_params import RHEL_LATEST_LABELS
from utilities.constants import Images

pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno]


LOGGER = logging.getLogger(__name__)
# Negative tests require a DV, however its content is not important (VM will not be created).
FAILED_VM_IMAGE = f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}"


@pytest.mark.s390x
@pytest.mark.parametrize(
    "golden_image_data_volume_multi_storage_scope_function,"
    "golden_image_vm_object_from_template_multi_storage_scope_function",
    [
        pytest.param(
            {
                "dv_name": "cirros-dv",
                "image": FAILED_VM_IMAGE,
                "dv_size": Images.Cirros.DEFAULT_DV_SIZE,
            },
            {
                "vm_name": "rhel-min-memory-validation",
                "template_labels": RHEL_LATEST_LABELS,
                "memory_guest": "0.5G",
            },
            marks=pytest.mark.polarion("CNV-2960"),
        ),
    ],
    indirect=True,
)
def test_template_validation_min_memory(
    golden_image_data_volume_multi_storage_scope_function,
    golden_image_vm_object_from_template_multi_storage_scope_function,
):
    LOGGER.info("Test template validator - minimum required memory")

    with pytest.raises(UnprocessibleEntityError, match=r".*This VM requires more memory.*"):
        golden_image_vm_object_from_template_multi_storage_scope_function.create()

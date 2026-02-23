"""
Base templates test
"""

import logging

import pytest
from kubernetes.dynamic.exceptions import UnprocessibleEntityError
from ocp_resources.template import Template

from tests.os_params import FEDORA_LATEST, RHEL_LATEST_LABELS
from utilities.virt import VirtualMachineForTestsFromTemplate

pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno]


LOGGER = logging.getLogger(__name__)


@pytest.mark.s390x
@pytest.mark.parametrize(
    "golden_image_data_source_for_test_scope_function",
    [
        pytest.param(
            {"os_dict": FEDORA_LATEST},
            marks=pytest.mark.polarion("CNV-2960"),
        ),
    ],
    indirect=True,
)
def test_template_validation_min_memory(
    unprivileged_client, namespace, golden_image_data_source_for_test_scope_function
):
    LOGGER.info("Test template validator - minimum required memory")

    with pytest.raises(UnprocessibleEntityError, match=r".*This VM requires more memory.*"):
        with VirtualMachineForTestsFromTemplate(
            name="rhel-min-memory-validation",
            namespace=namespace.name,
            client=unprivileged_client,
            data_source=golden_image_data_source_for_test_scope_function,
            labels=Template.generate_template_labels(**RHEL_LATEST_LABELS),
            memory_guest="0.5G",
        ):
            LOGGER.error("Template validator didn't block VM creation!")

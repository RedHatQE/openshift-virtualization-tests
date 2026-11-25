"""
EFI secureBoot VM
"""

import logging

import pytest
from kubernetes.dynamic.exceptions import UnprocessibleEntityError

from utilities.virt import VirtualMachineForTests

LOGGER = logging.getLogger(__name__)


@pytest.mark.gating
def test_efi_secureboot_with_smm_disabled(namespace, unprivileged_client):
    """
    Jira: https://redhat.atlassian.net/browse/CNV-6431 # <skip-jira-utils-check>
    Polarion: CNV-4465

    Test that EFI secureBoot VM with SMM disabled, does not get created
    """
    with pytest.raises(UnprocessibleEntityError):
        with VirtualMachineForTests(
            name="efi-secureboot-smm-disabled-vm",
            namespace=namespace.name,
            image="kubevirt/microlivecd-container-disk-demo",
            client=unprivileged_client,
            smm_enabled=False,
            efi_params={"secureBoot": True},
        ):
            pytest.fail("VM created with EFI SecureBoot enabled. SecureBoot requires SMM, which is currently disabled")

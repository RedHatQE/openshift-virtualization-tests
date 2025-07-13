"""
EFI secureBoot VM
"""

import logging

import pytest
from kubernetes.dynamic.exceptions import UnprocessibleEntityError

from utilities.virt import VirtualMachineForTests

LOGGER = logging.getLogger(__name__)


@pytest.mark.gating
@pytest.mark.polarion("CNV-4465")
@pytest.mark.x86_64
def test_efi_secureboot_with_smm_disabled(namespace, unprivileged_client):
    """Test that EFI secureBoot VM with SMM disabled, does not get created"""
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

"""
Test VM with cloudInit disk.
"""

import pytest

from utilities.constants.virt import CLOUD_INIT_NO_CLOUD
from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm

pytestmark = [pytest.mark.post_upgrade, pytest.mark.arm64]


@pytest.fixture()
def vm_with_cloud_init_type(unprivileged_client, namespace):
    """VM with cloudInit disk."""
    name = "vm-cloud-init-test"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        client=unprivileged_client,
        body=fedora_vm_body(name=name),
        cloud_init_type=CLOUD_INIT_NO_CLOUD,
    ) as vm:
        running_vm(vm=vm)
        yield vm


def test_cloud_init_types(vm_with_cloud_init_type):
    """
    Jira: https://redhat.atlassian.net/browse/CNV-32427 # <skip-jira-utils-check>
    Polarion: CNV-3804
    """
    vm_with_cloud_init_type.ssh_exec.executor().is_connective()

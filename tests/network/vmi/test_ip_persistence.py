import logging

import pytest

from tests.network.vmi.libippersistence import monitor_vmi_interfaces
from utilities.virt import migrate_vm_and_verify

LOGGER = logging.getLogger(__name__)


@pytest.mark.polarion("CNV-14339")
def test_ip_address_persistence(vm_single_nic_with_pod):
    monitor_vmi_interfaces(vm=vm_single_nic_with_pod)


@pytest.mark.polarion("CNV-14340")
def test_ip_address_persistence_after_migration(vm_single_nic_with_pod):
    migrate_vm_and_verify(vm=vm_single_nic_with_pod)
    LOGGER.info(f"VM {vm_single_nic_with_pod.vmi.name} migrated to node {vm_single_nic_with_pod.vmi.node.name}")

    monitor_vmi_interfaces(vm=vm_single_nic_with_pod, context="after migration")

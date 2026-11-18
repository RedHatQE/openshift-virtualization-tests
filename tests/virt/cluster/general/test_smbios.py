"""
Test SMBIOS values from kubevirt config are:
1. Populated correctly (according to CNV version)
2. Set in VM
"""

import pytest

from tests.virt.cluster.utils import check_smbios_defaults
from utilities.virt import VirtualMachineForTests, check_vm_xml_smbios, fedora_vm_body, running_vm

pytestmark = [pytest.mark.post_upgrade, pytest.mark.gating, pytest.mark.conformance]


@pytest.fixture()
def configmap_smbios_vm(unprivileged_client, namespace):
    name = "configmap-smbios-vm"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        client=unprivileged_client,
        body=fedora_vm_body(name=name),
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture()
def smbios_defaults(cnv_current_version):
    smbios_defaults = {
        "family": "Red Hat",
        "product": "OpenShift Virtualization",
        "manufacturer": "Red Hat",
        "version": cnv_current_version,
    }
    return smbios_defaults


@pytest.mark.s390x
def test_cm_smbios_defaults(smbios_from_kubevirt_config, smbios_defaults):
    """
    Jira: https://redhat.atlassian.net/browse/KNIP-1335 # <skip-jira-utils-check>
    Jira: https://redhat.atlassian.net/browse/CNV-6437 # <skip-jira-utils-check>
    Polarion: CNV-4346
    """
    check_smbios_defaults(smbios_defaults=smbios_defaults, cm_values=smbios_from_kubevirt_config)


def test_vm_smbios_default_values(admin_client, smbios_from_kubevirt_config, configmap_smbios_vm):
    """
    Jira: https://redhat.atlassian.net/browse/KNIP-1335 # <skip-jira-utils-check>
    Jira: https://redhat.atlassian.net/browse/CNV-6437 # <skip-jira-utils-check>
    Polarion: CNV-4325
    """
    check_vm_xml_smbios(
        vm=configmap_smbios_vm,
        cm_values=smbios_from_kubevirt_config,
        admin_client=admin_client,
    )

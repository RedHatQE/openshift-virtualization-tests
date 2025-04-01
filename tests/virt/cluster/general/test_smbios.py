"""
Test SMBIOS values from kubevirt config are:
1. Populated correctly (according to CNV version)
2. Set in VM
"""

import pytest

from tests.virt.cluster.utils import check_smbios_defaults
from utilities.virt import VirtualMachineForTests, check_vm_xml_smbios, fedora_vm_body, running_vm

pytestmark = [pytest.mark.post_upgrade, pytest.mark.gating]


@pytest.fixture()
def configmap_smbios_vm(namespace):
    name = "configmap-smbios-vm"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
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
        "sku": cnv_current_version,
    }
    return smbios_defaults


@pytest.mark.polarion("CNV-4346")
def test_cm_smbios_defaults(smbios_from_kubevirt_config, smbios_defaults):
    check_smbios_defaults(smbios_defaults=smbios_defaults, cm_values=smbios_from_kubevirt_config)


@pytest.mark.polarion("CNV-4325")
def test_vm_smbios_default_values(smbios_from_kubevirt_config, configmap_smbios_vm):
    check_vm_xml_smbios(
        vm=configmap_smbios_vm,
        cm_values=smbios_from_kubevirt_config,
    )

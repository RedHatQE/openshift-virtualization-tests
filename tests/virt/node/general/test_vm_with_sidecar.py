"""
VM with sidecar
"""

import shlex

import pytest
from pyhelper_utils.shell import run_ssh_commands

from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm


class FedoraVirtualMachineWithSideCar(VirtualMachineForTests):
    def __init__(self, name, namespace, interfaces=None, networks=None, client=None):
        super().__init__(
            name=name,
            namespace=namespace,
            interfaces=interfaces,
            networks=networks,
            client=client,
        )

    def to_dict(self):
        self.body = fedora_vm_body(name=self.name)
        super().to_dict()

        self.res["spec"]["template"]["metadata"].setdefault("annotations", {})
        self.res["spec"]["template"]["metadata"]["annotations"].update({
            "hooks.kubevirt.io/hookSidecars": '[{"args": ["--version", "v1alpha2"], '
            '"image": "quay.io/kubevirt/example-hook-sidecar:latest"}]',
            "smbios.vm.kubevirt.io/baseBoardManufacturer": "Radical Edward",
        })

        self.res["spec"]["template"]["metadata"].setdefault("labels", {})
        self.res["spec"]["template"]["metadata"]["labels"].update({"special": self.name})


@pytest.fixture()
def sidecar_vm(namespace, unprivileged_client):
    """Test VM with sidecar hook"""
    name = "vmi-with-sidecar-hook"
    with FedoraVirtualMachineWithSideCar(name=name, namespace=namespace.name, client=unprivileged_client) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.mark.parametrize(
    "enabled_featuregate_scope_function,",
    [
        pytest.param(
            "Sidecar",
            marks=pytest.mark.polarion("CNV-840"),
        ),
    ],
    indirect=True,
)
@pytest.mark.gating
def test_vm_with_sidecar_hook(enabled_featuregate_scope_function, sidecar_vm):
    """
    Test VM with sidecar hook, Install dmidecode with annotation
    smbios.vm.kubevirt.io/baseBoardManufacturer: "Radical Edward"
    And check that package includes manufacturer: "Radical Edward"
    """
    run_ssh_commands(
        host=sidecar_vm.ssh_exec,
        commands=shlex.split("sudo dmidecode -s baseboard-manufacturer | grep 'Radical Edward'\n"),
    )

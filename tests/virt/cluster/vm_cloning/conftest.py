import pytest

from utilities.virt import VirtualMachineForCloning, fedora_vm_body, running_vm


@pytest.fixture(scope="class")
def fedora_vm_for_cloning(request, namespace, cpu_for_migration):
    name = request.param["vm_name"]
    with VirtualMachineForCloning(
        name=name,
        namespace=namespace.name,
        body=fedora_vm_body(name=name),
        vm_labels=request.param.get("labels"),
        vm_annotations=request.param.get("annotations"),
        smbios_serial=request.param.get("smbios_serial"),
        cpu_model=cpu_for_migration,
    ) as vm:
        running_vm(vm=vm, wait_for_cloud_init=True)
        yield vm

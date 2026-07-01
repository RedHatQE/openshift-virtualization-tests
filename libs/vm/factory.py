from __future__ import annotations

from kubernetes.dynamic import DynamicClient
from pytest_testconfig import config as py_config

from libs.vm.spec import CPU, Devices, Domain, Memory, Metadata, Template, VMISpec, VMSpec
from libs.vm.vm import BaseVirtualMachine, container_image, containerdisk_storage
from utilities.constants import Images
from utilities.constants.architecture import MULTIARCH
from utilities.constants.images import OS_FLAVOR_FEDORA, ArchImages


def fedora_vm(
    namespace: str,
    name: str,
    client: DynamicClient,
    spec: VMSpec | None = None,
    vm_labels: dict[str, str] | None = None,
    vm_annotations: dict[str, str] | None = None,
) -> BaseVirtualMachine:
    spec = _fill_vm_spec_defaults(spec=spec)

    return BaseVirtualMachine(
        namespace=namespace,
        name=name,
        spec=spec,
        vm_labels=vm_labels,
        vm_annotations=vm_annotations,
        os_distribution=OS_FLAVOR_FEDORA,
        client=client,
    )


def fedora_image(arch: str | None = None) -> str:
    if arch:
        images = getattr(ArchImages, arch.upper())
    else:
        images = Images

    return container_image(base_image=images.Fedora.FEDORA_CONTAINER_IMAGE, arch=arch)


def _fill_vm_spec_defaults(spec: VMSpec | None) -> VMSpec:
    spec = spec or base_vmspec()

    vmi_spec = spec.template.spec

    if not vmi_spec.architecture and py_config.get("cluster_type") == MULTIARCH:
        cpu_arch = py_config.get("cpu_arch")
        vmi_spec.architecture = cpu_arch
    vmi_spec.domain.devices = vmi_spec.domain.devices or Devices(rng={})
    vmi_spec.domain.devices.disks = vmi_spec.domain.devices.disks or []
    vmi_spec.volumes = vmi_spec.volumes or []

    disk, volume = containerdisk_storage(image=fedora_image(arch=vmi_spec.architecture))
    vmi_spec.domain.devices.disks.insert(0, disk)
    vmi_spec.volumes.insert(0, volume)

    vmi_spec.domain.cpu = vmi_spec.domain.cpu or CPU(cores=1)
    vmi_spec.domain.memory = vmi_spec.domain.memory or Memory(guest="1Gi")

    return spec


def base_vmspec() -> VMSpec:
    return VMSpec(template=Template(metadata=Metadata(), spec=VMISpec(domain=Domain(devices=Devices()))))

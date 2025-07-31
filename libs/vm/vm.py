from __future__ import annotations

import uuid
from dataclasses import asdict
from typing import Any

from kubernetes.dynamic import DynamicClient
from ocp_resources.node import Node
from ocp_resources.resource import ResourceEditor
from ocp_resources.virtual_machine import VirtualMachine, VirtualMachineInstance
from pytest_testconfig import config as py_config

from libs.vm.spec import CloudInitNoCloud, ContainerDisk, Disk, SpecDisk, VMSpec, Volume
from utilities import infra
from utilities.constants import CLOUD_INIT_DISK_NAME
from utilities.infra import get_nodes_cpu_architecture
from utilities.network import IfaceNotFound
from utilities.virt import get_oc_image_info, vm_console_run_commands


class BaseVirtualMachine(VirtualMachine):
    """
    Virtual Machine object.
    """

    def __init__(
        self,
        namespace: str,
        name: str,
        spec: VMSpec,
        os_distribution: str,
        vm_labels: dict[str, str] | None = None,
        vm_annotations: dict[str, str] | None = None,
        client: DynamicClient | None = None,
    ) -> None:
        self._name = self._new_unique_name(prefix=name)
        self._spec = spec
        self._os_distribution = os_distribution
        vm_spec = asdict(obj=spec, dict_factory=self._filter_out_none_values)
        super().__init__(  # type: ignore[no-untyped-call]
            namespace=namespace,
            name=self._name,
            body={"spec": vm_spec},
            label=vm_labels,
            annotations=vm_annotations,
            client=client,
        )

    @staticmethod
    def _new_unique_name(prefix: str) -> str:
        return f"{prefix}-{uuid.uuid4().hex[:16]}"

    @staticmethod
    def _filter_out_none_values(data: list[tuple[str, Any]]) -> dict[str, Any]:
        return {key: val for (key, val) in data if val is not None}

    @property
    def login_params(self) -> dict[str, str]:
        return py_config["os_login_param"][self._os_distribution]

    def console(
        self,
        commands: list[str],
        timeout: int,
    ) -> dict[str, list[str]] | None:
        return vm_console_run_commands(vm=self, commands=commands, timeout=timeout)

    def wait_for_agent_connected(self) -> None:
        self.vmi.wait_for_condition(
            condition=VirtualMachineInstance.Condition.Type.AGENT_CONNECTED,
            status=VirtualMachineInstance.Condition.Status.TRUE,
        )

    def set_interface_state(self, network_name: str, state: str) -> None:
        if not self._spec.template.spec.domain.devices:
            raise IfaceNotFound(name=network_name)
        for interface in self._spec.template.spec.domain.devices.interfaces or []:
            if interface.name == network_name:
                interface.state = state
                break
        else:
            raise IfaceNotFound(name=network_name)

        devices = asdict(obj=self._spec.template.spec.domain.devices, dict_factory=self._filter_out_none_values)
        patches = {
            self: {"spec": {"template": {"spec": {"domain": {"devices": {"interfaces": devices["interfaces"]}}}}}}
        }
        ResourceEditor(patches=patches).update()


def container_image(base_image: str) -> str:
    pull_secret = infra.generate_openshift_pull_secret_file()
    image_info = get_oc_image_info(
        image=base_image,
        pull_secret=pull_secret,
        architecture=get_nodes_cpu_architecture(nodes=list(Node.get())),
    )
    return f"{base_image}@{image_info['digest']}"


def containerdisk_storage(image: str) -> tuple[SpecDisk, Volume]:
    name = "containerdisk"
    return SpecDisk(name=name, disk=Disk(bus="virtio")), Volume(name=name, containerDisk=ContainerDisk(image=image))


def cloudinitdisk_storage(data: CloudInitNoCloud) -> tuple[SpecDisk, Volume]:
    return SpecDisk(name=CLOUD_INIT_DISK_NAME, disk=Disk(bus="virtio")), Volume(
        name=CLOUD_INIT_DISK_NAME, cloudInitNoCloud=data
    )

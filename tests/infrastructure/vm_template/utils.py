"""Helper functions for VirtualMachineTemplate upgrade-continuity tests."""

import logging
from typing import TYPE_CHECKING, Any

from ocp_resources.virtual_machine import VirtualMachine

if TYPE_CHECKING:
    from kubernetes.dynamic import DynamicClient
    from ocp_resources.virtual_machine_template import VirtualMachineTemplate

LOGGER = logging.getLogger(__name__)


def process_and_create_vm(
    vmt: VirtualMachineTemplate,
    parameters: dict[str, Any] | None = None,
    namespace: str | None = None,
    client: DynamicClient | None = None,
    wait: bool = True,
) -> VirtualMachine:
    """
    Process the VirtualMachineTemplate and create the resulting VirtualMachine.

    Calls the template's ``process`` subresource to render a ``VirtualMachine`` spec, then
    deploys that VM in the cluster. The ``/process`` subresource does not set a namespace on
    the returned VM metadata, so the namespace is taken from the ``namespace`` argument,
    falling back to the template's own namespace (``vmt.namespace``).

    Args:
        vmt (VirtualMachineTemplate): The template to process and deploy.
        parameters (dict[str, Any] | None): Key-value pairs of template parameters to
            substitute, e.g. ``{"NAME": "my-vm"}``. Defaults to ``None`` (no substitutions,
            template defaults are used).
        namespace (str | None): Namespace in which to create the VirtualMachine. Defaults
            to the template's namespace (``vmt.namespace``).
        client (DynamicClient | None): Optional Kubernetes API client. Defaults to
            ``vmt.client``.
        wait (bool): Wait for the VirtualMachine resource to be created. Defaults to ``True``.

    Returns:
        VirtualMachine: The deployed VirtualMachine object.
    """
    LOGGER.info(f"Processing VirtualMachineTemplate {vmt.name} in namespace {vmt.namespace}")
    request_response = vmt.process(parameters=parameters, client=client)
    vm_dict: dict[str, Any] = request_response.to_dict()["virtualMachine"]
    vm_dict["metadata"]["namespace"] = namespace or vmt.namespace
    vm = VirtualMachine(kind_dict=vm_dict, client=client or vmt.client)
    LOGGER.info(f"Deploying VM {vm.name} in namespace {vm.namespace} from template {vmt.name}")
    vm.deploy(wait=wait)
    return vm

from typing import Any

from ocp_resources.virtual_machine import VirtualMachine
from ocp_resources.virtual_machine_template import VirtualMachineTemplate


def process_and_create_vm(
    vmt: VirtualMachineTemplate,
    parameters: dict[str, Any] | None = None,
    namespace: str | None = None,
    client: Any = None,
) -> VirtualMachine:
    """
    Process the VirtualMachineTemplate and create the resulting VirtualMachine.

    Calls :meth:`process` to render the template into a ``VirtualMachine`` spec,
    then deploys that VM in the cluster.  The ``/process`` subresource does not
    set a namespace on the returned VM metadata, so the namespace is taken from
    the ``namespace`` argument, falling back to the template's own namespace
    (``self.namespace``).

    Args:
        vmt (VirtualMachineTemplate): The template to process and deploy.
        parameters (dict[str, Any] | None): Key-value pairs of template parameters
            to substitute, e.g. ``{"NAME": "my-vm", "INSTANCETYPE": "u1.large"}``.
            Defaults to an empty dict (no substitutions).
        namespace (str | None): Namespace in which to create the VirtualMachine.
            Defaults to the template's namespace (``self.namespace``).
        client: Optional Kubernetes API client. Defaults to ``self.client``.

    Returns:
        VirtualMachine: The deployed :class:`~ocp_resources.virtual_machine.VirtualMachine`
        object.
    """
    processed = vmt.process(parameters=parameters, client=client)
    vm_dict: dict[str, Any] = processed["virtualMachine"]
    vm_dict["metadata"]["namespace"] = namespace or vmt.namespace
    vm = VirtualMachine(kind_dict=vm_dict, client=client or vmt.client)
    vm.deploy(wait=True)
    return vm

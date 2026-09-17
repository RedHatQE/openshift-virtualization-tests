"""Helper functions for VirtualMachineTemplate upgrade-continuity tests."""

from typing import TYPE_CHECKING, Any

from ocp_resources.virtual_machine import VirtualMachine
from ocp_resources.virtual_machine_cluster_instancetype import VirtualMachineClusterInstancetype
from ocp_resources.virtual_machine_cluster_preference import VirtualMachineClusterPreference

from utilities.storage import data_volume_template_with_source_ref_dict

if TYPE_CHECKING:
    from kubernetes.dynamic import DynamicClient
    from ocp_resources.data_source import DataSource
    from ocp_resources.virtual_machine_template import VirtualMachineTemplate


def vm_template_upgrade_virtual_machine_spec(data_source: DataSource, storage_class: str) -> dict[str, Any]:
    """Build the VirtualMachine spec rendered by the upgrade-continuity VirtualMachineTemplate.

    Args:
        data_source (DataSource): Golden image DataSource cloned into the rendered VM's disk.
        storage_class (str): Storage class for the rendered VM's DataVolume.

    Returns:
        dict[str, Any]: ``virtualMachine`` field for a VirtualMachineTemplate, parameterized
        with ``${NAME}``, ``${INSTANCETYPE}`` and ``${PREFERENCE}``.
    """
    return {
        "metadata": {"name": "${NAME}"},
        "spec": {
            "instancetype": {
                "kind": VirtualMachineClusterInstancetype.kind,
                "name": "${INSTANCETYPE}",
            },
            "preference": {
                "kind": VirtualMachineClusterPreference.kind,
                "name": "${PREFERENCE}",
            },
            "runStrategy": "Halted",
            "dataVolumeTemplates": [
                data_volume_template_with_source_ref_dict(
                    data_source=data_source,
                    storage_class=storage_class,
                    name="${NAME}",
                )
            ],
            "template": {
                "spec": {
                    "volumes": [
                        {
                            "name": "rootdisk",
                            "dataVolume": {
                                "name": "${NAME}",
                            },
                        }
                    ],
                }
            },
        },
    }


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
    request_response = vmt.process(parameters=parameters, client=client)
    vm_dict: dict[str, Any] = request_response.to_dict()["virtualMachine"]
    vm_dict["metadata"]["namespace"] = namespace or vmt.namespace
    vm = VirtualMachine(kind_dict=vm_dict, client=client or vmt.client)
    vm.deploy(wait=wait)
    return vm

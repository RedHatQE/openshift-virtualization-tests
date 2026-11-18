"""Helper functions for VirtualMachineTemplate upgrade-continuity tests."""

from typing import TYPE_CHECKING, Any

from ocp_resources.virtual_machine_cluster_instancetype import VirtualMachineClusterInstancetype
from ocp_resources.virtual_machine_cluster_preference import VirtualMachineClusterPreference

from utilities.storage import data_volume_template_with_source_ref_dict
from utilities.virt import VirtualMachineForTests

if TYPE_CHECKING:
    from ocp_resources.data_source import DataSource


def vm_template_upgrade_virtual_machine_spec(data_source: DataSource, storage_class: str | None) -> dict[str, Any]:
    """Build the VirtualMachine spec rendered by the upgrade-continuity VirtualMachineTemplate.

    Args:
        data_source (DataSource): Golden image DataSource cloned into the rendered VM's disk.
        storage_class (str | None): Storage class for the rendered VM's DataVolume. If `None`, use the cluster default.

    Returns:
        dict[str, Any]: ``virtualMachine`` field for a VirtualMachineTemplate, parameterized
        with ``${NAME}``, ``${INSTANCETYPE}`` and ``${PREFERENCE}``.
    """
    vm = VirtualMachineForTests(
        name="${NAME}",
        namespace=data_source.namespace,
        client=data_source.client,
        generate_unique_name=False,
        vm_instance_type=VirtualMachineClusterInstancetype(name="${INSTANCETYPE}", client=data_source.client),
        vm_preference=VirtualMachineClusterPreference(name="${PREFERENCE}", client=data_source.client),
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=data_source,
            storage_class=storage_class,
            name="${NAME}",
        ),
    )
    vm.to_dict()
    # The rendered VirtualMachineTemplate.spec.virtualMachine field takes only metadata/spec
    del vm.res["metadata"]["namespace"]
    return {"metadata": vm.res["metadata"], "spec": vm.res["spec"]}

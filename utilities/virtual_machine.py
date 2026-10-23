"""Helpers for building VirtualMachine specs used by VirtualMachineTemplate tests."""

from typing import Any

from ocp_resources.data_source import DataSource
from ocp_resources.virtual_machine_cluster_instancetype import VirtualMachineClusterInstancetype
from ocp_resources.virtual_machine_cluster_preference import VirtualMachineClusterPreference

from utilities.storage import data_volume_template_with_source_ref_dict
from utilities.virt import VirtualMachineForTests


def vm_template_upgrade_virtual_machine_spec(data_source: DataSource, storage_class: str | None) -> dict[str, Any]:
    """Build the ``virtualMachine`` field for a VirtualMachineTemplate.

    Produces a parameterized VM blueprint with ``${NAME}``, ``${INSTANCETYPE}`` and
    ``${PREFERENCE}`` placeholders and a DataVolume cloned from ``data_source``.

    Args:
        data_source (DataSource): Golden image DataSource cloned into the rendered VM's disk.
        storage_class (str | None): Storage class for the rendered VM's DataVolume. If None, use the cluster default.

    Returns:
        dict[str, Any]: ``virtualMachine`` field for a VirtualMachineTemplate, parameterized
        with ``${NAME}``, ``${INSTANCETYPE}`` and ``${PREFERENCE}``.
    """
    virtual_machine = VirtualMachineForTests(
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
    virtual_machine.to_dict()
    # The rendered VirtualMachineTemplate.spec.virtualMachine field takes only metadata/spec
    del virtual_machine.res["metadata"]["namespace"]
    return {"metadata": virtual_machine.res["metadata"], "spec": virtual_machine.res["spec"]}

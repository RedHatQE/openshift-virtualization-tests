"""VirtualMachineTemplate constants for test fixtures.

Covers parameter lists and virtual machine spec definitions used when
creating VirtualMachineTemplate resources in test fixtures.

Not here:
- Instance type or preference name strings → ``instance_types.py``
- OS flavor strings → ``images.py``
- Generic VM runtime configuration (eviction strategy, disk names, …) → ``virt.py``
"""

from ocp_resources.virtual_machine_cluster_instancetype import VirtualMachineClusterInstancetype
from ocp_resources.virtual_machine_cluster_preference import VirtualMachineClusterPreference

from utilities.constants.images import OS_FLAVOR_FEDORA
from utilities.constants.instance_types import U1_SMALL

# Parameter list whose defaults resolve to a structurally valid VM definition.
VALID_VM_TEMPLATE_PARAMETERS = [
    {
        "name": "NAME",
        "generate": "expression",
        "from": "vm-[a-z0-9]{8}",
        "description": "Unique VM name",
    },
    {
        "name": "INSTANCETYPE",
        "value": U1_SMALL,
        "description": "Instance type for the VM",
    },
    {
        "name": "PREFERENCE",
        "value": OS_FLAVOR_FEDORA,
        "description": "VM preference",
    },
]

# Virtual machine spec rendered by the valid VirtualMachineTemplate fixture.
VALID_VM_TEMPLATE_VIRTUAL_MACHINE = {
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
            {
                "metadata": {"name": "${NAME}"},
                "spec": {
                    "sourceRef": {
                        "kind": "DataSource",
                        "name": "rhel10",
                        "namespace": "openshift-virtualization-os-images",
                    },
                    "storage": {
                        "resources": {
                            "requests": {
                                "storage": "30Gi",
                            }
                        }
                    },
                },
            }
        ],
        "template": {
            "spec": {
                "architecture": "amd64",
                "domain": {
                    "devices": {
                        "autoattachPodInterface": False,
                    }
                },
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

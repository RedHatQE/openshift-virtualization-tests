"""VirtualMachineTemplate constants for the upgrade continuity tests.

Covers the parameter list and resource names used to create the VirtualMachineTemplate
and VirtualMachineTemplateRequest exercised in ``test_vm_template_upgrade.py``.

Not here:
- VM spec fragments rendered by the template -> built dynamically in ``utils.py``, since
  they depend on runtime fixture values (golden image DataSource, storage class)
"""

from utilities.constants.images import OS_FLAVOR_FEDORA
from utilities.constants.instance_types import U1_SMALL

VM_TEMPLATE_UPGRADE_TEMPLATE_NAME = "vm-template-upgrade"
VM_TEMPLATE_UPGRADE_REQUEST_NAME = "vm-template-upgrade-request"
VM_TEMPLATE_UPGRADE_VM_NAME = "vm-template-upgrade-vm"

# Parameter list whose defaults resolve to a structurally valid VM definition.
VM_TEMPLATE_UPGRADE_PARAMETERS = [
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

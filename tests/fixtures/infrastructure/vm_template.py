import pytest
from ocp_resources.virtual_machine_template import VirtualMachineTemplate

from utilities.constants.vm_template import VALID_VM_TEMPLATE_PARAMETERS, VALID_VM_TEMPLATE_VIRTUAL_MACHINE


@pytest.fixture()
def valid_vm_template(admin_client, namespace):
    """Create and yield a VirtualMachineTemplate with valid defaulted parameters.

    Creates a namespaced VirtualMachineTemplate whose parameter defaults
    (a generated VM name, an instance type, and a preference) all resolve to a
    structurally valid VM definition accepted by the admission webhook.
    The template is deleted from the cluster when the fixture tears down.

    Args:
        admin_client: Kubernetes client with cluster-admin privileges.
        namespace: Namespace object that determines where the template is created.

    Yields:
        VirtualMachineTemplate: The created template resource.
    """
    with VirtualMachineTemplate(
        client=admin_client,
        name="valid-test-template",
        namespace=namespace.name,
        parameters=VALID_VM_TEMPLATE_PARAMETERS,
        virtual_machine=VALID_VM_TEMPLATE_VIRTUAL_MACHINE,
    ) as vm_template:
        yield vm_template

"""Helper functions for VM primary network attachment tests."""

import logging

from ocp_resources.resource import ResourceEditor

from libs.vm.vm import BaseVirtualMachine

LOGGER = logging.getLogger(__name__)


def assert_restart_required_condition_not_set(vm: BaseVirtualMachine) -> None:
    """
    Assert that the RestartRequired condition is not set on the VM.

    The condition is considered not set if either:
    - The condition does not exist
    - The condition exists but its status is False

    Args:
        vm: The VM to check

    Raises:
        AssertionError: If the RestartRequired condition exists with status True
    """
    conditions = vm.instance.status.conditions or []
    restart_required_conditions = [condition for condition in conditions if condition["type"] == "RestartRequired"]

    if restart_required_conditions:
        condition = restart_required_conditions[0]
        assert condition["status"] == vm.Condition.Status.FALSE, (
            f"VM {vm.name} has RestartRequired condition set to {condition['status']}: {condition}"
        )


def add_pod_interface_and_network(vm: BaseVirtualMachine) -> None:
    """
    Add a pod interface and network to a VM.

    Args:
        vm: The VM to add the pod interface and network to
    """
    LOGGER.info(f"Adding pod interface and network to VM {vm.name}")
    patch = {
        vm: {
            "spec": {
                "template": {
                    "spec": {
                        "domain": {
                            "devices": {
                                "interfaces": [
                                    {
                                        "name": "default",
                                        "masquerade": {},
                                    }
                                ]
                            }
                        },
                        "networks": [
                            {
                                "name": "default",
                                "pod": {},
                            }
                        ],
                    }
                }
            }
        }
    }
    ResourceEditor(patches=patch).update()

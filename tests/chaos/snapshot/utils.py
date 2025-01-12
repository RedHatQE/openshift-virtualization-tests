from ocp_resources.virtual_machine_snapshot import VirtualMachineSnapshot

from utilities.constants import TIMEOUT_4MIN, TIMEOUT_5MIN


class VirtualMachineSnapshotWithDeadline(VirtualMachineSnapshot):
    def __init__(
        self,
        name=None,
        namespace=None,
        vm_name=None,
        client=None,
        teardown=True,
        yaml_file=None,
        delete_timeout=TIMEOUT_4MIN,
        failure_deadline=TIMEOUT_5MIN,
    ):
        super().__init__(
            name=name,
            namespace=namespace,
            vm_name=vm_name,
            client=client,
            teardown=teardown,
            yaml_file=yaml_file,
            delete_timeout=delete_timeout,
        )
        self.failure_deadline = f"{failure_deadline}s"

    def to_dict(self):
        super().to_dict()
        self.res["spec"]["failureDeadline"] = self.failure_deadline

from pyVim.connect import Disconnect, SmartConnect
from pyVmomi import vim
from timeout_sampler import retry


class VmNotFoundError(Exception):
    pass


class SourceHypervisorProvider:
    """A simple source provider context manager to manage VMs. Supports only basic operations: power on/off."""

    def __init__(self, host: str, username: str, password: str) -> None:
        self.host = host
        self.username = username
        self.password = password

    def __enter__(self):
        self._client = SmartConnect(
            host=self.host,
            user=self.username,
            pwd=self.password,
            disableSslCertValidation=True,
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        Disconnect(si=self._client)

    @property
    def content(self) -> vim.ServiceInstanceContent:
        return self._client.RetrieveContent()

    def power_on_vm(self, vm_name: str) -> None:
        vm = self._get_vm_by_name(name=vm_name)
        vm.PowerOn()
        self._check_for_vm_status(vm=vm, status=vim.VirtualMachine.PowerState.poweredOn)
        self._check_for_ip_obtained(vm=vm)

    def power_off_vm(self, vm_name: str) -> None:
        vm = self._get_vm_by_name(name=vm_name)
        vm.PowerOff()
        self._check_for_vm_status(vm=vm, status=vim.VirtualMachine.PowerState.poweredOff)

    def _get_vm_by_name(self, name: str) -> vim.VirtualMachine:
        for dc in self.content.rootFolder.childEntity:
            for vm in dc.vmFolder.childEntity:
                if vm.name == name:
                    return vm
        raise VmNotFoundError(f"VM '{name}' not found")

    @staticmethod
    @retry(wait_timeout=120, sleep=5, exceptions_dict={})
    def _check_for_vm_status(vm: vim.VirtualMachine, status: str) -> bool:
        return vm.runtime.powerState == status

    @staticmethod
    @retry(wait_timeout=120, sleep=5, exceptions_dict={})
    def _check_for_ip_obtained(vm: vim.VirtualMachine) -> bool:
        return vm.guest.ipAddress is not None

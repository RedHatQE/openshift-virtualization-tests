import logging
from functools import cache

from pyVim.connect import Disconnect, SmartConnect
from pyVmomi import vim
from timeout_sampler import TimeoutExpiredError, retry

LOGGER = logging.getLogger(__name__)


class VmNotFoundError(Exception):
    pass


class IfaceNotFoundError(Exception):
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

    def power_on_vm(self, vm_name: str) -> vim.VirtualMachine:
        LOGGER.info(f"Powering on VM '{vm_name}'")
        vm = self.get_vm_by_name(name=vm_name)
        vm.PowerOn()
        try:
            self._check_for_vm_status(vm=vm, status=vim.VirtualMachine.PowerState.poweredOn)
            self._check_for_ip_obtained(vm=vm)
        except TimeoutExpiredError:
            LOGGER.error(f"Timeout while trying to power on VM '{vm_name}' or waiting for IP address assignment")
            raise

        LOGGER.info(f"Successfully powered on VM '{vm_name}'")
        return vm

    def power_off_vm(self, vm_name: str) -> None:
        LOGGER.info(f"Powering off VM '{vm_name}'")
        vm = self.get_vm_by_name(name=vm_name)
        vm.PowerOff()
        try:
            self._check_for_vm_status(vm=vm, status=vim.VirtualMachine.PowerState.poweredOff)
        except TimeoutExpiredError:
            LOGGER.error(f"Timeout while trying to power off VM '{vm_name}'")
            raise

    def get_vm_by_name(self, name: str) -> vim.VirtualMachine:
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


@cache
def extract_vm_primary_network_data(vm: vim.VirtualMachine) -> tuple[str, str]:
    for device in vm.config.hardware.device:
        if isinstance(device, vim.vm.device.VirtualEthernetCard):
            for net in getattr(vm.guest, "net", []):
                if net.macAddress == device.macAddress and net.ipAddress:
                    return net.macAddress, net.ipAddress[0]
    raise IfaceNotFoundError("No network interface found in the VM or no IP address assigned.")

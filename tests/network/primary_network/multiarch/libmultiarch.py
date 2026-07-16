from libs.net.vmspec import lookup_iface_status_ip
from libs.vm.vm import BaseVirtualMachine
from tests.network.libs.connectivity import build_ping_command


def ping_between_vms(source_vm: BaseVirtualMachine, destination_vm: BaseVirtualMachine, ip_family: int = 4) -> None:
    """Ping from source VM to destination VM over the pod network.

    Args:
        source_vm: VM that initiates the ping.
        destination_vm: VM whose pod network IP is the ping target.
        ip_family: IP version to use (4 or 6).
    """
    dst_ip = lookup_iface_status_ip(vm=destination_vm, iface_name="default", ip_family=ip_family)
    ping_cmd = build_ping_command(dst_ip=str(dst_ip), count=10, timeout=10)
    source_vm.console(commands=[ping_cmd], timeout=20)

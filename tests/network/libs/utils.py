from utilities.virt import vm_console_run_commands


def ping_via_console(src_vm, dst_vm):
    """Ping between VMs via console.

    Pings from a source VM to a destination VM over the primary interface's IP.
    This method verifies console-based network connectivity by checking for a
    successful (zero) exit status of the ping command, avoiding SSH-related masking issues.

    Args:
        src_vm (VirtualMachineForTests | BaseVirtualMachine): Source virtual machine
            used to execute the ping.
        dst_vm (VirtualMachineForTests | BaseVirtualMachine): Destination virtual machine
            whose primary interface IP is pinged.

    Raises:
        CommandExecFailed: If the ping command fails, times out, or the
            console session ends unexpectedly.
    """
    dst_ip = dst_vm.vmi.interfaces[0]["ipAddress"]

    vm_console_run_commands(
        vm=src_vm,
        commands=[f"ping {dst_ip} -c 10 -w 10"],
        timeout=10,
    )

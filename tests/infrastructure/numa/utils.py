from utilities.virt import VirtualMachineForTests


def assert_qos_guaranteed(vm: VirtualMachineForTests) -> None:
    """
    Assert that the VM's virt-launcher pod is running with QoS class 'Guaranteed'.
    """
    qos = vm.vmi.virt_launcher_pod.instance.status.qosClass
    assert qos == "Guaranteed", f"QoS class is {qos}"

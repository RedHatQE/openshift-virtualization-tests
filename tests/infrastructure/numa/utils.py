from kubernetes.dynamic import DynamicClient

from utilities.virt import VirtualMachineForTests


def assert_qos_guaranteed(vm: VirtualMachineForTests, admin_client: DynamicClient) -> None:
    """
    Assert that the VM's virt-launcher pod is running with QoS class 'Guaranteed'.
    """
    qos = vm.vmi.get_virt_launcher_pod(privileged_client=admin_client).instance.status.qosClass
    assert qos == "Guaranteed", f"QoS class is {qos}"

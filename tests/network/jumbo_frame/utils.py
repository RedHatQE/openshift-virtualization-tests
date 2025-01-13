from contextlib import contextmanager

from utilities.network import compose_cloud_init_data_dict
from utilities.virt import VirtualMachineForTests, fedora_vm_body


@contextmanager
def create_vm_for_jumbo_test(
    index,
    namespace_name,
    client,
    cloud_init_data=None,
    networks=None,
    node_selector=None,
):
    vm_name = f"vm-jumbo-pod-{index}"

    with VirtualMachineForTests(
        namespace=namespace_name,
        name=vm_name,
        body=fedora_vm_body(name=vm_name),
        node_selector=node_selector,
        cloud_init_data=cloud_init_data,
        networks=networks,
        interfaces=networks.keys() if networks else None,
        client=client,
    ) as vm:
        yield vm


def cloud_init_data_for_secondary_traffic(index):
    network_data_data = {
        "ethernets": {
            "eth1": {"addresses": [f"10.200.0.{index}/24"]},
        }
    }

    cloud_init_data = compose_cloud_init_data_dict(
        network_data=network_data_data,
    )
    return cloud_init_data

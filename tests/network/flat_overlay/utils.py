import logging
import shlex

from ocp_resources.custom_resource_definition import CustomResourceDefinition
from ocp_resources.resource import NamespacedResource, Resource
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.network.flat_overlay.constants import (
    HTTP_SUCCESS_RESPONSE_STR,
)
from tests.network.libs.ip import random_ipv4_address
from utilities.constants import TIMEOUT_3MIN, TIMEOUT_5SEC
from utilities.exceptions import ResourceValueError
from utilities.infra import ExecCommandOnPod, get_node_selector_dict
from utilities.network import compose_cloud_init_data_dict
from utilities.virt import (
    VirtualMachineForTests,
    fedora_vm_body,
    fetch_pid_from_linux_vm,
    vm_console_run_commands,
)

LOGGER = logging.getLogger(__name__)


def create_flat_overlay_vm(
    vm_name,
    namespace_name,
    nad_name,
    unprivileged_client,
    host_ip_suffix,
    worker_node_hostname=None,
):
    networks = {nad_name: nad_name}
    network_data = {
        "ethernets": {
            "eth1": {"addresses": [f"{random_ipv4_address(net_seed=0, host_address=host_ip_suffix)}/24"]},
        }
    }
    cloud_init_data = compose_cloud_init_data_dict(network_data=network_data)
    with VirtualMachineForTests(
        namespace=namespace_name,
        name=vm_name,
        networks=networks,
        interfaces=networks.keys(),
        client=unprivileged_client,
        body=fedora_vm_body(name=vm_name),
        cloud_init_data=cloud_init_data,
        node_selector=get_node_selector_dict(node_selector=worker_node_hostname),
    ) as vm:
        vm.start(wait=True)
        vm.wait_for_agent_connected()
        yield vm


def get_vm_kubevirt_domain_label(vm):
    kubevirt_domain = f"{Resource.ApiGroup.KUBEVIRT_IO}/domain"
    kubevirt_value = vm.instance.spec.template.metadata.labels.get(kubevirt_domain)
    if kubevirt_value:
        return {kubevirt_domain: kubevirt_value}
    raise ResourceValueError(f"{kubevirt_domain} not found in vm's {vm.name} labels")


def create_ip_block(ip_address, ingress=True):
    network_direction = "from" if ingress else "to"
    return [{network_direction: [{"ipBlock": {"cidr": ip_address}}]}]


def wait_for_multi_network_policy_resources(client, deploy_mnp_crd=False):
    sample = None
    consecutive_check = 0
    mnp_crd = CustomResourceDefinition(
        name=f"multi-networkpolicies.{NamespacedResource.ApiGroup.K8S_CNI_CNCF_IO}", client=client
    )
    try:
        sampler = TimeoutSampler(
            wait_timeout=TIMEOUT_3MIN,
            sleep=TIMEOUT_5SEC,
            func=lambda: mnp_crd.exists,
        )
        for sample in sampler:
            if deploy_mnp_crd == bool(sample):
                # We should make sure that the change in the MNP CRD is stable
                consecutive_check += 1
                if consecutive_check == 3:
                    return
    except TimeoutExpiredError:
        LOGGER.error(
            f"Value for deploying the multi-networkpolicies crd is {deploy_mnp_crd}, but the CRD status doesn't match."
        )
        raise


def get_vm_connection_reply(
    source_vm,
    dst_ip,
    port,
):
    rc, out, _ = source_vm.ssh_exec.run_command(
        command=shlex.split(f"echo -e ' GET http://{dst_ip}:{port} HTTP/1.0\n\n' | nc {dst_ip} {port} -d 1")
    )
    assert not rc, "Could not establish a netcat connection"
    return out.strip()


def start_nc_response_on_vm(flat_l2_port, vm, num_connections):
    vm_console_run_commands(
        vm=vm,
        commands=[
            f'for i in {{1..{num_connections}}}; do echo -e "{HTTP_SUCCESS_RESPONSE_STR}-$i\n\n" | nc '
            f"-lp {flat_l2_port}; done &"
        ],
        return_code_validation=False,
    )
    fetch_pid_from_linux_vm(vm=vm, process_name="nc")


def is_port_number_available(
    workers_utility_pods,
    worker_node1,
    port,
):
    port_in_use = ExecCommandOnPod(utility_pods=workers_utility_pods, node=worker_node1).exec(
        command=f"ss -tulnap | grep {port}",
        ignore_rc=True,  # return value should be 1 if no socket was found
    )
    return not port_in_use


class NoAvailablePortError(Exception):
    pass

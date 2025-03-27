import logging
import shlex
from collections import OrderedDict

import pexpect
from kubernetes.dynamic.exceptions import ResourceNotFoundError
from ocp_resources.deployment import Deployment
from ocp_resources.node_network_state import NodeNetworkState
from ocp_resources.service import Service
from ocp_resources.service_mesh_member_roll import ServiceMeshMemberRoll
from pyhelper_utils.shell import run_ssh_commands
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.network.constants import BRCNV, SERVICE_MESH_PORT
from utilities import console
from utilities.constants import (
    IPV4_STR,
    ISTIO_SYSTEM_DEFAULT_NS,
    OS_FLAVOR_FEDORA,
    SSH_PORT_22,
    TIMEOUT_1MIN,
    TIMEOUT_2MIN,
    TIMEOUT_10SEC,
)
from utilities.network import (
    compose_cloud_init_data_dict,
    get_ip_from_vm_or_virt_handler_pod,
    get_vmi_ip_v4_by_name,
    ping,
)
from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm

LOGGER = logging.getLogger(__name__)
DHCP_SERVICE_RESTART = "sudo systemctl start dhcpd"
DHCP_SERVER_CONF_FILE = """
cat <<EOF >> /etc/dhcp/dhcpd.conf
default-lease-time 3600;
max-lease-time 7200;
authoritative;
subnet {DHCP_IP_SUBNET}.0 netmask 255.255.255.0 {{
option subnet-mask 255.255.255.0;
range {DHCP_IP_RANGE_START} {DHCP_IP_RANGE_END};
}}
EOF
"""
SERVICE_MESH_VM_MEMORY_REQ = "128M"
SERVICE_MESH_INJECT_ANNOTATION = "sidecar.istio.io/inject"


class ServiceMeshDeploymentService(Service):
    def __init__(self, app_name, namespace, port, port_name=None):
        super().__init__(
            name=app_name,
            namespace=namespace,
        )
        self.port = port
        self.app_name = app_name
        self.port_name = port_name

    def to_dict(self):
        super().to_dict()
        self.res.setdefault("spec", {})
        self.res["spec"]["selector"] = {"app": self.app_name}
        self.res["spec"]["ports"] = [
            {
                "port": self.port,
                "protocol": "TCP",
            },
        ]
        if self.port_name:
            self.res["spec"]["ports"][0]["name"] = self.port_name


class ServiceMeshMemberRollForTests(ServiceMeshMemberRoll):
    def __init__(
        self,
        members,
    ):
        """
        Service Mesh Member Roll creation
        Args:
            members (list): Namespaces to be added to Service Mesh
        """
        super().__init__(
            name="default",
            namespace=ISTIO_SYSTEM_DEFAULT_NS,
        )
        self.members = members

    def to_dict(self):
        super().to_dict()
        self.res["spec"] = {"members": self.members}


class FedoraVirtualMachineForServiceMesh(VirtualMachineForTests):
    def __init__(
        self,
        name,
        namespace,
        client,
    ):
        """
        Fedora VM Creation. Used for Service Mesh tests
        """

        super().__init__(
            name=name, namespace=namespace, client=client, os_flavor=OS_FLAVOR_FEDORA, body=fedora_vm_body(name=name)
        )

    def to_dict(self):
        super().to_dict()
        self.res["spec"]["template"]["metadata"].setdefault("annotations", {})
        self.res["spec"]["template"]["metadata"]["annotations"] = {
            SERVICE_MESH_INJECT_ANNOTATION: "true",
        }


class ServiceMeshDeployments(Deployment):
    def __init__(
        self,
        name,
        namespace,
        version,
        image,
        replicas=1,
        command=None,
        strategy=None,
        service_account=False,
        policy="Always",
        service_port=None,
        host=None,
        port=None,
        http_readiness_probe=False,
    ):
        self.name = f"{name}-{version}-dp"

        template = {}
        template.setdefault("metadata", {})
        selector = {
            "matchLabels": {
                "app": name,
                "version": version,
            },
        }

        super().__init__(name=self.name, namespace=namespace, template=template, selector=selector)
        self.version = version
        self.replicas = replicas
        self.image = image
        self.strategy = strategy
        self.service_account = service_account
        self.policy = policy
        self.port = port
        self.app_name = name
        self.command = command
        self.service_port = service_port
        self.host = host
        self.http_readiness_probe = http_readiness_probe

    def to_dict(self):
        super().to_dict()
        self.res.setdefault("spec", {})
        self.res["spec"]["replicas"] = self.replicas
        self.res["spec"]["selector"] = self.selector
        self.res["spec"].setdefault("template", {})
        self.res["spec"]["template"] = self.template
        self.res["spec"]["template"]["metadata"]["annotations"] = {SERVICE_MESH_INJECT_ANNOTATION: "true"}
        self.res["spec"]["template"]["metadata"]["labels"] = {
            "app": self.app_name,
            "version": self.version,
        }
        self.res["spec"]["template"].setdefault("spec", {})
        self.res["spec"]["template"]["spec"]["containers"] = [
            {
                "image": self.image,
                "imagePullPolicy": self.policy,
                "name": self.name,
            }
        ]
        self.res["spec"]["template"]["spec"]["restartPolicy"] = "Always"
        if self.strategy:
            self.res["spec"]["strategy"] = self.strategy
        if self.service_account:
            self.res["spec"]["template"]["spec"]["serviceAccountName"] = self.app_name
        if self.command:
            self.res["spec"]["template"]["spec"]["containers"][0]["command"] = self.command
        if self.port:
            self.res["spec"]["template"]["spec"]["containers"][0]["ports"] = [{"containerPort": self.port}]
        if self.http_readiness_probe:
            self.res["spec"]["template"]["spec"]["containers"][0].setdefault("readinessProbe", {})
            self.res["spec"]["template"]["spec"]["containers"][0]["readinessProbe"] = {
                "httpGet": {
                    "port": self.service_port,
                    "initialDelaySeconds": TIMEOUT_10SEC,
                    "periodSeconds": TIMEOUT_10SEC,
                    "timeout seconds": TIMEOUT_1MIN,
                },
            }


def assert_no_ping(src_vm, dst_ip, packet_size=None, count=None):
    assert ping(src_vm=src_vm, dst_ip=dst_ip, packet_size=packet_size, count=count) == 100


def update_cloud_init_extra_user_data(cloud_init_data, cloud_init_extra_user_data):
    for key, val in cloud_init_extra_user_data.items():
        if key not in cloud_init_data:
            cloud_init_data.update(cloud_init_extra_user_data)
        else:
            cloud_init_data[key] = cloud_init_data[key] + val


def wait_for_address_on_iface(worker_pod, iface_name):
    """
    This function returns worker's ip else throws 'resources.utils.TimeoutExpiredError: Timed Out:
    if function passed in func argument failed.
    """
    sample = None
    log = "Worker ip address for {iface_name} : {sample}"
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_2MIN,
        sleep=1,
        func=NodeNetworkState(worker_pod.node.name).ipv4,
        iface=iface_name,
    )
    try:
        for sample in samples:
            if sample:
                LOGGER.info(log.format(iface_name=iface_name, sample=sample))
                return sample
    except TimeoutExpiredError:
        LOGGER.error(log.format(iface_name=iface_name, sample=sample))
        raise


def assert_ssh_alive(ssh_vm, src_ip):
    """
    Check the ssh process is alive

    Args:
        ssh_vm (VirtualMachine): VM to ssh, this is the dst VM of run_ssh_in_background().
        src_ip (str): The IP of the src VM, this is the IP of the src VM of run_ssh_in_background().

    Raises:
        TimeoutExpiredError: When ssh process is not alive.
    """
    sampler = TimeoutSampler(
        wait_timeout=30,
        sleep=1,
        func=run_ssh_commands,
        host=ssh_vm.ssh_exec,
        commands=[shlex.split(f"sudo ss -o state established '( sport = 22 ) and dst = {src_ip}' --no-header")],
    )
    try:
        for sample in sampler:
            if sample:
                LOGGER.info(f"SSH connection from {src_ip} to {ssh_vm.name} is alive")
                return
    except TimeoutExpiredError:
        LOGGER.error(f"SSH connection from {src_ip} is not alive")
        raise


def run_ssh_in_background(nad, src_vm, dst_vm, dst_vm_user, dst_vm_password):
    """
    Start ssh connection to the vm
    """
    dst_ip = get_vmi_ip_v4_by_name(vm=dst_vm, name=nad.name)
    src_ip = str(get_vmi_ip_v4_by_name(vm=src_vm, name=nad.name))
    LOGGER.info(f"Start ssh connection to {dst_vm.name} from {src_vm.name}")
    run_ssh_commands(
        host=src_vm.ssh_exec,
        commands=[
            shlex.split(
                f"sshpass -p {dst_vm_password} ssh -o 'StrictHostKeyChecking no' "
                f"{dst_vm_user}@{dst_ip} 'sleep 99999' &>1 &"
            )
        ],
    )

    assert_ssh_alive(ssh_vm=dst_vm, src_ip=src_ip)


def assert_nncp_successfully_configured(nncp):
    successfully_configured = nncp.Conditions.Reason.SUCCESSFULLY_CONFIGURED
    sampler = TimeoutSampler(
        wait_timeout=TIMEOUT_1MIN,
        sleep=1,
        func=lambda: nncp.status,
    )
    try:
        for sample in sampler:
            if sample == successfully_configured:
                return

    except TimeoutExpiredError:
        LOGGER.error(f"{nncp.name} is not {successfully_configured}, but rather {nncp.status}.")
        raise


def authentication_request(vm, expected_output, **kwargs):
    """
    Return server response to a request sent from VM console. This request allows testing client authentication.

    Args:
        vm (VirtualMachine): VM that will be used for console connection
        expected_output (str): The expected response from the server

    Kwargs: ( Used to allow passing args from wait_service_mesh_components_convergence in service_mesh/conftest)
        service (str): target svc dns name

    Returns:
        str: Server response
    """
    return verify_console_command_output(
        vm=vm,
        command=f"curl http://{kwargs['service']}:{SERVICE_MESH_PORT}/ip",
        expected_output=expected_output,
    )


def assert_service_mesh_request(expected_output, request_response):
    assert expected_output in request_response, (
        f"Server response error.Expected output - {expected_output}received - {request_response}"
    )


def assert_authentication_request(vm, service_app_name):
    # Envoy proxy IP
    expected_output = "127.0.0.6"
    request_response = authentication_request(
        vm=vm,
        service=service_app_name,
        expected_output=expected_output,
    )
    assert_service_mesh_request(expected_output=expected_output, request_response=request_response)


def verify_console_command_output(
    vm,
    command,
    expected_output,
    timeout=TIMEOUT_1MIN,
):
    """
    Run a list of commands inside a VM and check for expected output.
    """
    with console.Console(vm=vm) as vmc:
        LOGGER.info(f"Execute {command} on {vm.name}")
        try:
            vmc.sendline(command)
            vmc.expect(expected_output, timeout=timeout)
            return expected_output
        except pexpect.exceptions.TIMEOUT:
            return vmc.before


def vm_for_brcnv_tests(
    vm_name,
    namespace,
    unprivileged_client,
    nads,
    address_suffix,
    node_selector=None,
):
    vm_name = f"{BRCNV}-{vm_name}"
    networks = OrderedDict()
    network_data = {"ethernets": {}}
    for idx, nad in enumerate(nads, start=1):
        networks[nad.name] = nad.name
        network_data["ethernets"][f"eth{idx}"] = {"addresses": [f"10.0.20{idx}.{address_suffix}/24"]}
    cloud_init_data = compose_cloud_init_data_dict(network_data=network_data)

    with VirtualMachineForTests(
        namespace=namespace.name,
        name=vm_name,
        body=fedora_vm_body(name=vm_name),
        networks=networks,
        interfaces=networks.keys(),
        node_selector=node_selector,
        cloud_init_data=cloud_init_data,
        client=unprivileged_client,
    ) as vm:
        running_vm(vm=vm)
        yield vm


def get_vlan_index_number(vlans_list):
    yield from vlans_list
    raise ValueError(f"vlans list is exhausted. Current list size is {len(vlans_list)} and all vlans are in use.")


def get_destination_ip_address(destination_vm):
    dst_ip = get_ip_from_vm_or_virt_handler_pod(
        family=IPV4_STR,
        vm=destination_vm,
    )
    assert dst_ip, f"Cannot get valid IP address from {destination_vm.name}."

    return dst_ip


def basic_expose_command(
    resource_name,
    svc_name,
    resource="vm",
    port="27017",
    target_port=SSH_PORT_22,
    service_type="NodePort",
    protocol="TCP",
):
    return (
        f"expose {resource} {resource_name} --port={port} --target-port="
        f"{target_port} --type={service_type} --name={svc_name} --protocol={protocol}"
    )


def get_service(name, namespace):
    service = Service(name=name, namespace=namespace)
    if service.exists:
        return service

    raise ResourceNotFoundError(f"Service {name}.")

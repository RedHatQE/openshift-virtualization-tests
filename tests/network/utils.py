import logging
import shlex

from ocp_resources.deployment import Deployment
from ocp_resources.node_network_state import NodeNetworkState
from ocp_resources.service import Service
from pyhelper_utils.shell import run_ssh_commands
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from libs.net.vmspec import lookup_iface_status_ip
from utilities.constants import (
    IPV4_STR,
    OS_FLAVOR_FEDORA,
    TIMEOUT_1MIN,
    TIMEOUT_2MIN,
    TIMEOUT_10SEC,
)
from utilities.network import (
    get_ip_from_vm_or_virt_handler_pod,
    ping,
)
from utilities.virt import VirtualMachineForTests, fedora_vm_body

LOGGER = logging.getLogger(__name__)
SERVICE_MESH_INJECT_ANNOTATION = "sidecar.istio.io/inject"


class ServiceMeshDeploymentService(Service):
    def __init__(self, app_name, namespace, port, client, port_name=None):
        super().__init__(
            name=app_name,
            namespace=namespace,
            client=client,
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
        client,
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

        super().__init__(name=self.name, namespace=namespace, template=template, selector=selector, client=client)
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
        func=NodeNetworkState(name=worker_pod.node.name, client=worker_pod.client).ipv4,
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
    dst_ip = lookup_iface_status_ip(vm=dst_vm, iface_name=nad.name, ip_family=4)
    src_ip = str(lookup_iface_status_ip(vm=src_vm, iface_name=nad.name, ip_family=4))
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

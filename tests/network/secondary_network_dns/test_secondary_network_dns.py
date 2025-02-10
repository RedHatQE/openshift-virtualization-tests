"""Test module for the KSD feature - Kubernetes Secondary network DNS."""

import logging
import shlex
import subprocess
from base64 import b64decode

import pytest
import yaml
from kubernetes.dynamic.exceptions import ResourceNotFoundError
from ocp_resources.dns_config_openshift_io import DNS
from ocp_resources.network_addons_config import NetworkAddonsConfig
from ocp_resources.secret import Secret
from openstack import connection, exceptions
from openstack.exceptions import ResourceNotFound
from pyhelper_utils.shell import run_command
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.network.utils import basic_expose_command, get_service
from utilities.constants import (
    CLUSTER,
    LINUX_BRIDGE,
    TIMEOUT_1SEC,
    TIMEOUT_5SEC,
    TIMEOUT_15SEC,
    TIMEOUT_30SEC,
    TIMEOUT_40SEC,
)
from utilities.exceptions import ServicePortNotFoundError
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.infra import ExecCommandOnPod, get_deployment_by_name, get_node_selector_dict
from utilities.network import (
    compose_cloud_init_data_dict,
    network_device,
    network_nad,
)
from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm

pytestmark = pytest.mark.usefixtures(
    "enabled_kube_secondary_dns_feature_gate",
    "exposed_kubernetes_secondary_dns_service",
)

LOGGER = logging.getLogger(__name__)
KUBERNETES_SECONDARY_DNS_SERVICE_PORT = 31111
KUBERNETES_SECONDARY_DNS_SERVICE_NAME = "dns-nodeport"


def secondary_network_in_nslookup_output(
    kubernetes_secondary_dns_service_port_number,
    secondary_network_fqdn,
    cluster_base_domain,
    kubernetes_secondary_dns_vm_secondary_interface_ip,
):
    # It can take up to 30 seconds for the IP address to be returned in the nslookup command (even if it already
    # exists in the zones file):
    # wildcard.apps.{cluster_base_domain} is the API access from outside the cluster
    sampler = TimeoutSampler(
        wait_timeout=TIMEOUT_40SEC,
        sleep=TIMEOUT_5SEC,
        check=False,
        func=run_command,
        command=shlex.split(
            f"nslookup -port={kubernetes_secondary_dns_service_port_number} {secondary_network_fqdn} wildcard.apps."
            f"{cluster_base_domain}"
        ),
    )
    sample = None
    try:
        for sample in sampler:
            if kubernetes_secondary_dns_vm_secondary_interface_ip in sample[1]:
                return True
    except (TimeoutExpiredError, subprocess.CalledProcessError):
        logging.error(
            f"VM IP address {kubernetes_secondary_dns_vm_secondary_interface_ip} "
            f"was not found in nslookup output:\n{sample}"
        )
        raise


@pytest.fixture(scope="module")
def openstack_cloud_credentials_secret(is_psi_cluster):
    if is_psi_cluster:
        secret_name = "openstack-cloud-credentials"
        secret = Secret(
            namespace="openshift-cloud-controller-manager",
            name=secret_name,
        )
        if secret.exists:
            return secret
        raise ResourceNotFoundError(f"Secret {secret_name} was not found.")
    return None


@pytest.fixture(scope="module")
def openstack_connection(openstack_cloud_credentials_secret):
    if openstack_cloud_credentials_secret:
        secret_dict_auth = yaml.safe_load(
            b64decode(openstack_cloud_credentials_secret.instance["data"]["clouds.yaml"]).decode(encoding="utf-8")
        )["clouds"]["openstack"]["auth"]
        openstack_connection = connection.Connection(
            auth_url=secret_dict_auth["auth_url"],
            project_name=secret_dict_auth["project_name"],
            username=secret_dict_auth["username"],
            password=secret_dict_auth["password"],
            user_domain_name=secret_dict_auth["user_domain_name"],
            project_domain_name=secret_dict_auth["project_domain_name"],
        )
        assert openstack_connection.session.get_token(), "Openstack connection has failed to create - no valid token."
        return openstack_connection
    return None


@pytest.fixture(scope="module")
def network_security_rule_for_virtual_workers(
    worker_machine1,
    openstack_connection,
    kubernetes_secondary_dns_service_port_number,
):
    openstack_security_group_rule = None
    if openstack_connection:
        # Add the openstack security rule to allow incoming network traffic to user ports:
        try:
            openstack_security_group_rule = openstack_connection.create_security_group_rule(
                port_range_min=kubernetes_secondary_dns_service_port_number,
                port_range_max=kubernetes_secondary_dns_service_port_number,
                remote_ip_prefix="0.0.0.0/0",
                protocol="udp",
                secgroup_name_or_id=worker_machine1.instance.spec.providerSpec.value.serverGroupName,
            )
        except exceptions.SDKException:
            LOGGER.error(
                "Failed to create security group rule for worker "
                f"nodes on a specific port {kubernetes_secondary_dns_service_port_number}"
            )
            raise
        assert openstack_security_group_rule.id, "Security group rule failed to create"
        LOGGER.info(f"Created a new security group rule - id: {openstack_security_group_rule.id}")
    yield openstack_security_group_rule
    if openstack_connection:
        # Remove the openstack security rule:
        try:
            openstack_connection.delete_security_group_rule(rule_id=openstack_security_group_rule.id)
        except exceptions.SDKException:
            LOGGER.error(f"Failed to delete security group rule {openstack_security_group_rule.id}")
            raise


@pytest.fixture(scope="module")
def enabled_kube_secondary_dns_feature_gate(hyperconverged_resource_scope_module):
    with ResourceEditorValidateHCOReconcile(
        patches={
            hyperconverged_resource_scope_module: {"spec": {"featureGates": {"deployKubeSecondaryDNS": True}}},
        },
        list_resource_reconcile=[NetworkAddonsConfig],
        wait_for_reconcile_post_update=True,
    ):
        yield


@pytest.fixture(scope="module")
def kubernetes_secondary_dns_deployment(hco_namespace):
    return get_deployment_by_name(namespace_name=hco_namespace.name, deployment_name="secondary-dns")


@pytest.fixture(scope="module")
def available_kubernetes_secondary_dns_service_port_number(
    workers_utility_pods,
    worker_node1,
):
    port_in_use = ExecCommandOnPod(utility_pods=workers_utility_pods, node=worker_node1).exec(
        command=f"ss -tulnap | grep {KUBERNETES_SECONDARY_DNS_SERVICE_PORT}",
        ignore_rc=True,  # return value should be 1 if no socket was found
    )
    assert not port_in_use, (
        f"Port {KUBERNETES_SECONDARY_DNS_SERVICE_PORT} is in use. Exposed service with that port cannot be created."
    )


@pytest.fixture(scope="module")
def created_dns_nodeport_service(
    hco_namespace,
    enabled_kube_secondary_dns_feature_gate,
    available_kubernetes_secondary_dns_service_port_number,
    kubernetes_secondary_dns_deployment,
):
    expose_command = basic_expose_command(
        resource_name=kubernetes_secondary_dns_deployment.name,
        svc_name=KUBERNETES_SECONDARY_DNS_SERVICE_NAME,
        port=KUBERNETES_SECONDARY_DNS_SERVICE_PORT,
        target_port=5353,
        resource="deployment",
        protocol="UDP",
    )
    oc_expose_command = f"oc {expose_command} -n {hco_namespace.name}"
    res, out, err = run_command(
        command=shlex.split(oc_expose_command),
    )
    assert res, f"Command {oc_expose_command} failed. \nOutpus: {out}\nError: {err}"


@pytest.fixture(scope="module")
def exposed_kubernetes_secondary_dns_service(
    kubernetes_secondary_dns_deployment,
    created_dns_nodeport_service,
):
    service = None
    sampler = TimeoutSampler(
        wait_timeout=TIMEOUT_15SEC,
        sleep=TIMEOUT_1SEC,
        func=get_service,
        name=KUBERNETES_SECONDARY_DNS_SERVICE_NAME,
        namespace=kubernetes_secondary_dns_deployment.namespace,
        exceptions_dict={ResourceNotFoundError: []},
    )
    try:
        for sample in sampler:
            if sample:
                service = sample
                break
    except TimeoutExpiredError:
        LOGGER.error(
            f"Newly created service {KUBERNETES_SECONDARY_DNS_SERVICE_NAME}, created in namespace "
            f"{kubernetes_secondary_dns_deployment.namespace} was not found"
        )
        raise
    yield service
    service.clean_up()


@pytest.fixture(scope="module")
def kubernetes_secondary_dns_bridge_worker_1(
    worker_node1,
    nodes_available_nics,
):
    with network_device(
        interface_type=LINUX_BRIDGE,
        nncp_name="ksd-nncp",
        interface_name="ksd-br",
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
        ports=[nodes_available_nics[worker_node1.name][-1]],
    ) as br:
        yield br


@pytest.fixture(scope="module")
def kubernetes_secondary_dns_nad(namespace, kubernetes_secondary_dns_bridge_worker_1):
    with network_nad(
        nad_type=kubernetes_secondary_dns_bridge_worker_1.bridge_type,
        nad_name="ksd-nad",
        interface_name=kubernetes_secondary_dns_bridge_worker_1.bridge_name,
        namespace=namespace,
    ) as nad:
        yield nad


@pytest.fixture(scope="module")
def kubernetes_secondary_dns_vm(
    namespace,
    worker_node1,
    kubernetes_secondary_dns_nad,
):
    name = "ksd-vm"
    networks = {kubernetes_secondary_dns_nad.name: kubernetes_secondary_dns_nad.name}
    cloud_init_data = compose_cloud_init_data_dict(
        network_data={"ethernets": {"eth1": {"addresses": ["10.200.0.1/24"]}}},
    )
    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        body=fedora_vm_body(name=name),
        networks=networks,
        interfaces=sorted(networks.keys()),
        client=namespace.client,
        cloud_init_data=cloud_init_data,
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
    ) as vm:
        running_vm(vm=vm, wait_for_cloud_init=True)
        yield vm


@pytest.fixture(scope="module")
def cluster_base_domain():
    cluster_dns_instance = DNS(name=CLUSTER)
    if cluster_dns_instance.exists:
        return cluster_dns_instance.instance["spec"]["baseDomain"]
    raise ResourceNotFound(f"No DNS instance named {CLUSTER} was found")


@pytest.fixture(scope="module")
def secondary_network_fqdn(cluster_base_domain, kubernetes_secondary_dns_vm):
    # The VM's secondary interface FQDN: <nic_name>.<vm_name>.<namespace>.vm.<cluster_base_domain>
    return (
        f"{kubernetes_secondary_dns_vm.interfaces[0]}.{kubernetes_secondary_dns_vm.name}."
        f"{kubernetes_secondary_dns_vm.namespace}.vm.{cluster_base_domain}"
    )


@pytest.fixture(scope="module")
def kubernetes_secondary_dns_vm_secondary_interface_ip(kubernetes_secondary_dns_vm):
    sampler = TimeoutSampler(
        wait_timeout=TIMEOUT_30SEC,
        sleep=TIMEOUT_5SEC,
        func=lambda: kubernetes_secondary_dns_vm.vmi.interface_ip(interface="eth1"),
    )
    try:
        for sample in sampler:
            if sample:
                return sample
    except TimeoutExpiredError:
        LOGGER.error(f"VM {kubernetes_secondary_dns_vm.name}'s secondary interface has no IP address")
        raise


@pytest.fixture(scope="module")
def kubernetes_secondary_dns_service_port_number(
    exposed_kubernetes_secondary_dns_service,
):
    for port in exposed_kubernetes_secondary_dns_service.instance.spec.ports:
        if port["port"] == KUBERNETES_SECONDARY_DNS_SERVICE_PORT:
            return port["nodePort"]
    raise ServicePortNotFoundError(
        port_number=KUBERNETES_SECONDARY_DNS_SERVICE_PORT,
        service_name=exposed_kubernetes_secondary_dns_service.name,
    )


@pytest.mark.polarion("CNV-9256")
def test_kubernetes_secondary_dns_basic_nslookup(
    cluster_base_domain,
    exposed_kubernetes_secondary_dns_service,
    secondary_network_fqdn,
    kubernetes_secondary_dns_vm_secondary_interface_ip,
    kubernetes_secondary_dns_service_port_number,
    network_security_rule_for_virtual_workers,
):
    assert secondary_network_in_nslookup_output(
        kubernetes_secondary_dns_service_port_number=kubernetes_secondary_dns_service_port_number,
        secondary_network_fqdn=secondary_network_fqdn,
        cluster_base_domain=cluster_base_domain,
        kubernetes_secondary_dns_vm_secondary_interface_ip=kubernetes_secondary_dns_vm_secondary_interface_ip,
    )

import shlex

import pytest
from ocp_resources.network_policy import NetworkPolicy
from ocp_resources.pod import Pod
from ocp_resources.service import Service
from pyhelper_utils.shell import run_command

from utilities.constants import (
    KUBEVIRT_APISERVER_PROXY_NP,
    KUBEVIRT_CONSOLE_PLUGIN_NP,
    POD_CONTAINER_SPEC,
    POD_SECURITY_CONTEXT_SPEC,
)

pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno, pytest.mark.arm64, pytest.mark.s390x]

TEST_SERVER_PORT = 9876
TEST_SERVER_APP_LABEL = "network-policy-server"


class AllowAllNetworkPolicy(NetworkPolicy):
    def __init__(self, name, namespace, client, match_labels):
        super().__init__(name=name, namespace=namespace, client=client)
        self.match_labels = dict(match_labels) if match_labels else {}

    def to_dict(self):
        super().to_dict()
        self.res["spec"] = {
            "podSelector": {"matchLabels": self.match_labels},
            "policyTypes": ["Ingress", "Egress"],
            "ingress": [{}],
            "egress": [{}],
        }


class ServerPod(Pod):
    def __init__(self, name, namespace, client, security_context, containers):
        super().__init__(
            name=name, namespace=namespace, client=client, security_context=security_context, containers=containers
        )

    def to_dict(self):
        super().to_dict()
        self.res.setdefault("metadata", {}).setdefault("labels", {}).update({"app": TEST_SERVER_APP_LABEL})


@pytest.fixture
def network_policy_by_name(admin_client, hco_namespace, network_policy_name):
    network_policy = NetworkPolicy(client=admin_client, namespace=hco_namespace.name, name=network_policy_name)
    assert network_policy.exists, f"NetworkPolicy {network_policy_name} not found in namespace {hco_namespace.name}"
    return network_policy


@pytest.fixture
def deployed_client_pod(admin_client, hco_namespace):
    """Create a client pod with curl installed for network policy testing"""
    with Pod(
        name="network-policy-client-pod",
        namespace=hco_namespace.name,
        client=admin_client,
        security_context=POD_SECURITY_CONTEXT_SPEC,
        containers=[POD_CONTAINER_SPEC],
    ) as pod:
        pod.wait_for_status(status=Pod.Status.RUNNING)
        yield pod


@pytest.fixture
def deployed_server_pod(admin_client, hco_namespace):
    """Create a server pod listening on TEST_SERVER_PORT for testing egress traffic from CNV components"""
    server_container_spec = {
        **POD_CONTAINER_SPEC,
        "name": "test-server",
        "command": [
            "/bin/bash",
            "-c",
            f'while true; do echo -e "HTTP/1.1 200 OK\\n\\nServer response $(date)" | nc -l -p {TEST_SERVER_PORT}; '
            f'echo "Connection handled, restarting server..."; done',
        ],
        "ports": [{"containerPort": TEST_SERVER_PORT, "protocol": "TCP"}],
    }

    server_pod = ServerPod(
        name="network-policy-server-pod",
        namespace=hco_namespace.name,
        client=admin_client,
        security_context=POD_SECURITY_CONTEXT_SPEC,
        containers=[server_container_spec],
    )

    with server_pod as pod:
        pod.wait_for_status(status=Pod.Status.RUNNING)
        yield pod


@pytest.fixture
def deployed_server_service(admin_client, hco_namespace, deployed_server_pod):  # noqa: ARG001
    """Create a service to expose the server pod on given port"""
    with Service(
        name="network-policy-server-service",
        namespace=hco_namespace.name,
        client=admin_client,
        selector={"app": TEST_SERVER_APP_LABEL},
        ports=[{"name": "http", "port": TEST_SERVER_PORT, "targetPort": TEST_SERVER_PORT, "protocol": "TCP"}],
    ) as service:
        yield service


@pytest.fixture
def network_policy_match_labels(network_policy_by_name):
    """Extract podSelector.matchLabels from a NetworkPolicy."""
    match_labels = network_policy_by_name.instance.spec.get("podSelector", {}).get("matchLabels")
    assert match_labels, f"NetworkPolicy {network_policy_by_name.name} has no/empty podSelector.matchLabels"
    return match_labels


@pytest.fixture
def service_by_network_policy(admin_client, hco_namespace, network_policy_by_name, network_policy_match_labels):
    """Find Service whose spec.selector is a subset of the NetworkPolicy podSelector.matchLabels."""
    services = list(Service.get(dyn_client=admin_client, namespace=hco_namespace.name))
    matching_services = []
    for service in services:
        selector = service.instance.spec.get("selector", {}) or {}
        # Service selector must be contained in the pod labels set
        if all(network_policy_match_labels.get(k) == v for k, v in selector.items()):
            matching_services.append(service)

    assert len(matching_services) == 1, (
        f"Expected exactly 1 Service whose spec.selector is a subset of NetworkPolicy {network_policy_by_name.name} "
        f"podSelector in namespace {hco_namespace.name}, but found {len(matching_services)}: "
        f"{[s.name for s in matching_services]}"
    )

    return matching_services[0]


@pytest.fixture
def service_ip(service_by_network_policy):
    """Extract clusterIP for testing network policy enforcement."""
    service_ip = service_by_network_policy.instance.spec.get("clusterIP")
    assert service_ip, f"Service {service_by_network_policy.name} has no clusterIP"
    if ":" in service_ip:
        pytest.skip(f"This test does not support sending traffic to IPv6: {service_ip}")
    return service_ip


@pytest.fixture
def service_port(service_by_network_policy):
    """Extract first port for testing network policy enforcement."""
    ports = service_by_network_policy.instance.spec.get("ports", [])
    assert len(ports) > 0, f"Service {service_by_network_policy.name} has no ports defined"

    service_port = ports[0].get("port")
    assert service_port, f"Service {service_by_network_policy.name} first port has no port number"
    return service_port


@pytest.fixture
def pods_by_network_policy(admin_client, hco_namespace, network_policy_by_name, network_policy_match_labels):
    """Get list of running pod names targeted by a NetworkPolicy using its podSelector."""
    label_pairs = [f"{key}={value}" for key, value in network_policy_match_labels.items()]
    full_label_selector = ",".join(label_pairs)
    pods = list(Pod.get(dyn_client=admin_client, namespace=hco_namespace.name, label_selector=full_label_selector))
    pod_names = [pod.name for pod in pods if getattr(pod.instance.status, "phase", "") == "Running"]
    assert len(pod_names) > 0, (
        f"No running pods found matching NetworkPolicy {network_policy_by_name.name} podSelector "
        f"in namespace {hco_namespace.name}"
    )
    pod_names.sort()
    return pod_names


@pytest.fixture
def ingress_traffic_preparation(
    deployed_client_pod, service_ip, service_port, hco_namespace, admin_client, network_policy_match_labels
):
    """
    Test preparation for ingress tests: Apply allow-all NetworkPolicy, verify traffic works, then remove it.
    This ensures that without restrictive policies, the connection should succeed.
    """
    with AllowAllNetworkPolicy(
        name="test-allow-all-traffic",
        namespace=hco_namespace.name,
        client=admin_client,
        match_labels=network_policy_match_labels,
    ):
        cmd = shlex.split(
            f"oc exec -n {hco_namespace.name} {deployed_client_pod.name} -- "
            f"curl -sS -k --connect-timeout 5 https://{service_ip}:{service_port}"
        )
        success, stdout, stderr = run_command(command=cmd, check=False)
        assert success, (
            f"Test preparation FAILED: With allow-all NetworkPolicy, connection should succeed but got "
            f"success={success}, stdout={stdout}, stderr={stderr}, cmd={' '.join(cmd)}"
        )
    yield {
        "deployed_client_pod": deployed_client_pod,
        "service_ip": service_ip,
        "service_port": service_port,
        "hco_namespace": hco_namespace,
    }


@pytest.fixture
def egress_traffic_preparation(
    pods_by_network_policy, hco_namespace, admin_client, network_policy_match_labels, deployed_server_service
):
    """
    Test preparation for egress tests: Apply allow-all NetworkPolicy, verify traffic works, then remove it.
    This ensures that without restrictive policies, the connection should succeed.
    """
    with AllowAllNetworkPolicy(
        name="test-allow-all-traffic",
        namespace=hco_namespace.name,
        client=admin_client,
        match_labels=network_policy_match_labels,
    ):
        pod_name = pods_by_network_policy[0]
        service_ip = (
            deployed_server_service.instance.spec.get("clusterIPs")
            or [deployed_server_service.instance.spec.get("clusterIP")]
        )[0]
        if ":" in service_ip:
            pytest.skip(f"This test does not support sending traffic to IPv6: {service_ip}")
        cmd = shlex.split(
            f"oc exec -n {hco_namespace.name} {pod_name} -- "
            f"curl -sS --connect-timeout 5 http://{service_ip}:{TEST_SERVER_PORT}"
        )
        success, stdout, stderr = run_command(command=cmd, check=False)
        assert success, (
            f"Test preparation FAILED (egress): With allow-all NetworkPolicy, connection should succeed but got "
            f"success={success}, stdout={stdout}, stderr={stderr}, cmd={' '.join(cmd)}"
        )

    yield {
        "pods_by_network_policy": pods_by_network_policy,
        "hco_namespace": hco_namespace,
        "server_service_ip": service_ip,
    }


@pytest.mark.polarion("CNV-12305")
@pytest.mark.parametrize("network_policy_name", [KUBEVIRT_CONSOLE_PLUGIN_NP])
def test_console_plugin_network_policy_blocks_ingress_unauthorized_traffic(
    network_policy_name, ingress_traffic_preparation
):
    """
    Test that KUBEVIRT_CONSOLE_PLUGIN_NP blocks unauthorized traffic.

    It uses a test pod with curl to try to reach the service IP+PORT,
    which should be blocked by the NetworkPolicy.
    """
    deployed_client_pod = ingress_traffic_preparation["deployed_client_pod"]
    service_ip = ingress_traffic_preparation["service_ip"]
    service_port = ingress_traffic_preparation["service_port"]
    hco_namespace = ingress_traffic_preparation["hco_namespace"]

    cmd = shlex.split(
        f"oc exec -n {hco_namespace.name} {deployed_client_pod.name} -- "
        f"curl -sS -k --connect-timeout 5 https://{service_ip}:{service_port}"
    )
    success, stdout, stderr = run_command(command=cmd, check=False)

    assert not success, (
        f"NetworkPolicy test FAILED: {network_policy_name} connection should be blocked "
        f"by NetworkPolicy but succeeded. success={success}, stdout={stdout}, stderr={stderr}, cmd={' '.join(cmd)}"
    )


@pytest.mark.polarion("CNV-12306")
@pytest.mark.parametrize("network_policy_name", [KUBEVIRT_APISERVER_PROXY_NP])
def test_apiserver_proxy_network_policy_blocks_egress_unauthorized_traffic(
    network_policy_name, egress_traffic_preparation
):
    """
    Test that KUBEVIRT_APISERVER_PROXY_NP blocks unauthorized traffic.

    It iterates through all pods matching the NetworkPolicy podSelector
    and verifies that connections to the console plugin service are blocked.
    """
    pods_by_network_policy = egress_traffic_preparation["pods_by_network_policy"]
    hco_namespace = egress_traffic_preparation["hco_namespace"]
    server_service_ip = egress_traffic_preparation["server_service_ip"]

    for pod_name in pods_by_network_policy:
        cmd = shlex.split(
            f"oc exec -n {hco_namespace.name} {pod_name} -- "
            f"curl -sS --connect-timeout 5 http://{server_service_ip}:{TEST_SERVER_PORT}"
        )
        success, stdout, stderr = run_command(command=cmd, check=False)

        assert not success, (
            f"NetworkPolicy test FAILED: {network_policy_name} pod {pod_name} connection should be blocked "
            f"by NetworkPolicy but succeeded. success={success}, stdout={stdout}, stderr={stderr}, cmd={' '.join(cmd)}"
        )

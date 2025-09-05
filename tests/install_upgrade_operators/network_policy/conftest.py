import pytest
from ocp_resources.network_policy import NetworkPolicy
from ocp_resources.pod import Pod
from ocp_resources.service import Service

from utilities.constants import POD_CONTAINER_SPEC, POD_SECURITY_CONTEXT_SPEC

from .utils import TEST_SERVER_APP_LABEL, TEST_SERVER_PORT, build_curl_command


@pytest.fixture
def network_policy_by_name(admin_client, hco_namespace, network_policy_name):
    return NetworkPolicy(
        client=admin_client, namespace=hco_namespace.name, name=network_policy_name, ensure_exists=True
    )


@pytest.fixture
def deployed_client_pod(admin_client, hco_namespace):
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
    server_container_spec = {
        **POD_CONTAINER_SPEC,
        "name": "test-server",
        "command": [
            "/bin/bash",
            "-c",
            f'while true; do echo -e "HTTP/1.1 200 OK\\n\\nServer response $(date)" | '
            f"nc -l -p {TEST_SERVER_PORT}; done",
        ],
        "ports": [{"containerPort": TEST_SERVER_PORT, "protocol": "TCP"}],
    }

    with Pod(
        name="network-policy-server-pod",
        namespace=hco_namespace.name,
        client=admin_client,
        security_context=POD_SECURITY_CONTEXT_SPEC,
        containers=[server_container_spec],
        label={"app": TEST_SERVER_APP_LABEL},
    ) as pod:
        pod.wait_for_status(status=Pod.Status.RUNNING)
        yield pod


@pytest.fixture
def deployed_server_service_ip(admin_client, hco_namespace, deployed_server_pod):
    with Service(
        name="network-policy-server-service",
        namespace=hco_namespace.name,
        client=admin_client,
        selector={"app": TEST_SERVER_APP_LABEL},
        ports=[{"name": "http", "port": TEST_SERVER_PORT, "targetPort": TEST_SERVER_PORT, "protocol": "TCP"}],
    ) as service:
        service_ip = service.instance.spec.get("clusterIP")
        yield service_ip


@pytest.fixture
def network_policy_match_labels(network_policy_by_name):
    match_labels = network_policy_by_name.instance.spec.get("podSelector", {}).get("matchLabels", {})
    assert match_labels, f"NetworkPolicy {network_policy_by_name.name} has no/empty podSelector.matchLabels"
    return dict(match_labels)


@pytest.fixture
def service_by_network_policy(admin_client, hco_namespace, network_policy_by_name, network_policy_match_labels):
    matching_services = []
    for service in Service.get(dyn_client=admin_client, namespace=hco_namespace.name):
        selector = service.instance.spec.get("selector", {})
        # Service selector must be contained in the pod labels set
        if selector.items() <= network_policy_match_labels.items():
            matching_services.append(service)

    assert len(matching_services) == 1, (
        f"Expected exactly 1 Service whose spec.selector is a subset of NetworkPolicy {network_policy_by_name.name} "
        f"podSelector in namespace {hco_namespace.name}, but found {len(matching_services)}: "
        f"{[service.name for service in matching_services]}"
    )

    return matching_services[0]


@pytest.fixture
def service_ip_by_network_policy(service_by_network_policy):
    service_ip = service_by_network_policy.instance.spec.get("clusterIP")
    assert service_ip, f"Service {service_by_network_policy.name} has no clusterIP"
    return service_ip


@pytest.fixture
def service_port_by_network_policy(service_by_network_policy):
    return service_by_network_policy.instance.spec.get("ports", [])[0].get("port")


@pytest.fixture
def pods_by_network_policy(admin_client, hco_namespace, network_policy_by_name, network_policy_match_labels):
    label_pairs = [f"{label_key}={label_value}" for label_key, label_value in network_policy_match_labels.items()]
    full_label_selector = ",".join(label_pairs)
    pods = Pod.get(dyn_client=admin_client, namespace=hco_namespace.name, label_selector=full_label_selector)
    running_pods = [pod for pod in pods if pod.status == Pod.Status.RUNNING]
    assert len(running_pods) > 0, (
        f"No running pods found matching NetworkPolicy {network_policy_by_name.name} podSelector "
        f"in namespace {hco_namespace.name}"
    )
    return running_pods


@pytest.fixture
def ingress_allowall_connectivity_precheck(
    admin_client,
    hco_namespace,
    deployed_client_pod,
    service_ip_by_network_policy,
    service_port_by_network_policy,
    network_policy_match_labels,
):
    with NetworkPolicy(
        name="test-allow-all-traffic",
        namespace=hco_namespace.name,
        client=admin_client,
        pod_selector={"matchLabels": network_policy_match_labels},
        policy_types=["Ingress", "Egress"],
        ingress=[{}],
        egress=[{}],
    ):
        try:
            deployed_client_pod.execute(
                command=build_curl_command(service_ip_by_network_policy, service_port_by_network_policy, https=True)
            )
        except Exception as e:
            pytest.fail(
                "Ingress connectivity test preparation FAILED: With allow-all NetworkPolicy, "
                f"connection from test client pod to the CNV service should succeed but got error: {e}"
            )


@pytest.fixture
def egress_allowall_connectivity_precheck(
    admin_client, hco_namespace, pods_by_network_policy, network_policy_match_labels, deployed_server_service_ip
):
    with NetworkPolicy(
        name="test-allow-all-traffic",
        namespace=hco_namespace.name,
        client=admin_client,
        pod_selector={"matchLabels": network_policy_match_labels},
        policy_types=["Ingress", "Egress"],
        ingress=[{}],
        egress=[{}],
    ):
        component_pod = pods_by_network_policy[0]
        try:
            component_pod.execute(command=build_curl_command(deployed_server_service_ip, TEST_SERVER_PORT))
        except Exception as e:
            pytest.fail(
                "Egress connectivity test preparation FAILED: With allow-all NetworkPolicy, "
                f"connection from {component_pod.name} to test server pod should succeed but got error: {e}"
            )

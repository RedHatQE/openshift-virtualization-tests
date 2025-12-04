import logging
import shlex

import pytest
from ocp_resources.destination_rule import DestinationRule
from ocp_resources.gateway import Gateway
from ocp_resources.peer_authentication import PeerAuthentication
from ocp_resources.resource import ResourceEditor
from ocp_resources.service import Service
from ocp_resources.service_account import ServiceAccount
from ocp_resources.virtual_service import VirtualService
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.network.constants import HTTPBIN_IMAGE
from tests.network.service_mesh.constants import (
    AUTH_COMMAND,
    DESTINATION_RULE_TYPE,
    GATEWAY_SELECTOR,
    GATEWAY_TYPE,
    HTTP_PROTOCOL,
    HTTPBIN_COMMAND,
    INGRESS_SERVICE,
    PEER_AUTHENTICATION_TYPE,
    SERVER_DEMO_HOST,
    SERVER_DEMO_NAME,
    SERVER_DEPLOYMENT_STRATEGY,
    SERVER_V1_IMAGE,
    SERVER_V2_IMAGE,
    SERVICE_MESH_PORT,
    VERSION_2_DEPLOYMENT,
    VIRTUAL_SERVICE_TYPE,
)
from tests.network.service_mesh.utils import run_console_command, traffic_management_request
from tests.network.utils import (
    FedoraVirtualMachineForServiceMesh,
    ServiceMeshDeployments,
    ServiceMeshDeploymentService,
)
from utilities.constants import PORT_80, TIMEOUT_4MIN, TIMEOUT_10SEC
from utilities.infra import add_scc_to_service_account, create_ns, label_project, unique_name
from utilities.virt import vm_console_run_commands

LOGGER = logging.getLogger(__name__)


class GatewayForTests(Gateway):
    def __init__(self, app_name, namespace, hosts, client):
        self.name = unique_name(name=app_name, service_type=GATEWAY_TYPE)
        super().__init__(
            name=self.name,
            namespace=namespace,
            client=client,
        )
        self.hosts = hosts

    def to_dict(self):
        super().to_dict()
        self.res.setdefault("spec", {})
        self.res["spec"]["selector"] = GATEWAY_SELECTOR
        self.res["spec"]["servers"] = [
            {
                "port": {
                    "number": PORT_80,
                    "name": HTTP_PROTOCOL.lower(),
                    "protocol": HTTP_PROTOCOL,
                },
                "hosts": self.hosts,
            }
        ]


class DestinationRuleForTests(DestinationRule):
    def __init__(self, app_name, namespace, versions, client):
        self.name = unique_name(name=app_name, service_type=DESTINATION_RULE_TYPE)
        super().__init__(
            name=self.name,
            namespace=namespace,
            client=client,
        )
        self.app_name = app_name
        self.versions = versions

    def to_dict(self):
        super().to_dict()
        self.res.setdefault("spec", {})
        self.res["spec"]["host"] = self.app_name
        self.res["spec"].setdefault("subsets", [])
        for version in self.versions:
            self.res["spec"]["subsets"].append({
                "name": version,  # Same as inner name.
                "labels": {
                    "version": version  # Maps to version label in deployment
                },
            })


class VirtualServiceForTests(VirtualService):
    def __init__(
        self,
        app_name,
        namespace,
        hosts,
        gateways,
        subset,
        port,
        client,
    ):
        self.name = unique_name(name=app_name, service_type=VIRTUAL_SERVICE_TYPE)
        super().__init__(
            name=self.name,
            namespace=namespace,
            client=client,
        )
        self.hosts = hosts
        self.gateways = gateways
        self.subset = subset
        self.port = port
        self.app_name = app_name

    def to_dict(self):
        super().to_dict()
        self.res.setdefault("spec", {})
        self.res["spec"]["hosts"] = self.hosts
        self.res["spec"]["gateways"] = self.gateways
        self.res["spec"]["http"] = [
            {
                "match": [
                    {
                        "uri": {
                            "prefix": "/",
                        },
                    },
                ],
                "route": [
                    {
                        "destination": {
                            "port": {"number": self.port},
                            "host": self.app_name,
                            "subset": self.subset,  # Map to the name in DestinationRule
                        },
                    },
                ],
            },
        ]


class PeerAuthenticationForTests(PeerAuthentication):
    def __init__(self, name, namespace, client):
        self.name = unique_name(name=name, service_type=PEER_AUTHENTICATION_TYPE)
        super().__init__(
            name=self.name,
            namespace=namespace,
            client=client,
        )

    def to_dict(self):
        super().to_dict()
        self.res["spec"] = {"mtls": {"mode": PeerAuthentication.MtlsMode.STRICT}}


def wait_service_mesh_components_convergence(func, vm, **kwargs):
    expected_output = "no healthy upstream"
    try:
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_4MIN,
            sleep=TIMEOUT_10SEC,
            func=func,
            vm=vm,
            **kwargs,
        ):
            if expected_output not in sample:
                return
    except TimeoutExpiredError:
        LOGGER.error("Service Mesh components didn't converge")
        raise


@pytest.fixture(scope="module")
def ns_outside_of_service_mesh(admin_client):
    yield from create_ns(admin_client=admin_client, name="outside-mesh")


@pytest.fixture(scope="module")
def service_mesh_tests_namespace(namespace, admin_client):
    # The namespace used for the ServiceMesh tests must be added the `istio-injection` label.
    label_project(name=namespace.name, label={"istio-injection": "enabled"}, admin_client=admin_client)
    return namespace


@pytest.fixture(scope="class")
def httpbin_deployment_service_mesh(unprivileged_client, service_mesh_tests_namespace):
    with ServiceMeshDeployments(
        name="httpbin",
        namespace=service_mesh_tests_namespace.name,
        version=ServiceMeshDeployments.ApiVersion.V1,
        image=HTTPBIN_IMAGE,
        command=shlex.split(HTTPBIN_COMMAND),
        port=SERVICE_MESH_PORT,
        service_port=SERVICE_MESH_PORT,
        service_account=True,
        client=unprivileged_client,
    ) as dp:
        yield dp


@pytest.fixture(scope="class")
def httpbin_service_account_service_mesh(unprivileged_client, httpbin_deployment_service_mesh):
    with ServiceAccount(
        name=httpbin_deployment_service_mesh.app_name,
        namespace=httpbin_deployment_service_mesh.namespace,
        client=unprivileged_client,
    ) as sa:
        add_scc_to_service_account(
            namespace=httpbin_deployment_service_mesh.namespace,
            scc_name="anyuid",
            sa_name=sa.name,
        )
        yield sa


@pytest.fixture(scope="class")
def httpbin_service_service_mesh(
    unprivileged_client, httpbin_deployment_service_mesh, httpbin_service_account_service_mesh
):
    with ServiceMeshDeploymentService(
        namespace=httpbin_deployment_service_mesh.namespace,
        app_name=httpbin_deployment_service_mesh.app_name,
        port=httpbin_deployment_service_mesh.service_port,
        client=unprivileged_client,
    ) as sv:
        yield sv


@pytest.fixture(scope="module")
def vm_fedora_with_service_mesh_annotation(
    unprivileged_client,
    service_mesh_tests_namespace,
):
    vm_name = "service-mesh-vm"
    with FedoraVirtualMachineForServiceMesh(
        client=unprivileged_client,
        name=vm_name,
        namespace=service_mesh_tests_namespace.name,
    ) as vm:
        vm.custom_service_enable(
            service_name=vm_name,
            port=SERVICE_MESH_PORT,
        )
        vm.start(wait=True)
        vm.wait_for_agent_connected()
        yield vm


@pytest.fixture(scope="module")
def outside_mesh_vm_fedora_with_service_mesh_annotation(
    admin_client,
    ns_outside_of_service_mesh,
):
    vm_name = "out-service-mesh-vm"
    with FedoraVirtualMachineForServiceMesh(
        client=admin_client,
        name=vm_name,
        namespace=ns_outside_of_service_mesh.name,
    ) as vm:
        vm.custom_service_enable(
            service_name=vm_name,
            port=SERVICE_MESH_PORT,
        )
        vm.start(wait=True)
        vm.wait_for_agent_connected()
        yield vm


@pytest.fixture(scope="class")
def server_deployment_v1(unprivileged_client, service_mesh_tests_namespace):
    with ServiceMeshDeployments(
        name=SERVER_DEMO_NAME,
        namespace=service_mesh_tests_namespace.name,
        version=ServiceMeshDeployments.ApiVersion.V1,
        image=SERVER_V1_IMAGE,
        strategy=SERVER_DEPLOYMENT_STRATEGY,
        host=SERVER_DEMO_HOST,
        service_port=SERVICE_MESH_PORT,
        client=unprivileged_client,
    ) as dp:
        yield dp


@pytest.fixture(scope="class")
def server_deployment_v2(unprivileged_client, server_deployment_v1):
    with ServiceMeshDeployments(
        name=server_deployment_v1.app_name,
        namespace=server_deployment_v1.namespace,
        version=VERSION_2_DEPLOYMENT,
        image=SERVER_V2_IMAGE,
        strategy=server_deployment_v1.strategy,
        host=server_deployment_v1.host,
        service_port=server_deployment_v1.service_port,
        client=unprivileged_client,
    ) as dp:
        yield dp


@pytest.fixture(scope="class")
def server_service_service_mesh(unprivileged_client, server_deployment_v1):
    with ServiceMeshDeploymentService(
        app_name=server_deployment_v1.app_name,
        namespace=server_deployment_v1.namespace,
        port=server_deployment_v1.service_port,
        client=unprivileged_client,
    ) as sv:
        yield sv


@pytest.fixture(scope="class")
def gateway_service_mesh(unprivileged_client, server_deployment_v1):
    with GatewayForTests(
        app_name=server_deployment_v1.app_name,
        namespace=server_deployment_v1.namespace,
        hosts=[server_deployment_v1.host],
        client=unprivileged_client,
    ) as gw:
        yield gw


@pytest.fixture(scope="class")
def virtual_service_mesh_service(unprivileged_client, server_deployment_v1, gateway_service_mesh):
    with VirtualServiceForTests(
        app_name=server_deployment_v1.app_name,
        namespace=server_deployment_v1.namespace,
        hosts=[server_deployment_v1.host],
        gateways=[gateway_service_mesh.name],
        subset=server_deployment_v1.version,
        port=server_deployment_v1.service_port,
        client=unprivileged_client,
    ) as vsv:
        yield vsv


@pytest.fixture(scope="class")
def destination_rule_service_mesh(unprivileged_client, server_deployment_v1, server_deployment_v2):
    with DestinationRuleForTests(
        app_name=server_deployment_v1.app_name,
        namespace=server_deployment_v1.namespace,
        versions=[server_deployment_v1.version, server_deployment_v2.version],
        client=unprivileged_client,
    ) as dr:
        yield dr


@pytest.fixture(scope="class")
def traffic_management_service_mesh_convergence(
    istio_system_namespace,
    vm_fedora_with_service_mesh_annotation,
    server_deployment_v1,
    server_deployment_v2,
    server_service_service_mesh,
    gateway_service_mesh,
    destination_rule_service_mesh,
    virtual_service_mesh_service,
    service_mesh_ingress_service_addr,
):
    wait_service_mesh_components_convergence(
        func=traffic_management_request,
        vm=vm_fedora_with_service_mesh_annotation,
        server=server_deployment_v1,
        destination=service_mesh_ingress_service_addr,
    )


@pytest.fixture(scope="class")
def service_mesh_ingress_service_addr(admin_client, istio_system_namespace):
    for svc in Service.get(
        dyn_client=admin_client,
        name=INGRESS_SERVICE,
        namespace=istio_system_namespace.metadata.name,
    ):
        return svc.instance.spec.clusterIP


@pytest.fixture()
def change_routing_to_v2(
    virtual_service_mesh_service,
    server_deployment_v2,
    vm_fedora_with_service_mesh_annotation,
    service_mesh_ingress_service_addr,
):
    LOGGER.info(f"Change routing to direct traffic only to: {server_deployment_v2.version}")
    patch = {
        "spec": {
            "http": [
                {
                    "route": [
                        {
                            "destination": {
                                "port": {"number": server_deployment_v2.service_port},
                                "host": server_deployment_v2.app_name,
                                "subset": server_deployment_v2.version,  # Map to the name in DestinationRule
                            },
                        },
                    ],
                },
            ]
        }
    }
    ResourceEditor(patches={virtual_service_mesh_service: patch}).update()
    wait_service_mesh_components_convergence(
        func=traffic_management_request,
        vm=vm_fedora_with_service_mesh_annotation,
        server=server_deployment_v2,
        destination=service_mesh_ingress_service_addr,
    )


@pytest.fixture(scope="class")
def peer_authentication_strict_service_mesh(unprivileged_client, service_mesh_tests_namespace):
    with PeerAuthenticationForTests(
        name="default",
        namespace=service_mesh_tests_namespace.name,
        client=unprivileged_client,
    ) as pa:
        yield pa


@pytest.fixture(scope="class")
def peer_authentication_service_mesh_deployment(
    istio_system_namespace,
    peer_authentication_strict_service_mesh,
    vm_fedora_with_service_mesh_annotation,
    ns_outside_of_service_mesh,
    httpbin_service_service_mesh,
):
    wait_service_mesh_components_convergence(
        func=run_console_command,
        vm=vm_fedora_with_service_mesh_annotation,
        command=AUTH_COMMAND.format(service=httpbin_service_service_mesh.app_name),
    )


@pytest.fixture()
def vmi_http_server(vm_fedora_with_service_mesh_annotation):
    vm_console_run_commands(
        vm=vm_fedora_with_service_mesh_annotation,
        commands=[f'while true ; do  echo -e "HTTP/1.1 200 OK\n\n $(date)" | nc -l -p {SERVICE_MESH_PORT}  ; done &'],
    )

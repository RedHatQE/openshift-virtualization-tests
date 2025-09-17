import pytest

from tests.network.service_mesh.constants import AUTH_COMMAND, EXPECTED_MESH_SUCCESS_OUTPUT
from tests.network.service_mesh.utils import (
    assert_traffic_management_request,
    inbound_request,
    run_console_command,
)
from utilities.virt import migrate_vm_and_verify

pytestmark = pytest.mark.service_mesh


@pytest.mark.s390x
class TestSMTrafficManagement:
    @pytest.mark.polarion("CNV-5782")
    @pytest.mark.single_nic
    def test_service_mesh_traffic_management(
        self,
        traffic_management_service_mesh_convergence,
        server_deployment_v1,
        vm_fedora_with_service_mesh_annotation,
        service_mesh_ingress_service_addr,
    ):
        assert_traffic_management_request(
            vm=vm_fedora_with_service_mesh_annotation,
            server=server_deployment_v1,
            destination=service_mesh_ingress_service_addr,
        )

    @pytest.mark.polarion("CNV-7304")
    @pytest.mark.single_nic
    def test_service_mesh_traffic_management_manipulated_rule(
        self,
        traffic_management_service_mesh_convergence,
        change_routing_to_v2,
        server_deployment_v2,
        vm_fedora_with_service_mesh_annotation,
        service_mesh_ingress_service_addr,
    ):
        assert_traffic_management_request(
            vm=vm_fedora_with_service_mesh_annotation,
            server=server_deployment_v2,
            destination=service_mesh_ingress_service_addr,
        )


@pytest.mark.s390x
class TestSMPeerAuthentication:
    @pytest.mark.ipv4
    @pytest.mark.polarion("CNV-5784")
    @pytest.mark.single_nic
    @pytest.mark.dependency(
        name="test_authentication_policy_from_mesh",
    )
    def test_authentication_policy_from_mesh(
        self,
        peer_authentication_service_mesh_deployment,
        vm_fedora_with_service_mesh_annotation,
        httpbin_service_service_mesh,
    ):
        result = run_console_command(
            vm=vm_fedora_with_service_mesh_annotation,
            command=AUTH_COMMAND.format(service=httpbin_service_service_mesh.app_name),
        )
        assert EXPECTED_MESH_SUCCESS_OUTPUT in result

    @pytest.mark.ipv4
    @pytest.mark.polarion("CNV-12181")
    @pytest.mark.single_nic
    @pytest.mark.dependency(
        name="test_authentication_policy_from_mesh_post_migration",
        depends=["test_authentication_policy_from_mesh"],
    )
    def test_authentication_policy_from_mesh_over_migration(
        self,
        vm_fedora_with_service_mesh_annotation,
        httpbin_service_service_mesh,
    ):
        migrate_vm_and_verify(vm=vm_fedora_with_service_mesh_annotation)
        result = run_console_command(
            vm=vm_fedora_with_service_mesh_annotation,
            command=AUTH_COMMAND.format(service=httpbin_service_service_mesh.app_name),
        )
        assert EXPECTED_MESH_SUCCESS_OUTPUT in result

    @pytest.mark.polarion("CNV-7305")
    @pytest.mark.ipv4
    @pytest.mark.single_nic
    def test_outside_mesh_traffic_blocked(
        self,
        outside_mesh_vm_fedora_with_service_mesh_annotation,
        peer_authentication_service_mesh_deployment,
        httpbin_service_service_mesh,
    ):
        # We must specify the full service DNS name since the VM is outside the mesh in a different namespace
        # Format: http://<service_name>.<service_namespace>.svc.cluster.local
        result = run_console_command(
            vm=outside_mesh_vm_fedora_with_service_mesh_annotation,
            command=AUTH_COMMAND.format(
                service=(
                    f"{httpbin_service_service_mesh.app_name}.{httpbin_service_service_mesh.namespace}."
                    "svc.cluster.local"
                )
            ),
        )
        assert "curl: (56) Recv failure" in result

    @pytest.mark.polarion("CNV-7128")
    @pytest.mark.single_nic
    def test_service_mesh_inbound_traffic_blocked(
        self,
        outside_mesh_vm_fedora_with_service_mesh_annotation,
        peer_authentication_service_mesh_deployment,
        vm_fedora_with_service_mesh_annotation,
        vmi_http_server,
    ):
        destination_service_spec = vm_fedora_with_service_mesh_annotation.custom_service.instance.spec
        inbound_request(
            vm=outside_mesh_vm_fedora_with_service_mesh_annotation,
            destination_address=destination_service_spec.clusterIPs[0],
            destination_port=destination_service_spec.ports[0].port,
        )

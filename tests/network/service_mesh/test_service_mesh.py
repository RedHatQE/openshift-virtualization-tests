import pytest

from tests.network.service_mesh.utils import (
    assert_traffic_management_request,
    inbound_request,
)
from tests.network.utils import assert_authentication_request

pytestmark = pytest.mark.service_mesh


class TestSMTrafficManagement:
    @pytest.mark.polarion("CNV-5782")
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


class TestSMPeerAuthentication:
    @pytest.mark.ipv4
    @pytest.mark.polarion("CNV-5784")
    def test_authentication_policy_from_mesh(
        self,
        peer_authentication_service_mesh_deployment,
        vm_fedora_with_service_mesh_annotation,
        httpbin_service_service_mesh,
    ):
        assert_authentication_request(
            vm=vm_fedora_with_service_mesh_annotation,
            service_app_name=httpbin_service_service_mesh.app_name,
        )

    @pytest.mark.polarion("CNV-7305")
    @pytest.mark.ipv4
    def test_authentication_policy_outside_mesh(
        self,
        outside_mesh_vm_fedora_with_service_mesh_annotation,
        peer_authentication_service_mesh_deployment,
        httpbin_service_service_mesh,
        outside_mesh_console_ready_vm,
    ):
        with pytest.raises(AssertionError):
            assert_authentication_request(
                vm=outside_mesh_vm_fedora_with_service_mesh_annotation,
                service_app_name=httpbin_service_service_mesh.app_name,
            )

    @pytest.mark.polarion("CNV-7128")
    def test_service_mesh_inbound_traffic_blocked(
        self,
        outside_mesh_vm_fedora_with_service_mesh_annotation,
        peer_authentication_service_mesh_deployment,
        vm_fedora_with_service_mesh_annotation,
        outside_mesh_console_ready_vm,
        vmi_http_server,
    ):
        destination_service_spec = vm_fedora_with_service_mesh_annotation.custom_service.instance.spec
        inbound_request(
            vm=outside_mesh_vm_fedora_with_service_mesh_annotation,
            destination_address=destination_service_spec.clusterIPs[0],
            destination_port=destination_service_spec.ports[0].port,
        )

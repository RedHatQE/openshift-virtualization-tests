import pytest

from tests.network.network_service.libservice import (
    SERVICE_IP_FAMILY_POLICY_PREFER_DUAL_STACK,
    SERVICE_IP_FAMILY_POLICY_REQUIRE_DUAL_STACK,
    SERVICE_IP_FAMILY_POLICY_SINGLE_STACK,
    assert_svc_ip_params,
)


class TestServiceConfigurationViaVirtctl:
    @pytest.mark.parametrize(
        "virtctl_expose_service, expected_num_families_in_service, ip_family_policy",
        [
            pytest.param(
                SERVICE_IP_FAMILY_POLICY_SINGLE_STACK,
                SERVICE_IP_FAMILY_POLICY_SINGLE_STACK,
                SERVICE_IP_FAMILY_POLICY_SINGLE_STACK,
                marks=(pytest.mark.polarion("CNV-6454")),
            ),
            pytest.param(
                SERVICE_IP_FAMILY_POLICY_PREFER_DUAL_STACK,
                SERVICE_IP_FAMILY_POLICY_PREFER_DUAL_STACK,
                SERVICE_IP_FAMILY_POLICY_PREFER_DUAL_STACK,
                marks=(pytest.mark.polarion("CNV-6481")),
            ),
            pytest.param(
                SERVICE_IP_FAMILY_POLICY_REQUIRE_DUAL_STACK,
                SERVICE_IP_FAMILY_POLICY_REQUIRE_DUAL_STACK,
                SERVICE_IP_FAMILY_POLICY_REQUIRE_DUAL_STACK,
                marks=(
                    pytest.mark.polarion("CNV-6482"),
                    pytest.mark.ipv4,
                    pytest.mark.ipv6,
                ),
            ),
        ],
        indirect=["virtctl_expose_service", "expected_num_families_in_service"],
    )
    @pytest.mark.single_nic
    def test_virtctl_expose_services(
        self,
        expected_num_families_in_service,
        virtctl_expose_service,
        ip_family_policy,
    ):
        assert_svc_ip_params(
            svc=virtctl_expose_service,
            expected_num_families_in_service=expected_num_families_in_service,
            expected_ip_family_policy=ip_family_policy,
        )

    @pytest.mark.multiarch
    @pytest.mark.polarion("CNV-15943")
    def test_services_between_different_archs(self):
        """
        Test Kubernetes Service connectivity between VMs on different architectures.
        Intended to run on multi-architecture cluster with AMD64 and ARM64 worker nodes

        STP Reference:
        https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/pull/12/
        (Not yet merged)

        Preconditions:
            - TCP Server VM on ARM64 node
            - TCP Client VM on AMD64 node
            - ClusterIP TCP service exposing the server VM's port

        Steps:
            1. Establish TCP connection from client VM to server VM via the ClusterIP service

        Expected:
            - TCP connection through the ClusterIP service succeeds
        """


# Mark test as unimplemented
TestServiceConfigurationViaVirtctl.test_services_between_different_archs.__test__ = False

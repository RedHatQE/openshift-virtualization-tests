import pytest
from tests.network.ip_family_services.libservice import (
    SERVICE_IP_FAMILY_POLICY_PREFER_DUAL_STACK,
    SERVICE_IP_FAMILY_POLICY_REQUIRE_DUAL_STACK,
    SERVICE_IP_FAMILY_POLICY_SINGLE_STACK,
    assert_svc_ip_params,
)


@pytest.mark.gating
class TestServiceConfigurationViaManifest:
    @pytest.mark.single_nic
    @pytest.mark.parametrize(
        "single_stack_service_ip_family, single_stack_service",
        [
            pytest.param("IPv4", "IPv4", marks=[pytest.mark.ipv4, pytest.mark.polarion("CNV-5789")]),
            pytest.param("IPv6", "IPv6", marks=[pytest.mark.ipv6, pytest.mark.polarion("CNV-12557")]),
        ],
        indirect=["single_stack_service"],
    )
    def test_service_with_configured_ip_families(
        self,
        running_vm_for_exposure,
        single_stack_service_ip_family,
        single_stack_service,
    ):
        ip_families_in_svc = running_vm_for_exposure.custom_service.instance.spec.ipFamilies

        assert len(ip_families_in_svc) == 1 and ip_families_in_svc[0] == single_stack_service_ip_family, (
            f"Wrong ipFamilies config in service on VM {running_vm_for_exposure.name}: "
            f"Expected: single stack {single_stack_service_ip_family} family, "
            f"Actual: {len(ip_families_in_svc)} ip families: {ip_families_in_svc} "
        )

    @pytest.mark.polarion("CNV-5831")
    @pytest.mark.single_nic
    @pytest.mark.usefixtures("default_ip_family_policy_service")
    def test_service_with_default_ip_family_policy(
        self,
        running_vm_for_exposure,
    ):
        ip_family_policy = running_vm_for_exposure.custom_service.instance.spec.ipFamilyPolicy
        assert ip_family_policy == SERVICE_IP_FAMILY_POLICY_SINGLE_STACK, (
            f"Service created with wrong default ipfamilyPolicy on VM {running_vm_for_exposure.name}: "
            f"Expected: {SERVICE_IP_FAMILY_POLICY_SINGLE_STACK}, "
            f"Actual: {ip_family_policy}"
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
                marks=(pytest.mark.polarion("CNV-6482")),
            ),
        ],
        indirect=["virtctl_expose_service", "expected_num_families_in_service"],
    )
    @pytest.mark.single_nic
    @pytest.mark.s390x
    def test_virtctl_expose_services(
        self,
        expected_num_families_in_service,
        running_vm_for_exposure,
        virtctl_expose_service,
        dual_stack_cluster,
        ip_family_policy,
    ):
        assert_svc_ip_params(
            svc=virtctl_expose_service,
            expected_num_families_in_service=expected_num_families_in_service,
            expected_ip_family_policy=ip_family_policy,
        )

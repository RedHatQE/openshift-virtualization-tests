"""
Service Configuration via Manifest Tests

Tests for service configuration using manifest-based approach.

STP Reference:
TODO: add link
"""

import pytest

from tests.network.network_service.libservice import SERVICE_IP_FAMILY_POLICY_SINGLE_STACK


@pytest.mark.gating
class TestServiceConfigurationViaManifest:
    """
    Tests for configuring Kubernetes services via manifest.

    Markers:
        - gating

    Preconditions:
        - Running VM exposed with a service
    """

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
        """
        Test that service is created with configured IP family.

        Markers:
            - single_nic

        Parametrize:
            - ip_family: [IPv4, IPv6]

        Preconditions:
            - Single stack service created with specified IP family

        Steps:
            1. Get ipFamilies from service spec

        Expected:
            - Service has single IP family matching configuration
        """
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
        """
        Test that service is created with default SingleStack IP family policy.

        Markers:
            - single_nic

        Preconditions:
            - Service created with default IP family policy

        Steps:
            1. Get ipFamilyPolicy from service spec

        Expected:
            - Service ipFamilyPolicy is SingleStack
        """
        ip_family_policy = running_vm_for_exposure.custom_service.instance.spec.ipFamilyPolicy
        assert ip_family_policy == SERVICE_IP_FAMILY_POLICY_SINGLE_STACK, (
            f"Service created with wrong default ipfamilyPolicy on VM {running_vm_for_exposure.name}: "
            f"Expected: {SERVICE_IP_FAMILY_POLICY_SINGLE_STACK},"
            f"Actual: {ip_family_policy}"
        )

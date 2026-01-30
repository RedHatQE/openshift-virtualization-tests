"""
Service Configuration via virtctl Tests

Tests for service configuration using virtctl expose command.

STP Reference:
TODO: add link
"""

import pytest

from tests.network.network_service.libservice import (
    SERVICE_IP_FAMILY_POLICY_PREFER_DUAL_STACK,
    SERVICE_IP_FAMILY_POLICY_REQUIRE_DUAL_STACK,
    SERVICE_IP_FAMILY_POLICY_SINGLE_STACK,
    assert_svc_ip_params,
)


class TestServiceConfigurationViaVirtctl:
    """
    Tests for configuring Kubernetes services via virtctl expose command.

    Preconditions:
        - Running VM available for service exposure
        - Dual-stack cluster configured
    """

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
    def test_virtctl_expose_services(
        self,
        expected_num_families_in_service,
        running_vm_for_exposure,
        virtctl_expose_service,
        dual_stack_cluster,
        ip_family_policy,
    ):
        """
        Test that virtctl expose creates service with correct IP family policy.

        Markers:
            - single_nic

        Parametrize:
            - ip_family_policy: [SingleStack, PreferDualStack, RequireDualStack]

        Preconditions:
            - Service created via virtctl expose with specified IP family policy

        Steps:
            1. Verify service IP family parameters

        Expected:
            - Service has correct number of IP families and IP family policy
        """
        assert_svc_ip_params(
            svc=virtctl_expose_service,
            expected_num_families_in_service=expected_num_families_in_service,
            expected_ip_family_policy=ip_family_policy,
        )

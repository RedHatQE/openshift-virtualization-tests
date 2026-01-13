"""
Test network specific configurations when exposing a VM via a service.
"""

import pytest

SINGLE_STACK_SERVICE_IP_FAMILY = "IPv4"

SERVICE_IP_FAMILY_POLICY_SINGLE_STACK = "SingleStack"
SERVICE_IP_FAMILY_POLICY_PREFER_DUAL_STACK = "PreferDualStack"
SERVICE_IP_FAMILY_POLICY_REQUIRE_DUAL_STACK = "RequireDualStack"


@pytest.mark.gating
@pytest.mark.s390x
class TestServiceConfigurationViaManifest:
    @pytest.mark.polarion("CNV-5789")
    @pytest.mark.single_nic
    # Not marked as `conformance`; requires NMState
    def test_service_with_configured_ip_families(
        self,
        running_vm_for_exposure,
        single_stack_service,
    ):
        assert (
            len(running_vm_for_exposure.custom_service.instance.spec.ipFamilies) == 1
            and running_vm_for_exposure.custom_service.instance.spec.ipFamilies[0] == SINGLE_STACK_SERVICE_IP_FAMILY
        ), "Wrong ipFamilies set in service"

    @pytest.mark.polarion("CNV-5831")
    @pytest.mark.single_nic
    def test_service_with_default_ip_family_policy(
        self,
        running_vm_for_exposure,
        default_ip_family_policy_service,
    ):
        assert (
            running_vm_for_exposure.custom_service.instance.spec.ipFamilyPolicy == SERVICE_IP_FAMILY_POLICY_SINGLE_STACK
        ), "Service created with wrong default ipfamilyPolicy."


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
    def test_vitrctl_expose_services(
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

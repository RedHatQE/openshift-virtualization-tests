"""
Test network specific configurations when exposing a VM via a service.
"""

import pytest

from tests.network.ip_family_services.utils import SERVICE_IP_FAMILY_POLICY_SINGLE_STACK


@pytest.mark.gating
@pytest.mark.s390x
class TestServiceConfigurationViaManifest:
    @pytest.mark.single_nic
    @pytest.mark.usefixtures("single_stack_service")
    @pytest.mark.parametrize(
        "single_stack_service_ip_family",
        [
            pytest.param("IPv4", marks=[pytest.mark.ipv4, pytest.mark.polarion("CNV-5789")]),
            pytest.param("IPv6", marks=[pytest.mark.ipv6, pytest.mark.polarion("CNV-12557")]),
        ],
        indirect=False,
    )
    # Not marked as `conformance`; requires NMState
    def test_service_with_configured_ip_families(
        self,
        running_vm_for_exposure,
        single_stack_service_ip_family,
    ):
        assert (
            len(running_vm_for_exposure.custom_service.instance.spec.ipFamilies) == 1
            and running_vm_for_exposure.custom_service.instance.spec.ipFamilies[0] == single_stack_service_ip_family
        ), f"Wrong ipFamilies set in service: {single_stack_service_ip_family}"

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

"""
Test network specific configurations when exposing a VM via a service.
"""

import pytest

from tests.network.ip_family_services.libipfamilyservices import SERVICE_IP_FAMILY_POLICY_SINGLE_STACK

SINGLE_STACK_SERVICE_IP_FAMILY = "IPv4"


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
import logging

import pytest

from tests.infrastructure.vm_console_proxy.utils import assert_resource_existence_and_availability
from utilities.constants import TIMEOUT_1MIN
from utilities.vnc_utils import VNCConnection

LOGGER = logging.getLogger(__name__)


@pytest.mark.usefixtures("enabled_vm_console_proxy_spec")
@pytest.mark.s390x
class TestVmConsoleProxyEnablement:
    @pytest.mark.dependency(name="test_vm_proxy_cluster_resources_available")
    @pytest.mark.polarion("CNV-10416")
    def test_vm_proxy_cluster_resources_available(self, vm_console_proxy_cluster_resource):
        assert_resource_existence_and_availability(resource=vm_console_proxy_cluster_resource, timeout=TIMEOUT_1MIN)

    @pytest.mark.dependency(name="test_vm_proxy_namespaced_resources_available")
    @pytest.mark.polarion("CNV-10409")
    def test_vm_proxy_namespaced_resources_available(self, vm_console_proxy_namespace_resource):
        assert_resource_existence_and_availability(resource=vm_console_proxy_namespace_resource, timeout=TIMEOUT_1MIN)

    @pytest.mark.dependency(
        depends=[
            "test_vm_proxy_cluster_resources_available",
            "test_vm_proxy_namespaced_resources_available",
        ],
        name="test_vm_console_proxy_token_access",
    )
    @pytest.mark.polarion("CNV-10429")
    def test_vm_console_proxy_token_access(
        self,
        vm_for_console_proxy,
        vm_console_proxy_service_account,
        vm_service_account_role_binding,
        vm_console_proxy_service_account_role_binding,
        generated_service_account_token,
        generated_vnc_access_token,
        logged_with_token,
    ):
        with VNCConnection(vm=vm_for_console_proxy):
            LOGGER.info("VNC Connection to Virtual Machine is Successful")

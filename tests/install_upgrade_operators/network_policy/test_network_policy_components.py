import pytest
from ocp_resources.exceptions import ExecOnPodError

from utilities.constants import (
    KUBEVIRT_APISERVER_PROXY_NP,
    KUBEVIRT_CONSOLE_PLUGIN_NP,
)

from .utils import TEST_SERVER_PORT, build_curl_command

pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno, pytest.mark.arm64, pytest.mark.s390x]


@pytest.mark.polarion("CNV-12305")
@pytest.mark.parametrize("network_policy_name", [KUBEVIRT_CONSOLE_PLUGIN_NP])
def test_console_plugin_network_policy_blocks_ingress_unauthorized_traffic(
    ingress_allowall_connectivity_precheck,
    deployed_client_pod,
    service_ip_by_network_policy,
    service_port_by_network_policy,
):
    """
    Test that KUBEVIRT_CONSOLE_PLUGIN_NP blocks unauthorized traffic.

    It uses a test pod with curl to try to reach the service IP+PORT,
    which should be blocked by the NetworkPolicy.
    """
    with pytest.raises(ExecOnPodError):
        deployed_client_pod.execute(
            command=build_curl_command(service_ip_by_network_policy, service_port_by_network_policy, https=True)
        )


@pytest.mark.polarion("CNV-12306")
@pytest.mark.parametrize("network_policy_name", [KUBEVIRT_APISERVER_PROXY_NP])
def test_apiserver_proxy_network_policy_blocks_egress_unauthorized_traffic(
    egress_allowall_connectivity_precheck,
    pods_by_network_policy,
    deployed_server_service_ip,
):
    """
    Test that KUBEVIRT_APISERVER_PROXY_NP blocks unauthorized traffic.

    It iterates through all pods matching the NetworkPolicy podSelector
    and verifies that connections to the test server service are blocked.
    """
    for test_pod in pods_by_network_policy:
        with pytest.raises(ExecOnPodError):
            test_pod.execute(command=build_curl_command(deployed_server_service_ip, TEST_SERVER_PORT))

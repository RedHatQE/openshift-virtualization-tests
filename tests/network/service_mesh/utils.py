import logging

import pytest

from tests.network.utils import (
    assert_service_mesh_request,
    verify_console_command_output,
)
from utilities.constants import TIMEOUT_3MIN

LOGGER = logging.getLogger(__name__)


def traffic_management_request(vm, expected_output, **kwargs):
    """
    Return server response to a request sent from VM console. This request allows testing traffic manipulation.

    Args:
        vm (VirtualMachine): VM that will be used for console connection
        expected_output (str): The expected response from the server

    Kwargs: (Used to allow passing args from wait_service_mesh_components_convergence in service_mesh/conftest)
        server (ServiceMeshDeployments): request destination server
        destination (str): Istio Ingress svc addr

    Returns:
        str: Server response
    """
    return verify_console_command_output(
        vm=vm,
        command=f"curl -H host:{kwargs['server'].host} http://{kwargs['destination']}/version",
        expected_output=expected_output,
    )


def assert_traffic_management_request(vm, server, destination):
    expected_output = server.version
    request_response = traffic_management_request(
        vm=vm, server=server, destination=destination, expected_output=expected_output
    )
    assert_service_mesh_request(expected_output=expected_output, request_response=request_response)


def inbound_request(vm, destination_address, destination_port):
    expected_output = "200 OK"
    request_response = verify_console_command_output(
        timeout=TIMEOUT_3MIN,
        vm=vm,
        command=f"curl http://{destination_address}:{destination_port}",
        expected_output=expected_output,
    )
    with pytest.raises(AssertionError):
        assert_service_mesh_request(expected_output=expected_output, request_response=request_response)

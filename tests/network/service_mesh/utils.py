import logging

import pexpect
import pytest

from utilities import console
from utilities.constants import TIMEOUT_1MIN, TIMEOUT_3MIN
from utilities.virt import VirtualMachineForTests

LOGGER = logging.getLogger(__name__)


def traffic_management_request(vm, **kwargs):
    """
    Return server response to a request sent from VM console. This request allows testing traffic manipulation.

    Args:
        vm (VirtualMachine): VM that will be used for console connection

    Kwargs: (Used to allow passing args from wait_service_mesh_components_convergence in service_mesh/conftest)
        server (ServiceMeshDeployments): request destination server
        destination (str): Istio Ingress svc addr

    Returns:
        str: Server response
    """
    return run_console_command(
        vm=vm,
        command=f"curl -H host:{kwargs['server'].host} http://{kwargs['destination']}/version",
    )


def assert_traffic_management_request(vm, server, destination):
    expected_output = server.version
    request_response = traffic_management_request(vm=vm, server=server, destination=destination)
    assert_service_mesh_request(expected_output=expected_output, request_response=request_response)


def inbound_request(vm, destination_address, destination_port):
    expected_output = "200 OK"
    request_response = run_console_command(
        timeout=TIMEOUT_3MIN,
        vm=vm,
        command=f"curl http://{destination_address}:{destination_port}",
    )
    with pytest.raises(AssertionError):
        assert_service_mesh_request(expected_output=expected_output, request_response=request_response)


def assert_service_mesh_request(expected_output, request_response):
    assert expected_output in request_response, (
        f"Server response error.Expected output - {expected_output}received - {request_response}"
    )


def run_console_command(vm: VirtualMachineForTests, command: str, timeout: int = TIMEOUT_1MIN) -> str:
    """
    Execute a command in VM console and return the output.

    Args:
        vm (VirtualMachineForTests): VM to be used for console connection.
        command (str): Command to execute.
        timeout (int, default=TIMEOUT_1MIN): Timeout for the command execution.

    Returns:
        str: Command output.
    """
    prompt = r"\$ "
    with console.Console(vm=vm, prompt=prompt) as vmc:
        LOGGER.info(f"Execute {command} on {vm.name}")
        try:
            vmc.sendline(command)
            vmc.expect(prompt, timeout=timeout)
            return vmc.before
        except pexpect.exceptions.TIMEOUT:
            LOGGER.info(f"Timeout: {vmc.before}")
            return vmc.before
        except pexpect.exceptions.EOF:
            LOGGER.info(f"EOF: {vmc.before}")
            return vmc.before

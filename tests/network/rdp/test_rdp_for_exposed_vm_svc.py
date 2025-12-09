"""
Test RDP - Expose Windows VirtualMachine (latest version) as a service and use for authenticating RDP connection.
"""

import logging

import pytest
from ocp_resources.service import Service
from pyhelper_utils.shell import run_ssh_commands
from pytest_testconfig import config as py_config

from tests.os_params import WINDOWS_LATEST, WINDOWS_LATEST_OS
from utilities.constants import (
    OS_FLAVOR_WINDOWS,
    TIMEOUT_5MIN,
)
from utilities.virt import VirtualMachineForTests, vm_instance_from_template, wait_for_windows_vm

LOGGER = logging.getLogger(__name__)
TCP_TIMEOUT_SEC = 60

pytestmark = [pytest.mark.ipv4]


@pytest.fixture(scope="module")
def rdp_vm(
    request,
    namespace,
    golden_image_data_source_scope_function,
    unprivileged_client,
):
    with vm_instance_from_template(
        request=request,
        namespace=namespace,
        data_source=golden_image_data_source_scope_function,
        unprivileged_client=unprivileged_client,
    ) as rdp_vm:
        wait_for_windows_vm(vm=rdp_vm, version=request.param["os_version"])
        configure_rdp_on_server_windows_vm(vm=rdp_vm)
        rdp_vm.custom_service_enable(service_name="rdp-svc-test", port=3389, service_type=Service.Type.NODE_PORT)
        LOGGER.info(
            f"{Service.Type.NODE_PORT} service created to expose VirtualMachine "
            f"{rdp_vm.name} via RDP port {rdp_vm.custom_service.service_port}..."
        )
        yield rdp_vm


@pytest.fixture(scope="module")
def rdp_pod(workers_utility_pods, rdp_vm):
    """
    Return a pod on a different node than the one that runs the VM (rdp_vm).

    Returns:
        Pod: A Pod object to execute from.
    """
    for pod in workers_utility_pods:
        if pod.node.name != rdp_vm.vmi.node.name:
            return pod
    assert False, f"No Pod found on a different node than the one that runs the VirtualMachine {rdp_vm.name}."


def configure_rdp_on_server_windows_vm(vm: VirtualMachineForTests) -> None:
    LOGGER.info(f"Configuring RDP on Windows VM {vm.name}")
    enable_rdp_cmds = [
        # Allow RDP connections
        (
            "Set-ItemProperty "
            "-Path 'HKLM:\\System\\CurrentControlSet\\Control\\Terminal Server' "
            "-Name 'fDenyTSConnections' -Value 0"
        ),
        # Disable Network Level Authentication (NLA) for RDP
        (
            "Set-ItemProperty "
            "-Path 'HKLM:\\System\\CurrentControlSet\\Control\\Terminal Server\\WinStations\\RDP-Tcp' "
            "-Name 'UserAuthentication' -Value 0"
        ),
        # Enable Windows Firewall rules for Remote Desktop
        'Enable-NetFirewallRule -DisplayGroup "Remote Desktop"',
        # Restart Remote Desktop service to apply changes
        "Restart-Service TermService -Force",
    ]
    run_ssh_commands(
        host=vm.ssh_exec,
        commands=[["powershell", "-Command", cmd] for cmd in enable_rdp_cmds],
        tcp_timeout=TCP_TIMEOUT_SEC,
    )


@pytest.mark.parametrize(
    "golden_image_data_volume_scope_function, rdp_vm",
    [
        pytest.param(
            {
                "dv_name": WINDOWS_LATEST_OS,
                "image": WINDOWS_LATEST.get("image_path"),
                "storage_class": py_config["default_storage_class"],
                "dv_size": WINDOWS_LATEST.get("dv_size"),
            },
            {
                "vm_name": f"win{WINDOWS_LATEST.get('os_version')}-vm-test",
                "os_version": WINDOWS_LATEST.get("os_version"),
                "template_labels": WINDOWS_LATEST.get("template_labels"),
                "network_model": "virtio",
            },
            marks=(pytest.mark.polarion("CNV-235")),
            id="test_rdp_for_exposed_win_vm_svc",
        ),
    ],
    indirect=True,
)
def test_rdp_for_exposed_win_vm_as_node_port_svc(
    rdp_vm,
    rdp_pod,
):
    """
    Creates a Windows VM from the latest Windows version and starts the VM.
    Exposes the VM as a NodePort service and authenticates connection to the service via RDP.

    For authenticating the RDP connection, we will use two packages:
        1. xvfb - Virtual X display server.
        2. xfreerdp - X11 RDP client.
    """
    rdp_auth_cmd = (
        f"WLOG_PREFIX='[%hr:%mi:%se:%ml] [%mn] - ' xvfb-run --server-args='-screen 0 1024x768x24' "
        f"xfreerdp /cert-ignore /auth-only "
        f"/v:{rdp_vm.custom_service.instance.spec.clusterIP}:{rdp_vm.custom_service.port} "
        f"/u:{py_config['os_login_param'][OS_FLAVOR_WINDOWS]['username']} "
        f"/p:{py_config['os_login_param'][OS_FLAVOR_WINDOWS]['password']}"
    )
    LOGGER.info(f"Checking RDP connection to exposed {Service.Type.NODE_PORT} service, Authentication only...")
    auth_result = rdp_pod.execute(command=["bash", "-c", rdp_auth_cmd], timeout=TIMEOUT_5MIN)
    # The exit status is 0 when authentication succeeds, 1 otherwise.
    assert "exit status 0" in auth_result

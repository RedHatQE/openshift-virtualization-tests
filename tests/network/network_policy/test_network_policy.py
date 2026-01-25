"""
Network policy tests
"""

import shlex

import pytest
from pyhelper_utils.exceptions import CommandExecFailed
from pyhelper_utils.shell import run_ssh_commands

from utilities.constants import PORT_80

PORT_81 = 81
CURL_TIMEOUT = 5

pytestmark = pytest.mark.sno


@pytest.mark.order(before="test_network_policy_allow_http80")
@pytest.mark.polarion("CNV-369")
@pytest.mark.single_nic
@pytest.mark.s390x
def test_network_policy_deny_all_http(
    deny_all_http_ports,
    network_policy_vma,
    network_policy_vmb,
    running_network_policy_vma,
    running_network_policy_vmb,
):
    dst_ip = network_policy_vma.vmi.virt_launcher_pod.instance.status.podIP
    with pytest.raises(CommandExecFailed):
        run_ssh_commands(
            host=network_policy_vmb.ssh_exec,
            commands=[
                shlex.split(f"curl --head {dst_ip}:{port} --connect-timeout {CURL_TIMEOUT}")
                for port in [PORT_80, PORT_81]
            ],
        )


@pytest.mark.order(before="test_network_policy_allow_all_http")
@pytest.mark.polarion("CNV-2775")
@pytest.mark.single_nic
@pytest.mark.s390x
def test_network_policy_allow_http80(
    allow_http80_port,
    network_policy_vma,
    network_policy_vmb,
    running_network_policy_vma,
    running_network_policy_vmb,
):
    dst_ip = network_policy_vma.vmi.virt_launcher_pod.instance.status.podIP
    run_ssh_commands(
        host=network_policy_vmb.ssh_exec,
        commands=[shlex.split(f"curl --head {dst_ip}:{PORT_80} --connect-timeout {CURL_TIMEOUT}")],
    )

    with pytest.raises(CommandExecFailed):
        run_ssh_commands(
            host=network_policy_vmb.ssh_exec,
            commands=[shlex.split(f"curl --head {dst_ip}:{PORT_81} --connect-timeout {CURL_TIMEOUT}")],
        )


@pytest.mark.polarion("CNV-2774")
@pytest.mark.single_nic
@pytest.mark.s390x
def test_network_policy_allow_all_http(
    allow_all_http_ports,
    network_policy_vma,
    network_policy_vmb,
    running_network_policy_vma,
    running_network_policy_vmb,
):
    dst_ip = network_policy_vma.vmi.virt_launcher_pod.instance.status.podIP
    run_ssh_commands(
        host=network_policy_vmb.ssh_exec,
        commands=[
            shlex.split(f"curl --head {dst_ip}:{port} --connect-timeout {CURL_TIMEOUT}") for port in [PORT_80, PORT_81]
        ],
    )
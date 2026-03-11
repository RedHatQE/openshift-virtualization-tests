import shlex

import pytest
from pyhelper_utils.exceptions import CommandExecFailed
from pyhelper_utils.shell import run_ssh_commands

from tests.network.network_policy.libnetpolicy import TEST_PORTS, format_curl_command

pytestmark = pytest.mark.sno


@pytest.mark.usefixtures("deny_all_http_ports")
@pytest.mark.order(before="test_network_policy_allow_single_http_port")
@pytest.mark.polarion("CNV-369")
@pytest.mark.single_nic
@pytest.mark.s390x
def test_network_policy_deny_all_http(
    subtests,
    network_policy_vma,
    network_policy_vmb,
    admin_client,
):
    pod_ips = network_policy_vma.vmi.get_virt_launcher_pod(privileged_client=admin_client).instance.status.podIPs
    for pod_ip_entry in pod_ips:
        dst_ip = pod_ip_entry["ip"]
        with subtests.test(msg=f"Testing {dst_ip}"):
            for port in TEST_PORTS:
                with pytest.raises(CommandExecFailed):
                    run_ssh_commands(
                        host=network_policy_vmb.ssh_exec,
                        commands=[shlex.split(format_curl_command(ip_address=dst_ip, port=port))],
                    )


@pytest.mark.usefixtures("allow_single_http_port")
@pytest.mark.order(before="test_network_policy_allow_all_http")
@pytest.mark.polarion("CNV-2775")
@pytest.mark.single_nic
@pytest.mark.s390x
def test_network_policy_allow_single_http_port(
    subtests,
    network_policy_vma,
    network_policy_vmb,
    admin_client,
):
    pod_ips = network_policy_vma.vmi.get_virt_launcher_pod(privileged_client=admin_client).instance.status.podIPs
    for pod_ip_entry in pod_ips:
        dst_ip = pod_ip_entry["ip"]
        with subtests.test(msg=f"Testing {dst_ip}"):
            run_ssh_commands(
                host=network_policy_vmb.ssh_exec,
                commands=[shlex.split(format_curl_command(ip_address=dst_ip, port=TEST_PORTS[0], head=True))],
            )

            with pytest.raises(CommandExecFailed):
                run_ssh_commands(
                    host=network_policy_vmb.ssh_exec,
                    commands=[shlex.split(format_curl_command(ip_address=dst_ip, port=TEST_PORTS[1], head=True))],
                )


@pytest.mark.usefixtures("allow_all_http_ports")
@pytest.mark.polarion("CNV-2774")
@pytest.mark.single_nic
@pytest.mark.s390x
def test_network_policy_allow_all_http(
    subtests,
    network_policy_vma,
    network_policy_vmb,
    admin_client,
):
    pod_ips = network_policy_vma.vmi.get_virt_launcher_pod(privileged_client=admin_client).instance.status.podIPs
    for pod_ip_entry in pod_ips:
        dst_ip = pod_ip_entry["ip"]
        with subtests.test(msg=f"Testing {dst_ip}"):
            run_ssh_commands(
                host=network_policy_vmb.ssh_exec,
                commands=[
                    shlex.split(format_curl_command(ip_address=dst_ip, port=port, head=True)) for port in TEST_PORTS
                ],
            )

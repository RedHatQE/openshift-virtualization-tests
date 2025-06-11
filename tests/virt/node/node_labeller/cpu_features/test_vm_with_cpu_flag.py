"""
VM with CPU flag
"""

import pytest
from timeout_sampler import TimeoutExpiredError

from utilities.constants import TIMEOUT_1MIN
from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm

pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno]


@pytest.fixture()
def cpu_flag_vm_positive(cluster_common_node_cpu, namespace, unprivileged_client):
    name = "vm-cpu-flags-positive"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        cpu_flags={"model": cluster_common_node_cpu},
        body=fedora_vm_body(name=name),
        client=unprivileged_client,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture(
    params=[
        pytest.param(
            [{"model": "Bad-Skylake-Server"}, "bad-skylake-server"],
            marks=(pytest.mark.polarion("CNV-1272")),
        ),
        pytest.param(
            [{"model": "commodore64"}, "commodore64"],
            marks=(pytest.mark.polarion("CNV-1273")),
        ),
    ],
    ids=["CPU-flag: Bad-Skylake-Server", "CPU-flag: commodore64"],
)
def cpu_flag_vm_negative(request, unprivileged_client, namespace):
    name = f"vm-cpu-flags-negative-{request.param[1]}"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        cpu_flags=request.param[0],
        body=fedora_vm_body(name=name),
        client=unprivileged_client,
    ) as vm:
        vm.start()
        yield vm


def test_vm_with_cpu_flag_negative(cpu_flag_vm_negative):
    """
    Negative test:
    Test VM with wrong cpu model,
    VM should not run in this case since cpu model not exist on any of the nodes
    """
    with pytest.raises(TimeoutExpiredError):
        cpu_flag_vm_negative.vmi.wait_until_running(timeout=TIMEOUT_1MIN)


@pytest.mark.gating
@pytest.mark.x86_64
@pytest.mark.s390x
@pytest.mark.polarion("CNV-1269")
def test_vm_with_cpu_flag_positive_case(cpu_flag_vm_positive, cluster_common_node_cpu):
    """
    Test VM with cpu flag, test CPU model and SSH connectivity
    """
    cpu_flag_vm_positive.ssh_exec.executor().is_connective()
    assert (
        cpu_flag_vm_positive.instance["spec"]["template"]["spec"]["domain"]["cpu"]["model"] == cluster_common_node_cpu
    )

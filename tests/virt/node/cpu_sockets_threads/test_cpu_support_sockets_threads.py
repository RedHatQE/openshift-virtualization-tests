"""
Test cpu support for sockets and threads
"""

import pytest
from kubernetes.dynamic.exceptions import UnprocessibleEntityError

from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm

pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno, pytest.mark.arm64]


def check_vm_dumpxml(vm, cores=None, sockets=None, threads=None):
    cpu = vm.privileged_vmi.xml_dict["domain"]["cpu"]["topology"]
    if sockets:
        assert cpu["@sockets"] == str(sockets), f"CPU sockets: Expected {sockets}, Found: {cpu['@sockets']}"
    if cores:
        assert cpu["@cores"] == str(cores), f"CPU cores: Expected {cores}, Found: {cpu['@cores']}"
    if threads:
        assert cpu["@threads"] == str(threads), f"CPU threads: Expected {threads}, Found: {cpu['@threads']}"


@pytest.fixture()
def vm_with_cpu_support(request, is_s390x_cluster, namespace, unprivileged_client):
    """
    VM with CPU support (cores,sockets,threads)
    """
    name = "vm-cpu-support"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        cpu_cores=request.param["cores"],
        cpu_sockets=request.param["sockets"],
        cpu_threads=1 if is_s390x_cluster else request.param["threads"],
        cpu_max_sockets=request.param["sockets"] or 1,
        body=fedora_vm_body(name=name),
        client=unprivileged_client,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.mark.parametrize(
    "vm_with_cpu_support",
    [
        pytest.param(
            {"sockets": 2, "cores": 2, "threads": 2},
            marks=(pytest.mark.polarion("CNV-2820"), pytest.mark.gating, pytest.mark.conformance),
            id="case1: 2 cores, 2 threads, 2 sockets",
        ),
        pytest.param(
            {"sockets": None, "cores": 1, "threads": 2},
            marks=(pytest.mark.polarion("CNV-2823")),
            id="case2: 1 cores, 2 threads, no sockets",
        ),
        pytest.param(
            {"sockets": 2, "cores": 1, "threads": None},
            marks=(pytest.mark.polarion("CNV-2822")),
            id="case3: 1 cores, no threads, 2 sockets",
        ),
        pytest.param(
            {"sockets": None, "cores": 2, "threads": None},
            marks=(pytest.mark.polarion("CNV-2821")),
            id="case4: 2 cores, no threads, no sockets",
        ),
    ],
    indirect=True,
)
@pytest.mark.s390x
def test_vm_with_cpu_support(vm_with_cpu_support):
    """
    Test VM with cpu support
    """
    check_vm_dumpxml(
        vm=vm_with_cpu_support,
        sockets=vm_with_cpu_support.cpu_sockets,
        cores=vm_with_cpu_support.cpu_cores,
        threads=vm_with_cpu_support.cpu_threads,
    )


@pytest.fixture()
def no_cpu_settings_vm(namespace, unprivileged_client):
    """
    Create VM without specific CPU settings
    """
    name = "no-cpu-settings-vm"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        body=fedora_vm_body(name=name),
        client=unprivileged_client,
    ) as vm:
        vm.start(wait=True)
        vm.vmi.wait_until_running()
        yield vm


@pytest.mark.gating
@pytest.mark.conformance
@pytest.mark.s390x
@pytest.mark.polarion("CNV-1485")
def test_vm_with_no_cpu_settings(no_cpu_settings_vm):
    """
    Test VM without cpu setting, check XML:
    <topology sockets='X' cores='1' threads='1'/>
    socket value will depend on maxSockets autocalculation on cluster
    """
    check_vm_dumpxml(vm=no_cpu_settings_vm, cores="1", threads="1")


@pytest.mark.gating
@pytest.mark.s390x
@pytest.mark.polarion("CNV-2818")
def test_vm_with_cpu_limitation(namespace, unprivileged_client):
    """
    Test VM with cpu limitation, CPU requests and limits are equals
    """
    name = "vm-cpu-limitation"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        cpu_cores=2,
        cpu_limits=2,
        cpu_requests=2,
        cpu_max_sockets=1,
        body=fedora_vm_body(name=name),
        client=unprivileged_client,
    ) as vm:
        vm.start(wait=True)
        vm.vmi.wait_until_running()
        check_vm_dumpxml(vm=vm, sockets="1", cores="2", threads="1")


@pytest.mark.polarion("CNV-2819")
@pytest.mark.s390x
def test_vm_with_cpu_limitation_negative(namespace, unprivileged_client):
    """
    Test VM with cpu limitation
    negative case: CPU requests is larger then limits
    """
    name = "vm-cpu-limitation-negative"
    with pytest.raises(UnprocessibleEntityError):
        with VirtualMachineForTests(
            name=name,
            namespace=namespace.name,
            cpu_limits=2,
            cpu_requests=4,
            body=fedora_vm_body(name=name),
            client=unprivileged_client,
        ):
            return

import logging

import bitmath
import pytest

from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm

LOGGER = logging.getLogger(__name__)

VM_MEMORY = "2Gi"


@pytest.fixture()
def vm_for_memory_overcommit(request, namespace):
    name = request.param["vm_name"]
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        body=fedora_vm_body(name=name),
        memory_guest=VM_MEMORY,
        memory_requests=request.param.get("memory_requests"),
    ) as vm:
        running_vm(vm=vm, wait_for_interfaces=False, check_ssh_connectivity=False)
        yield vm


@pytest.mark.gating
@pytest.mark.usefixtures("hco_memory_overcommit_increased")
class TestMemoryOvercommit:
    @pytest.mark.parametrize(
        "vm_for_memory_overcommit, expected_less_memory",
        [
            pytest.param(
                {"vm_name": "vm-with-guest-only"},
                True,
                marks=pytest.mark.polarion("CNV-12376"),
                id="vm_with_guest_only_has_less_pod_memory",
            ),
            pytest.param(
                {
                    "vm_name": "vm-with-memory-request",
                    "memory_requests": VM_MEMORY,
                },
                False,
                marks=pytest.mark.polarion("CNV-12377"),
                id="vm_with_memory_request_not_overcommited",
            ),
        ],
        indirect=["vm_for_memory_overcommit"],
    )
    def test_vm_memory_overcommit(
        self,
        admin_client,
        vm_for_memory_overcommit,
        expected_less_memory,
    ):
        pod_instance = vm_for_memory_overcommit.vmi.get_virt_launcher_pod(privileged_client=admin_client).instance
        pod_memory = pod_instance.spec.containers[0].resources.requests["memory"]
        assert (
            bitmath.parse_string_unsafe(pod_memory) < bitmath.parse_string_unsafe(VM_MEMORY)
        ) == expected_less_memory, f"POD Requests: {pod_memory}, VM Memory: {VM_MEMORY}"

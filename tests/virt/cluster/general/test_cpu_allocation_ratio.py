import pytest
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.limit_range import LimitRange

from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm

CPU_CORES = 3
CPU_THREADS = 1
CPU_SOCKETS = 1
VMI_CPU_ALLOCATION_RATIO = 20


def assert_pod_cpu_request_value(vmi_cpu_allocation_from_kubevirt, vm):
    cpu = vm.vmi.instance.spec.domain.cpu
    number_of_vcpus = cpu.cores * cpu.sockets * cpu.threads
    actual_pod_cpu_request = vm.vmi.virt_launcher_pod.instance.spec.containers[0].resources.requests.cpu
    expected_pod_cpu_request = int(number_of_vcpus * 1000 / vmi_cpu_allocation_from_kubevirt)
    assert actual_pod_cpu_request == f"{expected_pod_cpu_request}m", (
        f"expected_pod_cpu_request:{expected_pod_cpu_request} != actual_pod_cpu_request:{actual_pod_cpu_request}"
    )


def assert_vmi_cpu_allocation_ratio(vmi_cpu_allocation_from_kubevirt, cpu_allocation_ratio_from_hco):
    assert VMI_CPU_ALLOCATION_RATIO == cpu_allocation_ratio_from_hco, (
        f"cpuAllocationRatio:{VMI_CPU_ALLOCATION_RATIO}!=cpuAllocationSetInHco{cpu_allocation_ratio_from_hco}"
    )
    assert vmi_cpu_allocation_from_kubevirt == cpu_allocation_ratio_from_hco, (
        f"cpuAllocationKubevirt:{vmi_cpu_allocation_from_kubevirt}!=cpuAllocationHco:{cpu_allocation_ratio_from_hco}"
    )


@pytest.fixture()
def vmi_cpu_allocation_from_kubevirt(kubevirt_config):
    return kubevirt_config["developerConfiguration"]["cpuAllocationRatio"]


@pytest.fixture()
def vmi_cpu_allocation_ratio_from_hco_post_update(
    hyperconverged_resource_scope_function,
):
    return hyperconverged_resource_scope_function.instance.to_dict()["spec"]["resourceRequirements"][
        "vmiCPUAllocationRatio"
    ]


@pytest.fixture()
def hco_cr_with_vmi_cpu_allocation_ratio(
    hyperconverged_resource_scope_function,
):
    with ResourceEditorValidateHCOReconcile(
        patches={
            hyperconverged_resource_scope_function: {
                "spec": {"resourceRequirements": {"vmiCPUAllocationRatio": VMI_CPU_ALLOCATION_RATIO}}
            }
        },
        list_resource_reconcile=[KubeVirt],
        wait_for_reconcile_post_update=True,
    ):
        yield


@pytest.fixture()
def vm_for_test_cpu_allocation_ratio(
    namespace,
):
    name = "vm-for-cpu-allocation-ratio-test"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        cpu_cores=CPU_CORES,
        cpu_sockets=CPU_SOCKETS,
        cpu_threads=CPU_THREADS,
        body=fedora_vm_body(name=name),
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture()
def limit_range_for_cpu_allocation_test(namespace):
    with LimitRange(
        name="limit-range-for-cpu-allocation-test",
        namespace=namespace.name,
        limits=[
            {
                "default": {"cpu": "1"},
                "defaultRequest": {"cpu": "100m"},
                "max": {"cpu": "1100m"},
                "type": "Container",
            }
        ],
    ) as limit_range:
        yield limit_range


@pytest.mark.polarion("CNV-10521")
def test_inspect_cpu_allocation_ratio_pod(
    hco_cr_with_vmi_cpu_allocation_ratio,
    vm_for_test_cpu_allocation_ratio,
    vmi_cpu_allocation_from_kubevirt,
    vmi_cpu_allocation_ratio_from_hco_post_update,
):
    (
        assert_vmi_cpu_allocation_ratio(
            vmi_cpu_allocation_from_kubevirt=vmi_cpu_allocation_from_kubevirt,
            cpu_allocation_ratio_from_hco=vmi_cpu_allocation_ratio_from_hco_post_update,
        ),
    )
    (
        assert_pod_cpu_request_value(
            vmi_cpu_allocation_from_kubevirt=vmi_cpu_allocation_from_kubevirt,
            vm=vm_for_test_cpu_allocation_ratio,
        ),
    )


@pytest.mark.polarion("CNV-11294")
def test_limitrange_default_cpu_not_override_vm_cpu(
    limit_range_for_cpu_allocation_test,
    vmi_cpu_allocation_from_kubevirt,
    vm_for_test_cpu_allocation_ratio,
):
    assert_pod_cpu_request_value(
        vmi_cpu_allocation_from_kubevirt=vmi_cpu_allocation_from_kubevirt,
        vm=vm_for_test_cpu_allocation_ratio,
    )

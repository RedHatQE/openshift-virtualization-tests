import bitmath
import pytest
from ocp_resources.resource_quota import ResourceQuota

from tests.utils import hotplug_resource_and_wait_hotplug_migration_finish
from utilities.virt import (
    VirtualMachineForTests,
    fedora_vm_body,
    running_vm,
)

RESOURCE_QUOTA_CPU_LIMIT = 5
RESOURCE_QUOTA_MEMORY_LIMIT = "5Gi"

CPU_SOCKET_HOTPLUG = 3


@pytest.fixture()
def resource_quota_for_auto_resource_limits_test(request, namespace):
    with ResourceQuota(
        name="resource-quota-for-auto-resource-limits-test",
        namespace=namespace.name,
        hard=request.param,
    ) as resource_quota:
        yield resource_quota


@pytest.fixture()
def vm_auto_resource_limits(request, namespace, unprivileged_client, cpu_for_migration):
    with VirtualMachineForTests(
        name=request.param["name"],
        namespace=namespace.name,
        cpu_cores=1,
        cpu_sockets=1,
        memory_guest="1Gi",
        cpu_limits=request.param.get("cpu_limits"),
        memory_limits=request.param.get("memory_limits"),
        cpu_model=cpu_for_migration,
        body=fedora_vm_body(name=request.param["name"]),
        client=unprivileged_client,
    ) as vm:
        running_vm(vm=vm, wait_for_interfaces=False, check_ssh_connectivity=False)
        yield vm


@pytest.fixture()
def hotplugged_vm_with_cpu_auto_limits(vm_auto_resource_limits, unprivileged_client):
    hotplug_resource_and_wait_hotplug_migration_finish(
        vm=vm_auto_resource_limits, client=unprivileged_client, sockets=CPU_SOCKET_HOTPLUG
    )


@pytest.mark.gating
@pytest.mark.parametrize(
    "resource_quota_for_auto_resource_limits_test, vm_auto_resource_limits, expected_limits",
    [
        pytest.param(
            {
                "limits.cpu": RESOURCE_QUOTA_CPU_LIMIT,
            },
            {
                "name": "vm-for-cpu-limit",
            },
            {"cpu": True, "memory": False},
            marks=pytest.mark.polarion("CNV-11216"),
            id="set_only_cpu",
        ),
        pytest.param(
            {
                "limits.memory": RESOURCE_QUOTA_MEMORY_LIMIT,
            },
            {
                "name": "vm-for-memory-limit",
            },
            {"cpu": False, "memory": True},
            marks=pytest.mark.polarion("CNV-11217"),
            id="set_only_memory",
        ),
    ],
    indirect=["resource_quota_for_auto_resource_limits_test", "vm_auto_resource_limits"],
)
def test_auto_limits_set_one_resource(
    resource_quota_for_auto_resource_limits_test,
    vm_auto_resource_limits,
    expected_limits,
):
    pod_limits = vm_auto_resource_limits.vmi.virt_launcher_pod.instance.spec.containers[0].resources.limits
    for resource in expected_limits:
        if expected_limits[resource]:
            assert getattr(pod_limits, resource), f"{resource} limits should be set, \n {pod_limits}"
        else:
            assert not getattr(pod_limits, resource), f"{resource} limits should not be set, \n {pod_limits}"


@pytest.mark.parametrize(
    "resource_quota_for_auto_resource_limits_test, vm_auto_resource_limits",
    [
        pytest.param(
            {
                "limits.cpu": RESOURCE_QUOTA_CPU_LIMIT,
                "limits.memory": RESOURCE_QUOTA_MEMORY_LIMIT,
            },
            {
                "name": "vm-with-limits",
                "cpu_limits": "2",
                "memory_limits": "2Gi",
            },
            marks=(pytest.mark.polarion("CNV-11218"), pytest.mark.gating()),
        ),
    ],
    indirect=True,
)
def test_vm_with_limits_overrides_global_vlaues(
    resource_quota_for_auto_resource_limits_test,
    vm_auto_resource_limits,
):
    pod_limits = vm_auto_resource_limits.vmi.virt_launcher_pod.instance.spec.containers[0].resources.limits
    assert pod_limits.cpu == vm_auto_resource_limits.cpu_limits, (
        f"Cpu limits on the pod is not correct, expected {vm_auto_resource_limits.cpu_limits}, actual {pod_limits.cpu}"
    )
    # memory on the POD includes some overhead, need to round to the nearest GiB
    pod_memory = round(bitmath.parse_string_unsafe(s=pod_limits.memory).to_GiB().value)
    vm_memory = round(bitmath.parse_string_unsafe(s=vm_auto_resource_limits.memory_limits).to_GiB().value)
    assert pod_memory == vm_memory, (
        f"Memory limits on the pod is not correct, expected {vm_auto_resource_limits.memory_limits}, "
        f"actual {pod_limits.memory}"
    )


@pytest.mark.parametrize(
    "resource_quota_for_auto_resource_limits_test, vm_auto_resource_limits",
    [
        pytest.param(
            {
                "limits.cpu": RESOURCE_QUOTA_CPU_LIMIT,
            },
            {
                "name": "vm-for-auto-limits-and-cpu-hotplug",
            },
            marks=pytest.mark.polarion("CNV-11219"),
        ),
    ],
    indirect=True,
)
def test_auto_limits_with_cpu_hotplug(
    skip_if_no_common_cpu,
    resource_quota_for_auto_resource_limits_test,
    vm_auto_resource_limits,
    hotplugged_vm_with_cpu_auto_limits,
):
    pod_limits = vm_auto_resource_limits.vmi.virt_launcher_pod.instance.spec.containers[0].resources.limits
    assert int(pod_limits.cpu) == CPU_SOCKET_HOTPLUG, (
        f"Cpu limits on the pod is not correct, expected {CPU_SOCKET_HOTPLUG}, actual {pod_limits.cpu}"
    )

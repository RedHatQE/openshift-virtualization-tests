import logging

import bitmath
from ocp_resources.application_aware_applied_cluster_resource_quota import ApplicationAwareAppliedClusterResourceQuota
from ocp_resources.virtual_machine import VirtualMachine
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.virt.constants import PODS_STR
from tests.virt.utils import check_arq_status_values, wait_for_virt_launcher_pod, wait_when_pod_in_gated_state
from utilities.constants import (
    AAQ_VIRTUAL_RESOURCES,
    AAQ_VMI_POD_USAGE,
    TIMEOUT_1MIN,
    TIMEOUT_5SEC,
)

LOGGER = logging.getLogger(__name__)


def restart_vm_wait_for_gated_state(vm):
    vmi_old_pod = vm.vmi.virt_launcher_pod
    vm.restart()
    vmi_old_pod.wait_deleted()
    vm.wait_for_specific_status(status=VirtualMachine.Status.STARTING)
    wait_for_virt_launcher_pod(vmi=vm.vmi)
    wait_when_pod_in_gated_state(pod=vm.vmi.virt_launcher_pod)


def wait_for_aacrq_object_created(namespace, acrq_name):
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_1MIN,
        sleep=TIMEOUT_5SEC,
        func=lambda: ApplicationAwareAppliedClusterResourceQuota(namespace=namespace.name, name=acrq_name).exists,
    )
    try:
        for sample in samples:
            if sample:
                return
    except TimeoutExpiredError:
        LOGGER.error(f"AACRQ {acrq_name} not created in namespace {namespace.name}")
        raise


def get_pod_total_cpu_memory(pod_instance):
    # Convert CPU to millicores
    def _convert_cpu(cpu):
        return int(cpu[:-1]) if "m" in cpu else int(cpu) * 1000

    total_resources = {"limits": {"cpu": 0, "memory": 0}, "requests": {"cpu": 0, "memory": 0}}

    # sum CPU and memory for all containers
    for container in pod_instance.spec.containers:
        total_resources["limits"]["cpu"] += _convert_cpu(container.resources.limits.get("cpu", 0))
        total_resources["limits"]["memory"] += int(
            bitmath.parse_string_unsafe(container.resources.limits.get("memory", "0B")).to_Byte()
        )

        total_resources["requests"]["cpu"] += _convert_cpu(container.resources.requests.get("cpu", 0))
        total_resources["requests"]["memory"] += int(
            bitmath.parse_string_unsafe(container.resources.requests.get("memory", "0B")).to_Byte()
        )

    total_resources["limits"]["cpu"] = f"{total_resources['limits']['cpu']}m"
    total_resources["requests"]["cpu"] = f"{total_resources['requests']['cpu']}m"

    return total_resources


def check_arq_status_values_different_allocations(arq, vm, allocation_method):
    if allocation_method == AAQ_VIRTUAL_RESOURCES:
        # with VirtualResources allocation method ARQ shows what VM has in the spec
        resources = vm.vmi.instance.spec.domain.resources.to_dict()
    elif allocation_method == AAQ_VMI_POD_USAGE:
        # with VmiPodUsage allocation method ARQ shows the total POD usage (all containers)
        resources = get_pod_total_cpu_memory(pod_instance=vm.vmi.virt_launcher_pod.instance)

    assert resources, f"Not supported allocation method: {allocation_method}"

    check_arq_status_values(
        current_values=arq.instance.status.used,
        expected_values={PODS_STR: "1", **resources},
    )

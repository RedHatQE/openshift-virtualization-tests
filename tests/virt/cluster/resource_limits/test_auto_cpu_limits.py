import pytest
from ocp_resources.kubevirt import KubeVirt

from utilities.constants import RESOURCE_REQUIREMENTS_KEY_HCO_CR
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.infra import label_project
from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm

CORES = 2
SOCKETS = 2
THREADS = 2
TOTAL_GUEST_CPU = str(CORES * SOCKETS * THREADS)

REQUESTS = "requests"
LIMITS = "limits"

REQUESTS_300 = "300m"
LIMITS_500 = "500m"

AUTO_CPU_LIMIT_NAMESPACE_LABEL_SELECTOR = "autoCPULimitNamespaceLabelSelector"
CPU_LIMIT_LABEL = {"autocpulimit": "true"}


@pytest.fixture()
def vm_auto_cpu_limits(request, namespace, unprivileged_client):
    with VirtualMachineForTests(
        name=request.param["name"],
        namespace=namespace.name,
        cpu_cores=request.param.get("cpu_cores"),
        cpu_sockets=request.param.get("cpu_sockets"),
        cpu_threads=request.param.get("cpu_threads"),
        cpu_requests=request.param.get("cpu_requests"),
        cpu_limits=request.param.get("cpu_limits"),
        body=fedora_vm_body(name=request.param["name"]),
        client=unprivileged_client,
    ) as vm:
        running_vm(vm=vm, wait_for_interfaces=False, check_ssh_connectivity=False)
        yield vm


@pytest.fixture(scope="class")
def auto_cpu_limit_enabled_on_hco(admin_client, hyperconverged_resource_scope_class):
    with ResourceEditorValidateHCOReconcile(
        patches={
            hyperconverged_resource_scope_class: {
                "spec": {
                    RESOURCE_REQUIREMENTS_KEY_HCO_CR: {
                        AUTO_CPU_LIMIT_NAMESPACE_LABEL_SELECTOR: {"matchLabels:": CPU_LIMIT_LABEL}
                    }
                }
            }
        },
        list_resource_reconcile=[KubeVirt],
        wait_for_reconcile_post_update=True,
    ):
        yield


@pytest.fixture()
def labeled_namespace_with_cpu_limit(admin_client, namespace):
    label_project(name=namespace.name, label=CPU_LIMIT_LABEL, admin_client=admin_client)


@pytest.mark.usefixtures(
    "auto_cpu_limit_enabled_on_hco",
)
class TestAutoCpuLimits:
    @pytest.mark.parametrize(
        "vm_auto_cpu_limits, expected_cpu_values",
        [
            pytest.param(
                {
                    "name": "vm-cpu-requests",
                    "cpu_requests": REQUESTS_300,
                },
                {
                    REQUESTS: REQUESTS_300,
                    LIMITS: "1",
                },
                marks=pytest.mark.polarion("CNV-10101"),
                id="set_limit_in_any_namespaces",
            ),
            pytest.param(
                {
                    "name": "vm-cpu-requests-limits",
                    "cpu_requests": REQUESTS_300,
                    "cpu_limits": LIMITS_500,
                },
                {
                    REQUESTS: REQUESTS_300,
                    LIMITS: LIMITS_500,
                },
                marks=pytest.mark.polarion("CNV-10104"),
                id="vm_with_limits_override_global_values",
            ),
            pytest.param(
                {
                    "name": "vm-guest-cpu",
                    "cpu_cores": CORES,
                    "cpu_sockets": SOCKETS,
                    "cpu_threads": THREADS,
                },
                {
                    REQUESTS: f"{TOTAL_GUEST_CPU}00m",
                    LIMITS: TOTAL_GUEST_CPU,
                },
                marks=pytest.mark.polarion("CNV-10109"),
                id="limits_equal_to_number_of_guest_cpu",
            ),
        ],
        indirect=["vm_auto_cpu_limits"],
    )
    def test_auto_cpu_limits_successfully_applied(
        self,
        labeled_namespace_with_cpu_limit,
        vm_auto_cpu_limits,
        expected_cpu_values,
    ):
        vm_resources = vm_auto_cpu_limits.vmi.virt_launcher_pod.instance.spec.containers[0].resources
        assert vm_resources.requests.cpu == expected_cpu_values[REQUESTS], (
            f"Cpu requests on the pod is not correct, expected {expected_cpu_values[REQUESTS]}, "
            f"actual {vm_resources.requests.cpu}"
        )
        assert vm_resources.limits.cpu == expected_cpu_values[LIMITS], (
            f"Cpu limits on the pod is not correct, expected {expected_cpu_values[LIMITS]}, "
            f"actual {vm_resources.limits.cpu}"
        )

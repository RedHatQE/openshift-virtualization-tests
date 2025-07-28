import logging
import re
import shlex

import bitmath
import pytest
from kubernetes.dynamic.exceptions import UnprocessibleEntityError
from ocp_resources.daemonset import DaemonSet
from ocp_resources.data_source import DataSource
from ocp_resources.datavolume import DataVolume
from ocp_resources.deployment import Deployment
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_resources.pod import Pod
from ocp_resources.resource import Resource, ResourceEditor, get_client
from ocp_resources.storage_class import StorageClass
from ocp_resources.virtual_machine import VirtualMachine
from ocp_resources.virtual_machine_instance_migration import VirtualMachineInstanceMigration
from ocp_resources.virtual_machine_restore import VirtualMachineRestore
from pyhelper_utils.shell import run_ssh_commands
from pytest_testconfig import py_config
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.observability.metrics.constants import (
    BINDING_NAME,
    BINDING_TYPE,
    CNV_VMI_STATUS_RUNNING_COUNT,
    KUBEVIRT_API_REQUEST_DEPRECATED_TOTAL_WITH_VERSION_VERB_AND_RESOURCE,
    KUBEVIRT_CONSOLE_ACTIVE_CONNECTIONS_BY_VMI,
    KUBEVIRT_VM_CREATED_TOTAL_STR,
    KUBEVIRT_VMI_MIGRATIONS_IN_RUNNING_PHASE,
    KUBEVIRT_VMI_MIGRATIONS_IN_SCHEDULING_PHASE,
    KUBEVIRT_VMI_PHASE_COUNT_STR,
    KUBEVIRT_VMI_STATUS_ADDRESSES,
    KUBEVIRT_VNC_ACTIVE_CONNECTIONS_BY_VMI,
)
from tests.observability.metrics.utils import (
    SINGLE_VM,
    ZERO_CPU_CORES,
    binding_name_and_type_from_vm_or_vmi,
    create_windows11_wsl2_vm,
    disk_file_system_info,
    enable_swap_fedora_vm,
    fail_if_not_zero_restartcount,
    get_interface_name_from_vm,
    get_metric_sum_value,
    get_mutation_component_value_from_prometheus,
    get_not_running_prometheus_pods,
    get_resource_object,
    get_vm_comparison_info_dict,
    get_vmi_dommemstat_from_vm,
    get_vmi_guest_os_kernel_release_info_metric_from_vm,
    get_vmi_memory_domain_metric_value_from_prometheus,
    get_vmi_phase_count,
    metric_result_output_dict_by_mountpoint,
    restart_cdi_worker_pod,
    run_node_command,
    run_vm_commands,
    wait_for_metric_reset,
    wait_for_metric_vmi_request_cpu_cores_output,
    wait_for_no_metrics_value,
)
from tests.observability.utils import validate_metrics_value
from tests.utils import create_cirros_vm, create_vms, wait_for_cr_labels_change
from utilities import console
from utilities.constants import (
    CDI_UPLOAD_TMP_PVC,
    CLUSTER_NETWORK_ADDONS_OPERATOR,
    COUNT_FIVE,
    IPV4_STR,
    KUBEVIRT_VMI_MEMORY_DOMAIN_BYTES,
    KUBEVIRT_VMI_MEMORY_PGMAJFAULT_TOTAL,
    KUBEVIRT_VMI_MEMORY_PGMINFAULT_TOTAL,
    KUBEVIRT_VMI_MEMORY_SWAP_IN_TRAFFIC_BYTES,
    KUBEVIRT_VMI_MEMORY_SWAP_OUT_TRAFFIC_BYTES,
    KUBEVIRT_VMI_MEMORY_UNUSED_BYTES,
    KUBEVIRT_VMI_MEMORY_USABLE_BYTES,
    MIGRATION_POLICY_VM_LABEL,
    ONE_CPU_CORE,
    OS_FLAVOR_FEDORA,
    PVC,
    SOURCE_POD,
    SSP_OPERATOR,
    TCP_TIMEOUT_30SEC,
    TIMEOUT_2MIN,
    TIMEOUT_3MIN,
    TIMEOUT_4MIN,
    TIMEOUT_5MIN,
    TIMEOUT_10MIN,
    TIMEOUT_15SEC,
    TIMEOUT_30MIN,
    TWO_CPU_CORES,
    TWO_CPU_SOCKETS,
    TWO_CPU_THREADS,
    VERSION_LABEL_KEY,
    VIRT_HANDLER,
    VIRT_TEMPLATE_VALIDATOR,
    Images,
)
from utilities.hco import ResourceEditorValidateHCOReconcile, wait_for_hco_conditions
from utilities.infra import (
    create_ns,
    get_http_image_url,
    get_node_selector_dict,
    get_pod_by_name_prefix,
    is_jira_open,
    unique_name,
)
from utilities.monitoring import get_metrics_value
from utilities.network import assert_ping_successful, get_ip_from_vm_or_virt_handler_pod, ping
from utilities.ssp import verify_ssp_pod_is_running
from utilities.storage import (
    create_dv,
    data_volume_template_with_source_ref_dict,
    is_snapshot_supported_by_sc,
    vm_snapshot,
    wait_for_cdi_worker_pod,
)
from utilities.virt import (
    VirtualMachineForTests,
    fedora_vm_body,
    running_vm,
    target_vm_from_cloning_job,
)
from utilities.vnc_utils import VNCConnection

UPLOAD_STR = "upload"
CDI_UPLOAD_PRIME = "cdi-upload-prime"
IP_RE_PATTERN_FROM_INTERFACE = r"eth0.*?inet (\d+\.\d+\.\d+\.\d+)/\d+"
IP_ADDR_SHOW_COMMAND = shlex.split("ip addr show")
LOGGER = logging.getLogger(__name__)
METRICS_WITH_WINDOWS_VM_BUGS = [
    KUBEVIRT_VMI_MEMORY_UNUSED_BYTES,
    KUBEVIRT_VMI_MEMORY_SWAP_OUT_TRAFFIC_BYTES,
    KUBEVIRT_VMI_MEMORY_SWAP_IN_TRAFFIC_BYTES,
    KUBEVIRT_VMI_MEMORY_PGMAJFAULT_TOTAL,
    KUBEVIRT_VMI_MEMORY_USABLE_BYTES,
    KUBEVIRT_VMI_MEMORY_PGMINFAULT_TOTAL,
]


def wait_for_component_value_to_be_expected(prometheus, component_name, expected_count):
    """This function will wait till the expected value is greater than or equal to
    the value from Prometheus for the specific component_name.

    Args:
        prometheus (:obj:`Prometheus`): Prometheus object.
        component_name (String): Name of the component.
        expected_count (int): Expected value of the component after update.

    Returns:
        int: It will return the value of the component once it matches to the expected_count.
    """
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_10MIN,
        sleep=50,
        func=get_mutation_component_value_from_prometheus,
        prometheus=prometheus,
        component_name=component_name,
    )
    sample = None
    try:
        for sample in samples:
            if sample >= expected_count:
                return sample
    except TimeoutExpiredError:
        LOGGER.error(
            f"{component_name} value did not update. Current value {sample} and expected value {expected_count}"
        )
        raise


@pytest.fixture()
def updated_resource_with_invalid_label(request, admin_client, hco_namespace, hco_status_related_objects):
    resource_name = request.param["name"]
    resource = get_resource_object(
        related_objects=hco_status_related_objects,
        admin_client=admin_client,
        resource_kind=request.param["resource"],
        resource_name=request.param["name"],
    )
    labels = resource.instance.metadata.labels
    LOGGER.info(f"Updating metadata.label.{VERSION_LABEL_KEY} for {resource_name} ")
    with ResourceEditor(
        patches={
            resource: {
                "metadata": {
                    "labels": {VERSION_LABEL_KEY: None},
                    "namespace": hco_namespace.name,
                },
            }
        }
    ):
        wait_for_cr_labels_change(component=resource, expected_value=labels)
        yield


@pytest.fixture()
def updated_resource_multiple_times_with_invalid_label(
    request, prometheus, admin_client, hco_namespace, hco_status_related_objects
):
    """
    This fixture will repeatedly modify the given resource with invalid metadata labels.

    Args:
        admin_client (DynamicClient): OCP client with Admin permissions
        hco_namespace (Namespace): HCO namespace

    Returns:
        int: Returns latest metrics value of a given component once it matches to the expected_count
    """
    count = request.param["count"]
    comp_name = request.param["comp_name"]
    resource_name = request.param["name"]
    resource_version = None
    resource = get_resource_object(
        related_objects=hco_status_related_objects,
        admin_client=admin_client,
        resource_kind=request.param["resource"],
        resource_name=resource_name,
    )
    assert resource.exists, f"Resource: {comp_name} does not exist"
    labels = resource.instance.metadata.labels
    # Create the ResourceEditor once and then re-use it to make sure we are modifying
    # the resource exactly X times. Since the resource would be reconciled by HCO, there is no need to restore.
    increasing_value = get_mutation_component_value_from_prometheus(prometheus=prometheus, component_name=comp_name)
    LOGGER.warning(f"For {resource.name} starting value:{increasing_value}, resource version: {resource_version}")
    updated_value = 0
    for index in range(count):
        increasing_value += 1
        resource_editor = ResourceEditor(
            patches={
                resource: {
                    "metadata": {
                        "labels": {VERSION_LABEL_KEY: None},
                    },
                }
            }
        )
        resource_editor.update()
        wait_for_cr_labels_change(component=resource, expected_value=labels)
        updated_value = wait_for_component_value_to_be_expected(
            prometheus=prometheus,
            component_name=comp_name,
            expected_count=increasing_value,
        )
    yield updated_value
    wait_for_hco_conditions(admin_client=admin_client, hco_namespace=hco_namespace)


@pytest.fixture()
def mutation_count_before_change(request, prometheus):
    component_name = request.param
    LOGGER.info(f"Getting component '{component_name}' mutation count before change.")
    return get_mutation_component_value_from_prometheus(
        prometheus=prometheus,
        component_name=component_name,
    )


@pytest.fixture(scope="module")
def unique_namespace(admin_client, unprivileged_client):
    """
    Creates a namespace to be used by key metrics test cases.

    Yields:
        Namespace object to be used by the tests
    """
    namespace_name = unique_name(name="key-metrics")
    yield from create_ns(admin_client=admin_client, unprivileged_client=unprivileged_client, name=namespace_name)


@pytest.fixture()
def stopped_metrics_vm(running_metric_vm):
    running_metric_vm.stop(wait=True)
    yield


@pytest.fixture()
def starting_metrics_vm(running_metric_vm):
    running_metric_vm.start(wait=True)
    yield


@pytest.fixture()
def paused_metrics_vm(running_metric_vm):
    running_metric_vm.privileged_vmi.pause(wait=True)
    yield


@pytest.fixture(scope="module")
def initial_metric_cpu_value_zero(prometheus):
    wait_for_metric_vmi_request_cpu_cores_output(prometheus=prometheus, expected_cpu=ZERO_CPU_CORES)


@pytest.fixture(scope="class")
def error_state_vm(unique_namespace, unprivileged_client):
    vm_name = "vm-in-error-state"
    with VirtualMachineForTests(
        name=vm_name,
        namespace=unique_namespace.name,
        body=fedora_vm_body(name=vm_name),
        client=unprivileged_client,
        node_selector=get_node_selector_dict(node_selector="non-existent-node"),
    ) as vm:
        vm.start()
        vm.wait_for_specific_status(status=VirtualMachine.Status.ERROR_UNSCHEDULABLE)
        yield


@pytest.fixture(scope="module")
def vm_list(unique_namespace):
    """
    Creates n vms, waits for them all to go to running state and cleans them up at the end

    Args:
        unique_namespace (Namespace): Creates namespaces to be used by the test

    Yields:
        list: list of VirtualMachineForTests created
    """
    vms_list = create_vms(name_prefix="key-metric-vm", namespace_name=unique_namespace.name)
    for vm in vms_list:
        running_vm(vm=vm)
        enable_swap_fedora_vm(vm=vm)
    yield vms_list
    for vm in vms_list:
        vm.clean_up()


@pytest.fixture()
def node_setup(request, vm_list, workers_utility_pods):
    """
    This fixture runs commands on nodes hosting vms and reverses the changes at the end.

    Args:
        vm_list (list): Gets the list of vms created as a part of suite level set up.
        workers_utility_pods (list): Utility pods from worker nodes.

    """
    node_command = request.param.get("node_command")

    if node_command:
        vms = vm_list[: request.param.get("num_vms", SINGLE_VM)]
        run_node_command(
            vms=vms,
            utility_pods=workers_utility_pods,
            command=node_command["setup"],
        )

        yield
        run_node_command(
            vms=vms,
            utility_pods=workers_utility_pods,
            command=node_command["cleanup"],
        )
    else:
        yield


@pytest.fixture()
def vm_metrics_setup(request, vm_list):
    """
    This fixture runs commands against the vms to generate metrics

    Args:
        vm_list (list): Gets the list of vms created as a part of suite level set up

    Yields:
        list: list of vm objects against which commands to generate metric has been issued
    """
    vm_commands = request.param.get("vm_commands")
    vms = vm_list[: request.param.get("num_vms", SINGLE_VM)]
    if vm_commands:
        run_vm_commands(vms=vms, commands=vm_commands)

    yield vms


@pytest.fixture(scope="class")
def vmi_phase_count_before(request, prometheus):
    """
    This fixture queries Prometheus with the query in the get_vmi_phase_count before a VM is created
    and keeps the value for verification
    """
    return get_vmi_phase_count(
        prometheus=prometheus,
        os_name=request.param["labels"]["os"],
        flavor=request.param["labels"]["flavor"],
        workload=request.param["labels"]["workload"],
        query=request.param["query"],
    )


@pytest.fixture(scope="module", autouse=True)
def metrics_sanity(admin_client):
    """
    Perform verification in order to ensure that the cluster is ready for metrics-related tests
    """
    LOGGER.info("Verify that Prometheus pods exist and running as expected")
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_2MIN,
        sleep=1,
        func=get_not_running_prometheus_pods,
        admin_client=admin_client,
    )
    sample = None
    try:
        for sample in samples:
            if not sample:
                break
    except TimeoutExpiredError:
        LOGGER.error(f"timeout awaiting all Prometheus pods to be in Running status: violating_pods={sample}")
        raise


@pytest.fixture(scope="class")
def stopped_vm(vm_from_template_scope_class):
    vm_from_template_scope_class.stop(wait=True)
    return vm_from_template_scope_class


@pytest.fixture()
def virt_pod_info_from_prometheus(request, prometheus):
    """Get Virt Pod information from the recording rules (query) in the form of query_response dictionary.
    Extract Virt Pod name and it's values from the query_response dictionary and
    store it in the pod_details dictionary.

    Returns:
        set: It contains Pod names from the prometheus query result.
    """
    query_response = prometheus.query_sampler(
        query=request.param,
    )
    return {result["metric"]["pod"] for result in query_response}


@pytest.fixture()
def virt_pod_names_by_label(request, admin_client, hco_namespace):
    """Get pod names by a given label (request.param) in the list."""
    return [
        pod.name
        for pod in Pod.get(
            dyn_client=admin_client,
            namespace=hco_namespace.name,
            label_selector=request.param,
        )
    ]


@pytest.fixture(scope="module")
def single_metrics_namespace(admin_client, unprivileged_client):
    namespace_name = unique_name(name="test-metrics")
    yield from create_ns(admin_client=admin_client, unprivileged_client=unprivileged_client, name=namespace_name)


@pytest.fixture(scope="module")
def single_metric_vm(single_metrics_namespace):
    vm = create_vms(
        name_prefix="test-single-vm",
        namespace_name=single_metrics_namespace.name,
        vm_count=SINGLE_VM,
    )[0]
    running_vm(vm=vm)
    yield vm
    vm.clean_up()


@pytest.fixture()
def virt_up_metrics_values(request, prometheus):
    """Get value(int) from the 'up' recording rules(metrics)."""
    query_response = prometheus.query_sampler(
        query=request.param,
    )
    return int(query_response[0]["value"][1])


@pytest.fixture()
def vmi_domain_total_memory_bytes_metric_value_from_prometheus(prometheus, single_metric_vm):
    return get_vmi_memory_domain_metric_value_from_prometheus(
        prometheus=prometheus,
        vmi_name=single_metric_vm.vmi.name,
        query=KUBEVIRT_VMI_MEMORY_DOMAIN_BYTES,
    )


@pytest.fixture()
def vmi_domain_total_memory_in_bytes_from_vm(single_metric_vm):
    return get_vmi_dommemstat_from_vm(
        vmi_dommemstat=single_metric_vm.privileged_vmi.get_dommemstat(),
        domain_memory_string="actual",
    )


@pytest.fixture()
def cluster_network_addons_operator_scaled_down_and_up(request, prometheus, hco_namespace):
    metric_name = request.param
    deployment = Deployment(name=CLUSTER_NETWORK_ADDONS_OPERATOR, namespace=hco_namespace.name)
    initial_replicas = deployment.instance.spec.replicas
    deployment.scale_replicas(replica_count=0)
    deployment.wait_for_replicas(deployed=False)
    wait_for_metric_reset(
        prometheus=prometheus,
        metric_name=metric_name,
    )
    deployment.scale_replicas(replica_count=initial_replicas)
    deployment.wait_for_replicas(deployed=initial_replicas > 0)


@pytest.fixture()
def windows_dv_with_block_volume_mode(
    namespace,
    unprivileged_client,
    storage_class_with_block_volume_mode,
):
    with create_dv(
        dv_name="test-dv-windows-image",
        namespace=namespace.name,
        url=get_http_image_url(image_directory=Images.Windows.UEFI_WIN_DIR, image_name=Images.Windows.WIN2k19_IMG),
        size=Images.Windows.DEFAULT_DV_SIZE,
        storage_class=storage_class_with_block_volume_mode,
        client=unprivileged_client,
        volume_mode=DataVolume.VolumeMode.BLOCK,
    ) as dv:
        dv.wait_for_dv_success(timeout=TIMEOUT_30MIN)
        yield dv


@pytest.fixture()
def cloned_dv_from_block_to_fs(
    unprivileged_client,
    windows_dv_with_block_volume_mode,
    storage_class_with_filesystem_volume_mode,
):
    with create_dv(
        source=PVC,
        dv_name="cloned-test-dv-windows-image",
        namespace=windows_dv_with_block_volume_mode.namespace,
        source_pvc=windows_dv_with_block_volume_mode.name,
        source_namespace=windows_dv_with_block_volume_mode.namespace,
        size=windows_dv_with_block_volume_mode.size,
        storage_class=storage_class_with_filesystem_volume_mode,
        client=unprivileged_client,
        volume_mode=DataVolume.VolumeMode.FILE,
    ) as cdv:
        cdv.wait_for_status(status=DataVolume.Status.CLONE_IN_PROGRESS, timeout=TIMEOUT_2MIN)
        yield cdv


@pytest.fixture()
def running_cdi_worker_pod(cloned_dv_from_block_to_fs):
    for pod_name in [CDI_UPLOAD_TMP_PVC, SOURCE_POD]:
        wait_for_cdi_worker_pod(
            pod_name=pod_name,
            storage_ns_name=cloned_dv_from_block_to_fs.namespace,
        ).wait_for_status(status=Pod.Status.RUNNING, timeout=TIMEOUT_2MIN)


@pytest.fixture()
def restarted_cdi_dv_clone(
    unprivileged_client,
    cloned_dv_from_block_to_fs,
    running_cdi_worker_pod,
):
    restart_cdi_worker_pod(
        unprivileged_client=unprivileged_client,
        dv=cloned_dv_from_block_to_fs,
        pod_prefix=CDI_UPLOAD_TMP_PVC,
    )


@pytest.fixture()
def ready_uploaded_dv(unprivileged_client, namespace):
    with create_dv(
        source=UPLOAD_STR,
        dv_name=f"{UPLOAD_STR}-dv",
        namespace=namespace.name,
        storage_class=py_config["default_storage_class"],
        client=unprivileged_client,
    ) as dv:
        dv.wait_for_status(status=DataVolume.Status.UPLOAD_READY, timeout=TIMEOUT_2MIN)
        yield dv


@pytest.fixture()
def restarted_cdi_dv_upload(unprivileged_client, ready_uploaded_dv):
    restart_cdi_worker_pod(
        unprivileged_client=unprivileged_client,
        dv=ready_uploaded_dv,
        pod_prefix=CDI_UPLOAD_PRIME,
    )
    ready_uploaded_dv.wait_for_status(status=DataVolume.Status.UPLOAD_READY, timeout=TIMEOUT_2MIN)


@pytest.fixture()
def zero_clone_dv_restart_count(cloned_dv_from_block_to_fs):
    fail_if_not_zero_restartcount(dv=cloned_dv_from_block_to_fs)


@pytest.fixture()
def zero_upload_dv_restart_count(ready_uploaded_dv):
    fail_if_not_zero_restartcount(dv=ready_uploaded_dv)


@pytest.fixture(scope="class")
def kubevirt_vmi_phase_count_metric_no_value(prometheus):
    wait_for_no_metrics_value(prometheus=prometheus, metric_name=KUBEVIRT_VMI_PHASE_COUNT_STR)


@pytest.fixture(scope="class")
def cnv_vmi_status_running_count_metric_no_value(prometheus):
    wait_for_no_metrics_value(prometheus=prometheus, metric_name=CNV_VMI_STATUS_RUNNING_COUNT)


@pytest.fixture(scope="class")
def validated_preference_instance_type_of_target_vm(
    rhel_vm_with_instancetype_and_preference_for_cloning, cloning_job_scope_class
):
    with target_vm_from_cloning_job(cloning_job=cloning_job_scope_class) as target_vm:
        target_vm_instance_spec = target_vm.instance.spec
        assert (
            rhel_vm_with_instancetype_and_preference_for_cloning.vm_instance_type.name
            == target_vm_instance_spec.instancetype.name
        )
        assert (
            rhel_vm_with_instancetype_and_preference_for_cloning.vm_preference.name
            == target_vm_instance_spec.preference.name
        )
        yield target_vm


@pytest.fixture()
def connected_vm_console_successfully(vm_for_test, prometheus):
    with console.Console(vm=vm_for_test) as vmc:
        vmc.sendline("ls")
        yield
    validate_metrics_value(
        prometheus=prometheus,
        metric_name=KUBEVIRT_CONSOLE_ACTIVE_CONNECTIONS_BY_VMI.format(vm_name=vm_for_test.name),
        expected_value="0",
    )


@pytest.fixture()
def connected_vnc_console(prometheus, vm_for_test):
    with VNCConnection(vm=vm_for_test):
        LOGGER.info(f"Checking vnc on {vm_for_test.name}")
        yield
    validate_metrics_value(
        prometheus=prometheus,
        metric_name=KUBEVIRT_VNC_ACTIVE_CONNECTIONS_BY_VMI.format(vm_name=vm_for_test.name),
        expected_value="0",
    )


@pytest.fixture()
def memory_cached_sum_from_vm_console(vm_for_test):
    info_to_sum = ["Buffers", "Cached", "SwapCached"]
    proc_meminfo_content = run_ssh_commands(
        host=vm_for_test.ssh_exec,
        commands=shlex.split("cat /proc/meminfo"),
        tcp_timeout=TCP_TIMEOUT_30SEC,
    )[0]
    matches = re.findall(rf"({'|'.join(info_to_sum)}):\s+(\d+)\s+\S+", proc_meminfo_content)
    assert matches, f"/proc/meminfo content: {proc_meminfo_content}"
    assert sorted(list(dict(matches).keys())) == sorted(info_to_sum), (
        f"Expected info to collect: {info_to_sum}, Actual: {matches}"
    )
    return bitmath.kB(value=sum(list(map(int, dict(matches).values())))).bytes


@pytest.fixture()
def generated_network_traffic(vm_for_test):
    assert_ping_successful(
        src_vm=vm_for_test,
        dst_ip=vm_for_test.privileged_vmi.interfaces[0]["ipAddress"],
        count=20,
    )


@pytest.fixture()
def generated_network_traffic_windows_vm(windows_vm_for_test):
    ping(
        src_vm=windows_vm_for_test,
        dst_ip=get_ip_from_vm_or_virt_handler_pod(family=IPV4_STR, vm=windows_vm_for_test),
        windows=True,
    )


@pytest.fixture(scope="class")
def linux_vm_for_test_interface_name(vm_for_test):
    return get_interface_name_from_vm(vm=vm_for_test)


@pytest.fixture(scope="class")
def windows_vm_for_test_interface_name(windows_vm_for_test):
    return get_interface_name_from_vm(vm=windows_vm_for_test)


@pytest.fixture(scope="class")
def initial_total_created_vms(prometheus, namespace):
    return get_metric_sum_value(
        prometheus=prometheus, metric=KUBEVIRT_VM_CREATED_TOTAL_STR.format(namespace=namespace.name)
    )


@pytest.fixture()
def vmi_memory_available_memory(vm_for_test):
    memory_available_bytes = run_ssh_commands(
        host=vm_for_test.ssh_exec,
        commands=shlex.split("free -b"),
        tcp_timeout=TCP_TIMEOUT_30SEC,
    )[0]
    memory_available = re.search(r"Mem:\s+(\d+)", memory_available_bytes)
    assert memory_available, f"No information available for vm memory: {memory_available_bytes}"
    return float(memory_available.group(1))


@pytest.fixture(scope="class")
def vm_with_cpu_spec(namespace, unprivileged_client):
    name = "vm-resource-test"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        cpu_cores=TWO_CPU_CORES,
        cpu_sockets=TWO_CPU_SOCKETS,
        cpu_threads=TWO_CPU_THREADS,
        body=fedora_vm_body(name=name),
        client=unprivileged_client,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture(scope="class")
def modified_vm_cpu_requests(vm_with_cpu_spec):
    vm_cpu_spec = vm_with_cpu_spec.instance.to_dict()["spec"]["template"]["spec"]["domain"]["cpu"]
    for cpu_param in vm_cpu_spec:
        vm_cpu_spec[cpu_param] += 1
    with ResourceEditor(patches={vm_with_cpu_spec: {"spec": {"template": {"spec": {"domain": {"cpu": vm_cpu_spec}}}}}}):
        yield vm_cpu_spec


@pytest.fixture()
def vm_ip_address(vm_for_test):
    vm_ip = re.search(
        IP_RE_PATTERN_FROM_INTERFACE,
        vm_for_test.privileged_vmi.virt_launcher_pod.execute(command=IP_ADDR_SHOW_COMMAND),
        re.DOTALL,
    )
    assert vm_ip, f"Failed to find {vm_for_test.name} vm ip."
    return vm_ip.group(1)


@pytest.fixture()
def metric_validate_metric_labels_values_ip_labels(request, prometheus, vm_for_test):
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_4MIN,
        sleep=TIMEOUT_15SEC,
        func=prometheus.query_sampler,
        query=KUBEVIRT_VMI_STATUS_ADDRESSES.format(vm_name=vm_for_test.name),
    )
    sample = None
    try:
        for sample in samples:
            if sample:
                # Validate that the relevant labels exists
                metric_result = sample[0].get("metric")
                if all(metric_result.get(label) for label in ["instance", "address"]):
                    return metric_result
    except TimeoutExpiredError:
        LOGGER.info(f"Metric missing instance/address values: {sample}")
        raise


@pytest.fixture()
def vm_virt_controller_ip_address(
    prometheus, admin_client, hco_namespace, metric_validate_metric_labels_values_ip_labels
):
    virt_controller_pod_name = metric_validate_metric_labels_values_ip_labels.get("pod")
    assert virt_controller_pod_name, "virt-controller not found"
    virt_controller_pod_ip = re.search(
        IP_RE_PATTERN_FROM_INTERFACE,
        get_pod_by_name_prefix(
            dyn_client=admin_client,
            pod_prefix=virt_controller_pod_name,
            namespace=hco_namespace.name,
        ).execute(command=IP_ADDR_SHOW_COMMAND),
        re.DOTALL,
    )
    assert virt_controller_pod_ip, f"virt-controller: {virt_controller_pod_name} ip not found."
    return virt_controller_pod_ip.group(1)


@pytest.fixture()
def vm_for_test_snapshot(vm_for_test):
    with vm_snapshot(vm=vm_for_test, name=f"{vm_for_test.name}-snapshot") as snapshot:
        yield snapshot


@pytest.fixture()
def disk_file_system_info_linux(vm_for_test):
    return disk_file_system_info(vm=vm_for_test)


@pytest.fixture()
def disk_file_system_info_windows(windows_vm_for_test):
    return disk_file_system_info(vm=windows_vm_for_test)


@pytest.fixture()
def file_system_metric_mountpoints_existence(request, prometheus, vm_for_test, disk_file_system_info_linux):
    capacity_or_used = request.param
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_2MIN,
        sleep=TIMEOUT_15SEC,
        func=metric_result_output_dict_by_mountpoint,
        prometheus=prometheus,
        capacity_or_used=capacity_or_used,
        vm_name=vm_for_test.name,
    )
    mount_points_with_value_zero = None
    try:
        for sample in samples:
            if sample:
                if [mount_point for mount_point in disk_file_system_info_linux if not sample.get(mount_point)]:
                    continue
                mount_points_with_value_zero = {
                    mount_point: float(sample[mount_point]) for mount_point in sample if int(sample[mount_point]) == 0
                }
                if not mount_points_with_value_zero:
                    return
    except TimeoutExpiredError:
        LOGGER.info(f"There is at least one mount point with value zero: {mount_points_with_value_zero}")
        raise


@pytest.fixture(scope="class")
def vm_for_test_with_resource_limits(namespace):
    vm_name = "vm-with-limits"
    with VirtualMachineForTests(
        name=vm_name,
        namespace=namespace.name,
        cpu_limits=ONE_CPU_CORE,
        memory_limits=Images.Fedora.DEFAULT_MEMORY_SIZE,
        body=fedora_vm_body(name=vm_name),
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture()
def virt_handler_pods_count(hco_namespace):
    return str(
        DaemonSet(
            name=VIRT_HANDLER,
            namespace=hco_namespace.name,
        ).instance.status.numberReady
    )


@pytest.fixture()
def vm_instance_with_deprecated_api_version(namespace):
    vm_instance = VirtualMachine(name="vm-deprecated-api", namespace=namespace.name, client=get_client())
    vm_instance.api_version = f"{Resource.ApiGroup.KUBEVIRT_IO}/{Resource.ApiVersion.V1ALPHA3}"
    return vm_instance


@pytest.fixture()
def generated_api_deprecated_requests(prometheus, vm_instance_with_deprecated_api_version):
    initial_metric_value = int(
        get_metrics_value(
            prometheus=prometheus,
            metrics_name=KUBEVIRT_API_REQUEST_DEPRECATED_TOTAL_WITH_VERSION_VERB_AND_RESOURCE,
        )
    )
    for _ in range(COUNT_FIVE):
        try:
            vm_instance_with_deprecated_api_version.deploy()
        except UnprocessibleEntityError:
            continue
    return initial_metric_value + COUNT_FIVE


@pytest.fixture()
def storage_class_labels_for_testing(admin_client):
    chosen_sc_name = py_config["default_storage_class"]
    return {
        "storageclass": chosen_sc_name,
        "smartclone": "true" if is_snapshot_supported_by_sc(sc_name=chosen_sc_name, client=admin_client) else "false",
        "virtdefault": "true"
        if StorageClass(client=admin_client, name=chosen_sc_name).instance.metadata.annotations[
            StorageClass.Annotations.IS_DEFAULT_VIRT_CLASS
        ]
        == "true"
        else "false",
    }


@pytest.fixture()
def vm_for_snapshot_for_metrics_test(admin_client, storage_class_for_snapshot, namespace):
    with create_cirros_vm(
        storage_class=storage_class_for_snapshot,
        namespace=namespace.name,
        client=admin_client,
        dv_name="dv-for-snapshot",
        vm_name="vm-for-snapshot",
    ) as vm:
        yield vm


@pytest.fixture()
def vm_snapshot_for_metric_test(vm_for_snapshot_for_metrics_test):
    with vm_snapshot(
        vm=vm_for_snapshot_for_metrics_test, name=f"{vm_for_snapshot_for_metrics_test.name}-snapshot"
    ) as snapshot:
        yield snapshot


@pytest.fixture()
def restored_vm_using_snapshot(vm_for_snapshot_for_metrics_test, vm_snapshot_for_metric_test):
    vm_name = vm_for_snapshot_for_metrics_test.name
    vm_for_snapshot_for_metrics_test.stop(wait=True)
    with VirtualMachineRestore(
        name=f"restore-snapshot-{vm_name}",
        namespace=vm_snapshot_for_metric_test.namespace,
        vm_name=vm_name,
        snapshot_name=vm_snapshot_for_metric_test.name,
    ) as vm_restore:
        vm_restore.wait_restore_done()
        vm_for_snapshot_for_metrics_test.start(wait=True)
        yield vm_restore


@pytest.fixture()
def restored_pvc_name(admin_client, vm_for_snapshot_for_metrics_test):
    for pvc in PersistentVolumeClaim.get(
        dyn_client=admin_client,
        namespace=vm_for_snapshot_for_metrics_test.namespace,
        label_selector=f"restore.kubevirt.io/source-vm-name={vm_for_snapshot_for_metrics_test.name}",
    ):
        return pvc.name


@pytest.fixture()
def snapshot_labels_for_testing(vm_snapshot_for_metric_test, vm_for_snapshot_for_metrics_test, restored_pvc_name):
    return {
        "label_restore_kubevirt_io_source_vm_name": vm_for_snapshot_for_metrics_test.name,
        "persistentvolumeclaim": restored_pvc_name,
        "namespace": vm_snapshot_for_metric_test.namespace,
    }


@pytest.fixture(scope="class")
def template_validator_finalizer(hco_namespace):
    deployment = Deployment(name=VIRT_TEMPLATE_VALIDATOR, namespace=hco_namespace.name)
    with ResourceEditorValidateHCOReconcile(
        patches={deployment: {"metadata": {"finalizers": ["ssp.kubernetes.io/temporary-finalizer"]}}}
    ):
        yield


@pytest.fixture(scope="class")
def deleted_ssp_operator_pod(admin_client, hco_namespace):
    get_pod_by_name_prefix(
        dyn_client=admin_client,
        pod_prefix=SSP_OPERATOR,
        namespace=hco_namespace.name,
    ).delete(wait=True)
    yield
    verify_ssp_pod_is_running(dyn_client=admin_client, hco_namespace=hco_namespace)


@pytest.fixture(scope="class")
def initiate_metric_value(request, prometheus):
    return get_metrics_value(prometheus=prometheus, metrics_name=request.param)


@pytest.fixture()
def vm_for_vm_disk_allocation_size_test(namespace, unprivileged_client, golden_images_namespace):
    with VirtualMachineForTests(
        client=unprivileged_client,
        name="disk-allocation-size-vm",
        namespace=namespace.name,
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=DataSource(name=OS_FLAVOR_FEDORA, namespace=golden_images_namespace.name),
            storage_class=py_config["default_storage_class"],
        ),
        memory_guest=Images.Fedora.DEFAULT_MEMORY_SIZE,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture()
def vnic_info_from_vm_or_vmi(request, running_metric_vm):
    vm_spec = (
        running_metric_vm.vmi.instance.spec if request.param == "vmi" else running_metric_vm.instance.spec.template.spec
    )
    vm_interface = vm_spec.domain.devices.interfaces[0]
    binding_name_and_type = binding_name_and_type_from_vm_or_vmi(vm_interface=vm_interface)
    return {
        "vnic_name": vm_spec.networks[0].name,
        BINDING_NAME: binding_name_and_type[BINDING_NAME],
        BINDING_TYPE: binding_name_and_type[BINDING_TYPE],
        "model": vm_interface.model,
    }


@pytest.fixture()
def allocatable_nodes(nodes):
    return [node for node in nodes if node.instance.status.allocatable.memory != "0"]


@pytest.fixture()
def windows_vmi_domain_total_memory_bytes_metric_value_from_prometheus(prometheus, windows_vm_for_test):
    return get_vmi_memory_domain_metric_value_from_prometheus(
        prometheus=prometheus,
        vmi_name=windows_vm_for_test.vmi.name,
        query=KUBEVIRT_VMI_MEMORY_DOMAIN_BYTES,
    )


@pytest.fixture()
def vmi_domain_total_memory_in_bytes_from_windows_vm(windows_vm_for_test):
    return get_vmi_dommemstat_from_vm(
        vmi_dommemstat=windows_vm_for_test.privileged_vmi.get_dommemstat(),
        domain_memory_string="actual",
    )


@pytest.fixture()
def vmi_guest_os_kernel_release_info_linux(single_metric_vm):
    return get_vmi_guest_os_kernel_release_info_metric_from_vm(vm=single_metric_vm)


@pytest.fixture()
def vmi_guest_os_kernel_release_info_windows(windows_vm_for_test):
    return get_vmi_guest_os_kernel_release_info_metric_from_vm(vm=windows_vm_for_test, windows=True)


@pytest.fixture()
def linux_vm_info_to_compare(single_metric_vm):
    return get_vm_comparison_info_dict(vm=single_metric_vm)


@pytest.fixture()
def windows_vm_info_to_compare(windows_vm_for_test):
    return get_vm_comparison_info_dict(vm=windows_vm_for_test)


@pytest.fixture(scope="module")
def windows_vm_for_test(namespace, unprivileged_client):
    with create_windows11_wsl2_vm(
        dv_name="dv-for-windows",
        namespace=namespace.name,
        client=unprivileged_client,
        vm_name="win-vm-for-test",
        storage_class=py_config["default_storage_class"],
    ) as vm:
        yield vm


@pytest.fixture(scope="session")
def memory_metric_has_bug():
    return is_jira_open(jira_id="CNV-59679")


@pytest.fixture()
def xfail_if_memory_metric_has_bug(memory_metric_has_bug, cnv_vmi_monitoring_metrics_matrix__function__):
    if cnv_vmi_monitoring_metrics_matrix__function__ in METRICS_WITH_WINDOWS_VM_BUGS and memory_metric_has_bug:
        pytest.xfail(
            f"Bug (CNV-59679), Metric: {cnv_vmi_monitoring_metrics_matrix__function__} not showing "
            "any value for windows vm"
        )


@pytest.fixture()
def initial_migration_metrics_values(prometheus):
    yield {
        metric: get_metric_sum_value(prometheus=prometheus, metric=metric)
        for metric in [KUBEVIRT_VMI_MIGRATIONS_IN_SCHEDULING_PHASE, KUBEVIRT_VMI_MIGRATIONS_IN_RUNNING_PHASE]
    }


@pytest.fixture(scope="class")
def vm_for_migration_metrics_test(namespace, cpu_for_migration):
    name = "vm-for-migration-metrics-test"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        body=fedora_vm_body(name=name),
        cpu_model=cpu_for_migration,
        additional_labels=MIGRATION_POLICY_VM_LABEL,
    ) as vm:
        running_vm(vm=vm, check_ssh_connectivity=False)
        yield vm


@pytest.fixture()
def vm_migration_metrics_vmim(vm_for_migration_metrics_test):
    with VirtualMachineInstanceMigration(
        name="vm-migration-metrics-vmim",
        namespace=vm_for_migration_metrics_test.namespace,
        vmi_name=vm_for_migration_metrics_test.vmi.name,
    ) as vmim:
        yield vmim


@pytest.fixture(scope="class")
def vm_migration_metrics_vmim_scope_class(vm_for_migration_metrics_test):
    with VirtualMachineInstanceMigration(
        name="vm-migration-metrics-vmim",
        namespace=vm_for_migration_metrics_test.namespace,
        vmi_name=vm_for_migration_metrics_test.vmi.name,
    ) as vmim:
        vmim.wait_for_status(status=vmim.Status.RUNNING, timeout=TIMEOUT_3MIN)
        yield vmim


@pytest.fixture()
def vm_with_node_selector(namespace, worker_node1):
    name = "vm-with-node-selector"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        body=fedora_vm_body(name=name),
        additional_labels=MIGRATION_POLICY_VM_LABEL,
        node_selector=get_node_selector_dict(node_selector=worker_node1.name),
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture()
def vm_with_node_selector_vmim(vm_with_node_selector):
    with VirtualMachineInstanceMigration(
        name="vm-with-node-selector-vmim",
        namespace=vm_with_node_selector.namespace,
        vmi_name=vm_with_node_selector.vmi.name,
    ) as vmim:
        yield vmim


@pytest.fixture(scope="class")
def migration_succeeded_scope_class(vm_migration_metrics_vmim_scope_class):
    vm_migration_metrics_vmim_scope_class.wait_for_status(
        status=vm_migration_metrics_vmim_scope_class.Status.SUCCEEDED, timeout=TIMEOUT_5MIN
    )


@pytest.fixture()
def created_fake_data_volume_resource(namespace, admin_client):
    with DataVolume(
        name="fake-dv",
        namespace=namespace.name,
        url="http://broken-link.test",
        source="http",
        size=Images.Rhel.DEFAULT_DV_SIZE,
        storage_class=py_config["default_storage_class"],
        bind_immediate_annotation=True,
        api_name="storage",
        client=admin_client,
    ) as dv:
        yield dv


@pytest.fixture()
def initial_metric_value(request, prometheus):
    return int(get_metrics_value(prometheus=prometheus, metrics_name=request.param))


@pytest.fixture()
def deleted_vmi(running_metric_vm):
    running_metric_vm.delete(wait=True)


@pytest.fixture()
def deleted_windows_vmi(windows_vm_for_test):
    windows_vm_for_test.delete(wait=True)

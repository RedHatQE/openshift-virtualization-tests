import logging
import shlex

import bitmath
import pytest
from ocp_resources.data_source import DataSource
from ocp_resources.deployment import Deployment
from ocp_resources.pod import Pod
from ocp_resources.resource import ResourceEditor
from ocp_resources.storage_class import StorageClass
from ocp_resources.virtual_machine import VirtualMachine
from ocp_resources.virtual_machine_instance_migration import VirtualMachineInstanceMigration
from pytest_testconfig import py_config
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.observability.metrics.constants import (
    KUBEVIRT_CONSOLE_ACTIVE_CONNECTIONS_BY_VMI,
    KUBEVIRT_VMI_MIGRATIONS_IN_RUNNING_PHASE,
    KUBEVIRT_VMI_MIGRATIONS_IN_SCHEDULING_PHASE,
    KUBEVIRT_VMI_STATUS_ADDRESSES,
    KUBEVIRT_VNC_ACTIVE_CONNECTIONS_BY_VMI,
)
from tests.observability.metrics.utils import (
    SINGLE_VM,
    ZERO_CPU_CORES,
    create_windows11_wsl2_vm,
    disk_file_system_info,
    enable_swap_fedora_vm,
    get_metric_sum_value,
    get_vm_comparison_info_dict,
    get_vmi_guest_os_kernel_release_info_metric_from_vm,
    metric_result_output_dict_by_mountpoint,
    vnic_info_from_vm_or_vmi,
    wait_for_metric_vmi_request_cpu_cores_output,
)
from tests.observability.utils import validate_metrics_value
from tests.utils import create_vms
from utilities import console
from utilities.constants import (
    IPV4_STR,
    KUBEVIRT_VMI_MEMORY_PGMAJFAULT_TOTAL,
    KUBEVIRT_VMI_MEMORY_PGMINFAULT_TOTAL,
    KUBEVIRT_VMI_MEMORY_SWAP_IN_TRAFFIC_BYTES,
    KUBEVIRT_VMI_MEMORY_SWAP_OUT_TRAFFIC_BYTES,
    KUBEVIRT_VMI_MEMORY_UNUSED_BYTES,
    KUBEVIRT_VMI_MEMORY_USABLE_BYTES,
    MIGRATION_POLICY_VM_LABEL,
    ONE_CPU_CORE,
    ONE_CPU_THREAD,
    OS_FLAVOR_FEDORA,
    SSP_OPERATOR,
    TIMEOUT_2MIN,
    TIMEOUT_3MIN,
    TIMEOUT_4MIN,
    TIMEOUT_5MIN,
    TIMEOUT_15SEC,
    TWO_CPU_CORES,
    TWO_CPU_SOCKETS,
    TWO_CPU_THREADS,
    VIRT_TEMPLATE_VALIDATOR,
    Images,
)
from utilities.hco import ResourceEditorValidateHCOReconcile, enabled_aaq_in_hco
from utilities.infra import (
    create_ns,
    get_node_selector_dict,
    get_pod_by_name_prefix,
    is_jira_open,
    unique_name,
)
from utilities.monitoring import get_metrics_value
from utilities.network import assert_ping_successful, get_ip_from_vm_or_virt_handler_pod, ping
from utilities.ssp import verify_ssp_pod_is_running
from utilities.storage import (
    data_volume_template_with_source_ref_dict,
    is_snapshot_supported_by_sc,
    vm_snapshot,
)
from utilities.virt import (
    VirtualMachineForTests,
    fedora_vm_body,
    running_vm,
)
from utilities.vnc_utils import VNCConnection

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
    return vm_for_test.vmi.interfaces[0].interfaceName


@pytest.fixture(scope="class")
def windows_vm_for_test_interface_name(windows_vm_for_test):
    return windows_vm_for_test.vmi.interfaces[0].interfaceName


@pytest.fixture(scope="class")
def vm_with_cpu_spec(namespace, unprivileged_client, is_s390x_cluster):
    name = "vm-resource-test"
    cpu_threads = ONE_CPU_THREAD if is_s390x_cluster else TWO_CPU_THREADS  # dynamically set based on arch

    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        cpu_cores=TWO_CPU_CORES,
        cpu_sockets=TWO_CPU_SOCKETS,
        cpu_threads=cpu_threads,
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
def kubevirt_vmi_status_addresses_ip_labels_values(prometheus, vm_for_test):
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
def vm_virt_controller_ip_address(admin_client, hco_namespace, kubevirt_vmi_status_addresses_ip_labels_values):
    virt_controller_pod_name = kubevirt_vmi_status_addresses_ip_labels_values.get("pod")
    assert virt_controller_pod_name, "virt-controller not found"
    virt_controller_pod_ip = get_pod_by_name_prefix(
        dyn_client=admin_client,
        pod_prefix=virt_controller_pod_name,
        namespace=hco_namespace.name,
    ).ip
    assert virt_controller_pod_ip, f"virt-controller: {virt_controller_pod_name} ip not found."
    return virt_controller_pod_ip


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
def vnic_info_from_vm_or_vmi_linux(request, running_metric_vm):
    return vnic_info_from_vm_or_vmi(vm_or_vmi=request.param, vm=running_metric_vm)


@pytest.fixture()
def vnic_info_from_vmi_windows(windows_vm_for_test):
    return vnic_info_from_vm_or_vmi(vm_or_vmi="vmi", vm=windows_vm_for_test)


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
def initial_metric_value(request, prometheus):
    return int(get_metrics_value(prometheus=prometheus, metrics_name=request.param))


@pytest.fixture()
def deleted_vmi(running_metric_vm):
    running_metric_vm.delete(wait=True)


@pytest.fixture()
def deleted_windows_vmi(windows_vm_for_test):
    windows_vm_for_test.delete(wait=True)


@pytest.fixture(scope="module")
def enabled_aaq_in_hco_scope_module(admin_client, hco_namespace, hyperconverged_resource_scope_module):
    with enabled_aaq_in_hco(
        client=admin_client,
        hco_namespace=hco_namespace,
        hyperconverged_resource=hyperconverged_resource_scope_module,
    ):
        yield


@pytest.fixture()
def application_aware_resource_quota_creation_timestamp(application_aware_resource_quota):
    return application_aware_resource_quota.instance.metadata.creationTimestamp


@pytest.fixture()
def aaq_resource_hard_limit_and_used(application_aware_resource_quota):
    application_aware_resource_quota_instance = application_aware_resource_quota.instance
    resource_hard_limit = application_aware_resource_quota_instance.spec.hard
    resource_used = application_aware_resource_quota_instance.status.used
    formatted_hard_limit = {
        key: int(bitmath.parse_string_unsafe(value).to_Byte().value) if isinstance(value, str) else int(value)
        for key, value in resource_hard_limit.items()
    }
    formatted_used_value = {
        key: int(bitmath.parse_string_unsafe(value).to_Byte().value) if isinstance(value, str) else int(value)
        for key, value in resource_used.items()
    }
    return formatted_hard_limit, formatted_used_value

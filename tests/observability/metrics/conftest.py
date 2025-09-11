import logging
import re
import shlex

import pytest
from ocp_resources.daemonset import DaemonSet
from ocp_resources.data_source import DataSource
from ocp_resources.datavolume import DataVolume
from ocp_resources.deployment import Deployment
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_resources.pod import Pod
from ocp_resources.resource import ResourceEditor
from ocp_resources.storage_class import StorageClass
from ocp_resources.virtual_machine import VirtualMachine
from pyhelper_utils.shell import run_ssh_commands
from pytest_testconfig import py_config
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.observability.metrics.constants import (
    KUBEVIRT_CONSOLE_ACTIVE_CONNECTIONS_BY_VMI,
    KUBEVIRT_VMI_STATUS_ADDRESSES,
    KUBEVIRT_VNC_ACTIVE_CONNECTIONS_BY_VMI,
)
from tests.observability.metrics.utils import (
    SINGLE_VM,
    ZERO_CPU_CORES,
    disk_file_system_info,
    enable_swap_fedora_vm,
    fail_if_not_zero_restartcount,
    metric_result_output_dict_by_mountpoint,
    restart_cdi_worker_pod,
    wait_for_metric_vmi_request_cpu_cores_output,
)
from tests.observability.utils import validate_metrics_value
from tests.utils import create_vms
from utilities import console
from utilities.constants import (
    CDI_UPLOAD_TMP_PVC,
    NODE_STR,
    ONE_CPU_CORE,
    OS_FLAVOR_FEDORA,
    PVC,
    SOURCE_POD,
    SSP_OPERATOR,
    TIMEOUT_2MIN,
    TIMEOUT_4MIN,
    TIMEOUT_15SEC,
    TIMEOUT_30MIN,
    TWO_CPU_CORES,
    TWO_CPU_SOCKETS,
    TWO_CPU_THREADS,
    VIRT_HANDLER,
    VIRT_TEMPLATE_VALIDATOR,
    Images,
)
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.infra import create_ns, get_http_image_url, get_node_selector_dict, get_pod_by_name_prefix, unique_name
from utilities.monitoring import get_metrics_value
from utilities.network import assert_ping_successful
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
)
from utilities.vnc_utils import VNCConnection

UPLOAD_STR = "upload"
CDI_UPLOAD_PRIME = "cdi-upload-prime"
IP_RE_PATTERN_FROM_INTERFACE = r"eth0.*?inet (\d+\.\d+\.\d+\.\d+)/\d+"
IP_ADDR_SHOW_COMMAND = shlex.split("ip addr show")
LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def unique_namespace(unprivileged_client):
    """
    Creates a namespace to be used by key metrics test cases.

    Yields:
        Namespace object to be used by the tests
    """
    namespace_name = unique_name(name="key-metrics")
    yield from create_ns(unprivileged_client=unprivileged_client, name=namespace_name)


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
def single_metrics_namespace(unprivileged_client):
    namespace_name = unique_name(name="test-metrics")
    yield from create_ns(unprivileged_client=unprivileged_client, name=namespace_name)


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


@pytest.fixture(scope="class")
def vm_for_test_interface_name(vm_for_test):
    interface_name = vm_for_test.privileged_vmi.virt_launcher_pod.execute(
        command=shlex.split("bash -c \"virsh domiflist 1 | grep ethernet | awk '{print $1}'\"")
    )
    assert interface_name, f"Interface not found for vm {vm_for_test.name}"
    return interface_name


@pytest.fixture()
def single_metric_vmi_guest_os_kernel_release_info(single_metric_vm):
    return {
        "guest_os_kernel_release": run_ssh_commands(host=single_metric_vm.ssh_exec, commands=shlex.split("uname -r"))[
            0
        ].strip(),
        "namespace": single_metric_vm.namespace,
        NODE_STR: single_metric_vm.vmi.virt_launcher_pod.node.name,
    }


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
def dfs_info(vm_for_test):
    return disk_file_system_info(vm=vm_for_test)


@pytest.fixture()
def file_system_metric_mountpoints_existence(request, prometheus, vm_for_test, dfs_info):
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
                if [mount_point for mount_point in dfs_info if not sample.get(mount_point)]:
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
def vm_migration_state(vm_for_migration_metrics_test):
    return vm_for_migration_metrics_test.vmi.instance.status.migrationState


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
def pvc_size_bytes(vm_for_vm_disk_allocation_size_test):
    return PersistentVolumeClaim(
        name=vm_for_vm_disk_allocation_size_test.instance.spec.dataVolumeTemplates[0].metadata.name,
        namespace=vm_for_vm_disk_allocation_size_test.namespace,
    ).instance.spec.resources.requests.storage

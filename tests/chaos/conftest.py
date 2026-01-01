import logging
import multiprocessing
import random

import pytest
from ocp_resources.datavolume import DataVolume
from ocp_resources.deployment import Deployment
from pytest_testconfig import py_config

from tests.chaos.constants import CHAOS_LABEL, CHAOS_LABEL_KEY, HOST_LABEL
from tests.chaos.utils import (
    create_cluster_monitoring_process,
    create_nginx_monitoring_process,
    create_pod_deleting_process,
    create_vm_with_nginx_service,
    get_instance_type,
    pod_deleting_process_recover,
    terminate_process,
)
from utilities.artifactory import get_artifactory_config_map, get_artifactory_secret
from utilities.constants import (
    KUBEMACPOOL_MAC_CONTROLLER_MANAGER,
    OS_FLAVOR_RHEL,
    PORT_80,
    TIMEOUT_2MIN,
    TIMEOUT_3MIN,
    TIMEOUT_5SEC,
    TIMEOUT_10MIN,
    TIMEOUT_10SEC,
    TIMEOUT_15MIN,
    U1_SMALL,
    Images,
    NamespacesNames,
)
from utilities.infra import (
    ExecCommandOnPod,
    create_ns,
    get_nodes_with_label,
    get_pod_by_name_prefix,
    get_utility_pods_from_nodes,
    label_nodes,
    scale_deployment_replicas,
    utility_daemonset_for_custom_tests,
    wait_for_node_status,
)
from utilities.virt import VirtualMachineForTests, running_vm

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def chaos_namespace(admin_client):
    yield from create_ns(admin_client=admin_client, name=NamespacesNames.CHAOS)


@pytest.fixture()
def chaos_vms_list_rhel9(request, admin_client, chaos_namespace):
    vms_list = []
    for idx in range(request.param["number_of_vms"]):
        vm = VirtualMachineForTests(
            client=admin_client,
            name=f"vm-chaos-{idx}",
            namespace=chaos_namespace.name,
            image=Images.Rhel.RHEL9_REGISTRY_GUEST_IMG,
            memory_requests=Images.Rhel.DEFAULT_MEMORY_SIZE,
        )
        vms_list.append(vm)
    yield vms_list
    for vm in vms_list:
        vm.clean_up()


@pytest.fixture()
def chaos_vm_rhel9(admin_client, chaos_namespace):
    with VirtualMachineForTests(
        client=admin_client,
        name="vm-chaos",
        namespace=chaos_namespace.name,
        image=Images.Rhel.RHEL9_REGISTRY_GUEST_IMG,
        memory_requests=Images.Rhel.DEFAULT_MEMORY_SIZE,
    ) as vm:
        running_vm(vm=vm, wait_for_interfaces=False, check_ssh_connectivity=False)
        yield vm


@pytest.fixture()
def chaos_dv_rhel9(
    request,
    admin_client,
    chaos_namespace,
    rhel9_http_image_url,
    artifactory_secret_chaos_namespace_scope_module,
    artifactory_config_map_chaos_namespace_scope_module,
):
    yield DataVolume(
        source="http",
        name="chaos-dv",
        api_name="storage",
        namespace=chaos_namespace.name,
        url=rhel9_http_image_url,
        size=Images.Rhel.DEFAULT_DV_SIZE,
        storage_class=request.param["storage_class"],
        client=admin_client,
        secret=artifactory_secret_chaos_namespace_scope_module,
        cert_configmap=artifactory_config_map_chaos_namespace_scope_module.name,
    )


@pytest.fixture()
def chaos_vm_rhel9_with_dv(admin_client, chaos_namespace, chaos_dv_rhel9):
    chaos_dv_rhel9.to_dict()
    yield VirtualMachineForTests(
        client=admin_client,
        name="vm-chaos",
        namespace=chaos_namespace.name,
        os_flavor=OS_FLAVOR_RHEL,
        memory_requests=Images.Rhel.DEFAULT_MEMORY_SIZE,
        data_volume_template={
            "metadata": chaos_dv_rhel9.res["metadata"],
            "spec": chaos_dv_rhel9.res["spec"],
        },
    )


@pytest.fixture()
def chaos_vm_rhel9_with_dv_started(chaos_dv_rhel9, chaos_vm_rhel9_with_dv):
    chaos_vm_rhel9_with_dv.deploy()
    chaos_vm_rhel9_with_dv.start(wait=True, timeout=TIMEOUT_10MIN)
    yield chaos_vm_rhel9_with_dv


@pytest.fixture()
def downscaled_storage_provisioner_deployment(request, admin_client):
    deployment = Deployment(
        client=admin_client,
        namespace=NamespacesNames.OPENSHIFT_STORAGE,
        name=request.param["storage_provisioner_deployment"],
    )
    initial_replicas = deployment.instance.spec.replicas
    with scale_deployment_replicas(
        deployment_name=deployment.name,
        namespace=deployment.namespace,
        replica_count=0,
    ):
        yield {"deployment": deployment, "initial_replicas": initial_replicas}


@pytest.fixture()
def kmp_manager_nodes(admin_client):
    yield [
        pod.node
        for pod in get_pod_by_name_prefix(
            dyn_client=admin_client,
            pod_prefix=KUBEMACPOOL_MAC_CONTROLLER_MANAGER,
            namespace=py_config["hco_namespace"],
            get_all=True,
        )
    ]


@pytest.fixture()
def rebooted_control_plane_node(request, admin_client, control_plane_nodes, kmp_manager_nodes):
    control_plane_node_to_reboot = request.param["control_plane_node_to_reboot"]

    if control_plane_node_to_reboot == "node_with_kmp_manager":
        yield random.choice(seq=kmp_manager_nodes)
    else:
        yield random.choice(
            seq=[node for node in control_plane_nodes if node.name not in [node.name for node in kmp_manager_nodes]]
        )


@pytest.fixture()
def rebooting_control_plane_node(
    rebooted_control_plane_node,
    control_plane_utility_pods,
):
    LOGGER.info(f"Rebooting control plane node {rebooted_control_plane_node.name}...")
    ExecCommandOnPod(utility_pods=control_plane_utility_pods, node=rebooted_control_plane_node).exec(
        command="shutdown -r", ignore_rc=True
    )
    wait_for_node_status(node=rebooted_control_plane_node, status=False, wait_timeout=TIMEOUT_3MIN)
    yield rebooted_control_plane_node
    wait_for_node_status(node=rebooted_control_plane_node, wait_timeout=TIMEOUT_15MIN)


@pytest.fixture()
def pod_deleting_process(request, admin_client):
    pod_prefix = request.param["pod_prefix"]
    namespace_name = request.param["namespace_name"]
    process = create_pod_deleting_process(
        dyn_client=admin_client,
        pod_prefix=pod_prefix,
        namespace_name=namespace_name,
        ratio=request.param["ratio"],
        interval=request.param["interval"],
        max_duration=request.param["max_duration"],
    )
    process.start()
    yield {
        "namespace_name": namespace_name,
        "pod_prefix": pod_prefix,
    }
    terminate_process(process=process)


@pytest.fixture()
def cluster_monitoring_process(admin_client, hco_namespace, chaos_namespace):
    LOGGER.info(f"Monitoring pods in namespaces: {hco_namespace.name}, {chaos_namespace.name}")

    cluster_monitoring_process = create_cluster_monitoring_process(
        client=admin_client,
        hco_namespace=hco_namespace,
        additional_namespaces=[chaos_namespace],
    )
    cluster_monitoring_process.start()
    yield cluster_monitoring_process
    terminate_process(process=cluster_monitoring_process)


@pytest.fixture()
def chaos_worker_background_process(
    request,
    workers,
    utility_pods_for_chaos_tests,
):
    """
    Creates a process that, when started,
    executes a command on the worker node that has the label "chaos=true".

    request.params:
        max_duration (int): Used for commands with timeouts.
        background_command (str): The command that will be executed inside the node.
        process_name (str): Name for the background process.
    Returns:
        multiprocessing.Process: Process that execute a command inside a worker node .
    """

    process_name = request.param["process_name"]
    target_nodes = get_nodes_with_label(nodes=workers, label=CHAOS_LABEL_KEY)
    assert target_nodes, f"no nodes with label:{CHAOS_LABEL_KEY} were found"
    target_node = target_nodes[0]
    LOGGER.info(f"Target node is: {target_node.name}")
    background_process = multiprocessing.Process(
        name=process_name,
        target=lambda: ExecCommandOnPod(utility_pods=utility_pods_for_chaos_tests, node=target_node).exec(
            command=request.param["background_command"],
            chroot_host=False,
            timeout=request.param["max_duration"] + TIMEOUT_5SEC,
        ),
    )
    background_process.start()
    LOGGER.info(f"{process_name} process started")
    yield background_process
    terminate_process(process=background_process)


@pytest.fixture()
def nginx_monitoring_process(
    control_plane_nodes,
    control_plane_utility_pods,
    vm_with_nginx_service,
):
    nginx_monitoring_process = create_nginx_monitoring_process(
        url=f"{vm_with_nginx_service.custom_service.instance.spec.clusterIPs[0]}:{PORT_80}",
        curl_timeout=TIMEOUT_10SEC,
        sampling_duration=TIMEOUT_2MIN,
        sampling_interval=TIMEOUT_5SEC,
        utility_pods=control_plane_utility_pods,
        control_plane_host_node=random.choice(control_plane_nodes),
    )
    nginx_monitoring_process.start()
    LOGGER.info(f"{nginx_monitoring_process} process started")
    yield nginx_monitoring_process
    terminate_process(process=nginx_monitoring_process)


@pytest.fixture()
def vm_with_nginx_service(chaos_namespace, admin_client, workers_utility_pods, workers):
    yield from create_vm_with_nginx_service(
        chaos_namespace=chaos_namespace,
        admin_client=admin_client,
        utility_pods=workers_utility_pods,
        node=random.choice(workers),
    )


@pytest.fixture()
def vm_with_nginx_service_and_node_selector(chaos_namespace, admin_client, workers_utility_pods, workers):
    yield from create_vm_with_nginx_service(
        chaos_namespace=chaos_namespace,
        admin_client=admin_client,
        utility_pods=workers_utility_pods,
        node=random.choice(workers),
        node_selector_label=HOST_LABEL,
    )


@pytest.fixture()
def label_host_node(workers):
    yield from label_nodes(nodes=[random.choice(workers)], labels=HOST_LABEL)


@pytest.fixture()
def label_migration_target_node_for_chaos(workers, vm_with_nginx_service):
    target_node = random.choice([node for node in workers if node.name != vm_with_nginx_service.vmi.node.name])
    LOGGER.info(f"Migration target Node is: {target_node.name}")
    yield from label_nodes(
        nodes=[target_node],
        labels={**CHAOS_LABEL, **HOST_LABEL},
    )


@pytest.fixture()
def utility_daemonset_for_chaos_tests(
    generated_pulled_secret,
    cnv_tests_utilities_service_account,
):
    """
    Deploy utility daemonset into the cnv-tests-utilities namespace.
    This daemonset deploys a pod on every node with the label "chaos=true" and the main usage
    is to run stress-ng commands on the hosts.
    """
    yield from utility_daemonset_for_custom_tests(
        generated_pulled_secret=generated_pulled_secret,
        cnv_tests_utilities_service_account=cnv_tests_utilities_service_account,
        label=CHAOS_LABEL_KEY,
        node_selector_label=CHAOS_LABEL,
        delete_pod_resources_limit=True,
    )


@pytest.fixture
def utility_pods_for_chaos_tests(
    admin_client,
    workers,
    utility_daemonset_for_chaos_tests,
):
    return get_utility_pods_from_nodes(
        nodes=get_nodes_with_label(nodes=workers, label=CHAOS_LABEL_KEY),
        admin_client=admin_client,
        label_selector=f"cnv-test={utility_daemonset_for_chaos_tests.instance.metadata.labels['cnv-test']}",
    )


@pytest.fixture()
def vm_node_with_chaos_label(vm_with_nginx_service):
    yield from label_nodes(nodes=[vm_with_nginx_service.vmi.node], labels=CHAOS_LABEL)


@pytest.fixture(scope="module")
def artifactory_secret_chaos_namespace_scope_module(chaos_namespace):
    artifactory_secret = get_artifactory_secret(namespace=chaos_namespace.name)
    yield artifactory_secret
    if artifactory_secret.exists:
        artifactory_secret.clean_up()


@pytest.fixture(scope="module")
def artifactory_config_map_chaos_namespace_scope_module(chaos_namespace):
    artifactory_config_map = get_artifactory_config_map(namespace=chaos_namespace.name)
    yield artifactory_config_map
    if artifactory_config_map.exists:
        artifactory_config_map.clean_up()


@pytest.fixture(scope="class")
def chaos_vms_instancetype_list(request, admin_client, chaos_namespace):
    required_instancetype = get_instance_type(name=U1_SMALL)

    vms_list = []
    for idx in range(request.param["number_of_vms"]):
        vm = VirtualMachineForTests(
            client=admin_client,
            name=f"vm-chaos-{idx}",
            namespace=chaos_namespace.name,
            image=Images.Rhel.RHEL9_REGISTRY_GUEST_IMG,
            vm_instance_type=required_instancetype,
        )
        vms_list.append(vm)
    yield vms_list
    for vm in vms_list:
        if vm.exists:
            vm.clean_up()


@pytest.fixture(scope="class")
def deleted_pod_by_name_prefix(admin_client, cnv_pod_deletion_test_matrix__class__):
    pod_matrix_key = [*cnv_pod_deletion_test_matrix__class__][0]
    pod_deletion_config = cnv_pod_deletion_test_matrix__class__[pod_matrix_key]

    deleted_pod_by_name_prefix = create_pod_deleting_process(
        dyn_client=admin_client,
        pod_prefix=pod_deletion_config["pod_prefix"],
        namespace_name=pod_deletion_config["namespace_name"],
        ratio=pod_deletion_config["ratio"],
        interval=pod_deletion_config["interval"],
        max_duration=pod_deletion_config["max_duration"],
    )
    deleted_pod_by_name_prefix.start()
    yield
    terminate_process(process=deleted_pod_by_name_prefix)

    pod_deleting_process_recover(
        resource=pod_deletion_config["resource"],
        namespace=pod_deletion_config["namespace_name"],
        pod_prefix=pod_deletion_config["pod_prefix"],
    )


@pytest.fixture(scope="module")
def multiprocessing_start_method_fork():
    # Use fork context to avoid pickling issues with nested functions
    # https://docs.python.org/3/library/multiprocessing.html#multiprocessing.Process
    # https://github.com/python/cpython/issues/132898
    original_start_method = multiprocessing.get_start_method()
    multiprocessing.set_start_method("fork", force=True)
    yield
    multiprocessing.set_start_method(original_start_method, force=True)

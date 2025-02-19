import pytest
from ocp_resources.persistent_volume import PersistentVolume
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_resources.resource import ResourceEditor

from tests.storage.constants import HPP_STORAGE_CLASSES
from tests.storage.hpp.utils import (
    DV_NAME,
    HPP_KEY,
    HPP_NODE_PLACEMENT_DICT,
    TYPE,
    VM_NAME,
    update_node_taint,
    wait_for_desired_hpp_pods_running,
)
from tests.utils import create_cirros_vm
from utilities.constants import TIMEOUT_5MIN
from utilities.hco import add_labels_to_nodes
from utilities.infra import (
    get_node_selector_dict,
    get_utility_pods_from_nodes,
    utility_daemonset_for_custom_tests,
)


@pytest.fixture
def utility_daemonset_for_hpp_test(
    generated_pulled_secret,
    cnv_tests_utilities_service_account,
):
    """
    Deploy utility daemonset into the cnv_tests_utilities_namespace namespace.
    This daemonset deploys a pod on every node with hostNetwork and the main usage is to run commands on the hosts.
    """
    utility_pods_for_hpp_test = "utility-pods-for-hpp-test"

    yield from utility_daemonset_for_custom_tests(
        generated_pulled_secret=generated_pulled_secret,
        cnv_tests_utilities_service_account=cnv_tests_utilities_service_account,
        label=utility_pods_for_hpp_test,
    )


@pytest.fixture
def utility_pods_for_hpp_test(
    admin_client,
    workers,
    utility_daemonset_for_hpp_test,
):
    utility_pod_label = utility_daemonset_for_hpp_test.instance.metadata.labels["cnv-test"]
    return get_utility_pods_from_nodes(
        nodes=workers,
        admin_client=admin_client,
        label_selector=f"cnv-test={utility_pod_label}",
    )


@pytest.fixture()
def cirros_vm_for_node_placement_tests(
    request,
    namespace,
    worker_node2,
    storage_class_matrix_hpp_matrix__module__,
    unprivileged_client,
):
    with create_cirros_vm(
        storage_class=[*storage_class_matrix_hpp_matrix__module__][0],
        namespace=namespace.name,
        client=unprivileged_client,
        dv_name=request.param.get(DV_NAME),
        vm_name=request.param.get(VM_NAME),
        node=get_node_selector_dict(node_selector=request.param.get("node", worker_node2.hostname)),
        wait_running=request.param.get("wait_running", True),
    ) as vm:
        yield vm
    if vm.vmi.exists:
        vm.vmi.wait_deleted(timeout=TIMEOUT_5MIN)


@pytest.fixture(scope="module")
def update_node_labels(worker_node1):
    worker_resources = add_labels_to_nodes(
        nodes=[
            worker_node1,
        ],
        node_labels={HPP_KEY: "hpp-val"},
    )
    yield
    for worker_resource in worker_resources:
        worker_resource.restore()


@pytest.fixture()
def updated_hpp_with_node_placement(
    worker_node2,
    worker_node3,
    hostpath_provisioner_scope_module,
    request,
    hpp_daemonset_scope_session,
    schedulable_nodes,
):
    node_placement_type = request.param[TYPE]
    with ResourceEditor(
        patches={hostpath_provisioner_scope_module: HPP_NODE_PLACEMENT_DICT[node_placement_type]}
    ) as updated_resource:
        if node_placement_type == "tolerations":
            with update_node_taint(node=worker_node2), update_node_taint(node=worker_node3):
                # Wait for 1 hpp pod to be running, and for others to be deleted
                wait_for_desired_hpp_pods_running(hpp_daemonset=hpp_daemonset_scope_session, number_of_pods=1)
                yield updated_resource
        else:
            # Wait for 1 hpp pod to be running, and for others to be deleted
            wait_for_desired_hpp_pods_running(hpp_daemonset=hpp_daemonset_scope_session, number_of_pods=1)
            yield updated_resource
    # Wait for hpp pods to be restored
    wait_for_desired_hpp_pods_running(hpp_daemonset=hpp_daemonset_scope_session, number_of_pods=len(schedulable_nodes))


@pytest.fixture()
def cirros_pvc_on_hpp(cirros_vm_for_node_placement_tests):
    return PersistentVolumeClaim(
        namespace=cirros_vm_for_node_placement_tests.namespace,
        name=cirros_vm_for_node_placement_tests.data_volume_template["metadata"]["name"],
    )


@pytest.fixture()
def cirros_pv_on_hpp(cirros_pvc_on_hpp):
    return PersistentVolume(
        name=cirros_pvc_on_hpp.instance.spec.volumeName,
    )


@pytest.fixture(scope="session")
def skip_test_if_no_hpp_requested(available_storage_classes_names):
    # Skip test if HPP is not passed with --storage-class-matrix
    if not any(storage_class in HPP_STORAGE_CLASSES for storage_class in available_storage_classes_names):
        pytest.skip(f"HPP is not passed with --storage-class-matrix: {available_storage_classes_names}")

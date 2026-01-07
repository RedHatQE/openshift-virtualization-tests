import logging

import pytest
from ocp_resources.namespace import Namespace
from ocp_resources.ssp import SSP
from ocp_resources.virtual_machine_instance import VirtualMachineInstance
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.observability.metrics.utils import validate_initial_virt_operator_replicas_reverted
from utilities.constants import (
    TIMEOUT_5MIN,
    TIMEOUT_5SEC,
    VIRT_OPERATOR,
)
from utilities.hco import ResourceEditorValidateHCOReconcile, get_installed_hco_csv
from utilities.infra import (
    create_ns,
    get_deployment_by_name,
    get_node_selector_dict,
    scale_deployment_replicas,
)
from utilities.virt import VirtualMachineForTests, fedora_vm_body, get_all_virt_pods_with_running_status, running_vm

LOGGER = logging.getLogger(__name__)
ANNOTATIONS_FOR_VIRT_OPERATOR_ENDPOINT = {
    "annotations": {
        "control-plane.alpha.kubernetes.io/leader": '{"holderIdentity":"fake-holder",'
        '"leaseDurationSeconds":3600,"acquireTime":"now()",'
        '"renewTime":"now()+1","leaderTransitions":1}'
    }
}


@pytest.fixture(scope="class")
def paused_ssp_operator(admin_client, hco_namespace, ssp_resource_scope_class):
    """
    Pause ssp-operator to avoid from reconciling any related objects
    """
    with ResourceEditorValidateHCOReconcile(
        patches={ssp_resource_scope_class: {"metadata": {"annotations": {"kubevirt.io/operator.paused": "true"}}}},
        list_resource_reconcile=[SSP],
    ):
        yield


@pytest.fixture(scope="session")
def olm_namespace(admin_client):
    return Namespace(name="openshift-operator-lifecycle-manager", client=admin_client, ensure_exists=True)


@pytest.fixture(scope="class")
def disabled_olm_operator(olm_namespace):
    with scale_deployment_replicas(
        deployment_name="olm-operator",
        namespace=olm_namespace.name,
        replica_count=0,
    ):
        yield


@pytest.fixture(scope="class")
def disabled_virt_operator(admin_client, hco_namespace, disabled_olm_operator):
    virt_pods_with_running_status = get_all_virt_pods_with_running_status(
        client=admin_client, hco_namespace=hco_namespace
    )
    virt_pods_count_before_disabling_virt_operator = len(virt_pods_with_running_status.keys())
    with scale_deployment_replicas(
        deployment_name=VIRT_OPERATOR,
        namespace=hco_namespace.name,
        replica_count=0,
    ):
        yield

    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_5MIN,
        sleep=TIMEOUT_5SEC,
        func=get_all_virt_pods_with_running_status,
        client=admin_client,
        hco_namespace=hco_namespace,
    )
    sample = None
    try:
        for sample in samples:
            if len(sample.keys()) == virt_pods_count_before_disabling_virt_operator:
                return True
    except TimeoutExpiredError:
        LOGGER.error(
            f"After restoring replicas for {VIRT_OPERATOR},"
            f"{virt_pods_with_running_status} virt pods were expected to be in running state."
            f"Here are available virt pods: {sample}"
        )
        raise


@pytest.fixture(scope="class")
def csv_scope_class(admin_client, hco_namespace, installing_cnv):
    if not installing_cnv:
        return get_installed_hco_csv(admin_client=admin_client, hco_namespace=hco_namespace)


@pytest.fixture(scope="module")
def virt_operator_deployment(admin_client, hco_namespace):
    return get_deployment_by_name(
        deployment_name=VIRT_OPERATOR, namespace_name=hco_namespace.name, admin_client=admin_client
    )


@pytest.fixture(scope="module")
def initial_virt_operator_replicas(prometheus, virt_operator_deployment, hco_namespace):
    virt_operator_deployment.wait_for_replicas()
    virt_operator_deployment_initial_replicas = virt_operator_deployment.instance.status.replicas
    assert virt_operator_deployment_initial_replicas, f"Not replicas found for {VIRT_OPERATOR}"
    return str(virt_operator_deployment_initial_replicas)


@pytest.fixture(scope="class")
def initial_virt_operator_replicas_reverted(prometheus, initial_virt_operator_replicas):
    validate_initial_virt_operator_replicas_reverted(
        prometheus=prometheus, initial_virt_operator_replicas=initial_virt_operator_replicas
    )


@pytest.fixture(scope="session")
def vm_with_node_selector_namespace(admin_client, unprivileged_client):
    yield from create_ns(admin_client=admin_client, unprivileged_client=unprivileged_client, name="test-outdated-vm-ns")


@pytest.fixture(scope="session")
def vm_with_node_selector_for_upgrade(vm_with_node_selector_namespace, unprivileged_client, worker_node1):
    name = "vm-with-node-selector"
    with VirtualMachineForTests(
        name=name,
        namespace=vm_with_node_selector_namespace.name,
        body=fedora_vm_body(name=name),
        node_selector=get_node_selector_dict(node_selector=worker_node1.name),
        client=unprivileged_client,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture(scope="session")
def outdated_vmis_count(admin_client):
    vmis_with_outdated_label = len(
        list(
            VirtualMachineInstance.get(
                client=admin_client,
                label_selector="kubevirt.io/outdatedLauncherImage",
            )
        )
    )
    assert vmis_with_outdated_label > 0, "There is no outdated vms"
    return vmis_with_outdated_label


@pytest.fixture(scope="session")
def kubevirt_resource_outdated_vmi_workloads_count(kubevirt_resource_scope_session):
    return kubevirt_resource_scope_session.instance.status.outdatedVirtualMachineInstanceWorkloads

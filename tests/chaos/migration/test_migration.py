import random

import pytest
from ocp_resources.deployment import Deployment
from ocp_resources.namespace import Namespace
from ocp_resources.virtual_machine_instance import VirtualMachineInstance

from tests.chaos.constants import STRESS_NG
from tests.chaos.migration.utils import (
    assert_migration_result_and_cleanup,
)
from utilities.constants import (
    PORT_80,
    QUARANTINED,
    TIMEOUT_2MIN,
    TIMEOUT_3MIN,
    TIMEOUT_5MIN,
    TIMEOUT_5SEC,
    TIMEOUT_15MIN,
    TIMEOUT_30SEC,
    NamespacesNames,
    StorageClassNames,
)
from utilities.infra import wait_for_pods_running
from utilities.virt import verify_vm_service_reachable, wait_for_vmi_relocation_and_running

pytestmark = [
    pytest.mark.chaos,
    pytest.mark.usefixtures("multiprocessing_start_method_fork", "chaos_namespace", "cluster_monitoring_process"),
]


@pytest.mark.s390x
@pytest.mark.gpfs
@pytest.mark.parametrize(
    "pod_deleting_process",
    [
        pytest.param(
            {
                "pod_prefix": "apiserver",
                "resource": Deployment,
                "namespace_name": NamespacesNames.OPENSHIFT_APISERVER,
                "ratio": 0.5,
                "interval": TIMEOUT_5SEC,
                "max_duration": TIMEOUT_5MIN,
            },
            marks=pytest.mark.polarion("CNV-5455"),
            id="openshift-apiserver",
        ),
        pytest.param(
            {
                "pod_prefix": "virt-launcher",
                "resource": VirtualMachineInstance,
                "namespace_name": NamespacesNames.CHAOS,
                "ratio": 1,
                "interval": TIMEOUT_30SEC,
                "max_duration": TIMEOUT_2MIN,
            },
            marks=pytest.mark.polarion("CNV-5454"),
            id="virt_launcher",
        ),
    ],
    indirect=True,
)
def test_pod_delete_migration(
    chaos_vm_rhel9,
    pod_deleting_process,
    tainted_node_for_vm_chaos_rhel9_migration,
    admin_client,
):
    """
    This experiment tests the robustness of the cluster
    by killing random function supported pods in their corresponding namespaces
    while a VM is being migrated and asserting that a given running VMI
    is running on a different node at the end of the test
    """

    wait_for_vmi_relocation_and_running(vm=chaos_vm_rhel9, initial_node=tainted_node_for_vm_chaos_rhel9_migration)
    wait_for_pods_running(
        admin_client=admin_client,
        namespace=Namespace(name=pod_deleting_process["namespace_name"]),
        number_of_consecutive_checks=10,
        filter_pods_by_name=pod_deleting_process["pod_prefix"],
    )


@pytest.mark.s390x
@pytest.mark.gpfs
@pytest.mark.parametrize(
    "chaos_worker_background_process",
    [
        pytest.param(
            {
                "max_duration": TIMEOUT_2MIN,
                # The background_command may change when we have tools to create more stress.
                "background_command": f"{STRESS_NG}  --io 5 -t 120s",
                "process_name": STRESS_NG,
            },
            marks=pytest.mark.polarion("CNV-7302"),
            id="io-stress",
        ),
        pytest.param(
            {
                "max_duration": TIMEOUT_2MIN,
                "background_command": f"{STRESS_NG} --cpu 6 -t 120s",
                "process_name": STRESS_NG,
            },
            marks=pytest.mark.polarion("CNV-7344"),
            id="cpu-stress",
        ),
    ],
    indirect=True,
)
def test_stress_migration_target_node(
    workers,
    workers_utility_pods,
    label_host_node,
    vm_with_nginx_service_and_node_selector,
    label_migration_target_node_for_chaos,
    chaos_worker_background_process,
    tainted_node_for_vm_nginx_migration,
):
    """
    This experiment generates I/O load on the target node of a VM migration. The expected result is for the VM to
    eventually be successfully migrated.
    """
    assert_migration_result_and_cleanup(
        initial_node=tainted_node_for_vm_nginx_migration,
        vm=vm_with_nginx_service_and_node_selector,
        chaos_worker_background_process=chaos_worker_background_process,
    )
    verify_vm_service_reachable(
        utility_pods=workers_utility_pods,
        node=random.choice(workers),
        url=f"{vm_with_nginx_service_and_node_selector.custom_service.instance.spec.clusterIPs[0]}:{PORT_80}",
    )


@pytest.mark.s390x
@pytest.mark.parametrize(
    "chaos_dv_rhel9, pod_deleting_process",
    [
        pytest.param(
            {"storage_class": StorageClassNames.CEPH_RBD_VIRTUALIZATION},
            {
                "pod_prefix": "rook-ceph-operator",
                "resource": Deployment,
                "namespace_name": NamespacesNames.OPENSHIFT_STORAGE,
                "ratio": 1,
                "interval": TIMEOUT_5SEC,
                "max_duration": TIMEOUT_5MIN,
            },
            marks=pytest.mark.polarion("CNV-7257"),
            id="rook-ceph-operator",
        ),
        pytest.param(
            {"storage_class": StorageClassNames.CEPH_RBD_VIRTUALIZATION},
            {
                "pod_prefix": "ocs-operator",
                "resource": Deployment,
                "namespace_name": NamespacesNames.OPENSHIFT_STORAGE,
                "ratio": 1,
                "interval": TIMEOUT_5SEC,
                "max_duration": TIMEOUT_5MIN,
            },
            marks=pytest.mark.polarion("CNV-7754"),
            id="ocs-operator",
        ),
        pytest.param(
            {"storage_class": StorageClassNames.CEPH_RBD_VIRTUALIZATION},
            {
                "pod_prefix": "rook-ceph-osd",
                "resource": Deployment,
                "namespace_name": NamespacesNames.OPENSHIFT_STORAGE,
                "ratio": 1,
                "interval": TIMEOUT_5SEC,
                "max_duration": TIMEOUT_3MIN,
            },
            marks=pytest.mark.polarion("CNV-7250"),
            id="rook-ceph-osd",
        ),
    ],
    indirect=True,
)
def test_pod_delete_storage_migration(
    chaos_dv_rhel9,
    chaos_vm_rhel9_with_dv_started,
    pod_deleting_process,
    tainted_node_for_vm_chaos_rhel9_with_dv_migration,
):
    """
    This scenario verifies that the migration of a vm with a dv
    is completed while we disrupt different storage resources
    """
    assert wait_for_vmi_relocation_and_running(
        vm=chaos_vm_rhel9_with_dv_started,
        initial_node=tainted_node_for_vm_chaos_rhel9_with_dv_migration,
    ), "The VMI has not been migrated to a different node."


@pytest.mark.s390x
@pytest.mark.gpfs
@pytest.mark.parametrize(
    "chaos_worker_background_process",
    [
        pytest.param(
            {
                "max_duration": TIMEOUT_2MIN,
                "background_command": f"{STRESS_NG}  --io 5 -t 120s",
                "process_name": STRESS_NG,
            },
            marks=pytest.mark.polarion("CNV-7251"),
            id="io-stress",
        ),
        pytest.param(
            {
                "max_duration": TIMEOUT_2MIN,
                "background_command": f"{STRESS_NG} --cpu 6 -t 120s",
                "process_name": STRESS_NG,
            },
            marks=pytest.mark.polarion("CNV-7345"),
            id="cpu-stress",
        ),
    ],
    indirect=True,
)
def test_stress_migration_source_node(
    workers,
    workers_utility_pods,
    vm_with_nginx_service,
    vm_node_with_chaos_label,
    chaos_worker_background_process,
    tainted_node_for_vm_nginx_migration,
):
    """
    This experiment generates I/O load on the source node of a VM migration. The expected result is for the VM to
    eventually be successfully migrated.
    """
    assert_migration_result_and_cleanup(
        vm=vm_with_nginx_service,
        initial_node=tainted_node_for_vm_nginx_migration,
        chaos_worker_background_process=chaos_worker_background_process,
    )
    verify_vm_service_reachable(
        utility_pods=workers_utility_pods,
        node=random.choice(workers),
        url=f"{vm_with_nginx_service.custom_service.instance.spec.clusterIPs[0]}:{PORT_80}",
    )


@pytest.mark.xfail(
    reason=(f"{QUARANTINED}: Failed on teardown with kubernetes.client.exceptions.ApiException. Tracked in CNV-62939"),
    run=False,
)
@pytest.mark.s390x
@pytest.mark.gpfs
@pytest.mark.polarion("CNV-6120")
def test_migration_reboot_source_node(
    chaos_migration_policy,
    vm_with_nginx_service,
    tainted_node_for_vm_nginx_migration,
    rebooted_source_node,
):
    """
    This experiment restarts the source node during the VM migration.
    'bandwidthPerMigration' is for prolonging the duration of migration.
    The expected result is for the VM to eventually be successfully migrated.
    """

    assert wait_for_vmi_relocation_and_running(
        vm=vm_with_nginx_service,
        initial_node=tainted_node_for_vm_nginx_migration,
        timeout=TIMEOUT_15MIN,
    ), "The VMI has not been migrated to a different node."


@pytest.mark.xfail(
    reason=(f"{QUARANTINED}: Failed on teardown with kubernetes.client.exceptions.ApiException. Tracked in CNV-62949"),
    run=False,
)
@pytest.mark.gpfs
@pytest.mark.polarion("CNV-5456")
def test_migration_reboot_target_node(
    chaos_migration_policy,
    labeled_source_node,
    vm_with_nginx_service_and_node_selector,
    labeled_migration_target_node,
    tainted_node_for_vm_nginx_with_node_selector_migration,
    rebooted_target_node,
):
    """
    This experiment restarts the target node during the VM migration.
    'bandwidthPerMigration' is for prolonging the duration of migration.
    The expected result is for the VM to eventually be successfully migrated.
    """

    assert wait_for_vmi_relocation_and_running(
        vm=vm_with_nginx_service_and_node_selector,
        initial_node=labeled_source_node,
        timeout=TIMEOUT_15MIN,
    ), "The VMI has not been migrated to a different node."

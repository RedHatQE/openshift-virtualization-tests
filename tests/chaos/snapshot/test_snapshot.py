import pytest
from ocp_resources.daemonset import DaemonSet
from ocp_resources.deployment import Deployment
from ocp_resources.virtual_machine_restore import VirtualMachineRestore
from pytest_testconfig import py_config

from utilities.constants import TIMEOUT_5MIN, TIMEOUT_5SEC, NamespacesNames

pytestmark = [
    pytest.mark.chaos,
    pytest.mark.gpfs,
    pytest.mark.usefixtures(
        "skip_if_no_storage_class_for_snapshot",
        "multiprocessing_start_method_fork",
        "chaos_namespace",
        "cluster_monitoring_process",
    ),
]


@pytest.mark.s390x
@pytest.mark.parametrize(
    "pod_deleting_process, chaos_online_snapshots",
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
            {"number_of_snapshots": 3},
            marks=pytest.mark.polarion("CNV-8260"),
            id="openshift-apiserver",
        ),
        pytest.param(
            {
                "pod_prefix": "csi-snapshot-controller",
                "resource": Deployment,
                "namespace_name": NamespacesNames.OPENSHIFT_CLUSTER_STORAGE_OPERATOR,
                "ratio": 0.5,
                "interval": TIMEOUT_5SEC,
                "max_duration": TIMEOUT_5MIN,
            },
            {"number_of_snapshots": 3},
            marks=pytest.mark.polarion("CNV-8382"),
            id="snapshot-controller",
        ),
        pytest.param(
            {
                "pod_prefix": "virt-api",
                "resource": Deployment,
                "namespace_name": py_config["hco_namespace"],
                "ratio": 0.5,
                "interval": TIMEOUT_5SEC,
                "max_duration": TIMEOUT_5MIN,
            },
            {"number_of_snapshots": 3},
            marks=pytest.mark.polarion("CNV-8534"),
            id="cnv-control-plane-virt-api",
        ),
        pytest.param(
            {
                "pod_prefix": "rook-ceph-osd",
                "resource": Deployment,
                "namespace_name": NamespacesNames.OPENSHIFT_STORAGE,
                "ratio": 0.5,
                "interval": TIMEOUT_5SEC,
                "max_duration": TIMEOUT_5MIN,
            },
            {"number_of_snapshots": 3},
            marks=pytest.mark.polarion("CNV-8930"),
            id="rook-ceph-osd",
        ),
        pytest.param(
            {
                "pod_prefix": "csi-rbdplugin",
                "resource": DaemonSet,
                "namespace_name": NamespacesNames.OPENSHIFT_STORAGE,
                "ratio": 0.5,
                "interval": TIMEOUT_5SEC,
                "max_duration": TIMEOUT_5MIN,
            },
            {"number_of_snapshots": 3},
            marks=pytest.mark.polarion("CNV-8750"),
            id="csi-driver",
        ),
    ],
    indirect=True,
)
def test_pod_delete_snapshot(
    admin_client,
    chaos_vm_rhel9_for_snapshot,
    pod_deleting_process,
    chaos_online_snapshots,
):
    """
    This experiment tests the robustness of the VM snapshot feature
    by killing random function supported pods in their corresponding namespace
    and asserting that VM snapshots can be taken, restored and deleted during the process.
    """
    chaos_vm_rhel9_for_snapshot.stop(wait=True)
    for idx, snapshot in enumerate(chaos_online_snapshots):
        with VirtualMachineRestore(
            client=admin_client,
            name=f"restore-snapshot-{idx}",
            namespace=chaos_vm_rhel9_for_snapshot.namespace,
            vm_name=chaos_vm_rhel9_for_snapshot.name,
            snapshot_name=snapshot.name,
        ) as vm_restore:
            vm_restore.wait_restore_done()
        snapshot.clean_up()

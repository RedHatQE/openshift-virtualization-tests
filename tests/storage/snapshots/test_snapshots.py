# -*- coding: utf-8 -*-

"""
Snapshots tests
"""

import logging

import pytest
from kubernetes.client.rest import ApiException
from ocp_resources.virtual_machine_restore import VirtualMachineRestore
from ocp_resources.virtual_machine_snapshot import VirtualMachineSnapshot

from tests.storage.constants import ADMIN_NAMESPACE_PARAM
from tests.storage.snapshots.constants import (
    ERROR_MSG_USER_CANNOT_CREATE_VM_RESTORE,
    ERROR_MSG_USER_CANNOT_LIST_VM_RESTORE,
    ERROR_MSG_USER_CANNOT_LIST_VM_SNAPSHOTS,
    ERROR_MSG_VM_IS_RUNNING,
    WINDOWS_DIRECTORY_PATH,
)
from tests.storage.snapshots.utils import (
    assert_directory_existence,
    expected_output_after_restore,
    fail_to_create_snapshot_no_permissions,
    start_windows_vm_after_restore,
)
from utilities.constants import LS_COMMAND
from utilities.storage import run_command_on_cirros_vm_and_check_output

LOGGER = logging.getLogger(__name__)


pytestmark = pytest.mark.usefixtures(
    "namespace",
    "skip_if_no_storage_class_for_snapshot",
)


@pytest.mark.polarion("CNV-5781")
def test_snapshot_feature_gate_present(kubevirt_feature_gates):
    """
    This test will ensure that 'Snapshot' feature gate is present in KubeVirt ConfigMap.
    """
    assert "Snapshot" in kubevirt_feature_gates


class TestRestoreSnapshots:
    @pytest.mark.parametrize(
        "cirros_vm_name, snapshots_with_content, expected_results, snapshots_to_restore_idx",
        [
            pytest.param(
                {"vm_name": "vm-cnv-4789"},
                {"number_of_snapshots": 1, "online_vm": False},
                [expected_output_after_restore(1)],
                [0],
                marks=(
                    pytest.mark.polarion("CNV-4789"),
                    pytest.mark.gating(),
                ),
                id="test_restore_basic_snapshot",
            ),
            pytest.param(
                {"vm_name": "vm-cnv-4865"},
                {"number_of_snapshots": 3, "online_vm": False},
                [expected_output_after_restore(2)],
                [1],
                marks=pytest.mark.polarion("CNV-4865"),
                id="test_restore_middle_snapshot",
            ),
            pytest.param(
                {"vm_name": "vm-cnv-4843"},
                {"number_of_snapshots": 3, "online_vm": False},
                [
                    expected_output_after_restore(3),
                    expected_output_after_restore(2),
                    expected_output_after_restore(1),
                ],
                [2, 1, 0],
                marks=pytest.mark.polarion("CNV-4843"),
                id="test_restore_all_snapshots",
            ),
            pytest.param(
                {"vm_name": "vm-cnv-6526"},
                {"number_of_snapshots": 1, "online_vm": True},
                [expected_output_after_restore(1)],
                [0],
                marks=pytest.mark.polarion("CNV-6526"),
                id="test_restore_basic_snapshot",
            ),
            pytest.param(
                {"vm_name": "vm-cnv-6527"},
                {"number_of_snapshots": 3, "online_vm": True},
                [expected_output_after_restore(2)],
                [1],
                marks=pytest.mark.polarion("CNV-6527"),
                id="test_restore_middle_snapshot",
            ),
            pytest.param(
                {"vm_name": "vm-cnv-6528"},
                {"number_of_snapshots": 3, "online_vm": True},
                [
                    expected_output_after_restore(3),
                    expected_output_after_restore(2),
                    expected_output_after_restore(1),
                ],
                [2, 1, 0],
                marks=pytest.mark.polarion("CNV-6528"),
                id="test_restore_all_snapshots",
            ),
        ],
        indirect=["cirros_vm_name", "snapshots_with_content"],
    )
    def test_restore_snapshots(
        self,
        cirros_vm_for_snapshot,
        snapshots_with_content,
        expected_results,
        snapshots_to_restore_idx,
    ):
        for idx in range(len(snapshots_to_restore_idx)):
            snap_idx = snapshots_to_restore_idx[idx]
            with VirtualMachineRestore(
                name=f"restore-snapshot-{snap_idx}",
                namespace=cirros_vm_for_snapshot.namespace,
                vm_name=cirros_vm_for_snapshot.name,
                snapshot_name=snapshots_with_content[snap_idx].name,
            ) as vm_restore:
                vm_restore.wait_restore_done()
                cirros_vm_for_snapshot.start(wait=True)
                run_command_on_cirros_vm_and_check_output(
                    vm=cirros_vm_for_snapshot,
                    command=LS_COMMAND,
                    expected_result=expected_results[idx],
                )
                cirros_vm_for_snapshot.stop(wait=True)

    @pytest.mark.parametrize(
        "cirros_vm_name, snapshots_with_content",
        [
            pytest.param(
                {"vm_name": "vm-cnv-5048"},
                {"number_of_snapshots": 1},
                marks=pytest.mark.polarion("CNV-5048"),
            ),
        ],
        indirect=True,
    )
    def test_restore_snapshot_while_vm_is_running(
        self,
        cirros_vm_for_snapshot,
        snapshots_with_content,
    ):
        cirros_vm_for_snapshot.start(wait=True)
        with pytest.raises(
            ApiException,
            match=ERROR_MSG_VM_IS_RUNNING,
        ):
            with VirtualMachineRestore(
                name="restore-snapshot-cnv-5048",
                namespace=cirros_vm_for_snapshot.namespace,
                vm_name=cirros_vm_for_snapshot.name,
                snapshot_name=snapshots_with_content[0].name,
            ):
                return

    @pytest.mark.parametrize(
        "cirros_vm_name, snapshots_with_content, namespace",
        [
            pytest.param(
                {"vm_name": "vm-cnv-5049"},
                {"number_of_snapshots": 1},
                ADMIN_NAMESPACE_PARAM,
                marks=pytest.mark.polarion("CNV-5049"),
            ),
        ],
        indirect=True,
    )
    def test_fail_restore_vm_with_unprivileged_client(
        self,
        cirros_vm_for_snapshot,
        snapshots_with_content,
        unprivileged_client,
    ):
        with pytest.raises(
            ApiException,
            match=ERROR_MSG_USER_CANNOT_CREATE_VM_RESTORE,
        ):
            with VirtualMachineRestore(
                client=unprivileged_client,
                name="restore-snapshot-cnv-5049-unprivileged",
                namespace=cirros_vm_for_snapshot.namespace,
                vm_name=cirros_vm_for_snapshot.name,
                snapshot_name=snapshots_with_content[0].name,
            ):
                return

    @pytest.mark.sno
    @pytest.mark.parametrize(
        "cirros_vm_name, snapshots_with_content",
        [
            pytest.param(
                {"vm_name": "vm-cnv-5084"},
                {"number_of_snapshots": 1},
                marks=pytest.mark.polarion("CNV-5084"),
                id="test_that_restore_the_same_snapshot_twice ",
            ),
        ],
        indirect=True,
    )
    def test_restore_same_snapshot_twice(
        self,
        cirros_vm_for_snapshot,
        snapshots_with_content,
    ):
        with VirtualMachineRestore(
            name="restore-snapshot-cnv-5084-first",
            namespace=cirros_vm_for_snapshot.namespace,
            vm_name=cirros_vm_for_snapshot.name,
            snapshot_name=snapshots_with_content[0].name,
        ) as first_restore:
            first_restore.wait_restore_done()
            with VirtualMachineRestore(
                name="restore-snapshot-cnv-5084-second",
                namespace=cirros_vm_for_snapshot.namespace,
                vm_name=cirros_vm_for_snapshot.name,
                snapshot_name=snapshots_with_content[0].name,
            ) as second_restore:
                second_restore.wait_restore_done()
                cirros_vm_for_snapshot.start(wait=True)
                run_command_on_cirros_vm_and_check_output(
                    vm=cirros_vm_for_snapshot,
                    command=LS_COMMAND,
                    expected_result=expected_output_after_restore(1),
                )


@pytest.mark.parametrize(
    "cirros_vm_name, snapshots_with_content",
    [
        pytest.param(
            {"vm_name": "vm-cnv-4866"},
            {"number_of_snapshots": 2},
            marks=pytest.mark.polarion("CNV-4866"),
        ),
    ],
    indirect=True,
)
def test_remove_vm_with_snapshots(
    cirros_vm_for_snapshot,
    snapshots_with_content,
):
    cirros_vm_for_snapshot.delete(wait=True)
    for snapshot in snapshots_with_content:
        assert snapshot.instance.status.readyToUse


@pytest.mark.parametrize(
    "cirros_vm_name, snapshots_with_content, expected_result",
    [
        pytest.param(
            {"vm_name": "vm-cnv-4870"},
            {"number_of_snapshots": 2},
            "after-snap-1.txt after-snap-2.txt before-snap-1.txt before-snap-2.txt",
            marks=pytest.mark.polarion("CNV-4870"),
        ),
    ],
    indirect=["cirros_vm_name", "snapshots_with_content"],
)
def test_remove_snapshots_while_vm_is_running(
    cirros_vm_for_snapshot,
    snapshots_with_content,
    expected_result,
):
    cirros_vm_for_snapshot.start(wait=True)
    for idx in range(len(snapshots_with_content)):
        snapshots_with_content[idx].delete(wait=True)
        run_command_on_cirros_vm_and_check_output(
            vm=cirros_vm_for_snapshot,
            command=LS_COMMAND,
            expected_result=expected_result,
        )
        cirros_vm_for_snapshot.restart(wait=True)
        run_command_on_cirros_vm_and_check_output(
            vm=cirros_vm_for_snapshot,
            command=LS_COMMAND,
            expected_result=expected_result,
        )


@pytest.mark.parametrize(
    "namespace, resource, error_msg",
    [
        pytest.param(
            ADMIN_NAMESPACE_PARAM,
            VirtualMachineSnapshot,
            ERROR_MSG_USER_CANNOT_LIST_VM_SNAPSHOTS,
            marks=pytest.mark.polarion("CNV-5050"),
        ),
        pytest.param(
            ADMIN_NAMESPACE_PARAM,
            VirtualMachineRestore,
            ERROR_MSG_USER_CANNOT_LIST_VM_RESTORE,
            marks=pytest.mark.polarion("CNV-5331"),
        ),
    ],
    indirect=["namespace"],
)
def test_unprivileged_client_fails_to_list_resources(namespace, unprivileged_client, resource, error_msg):
    with pytest.raises(
        ApiException,
        match=error_msg,
    ):
        list(resource.get(dyn_client=unprivileged_client, namespace=namespace.name))
        return


@pytest.mark.parametrize(
    "cirros_vm_name, namespace",
    [
        pytest.param(
            {"vm_name": "vm-cnv-4867"},
            ADMIN_NAMESPACE_PARAM,
            marks=pytest.mark.polarion("CNV-4867"),
        ),
    ],
    indirect=True,
)
def test_fail_to_snapshot_with_unprivileged_client_no_permissions(
    cirros_vm_for_snapshot,
    unprivileged_client,
):
    fail_to_create_snapshot_no_permissions(
        snapshot_name="snapshot-cnv-4867-unprivileged",
        namespace=cirros_vm_for_snapshot.namespace,
        vm_name=cirros_vm_for_snapshot.name,
        client=unprivileged_client,
    )


@pytest.mark.parametrize(
    "cirros_vm_name, namespace",
    [
        pytest.param(
            {"vm_name": "vm-cnv-4868"},
            ADMIN_NAMESPACE_PARAM,
            marks=pytest.mark.polarion("CNV-4868"),
        ),
    ],
    indirect=True,
)
def test_fail_to_snapshot_with_unprivileged_client_dv_permissions(
    cirros_vm_for_snapshot,
    permissions_for_dv,
    unprivileged_client,
):
    fail_to_create_snapshot_no_permissions(
        snapshot_name="snapshot-cnv-4868-unprivileged",
        namespace=cirros_vm_for_snapshot.namespace,
        vm_name=cirros_vm_for_snapshot.name,
        client=unprivileged_client,
    )


@pytest.mark.parametrize(
    "windows_vm_for_snapshot",
    [
        pytest.param(
            {"dv_name": "dv-8307", "vm_name": "vm-8307"},
            marks=pytest.mark.polarion("CNV-8307"),
        ),
    ],
    indirect=True,
)
def test_online_windows_vm_successful_restore(
    windows_vm_for_snapshot,
    windows_snapshot,
    snapshot_dirctory_removed,
):
    with VirtualMachineRestore(
        name="restore-vm",
        namespace=windows_vm_for_snapshot.namespace,
        vm_name=windows_vm_for_snapshot.name,
        snapshot_name=windows_snapshot.name,
    ) as restore:
        start_windows_vm_after_restore(vm_restore=restore, windows_vm=windows_vm_for_snapshot)
        assert_directory_existence(
            expected_result=True,
            windows_vm=windows_vm_for_snapshot,
            directory_path=WINDOWS_DIRECTORY_PATH,
        )


@pytest.mark.parametrize(
    "windows_vm_for_snapshot",
    [
        pytest.param(
            {"dv_name": "dv-8536", "vm_name": "vm-8536"},
            marks=pytest.mark.polarion("CNV-8536"),
        ),
    ],
    indirect=True,
)
def test_write_to_file_while_snapshot(
    windows_vm_for_snapshot,
    windows_snapshot,
    file_created_during_snapshot,
):
    with VirtualMachineRestore(
        name="restore-vm",
        namespace=windows_vm_for_snapshot.namespace,
        vm_name=windows_vm_for_snapshot.name,
        snapshot_name=windows_snapshot.name,
    ) as restore:
        start_windows_vm_after_restore(vm_restore=restore, windows_vm=windows_vm_for_snapshot)

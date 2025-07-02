"""
Clone tests
"""

import pytest
from ocp_resources.datavolume import DataVolume

from tests.os_params import WINDOWS_11, WINDOWS_11_TEMPLATE_LABELS
from tests.storage.utils import (
    assert_pvc_snapshot_clone_annotation,
    assert_use_populator,
    create_vm_and_verify_image_permission,
    create_vm_from_dv,
    create_windows_vm_validate_guest_agent_info,
)
from utilities.constants import (
    OS_FLAVOR_CIRROS,
    OS_FLAVOR_WINDOWS,
    TIMEOUT_1MIN,
    TIMEOUT_10MIN,
    TIMEOUT_40MIN,
    Images,
)
from utilities.storage import (
    check_disk_count_in_vm,
    create_dv,
    data_volume_template_dict,
    overhead_size_for_dv,
)
from utilities.virt import (
    VirtualMachineForTests,
    restart_vm_wait_for_running_vm,
    running_vm,
)

WINDOWS_CLONE_TIMEOUT = TIMEOUT_40MIN


def create_vm_from_clone_dv_template(
    vm_name,
    dv_name,
    namespace_name,
    source_dv,
    client,
    volume_mode,
    storage_class,
    size=None,
):
    with VirtualMachineForTests(
        name=vm_name,
        namespace=namespace_name,
        os_flavor=OS_FLAVOR_CIRROS,
        client=client,
        memory_requests=Images.Cirros.DEFAULT_MEMORY_SIZE,
        data_volume_template=data_volume_template_dict(
            target_dv_name=dv_name,
            target_dv_namespace=namespace_name,
            source_dv=source_dv,
            volume_mode=volume_mode,
            size=size,
            storage_class=storage_class,
        ),
    ) as vm:
        running_vm(vm=vm, wait_for_interfaces=False)
        check_disk_count_in_vm(vm=vm)


@pytest.mark.tier3
@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_function",
    [
        pytest.param(
            {
                "dv_name": "dv-source",
                "image": f"{Images.Windows.DIR}/{Images.Windows.WIN11_IMG}",
                "dv_size": Images.Windows.DEFAULT_DV_SIZE,
            },
            marks=(pytest.mark.polarion("CNV-1892")),
        ),
    ],
    indirect=True,
)
def test_successful_clone_of_large_image(
    admin_client,
    namespace,
    data_volume_multi_storage_scope_function,
):
    conditions = [
        DataVolume.Condition.Type.BOUND,
        DataVolume.Condition.Type.READY,
    ]
    with create_dv(
        source="pvc",
        dv_name="dv-target",
        namespace=namespace.name,
        size=data_volume_multi_storage_scope_function.size,
        source_pvc=data_volume_multi_storage_scope_function.name,
        storage_class=data_volume_multi_storage_scope_function.storage_class,
    ) as cdv:
        cdv.wait_for_dv_success(timeout=WINDOWS_CLONE_TIMEOUT)
        for condition in conditions:
            cdv.wait_for_condition(
                condition=condition,
                status=DataVolume.Condition.Status.TRUE,
                timeout=TIMEOUT_1MIN,
            )


@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_function",
    [
        pytest.param(
            {
                "dv_name": "dv-source",
                "image": f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}",
                "dv_size": Images.Cirros.DEFAULT_DV_SIZE,
            },
            marks=(
                pytest.mark.polarion("CNV-2148"),
                pytest.mark.post_upgrade(),
                pytest.mark.sno(),
                pytest.mark.gating(),
            ),
        ),
    ],
    indirect=True,
)
def test_successful_vm_restart_with_cloned_dv(
    namespace,
    data_volume_multi_storage_scope_function,
):
    with create_dv(
        source="pvc",
        dv_name="dv-target",
        namespace=namespace.name,
        size=data_volume_multi_storage_scope_function.size,
        source_pvc=data_volume_multi_storage_scope_function.name,
        storage_class=data_volume_multi_storage_scope_function.storage_class,
    ) as cdv:
        cdv.wait_for_dv_success(timeout=TIMEOUT_10MIN)
        with create_vm_from_dv(dv=cdv) as vm_dv:
            restart_vm_wait_for_running_vm(vm=vm_dv, wait_for_interfaces=False)
            check_disk_count_in_vm(vm=vm_dv)


@pytest.mark.tier3
@pytest.mark.parametrize(
    ("data_volume_multi_storage_scope_function", "vm_params"),
    [
        pytest.param(
            {
                "dv_name": "dv-source",
                "source": "http",
                "image": f"{Images.Windows.DIR}/{Images.Windows.WIN11_IMG}",
                "dv_size": Images.Windows.DEFAULT_DV_SIZE,
            },
            {
                "vm_name": f"vm-win-{WINDOWS_11.get('os_version')}",
                "template_labels": WINDOWS_11_TEMPLATE_LABELS,
                "os_version": WINDOWS_11.get("os_version"),
                "ssh": True,
            },
            marks=pytest.mark.polarion("CNV-3638"),
        ),
    ],
    indirect=["data_volume_multi_storage_scope_function"],
)
def test_successful_vm_from_cloned_dv_windows(
    unprivileged_client,
    data_volume_multi_storage_scope_function,
    vm_params,
    namespace,
):
    with create_dv(
        source="pvc",
        dv_name="dv-target",
        namespace=data_volume_multi_storage_scope_function.namespace,
        size=data_volume_multi_storage_scope_function.size,
        source_pvc=data_volume_multi_storage_scope_function.name,
        storage_class=data_volume_multi_storage_scope_function.storage_class,
    ) as cdv:
        cdv.wait_for_dv_success(timeout=WINDOWS_CLONE_TIMEOUT)
        create_windows_vm_validate_guest_agent_info(
            dv=cdv,
            namespace=namespace,
            unprivileged_client=unprivileged_client,
            vm_params=vm_params,
        )


@pytest.mark.sno
@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_function",
    [
        pytest.param(
            {
                "dv_name": "dv-source",
                "image": f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}",
                "dv_size": Images.Cirros.DEFAULT_DV_SIZE,
            },
            marks=(pytest.mark.polarion("CNV-4035")),
        )
    ],
    indirect=True,
)
def test_disk_image_after_clone(
    skip_block_volumemode_scope_function,
    unprivileged_client,
    namespace,
    data_volume_multi_storage_scope_function,
    cluster_csi_drivers_names,
):
    storage_class = data_volume_multi_storage_scope_function.storage_class
    with create_dv(
        source="pvc",
        dv_name="dv-cnv-4035",
        namespace=namespace.name,
        size=data_volume_multi_storage_scope_function.size,
        source_pvc=data_volume_multi_storage_scope_function.name,
        client=unprivileged_client,
        storage_class=storage_class,
    ) as cdv:
        cdv.wait_for_dv_success()
        create_vm_and_verify_image_permission(dv=cdv)
        assert_use_populator(
            pvc=cdv.pvc,
            storage_class=storage_class,
            cluster_csi_drivers_names=cluster_csi_drivers_names,
        )


@pytest.mark.parametrize(
    "data_volume_snapshot_capable_storage_scope_function",
    [
        pytest.param(
            {
                "dv_name": "dv-source-cirros",
                "image": f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}",
                "dv_size": Images.Cirros.DEFAULT_DV_SIZE,
            },
            marks=(pytest.mark.polarion("CNV-3545"), pytest.mark.gating()),
        ),
        pytest.param(
            {
                "dv_name": "dv-source-win",
                "image": f"{Images.Windows.DIR}/{Images.Windows.WIN11_IMG}",
                "dv_size": Images.Windows.DEFAULT_DV_SIZE,
            },
            marks=(pytest.mark.polarion("CNV-3552"), pytest.mark.tier3()),
        ),
    ],
    indirect=True,
)
def test_successful_snapshot_clone(
    data_volume_snapshot_capable_storage_scope_function,
    cluster_csi_drivers_names,
):
    namespace = data_volume_snapshot_capable_storage_scope_function.namespace
    storage_class = data_volume_snapshot_capable_storage_scope_function.storage_class
    with create_dv(
        source="pvc",
        dv_name="dv-target",
        namespace=namespace,
        size=data_volume_snapshot_capable_storage_scope_function.size,
        source_pvc=data_volume_snapshot_capable_storage_scope_function.name,
        storage_class=storage_class,
    ) as cdv:
        cdv.wait_for_dv_success()
        if OS_FLAVOR_WINDOWS not in data_volume_snapshot_capable_storage_scope_function.url.split("/")[-1]:
            with create_vm_from_dv(dv=cdv) as vm_dv:
                check_disk_count_in_vm(vm=vm_dv)
        pvc = cdv.pvc
        assert_use_populator(
            pvc=pvc,
            storage_class=storage_class,
            cluster_csi_drivers_names=cluster_csi_drivers_names,
        )
        assert_pvc_snapshot_clone_annotation(pvc=pvc, storage_class=storage_class)


@pytest.mark.gating
@pytest.mark.polarion("CNV-5607")
def test_clone_from_fs_to_block_using_dv_template(
    skip_test_if_no_filesystem_sc,
    skip_test_if_no_block_sc,
    unprivileged_client,
    namespace,
    cirros_dv_with_filesystem_volume_mode,
    storage_class_with_block_volume_mode,
):
    create_vm_from_clone_dv_template(
        vm_name="vm-5607",
        dv_name="dv-5607",
        namespace_name=namespace.name,
        source_dv=cirros_dv_with_filesystem_volume_mode,
        client=unprivileged_client,
        volume_mode=DataVolume.VolumeMode.BLOCK,
        storage_class=storage_class_with_block_volume_mode,
    )


@pytest.mark.polarion("CNV-5608")
@pytest.mark.smoke()
@pytest.mark.s390x
def test_clone_from_block_to_fs_using_dv_template(
    skip_test_if_no_filesystem_sc,
    skip_test_if_no_block_sc,
    unprivileged_client,
    namespace,
    cirros_dv_with_block_volume_mode,
    storage_class_with_filesystem_volume_mode,
    default_fs_overhead,
):
    create_vm_from_clone_dv_template(
        vm_name="vm-5608",
        dv_name="dv-5608",
        namespace_name=namespace.name,
        source_dv=cirros_dv_with_block_volume_mode,
        client=unprivileged_client,
        volume_mode=DataVolume.VolumeMode.FILE,
        # add fs overhead and round up the result
        size=overhead_size_for_dv(
            image_size=int(cirros_dv_with_block_volume_mode.size[:-2]),
            overhead_value=default_fs_overhead,
        ),
        storage_class=storage_class_with_filesystem_volume_mode,
    )

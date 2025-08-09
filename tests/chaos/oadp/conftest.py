import logging

import pytest

from utilities.oadp import FILE_NAME_FOR_BACKUP, TEXT_TO_TEST, create_rhel_vm, is_storage_class_support_volume_mode
from utilities.storage import write_file

LOGGER = logging.getLogger(__name__)


@pytest.fixture()
def vm_with_datavolume_template(
    request,
    chaos_namespace,
    snapshot_storage_class_name_scope_module,
):
    volume_mode = request.param.get("volume_mode")
    if not is_storage_class_support_volume_mode(
        storage_class_name=snapshot_storage_class_name_scope_module,
        requested_volume_mode=volume_mode,
    ):
        pytest.skip(
            f"Storage class: {snapshot_storage_class_name_scope_module} don't support volume mode: {volume_mode}"
        )

    vm_name = request.param.get("vm_name")
    dv_name = f"dv-{vm_name}"

    with create_rhel_vm(
        storage_class=snapshot_storage_class_name_scope_module,
        namespace=chaos_namespace.name,
        vm_name=vm_name,
        dv_name=dv_name,
        wait_running=True,
        volume_mode=volume_mode,
        rhel_image=request.param.get("rhel_image"),
    ) as vm:
        write_file(
            vm=vm,
            filename=FILE_NAME_FOR_BACKUP,
            content=TEXT_TO_TEST,
            stop_vm=False,
        )
        yield vm

"""
General storage behavior tests
"""

import logging

import pytest

from tests.storage.cdi_import.utils import wait_for_pvc_recreate
from utilities import console
from utilities.constants import (
    OS_FLAVOR_FEDORA,
    TIMEOUT_1MIN,
    TIMEOUT_5MIN,
    Images,
)
from utilities.storage import (
    create_dummy_first_consumer_pod,
    create_dv,
    create_vm_from_dv,
    get_dv_size_from_datasource,
    sc_volume_binding_mode_is_wffc,
)

pytestmark = [
    pytest.mark.post_upgrade,
]

LOGGER = logging.getLogger(__name__)


@pytest.mark.sno
@pytest.mark.polarion("CNV-675")
def test_pvc_recreates_after_deletion(namespace, storage_class_name_scope_function, fedora_data_source_scope_module):
    with create_dv(
        dv_name=f"cnv-675-{storage_class_name_scope_function}",
        namespace=namespace.name,
        storage_class=storage_class_name_scope_function,
        size=get_dv_size_from_datasource(fedora_data_source_scope_module),
        client=namespace.client,
        source_ref={
            "kind": fedora_data_source_scope_module.kind,
            "name": fedora_data_source_scope_module.name,
            "namespace": fedora_data_source_scope_module.namespace,
        },
    ) as dv:
        dv.wait_for_dv_success(timeout=TIMEOUT_5MIN)
        pvc = dv.pvc
        pvc_original_timestamp = pvc.instance.metadata.creationTimestamp
        pvc.delete()
        wait_for_pvc_recreate(pvc=pvc, pvc_original_timestamp=pvc_original_timestamp)
        storage_class = storage_class_name_scope_function
        if sc_volume_binding_mode_is_wffc(sc=storage_class, client=namespace.client):
            create_dummy_first_consumer_pod(pvc=pvc)
        dv.wait_for_dv_success()


@pytest.mark.polarion("CNV-3065")
@pytest.mark.sno
def test_disk_falloc(
    storage_class_name_scope_function, unprivileged_client, fedora_data_source_scope_module, namespace
):
    size = get_dv_size_from_datasource(data_source=fedora_data_source_scope_module)
    with create_dv(
        client=unprivileged_client,
        dv_name=f"cnv-3065-{storage_class_name_scope_function}",
        namespace=namespace.name,
        source_ref={
            "kind": fedora_data_source_scope_module.kind,
            "name": fedora_data_source_scope_module.name,
            "namespace": fedora_data_source_scope_module.namespace,
        },
        size=size,
        storage_class=storage_class_name_scope_function,
    ) as dv:
        dv.wait_for_dv_success(timeout=TIMEOUT_5MIN)
        with (
            (
                create_vm_from_dv(
                    vm_name="cnv-3065-vm",
                    client=unprivileged_client,
                    dv=dv,
                    os_flavor=OS_FLAVOR_FEDORA,
                    memory_guest=Images.Fedora.DEFAULT_MEMORY_SIZE,
                )
            ) as vm_dv,
            console.Console(vm=vm_dv) as vm_console,
        ):
            LOGGER.info(f"Fill disk space with size {size}")
            vm_console.sendline(f"fallocate -l {size} test-file")
            vm_console.expect("No space left on device", timeout=TIMEOUT_1MIN)

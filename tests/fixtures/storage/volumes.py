import logging

import pytest

from utilities.storage import data_volume
from utilities.virt import vm_instance_from_template

LOGGER = logging.getLogger(__name__)


@pytest.fixture()
def data_volume_multi_storage_scope_function(
    request,
    namespace,
    storage_class_matrix__function__,
):
    yield from data_volume(
        request=request,
        namespace=namespace,
        storage_class_matrix=storage_class_matrix__function__,
        client=namespace.client,
    )


@pytest.fixture(scope="module")
def data_volume_multi_storage_scope_module(
    request,
    namespace,
    storage_class_matrix__module__,
):
    yield from data_volume(
        request=request,
        namespace=namespace,
        storage_class_matrix=storage_class_matrix__module__,
        client=namespace.client,
    )


@pytest.fixture()
def data_volume_scope_function(request, namespace):
    yield from data_volume(
        request=request,
        namespace=namespace,
        storage_class=request.param["storage_class"],
        client=namespace.client,
    )


@pytest.fixture(scope="class")
def data_volume_scope_class(request, namespace):
    yield from data_volume(
        request=request,
        namespace=namespace,
        storage_class=request.param["storage_class"],
        client=namespace.client,
    )


@pytest.fixture()
def vm_instance_from_template_multi_storage_scope_function(
    request,
    unprivileged_client,
    namespace,
    data_volume_multi_storage_scope_function,
    cpu_for_migration,
):
    """Calls vm_instance_from_template contextmanager

    Creates a VM from template and starts it (if requested).
    """

    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        existing_data_volume=data_volume_multi_storage_scope_function,
        vm_cpu_model=(cpu_for_migration if request.param.get("set_vm_common_cpu") else None),
    ) as vm:
        yield vm

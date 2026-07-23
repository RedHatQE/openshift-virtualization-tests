import logging

import pytest

from utilities.storage import data_volume

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

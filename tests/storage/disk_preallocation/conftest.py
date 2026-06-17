"""Pytest conftest file for CDI disk preallocation tests."""

import pytest
from ocp_resources.cdi import CDI

from tests.storage.constants import QUAY_FEDORA_CONTAINER_IMAGE
from tests.storage.disk_preallocation.utils import wait_for_cdi_preallocation_enabled
from utilities.constants import REGISTRY_STR, Images
from utilities.hco import (
    ResourceEditorValidateHCOReconcile,
    hco_cr_jsonpatch_annotations_dict,
)
from utilities.storage import create_dv


@pytest.fixture(scope="module")
def cdi_preallocation_enabled(hyperconverged_resource_scope_module, cdi_config):
    preallocation_value = True
    with ResourceEditorValidateHCOReconcile(
        patches={
            hyperconverged_resource_scope_module: hco_cr_jsonpatch_annotations_dict(
                component="cdi",
                path="preallocation",
                value=preallocation_value,
            )
        },
        list_resource_reconcile=[CDI],
    ):
        wait_for_cdi_preallocation_enabled(cdi_config=cdi_config, expected_value=preallocation_value)
        yield


@pytest.fixture()
def registry_dv_with_preallocation(namespace, storage_class_name_scope_function):
    with create_dv(
        dv_name=f"cnv-5512-{storage_class_name_scope_function}",
        namespace=namespace.name,
        source=REGISTRY_STR,
        url=QUAY_FEDORA_CONTAINER_IMAGE,
        size=Images.Fedora.DEFAULT_DV_SIZE,
        storage_class=storage_class_name_scope_function,
        client=namespace.client,
        preallocation=True,
    ) as dv:
        dv.wait_for_dv_success()
        yield dv


@pytest.fixture(scope="module")
def registry_dv_no_preallocation_spec(namespace, storage_class_name_scope_module):
    with create_dv(
        dv_name=f"cnv-5513-{storage_class_name_scope_module}",
        namespace=namespace.name,
        source=REGISTRY_STR,
        url=QUAY_FEDORA_CONTAINER_IMAGE,
        size=Images.Fedora.DEFAULT_DV_SIZE,
        storage_class=storage_class_name_scope_module,
        client=namespace.client,
    ) as dv:
        dv.wait_for_dv_success()
        yield dv


@pytest.fixture()
def registry_dv_with_preallocation_false(namespace, storage_class_name_scope_function):
    with create_dv(
        dv_name=f"cnv-5741-{storage_class_name_scope_function}",
        namespace=namespace.name,
        source=REGISTRY_STR,
        url=QUAY_FEDORA_CONTAINER_IMAGE,
        size=Images.Fedora.DEFAULT_DV_SIZE,
        storage_class=storage_class_name_scope_function,
        client=namespace.client,
        preallocation=False,
    ) as dv:
        dv.wait_for_dv_success()
        yield dv


@pytest.fixture()
def blank_dv_with_preallocation(namespace, storage_class_name_scope_function):
    with create_dv(
        dv_name=f"cnv-5737-{storage_class_name_scope_function}",
        namespace=namespace.name,
        source="blank",
        size="100Mi",
        storage_class=storage_class_name_scope_function,
        client=namespace.client,
        preallocation=True,
    ) as dv:
        dv.wait_for_dv_success()
        yield dv

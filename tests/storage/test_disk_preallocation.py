# -*- coding: utf-8 -*-

"""
CDI disk preallocation test suite
"""

import logging

import pytest
from ocp_resources.cdi import CDI
from ocp_resources.resource import NamespacedResource
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.os_params import RHEL_LATEST
from utilities.constants import TIMEOUT_2MIN, Images
from utilities.hco import (
    ResourceEditorValidateHCOReconcile,
    hco_cr_jsonpatch_annotations_dict,
)

pytestmark = pytest.mark.post_upgrade


LOGGER = logging.getLogger(__name__)


def assert_preallocation_requested_annotation(pvc, status):
    preallocation_requested_annotation = (
        f"{NamespacedResource.ApiGroup.CDI_KUBEVIRT_IO}/storage.preallocation.requested"
    )
    assert pvc.instance.metadata.annotations.get(preallocation_requested_annotation) == status, (
        f"'{preallocation_requested_annotation}' should be '{status}'"
    )


def assert_preallocation_annotation(pvc, res):
    preallocation_annotation = f"{NamespacedResource.ApiGroup.CDI_KUBEVIRT_IO}/storage.preallocation"
    assert pvc.instance.metadata.annotations.get(preallocation_annotation) == res, (
        f"'{preallocation_annotation}' should be '{res}'"
    )


def wait_for_cdi_preallocation_enabled(cdi_config, expected_value):
    preallocation_status = ""
    try:
        for preallocation_status in TimeoutSampler(
            wait_timeout=TIMEOUT_2MIN,
            sleep=1,
            func=lambda: cdi_config.instance.status.preallocation,
        ):
            if preallocation_status == expected_value:
                return
    except TimeoutExpiredError:
        LOGGER.error(
            f"CDIconfig status.preallocation is '{preallocation_status}', but expected to be '{expected_value}'"
        )
        raise


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


@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_function",
    [
        pytest.param(
            {
                "dv_name": "cnv-5512",
                "image": RHEL_LATEST["image_path"],
                "dv_size": Images.Rhel.DEFAULT_DV_SIZE,
                "preallocation": True,
            },
            marks=(
                pytest.mark.polarion("CNV-5512"),
                pytest.mark.gating(),
                pytest.mark.sno(),
            ),
        ),
    ],
    indirect=True,
)
@pytest.mark.s390x
def test_preallocation_dv(
    data_volume_multi_storage_scope_function,
):
    """
    Test that preallocation of the kubevirt disk is enabled via an API in the DataVolume spec
    """
    pvc = data_volume_multi_storage_scope_function.pvc
    assert_preallocation_requested_annotation(pvc=pvc, status="true")
    assert_preallocation_annotation(pvc=pvc, res="true")


@pytest.mark.sno
@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_module",
    [
        pytest.param(
            {
                "dv_name": "cnv-5513",
                "source": "http",
                "image": f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}",
                "dv_size": "100Mi",
            },
            marks=pytest.mark.polarion("CNV-5513"),
        ),
    ],
    indirect=True,
)
def test_preallocation_globally_dv_spec_without_preallocation(
    cdi_preallocation_enabled,
    data_volume_multi_storage_scope_module,
):
    """
    Test that preallocation can be also turned on for all DataVolumes with the CDI CR entry.
    When create a general DataVolume without preallocation on DataVolume's spec, CDI would look into CDI CR.
    """
    pvc = data_volume_multi_storage_scope_module.pvc
    assert_preallocation_requested_annotation(pvc=pvc, status="true")


@pytest.mark.sno
@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_function",
    [
        pytest.param(
            {
                "dv_name": "cnv-5741",
                "source": "http",
                "image": f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}",
                "dv_size": "200Mi",
                "preallocation": False,
            },
            marks=pytest.mark.polarion("CNV-5741"),
        ),
    ],
    indirect=True,
)
def test_preallocation_globally_dv_spec_with_preallocation_false(
    cdi_preallocation_enabled,
    data_volume_multi_storage_scope_function,
):
    """
    When create a general DataVolume with preallocation set false on DataVolume's spec, preallocation will not be used.
    It won't take CDI CR into account because it is explicit in the DV.
    """
    pvc = data_volume_multi_storage_scope_function.pvc
    assert_preallocation_requested_annotation(pvc=pvc, status="false")


@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_function",
    [
        pytest.param(
            {
                "dv_name": "cnv-5737",
                "source": "blank",
                "dv_size": "100Mi",
                "preallocation": True,
            },
            marks=(
                pytest.mark.polarion("CNV-5737"),
                pytest.mark.gating(),
                pytest.mark.sno(),
            ),
        ),
    ],
    indirect=True,
)
@pytest.mark.s390x
def test_preallocation_for_blank_dv(
    data_volume_multi_storage_scope_function,
):
    """
    Test that preallocation for blank disk should be supported
    """
    pvc = data_volume_multi_storage_scope_function.pvc
    assert_preallocation_requested_annotation(pvc=pvc, status="true")
    assert_preallocation_annotation(pvc=pvc, res="true")

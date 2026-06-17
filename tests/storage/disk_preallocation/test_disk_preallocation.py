import pytest

from tests.storage.disk_preallocation.utils import (
    assert_preallocation_annotation,
    assert_preallocation_requested_annotation,
)

pytestmark = pytest.mark.post_upgrade


@pytest.mark.polarion("CNV-5512")
@pytest.mark.gating
@pytest.mark.sno
@pytest.mark.s390x
def test_preallocation_dv(registry_dv_with_preallocation):
    """
    Test that preallocation of the kubevirt disk is enabled via an API in the DataVolume spec
    """
    pvc = registry_dv_with_preallocation.pvc
    assert_preallocation_requested_annotation(pvc=pvc, status="true")
    assert_preallocation_annotation(pvc=pvc, res="true")


@pytest.mark.polarion("CNV-5513")
@pytest.mark.sno
@pytest.mark.usefixtures("cdi_preallocation_enabled")
def test_preallocation_globally_dv_spec_without_preallocation(
    registry_dv_no_preallocation_spec,
):
    """
    Test that preallocation can be also turned on for all DataVolumes with the CDI CR entry.
    When create a general DataVolume without preallocation on DataVolume's spec, CDI would look into CDI CR.
    """
    pvc = registry_dv_no_preallocation_spec.pvc
    assert_preallocation_requested_annotation(pvc=pvc, status="true")


@pytest.mark.polarion("CNV-5741")
@pytest.mark.sno
@pytest.mark.usefixtures("cdi_preallocation_enabled")
def test_preallocation_globally_dv_spec_with_preallocation_false(
    registry_dv_with_preallocation_false,
):
    """
    When create a general DataVolume with preallocation set false on DataVolume's spec, preallocation will not be used.
    It won't take CDI CR into account because it is explicit in the DV.
    """
    pvc = registry_dv_with_preallocation_false.pvc
    assert_preallocation_requested_annotation(pvc=pvc, status="false")


@pytest.mark.polarion("CNV-5737")
@pytest.mark.gating
@pytest.mark.sno
@pytest.mark.s390x
def test_preallocation_for_blank_dv(blank_dv_with_preallocation):
    """
    Test that preallocation for blank disk should be supported
    """
    pvc = blank_dv_with_preallocation.pvc
    assert_preallocation_requested_annotation(pvc=pvc, status="true")
    assert_preallocation_annotation(pvc=pvc, res="true")

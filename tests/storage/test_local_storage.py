# -*- coding: utf-8 -*-

"""
Test local storage
"""

import pytest
from ocp_resources.persistent_volume import PersistentVolume
from ocp_resources.storage_class import StorageClass
from ocp_resources.storage_profile import StorageProfile

PV_LABEL_PREFIX = "storage.openshift.com/local-volume-owner-name"
SC_LABEL_PREFIX = "local.storage.openshift.io/owner-name"
LOCAL_BLOCK_HPP = "local-block-hpp"
LOCAL_BLOCK_OCS = "local-block-ocs"


@pytest.fixture()
def skip_if_no_local_storage_class(local_storage_class):
    if not local_storage_class:
        pytest.skip("No local storage class exists")


@pytest.fixture()
def local_storage_pv_spec(request, admin_client):
    for local_sc_pv in PersistentVolume.get(dyn_client=admin_client, label_selector=request.param["pv_label"]):
        return local_sc_pv.instance.spec


@pytest.fixture()
def local_storage_class(request, admin_client):
    for local_sc in StorageClass.get(dyn_client=admin_client, label_selector=request.param["sc_label"]):
        return local_sc


@pytest.fixture()
def local_storage_profile_claim_property_sets(local_storage_class):
    return StorageProfile(name=local_storage_class.name).instance.status["claimPropertySets"][0]


@pytest.mark.parametrize(
    "local_storage_class, local_storage_pv_spec",
    [
        pytest.param(
            {"sc_label": f"{SC_LABEL_PREFIX}={LOCAL_BLOCK_HPP}"},
            {"pv_label": f"{PV_LABEL_PREFIX}={LOCAL_BLOCK_HPP}"},
            marks=pytest.mark.polarion("CNV-8543"),
            id="local_block_hpp",
        ),
        pytest.param(
            {"sc_label": f"{SC_LABEL_PREFIX}={LOCAL_BLOCK_OCS}"},
            {"pv_label": f"{PV_LABEL_PREFIX}={LOCAL_BLOCK_OCS}"},
            marks=pytest.mark.polarion("CNV-8542"),
            id="local_block_ocs",
        ),
    ],
    indirect=True,
)
@pytest.mark.s390x
def test_local_storage_profile_claim_property_sets(
    skip_if_no_local_storage_class,
    local_storage_class,
    local_storage_pv_spec,
    local_storage_profile_claim_property_sets,
):
    access_mode = local_storage_pv_spec.accessModes[0]
    volume_mode = local_storage_pv_spec.volumeMode
    assert local_storage_profile_claim_property_sets["accessModes"][0] == access_mode, (
        f"accessModes is not {access_mode} in storage class {local_storage_class.name}"
    )
    assert local_storage_profile_claim_property_sets["volumeMode"] == volume_mode, (
        f"volumeMode is not {volume_mode} in storage class {local_storage_class.name}"
    )

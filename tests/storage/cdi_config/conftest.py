# -*- coding: utf-8 -*-

"""
Pytest conftest file for CNV CDI Config tests
"""

import pytest
from ocp_resources.cdi import CDI

from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.storage import cdi_feature_gate_list_with_added_feature


@pytest.fixture()
def cdi_with_extra_non_existent_feature_gate(cdi):
    with ResourceEditorValidateHCOReconcile(
        patches={
            cdi: {
                "spec": {
                    "config": {
                        "featureGates": cdi_feature_gate_list_with_added_feature(feature="ExtraNonExistentFeature")
                    }
                },
            },
        },
        list_resource_reconcile=[CDI],
        wait_for_reconcile_post_update=True,
    ):
        yield cdi


@pytest.fixture()
def initial_cdi_config_from_cr(cdi):
    return cdi.instance.to_dict()["spec"]["config"]

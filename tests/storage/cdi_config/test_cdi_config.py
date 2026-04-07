# -*- coding: utf-8 -*-

"""CDIConfig tests"""

import pytest
from ocp_resources.cdi import CDI
from ocp_resources.route import Route
from timeout_sampler import TimeoutSampler

from tests.storage.cdi_config.utils import (
    INSECURE_REGISTRIES_LIST,
    NON_EXISTENT_SCRATCH_SC_DICT,
    STORAGE_WORKLOADS_DICT,
)
from tests.storage.utils import LOGGER
from utilities.constants import CDI_UPLOADPROXY
from utilities.hco import ResourceEditorValidateHCOReconcile

pytestmark = pytest.mark.post_upgrade


@pytest.mark.sno
@pytest.mark.gating
@pytest.mark.polarion("CNV-2208")
@pytest.mark.s390x
def test_cdi_config_exists(cdi_config, upload_proxy_route):
    assert cdi_config.upload_proxy_url == upload_proxy_route.host


@pytest.mark.destructive
@pytest.mark.polarion("CNV-2209")
def test_different_route_for_upload_proxy(hco_namespace, cdi_config, uploadproxy_route_deleted):
    with Route(
        namespace=hco_namespace.name,
        name="new-route-uploadproxy",
        service=CDI_UPLOADPROXY,
    ) as new_route:
        cdi_config.wait_until_upload_url_changed(uploadproxy_url=new_route.host)


@pytest.mark.sno
@pytest.mark.polarion("CNV-2215")
@pytest.mark.s390x
def test_route_for_different_service(admin_client, cdi_config, upload_proxy_route):
    with Route(
        namespace=upload_proxy_route.namespace, name="cdi-api", service="cdi-api", client=admin_client
    ) as cdi_api_route:
        assert cdi_config.upload_proxy_url != cdi_api_route.host
        assert cdi_config.upload_proxy_url == upload_proxy_route.host


@pytest.mark.sno
@pytest.mark.polarion("CNV-2216")
@pytest.mark.s390x
def test_upload_proxy_url_overridden(admin_client, cdi_config, namespace, cdi_config_upload_proxy_overridden):
    with Route(namespace=namespace.name, name="my-route", service=CDI_UPLOADPROXY, client=admin_client) as new_route:
        assert cdi_config.upload_proxy_url != new_route.host


@pytest.mark.sno
@pytest.mark.polarion("CNV-6312")
@pytest.mark.s390x
def test_cdi_spec_reconciled_by_hco(initial_cdi_config_from_cr, updated_cdi_extra_non_existent_feature_gate):
    """
    Test that added feature gate on the CDI CR does not persist
    (HCO Should reconcile back changes on the CDI CR)
    """
    assert (
        updated_cdi_extra_non_existent_feature_gate.instance.to_dict()["spec"]["config"] == initial_cdi_config_from_cr
    ), "HCO should have reconciled back changes"


@pytest.mark.sno
@pytest.mark.parametrize(
    ("hco_updated_spec_stanza", "expected_in_cdi_config_from_cr"),
    [
        pytest.param(
            {"resourceRequirements": {"storageWorkloads": STORAGE_WORKLOADS_DICT}},
            {"podResourceRequirements": STORAGE_WORKLOADS_DICT},
            marks=(pytest.mark.polarion("CNV-6000")),
            id="test_storage_workloads_in_hco_propagated_to_cdi_cr",
        ),
        pytest.param(
            NON_EXISTENT_SCRATCH_SC_DICT,
            NON_EXISTENT_SCRATCH_SC_DICT,
            marks=(pytest.mark.polarion("CNV-6001")),
            id="test_scratch_sc_in_hco_propagated_to_cdi_cr",
        ),
        pytest.param(
            {"storageImport": {"insecureRegistries": INSECURE_REGISTRIES_LIST}},
            {"insecureRegistries": INSECURE_REGISTRIES_LIST},
            marks=(pytest.mark.polarion("CNV-6092")),
            id="test_insecure_registries_in_hco_propagated_to_cdi_cr",
        ),
    ],
)
@pytest.mark.s390x
def test_cdi_tunables_in_hco_propagated_to_cr(
    hyperconverged_resource_scope_module,
    cdi,
    namespace,
    expected_in_cdi_config_from_cr,
    hco_updated_spec_stanza,
):
    """
    Test that the exposed CDI-related tunables in HCO are propagated to the CDI CR
    """
    initial_cdi_config_from_cr = cdi.instance.to_dict()["spec"]["config"]

    def _verify_propagation():
        current_cdi_config_from_cr = cdi.instance.to_dict()["spec"]["config"]
        return {
            **initial_cdi_config_from_cr,
            **expected_in_cdi_config_from_cr,
        } == current_cdi_config_from_cr

    samples = TimeoutSampler(
        wait_timeout=20,
        sleep=1,
        func=_verify_propagation,
    )

    with ResourceEditorValidateHCOReconcile(
        patches={hyperconverged_resource_scope_module: {"spec": hco_updated_spec_stanza}},
        list_resource_reconcile=[CDI],
    ):
        for sample in samples:
            if sample:
                break

    LOGGER.info("Check values revert back to original")
    for sample in samples:
        if not sample:
            break

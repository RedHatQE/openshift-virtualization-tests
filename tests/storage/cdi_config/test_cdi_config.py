# -*- coding: utf-8 -*-

"""CDIConfig tests"""

import pytest
from ocp_resources.cdi import CDI
from ocp_resources.config_map import ConfigMap
from ocp_resources.route import Route
from timeout_sampler import TimeoutSampler

from tests.storage.cdi_config.utils import (
    INSECURE_REGISTRIES_LIST,
    NON_EXISTENT_SCRATCH_SC_DICT,
    STORAGE_WORKLOADS_DICT,
    cdiconfig_update,
)
from tests.storage.utils import LOGGER, get_file_url_https_server
from utilities.artifactory import get_test_artifact_server_url
from utilities.constants import CDI_UPLOADPROXY, Images, StorageClassNames
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.storage import (
    create_dv,
    create_vm_from_dv,
    update_default_sc,
    wait_for_default_sc_in_cdiconfig,
)

pytestmark = pytest.mark.post_upgrade


@pytest.mark.sno
@pytest.mark.polarion("CNV-2451")
@pytest.mark.s390x
def test_cdiconfig_scratchspace_fs_upload_to_block(
    available_hpp_storage_class,
    tmpdir,
    hyperconverged_resource_scope_module,
    cdi_config,
    namespace,
    unprivileged_client,
    https_server_certificate,
):
    cdiconfig_update(
        source="upload",
        hco_cr=hyperconverged_resource_scope_module,
        cdiconfig=cdi_config,
        dv_name="cnv-2451",
        storage_class_type=available_hpp_storage_class.name,
        images_https_server_name=get_test_artifact_server_url(schema="https"),
        storage_ns_name=namespace.name,
        run_vm=True,
        tmpdir=tmpdir,
        client=unprivileged_client,
        https_server_certificate=https_server_certificate,
    )


@pytest.mark.sno
@pytest.mark.polarion("CNV-2478")
@pytest.mark.s390x
def test_cdiconfig_scratchspace_fs_import_to_block(
    available_hpp_storage_class,
    hyperconverged_resource_scope_module,
    cdi_config,
    namespace,
    unprivileged_client,
    https_server_certificate,
):
    cdiconfig_update(
        source="http",
        hco_cr=hyperconverged_resource_scope_module,
        cdiconfig=cdi_config,
        dv_name="cnv-2478",
        storage_class_type=available_hpp_storage_class.name,
        storage_ns_name=namespace.name,
        images_https_server_name=get_test_artifact_server_url(schema="https"),
        run_vm=True,
        client=unprivileged_client,
        https_server_certificate=https_server_certificate,
    )


@pytest.mark.sno
@pytest.mark.polarion("CNV-2214")
@pytest.mark.s390x
def test_cdiconfig_status_scratchspace_update_with_spec(
    available_hpp_storage_class,
    hyperconverged_resource_scope_module,
    cdi_config,
    namespace,
    unprivileged_client,
    https_server_certificate,
):
    cdiconfig_update(
        source="http",
        hco_cr=hyperconverged_resource_scope_module,
        cdiconfig=cdi_config,
        dv_name="cnv-2214",
        storage_class_type=available_hpp_storage_class.name,
        storage_ns_name=namespace.name,
        client=unprivileged_client,
        https_server_certificate=https_server_certificate,
    )


@pytest.mark.sno
@pytest.mark.polarion("CNV-2440")
@pytest.mark.s390x
def test_cdiconfig_scratch_space_not_default(
    available_hpp_storage_class,
    hyperconverged_resource_scope_module,
    cdi_config,
    namespace,
    unprivileged_client,
    https_server_certificate,
):
    cdiconfig_update(
        source="http",
        hco_cr=hyperconverged_resource_scope_module,
        cdiconfig=cdi_config,
        dv_name="cnv-2440",
        storage_class_type=available_hpp_storage_class.name,
        images_https_server_name=get_test_artifact_server_url(schema="https"),
        storage_ns_name=namespace.name,
        run_vm=True,
        client=unprivileged_client,
        https_server_certificate=https_server_certificate,
    )


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
@pytest.mark.polarion("CNV-2441")
@pytest.mark.s390x
def test_cdiconfig_changing_storage_class_default(
    unprivileged_client,
    skip_test_if_no_ocs_sc,
    available_hpp_storage_class,
    namespace,
    default_sc_as_fallback_for_scratch,
    cdi_config,
    https_server_certificate,
):
    with update_default_sc(default=False, storage_class=default_sc_as_fallback_for_scratch):
        with update_default_sc(default=True, storage_class=available_hpp_storage_class):
            url = get_file_url_https_server(
                images_https_server=get_test_artifact_server_url(schema="https"),
                file_name=Images.Cirros.QCOW2_IMG,
            )
            with ConfigMap(
                client=unprivileged_client,
                name="https-cert-configmap",
                namespace=namespace.name,
                data={"tlsregistry.crt": https_server_certificate},
            ) as configmap:
                with create_dv(
                    client=unprivileged_client,
                    source="http",
                    dv_name="import-cdiconfig-scratch-space-not-default",
                    namespace=configmap.namespace,
                    url=url,
                    storage_class=StorageClassNames.CEPH_RBD_VIRTUALIZATION,
                    cert_configmap=configmap.name,
                ) as dv:
                    dv.wait_for_dv_success()
                    create_vm_from_dv(client=unprivileged_client, dv=dv)


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

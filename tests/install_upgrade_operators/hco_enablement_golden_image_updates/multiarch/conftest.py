import logging

import pytest

from tests.install_upgrade_operators.constants import MANAGED_CRS_LIST
from tests.install_upgrade_operators.hco_enablement_golden_image_updates.multiarch.utils import (
    CUSTOM_MULTIARCH_DATASOURCE_NAME,
    get_control_plane_architecture,
    get_expected_arch_specific_resource_names,
    get_no_arch_annotation_template,
    get_unsupported_arch_template,
    get_worker_node_architectures,
)
from utilities.constants import (
    FEATURE_GATES,
    KUBERNETES_ARCH_LABEL,
)
from utilities.hco import (
    ResourceEditorValidateHCOReconcile,
    apply_np_changes,
    update_hco_templates_spec,
)
from utilities.ssp import wait_for_at_least_one_auto_update_data_import_cron

LOGGER = logging.getLogger(__name__)

ENABLE_MULTI_ARCH_BOOT_IMAGE_IMPORT = "enableMultiArchBootImageImport"


@pytest.fixture(scope="class")
def disabled_multiarch_feature_gate(
    admin_client,
    hco_namespace,
    hyperconverged_resource_scope_class,
    golden_images_namespace,
):
    with ResourceEditorValidateHCOReconcile(
        patches={
            hyperconverged_resource_scope_class: {"spec": {FEATURE_GATES: {ENABLE_MULTI_ARCH_BOOT_IMAGE_IMPORT: False}}}
        },
        list_resource_reconcile=MANAGED_CRS_LIST,
        wait_for_reconcile_post_update=True,
    ):
        yield


@pytest.fixture(scope="class")
def enabled_multiarch_feature_gate(
    admin_client,
    hco_namespace,
    hyperconverged_resource_scope_class,
    golden_images_namespace,
):
    feature_gates = hyperconverged_resource_scope_class.instance.spec.get(FEATURE_GATES, {})
    if feature_gates.get(ENABLE_MULTI_ARCH_BOOT_IMAGE_IMPORT):
        yield
    else:
        with ResourceEditorValidateHCOReconcile(
            patches={
                hyperconverged_resource_scope_class: {
                    "spec": {FEATURE_GATES: {ENABLE_MULTI_ARCH_BOOT_IMAGE_IMPORT: True}}
                }
            },
            list_resource_reconcile=MANAGED_CRS_LIST,
            wait_for_reconcile_post_update=True,
        ):
            wait_for_at_least_one_auto_update_data_import_cron(
                admin_client=admin_client,
                namespace=golden_images_namespace,
            )
            yield


@pytest.fixture(scope="class")
def worker_architectures(workers):
    return get_worker_node_architectures(workers=workers)


@pytest.fixture(scope="class")
def control_plane_architecture(control_plane_nodes):
    return get_control_plane_architecture(control_plane_nodes=control_plane_nodes)


@pytest.fixture(scope="class")
def expected_arch_specific_resource_names(default_common_templates_related_resources, worker_architectures):
    return {
        kind: get_expected_arch_specific_resource_names(
            base_resource_names=names,
            architectures=worker_architectures,
        )
        for kind, names in default_common_templates_related_resources.items()
    }


@pytest.fixture()
def single_arch_node_placement(
    admin_client,
    hco_namespace,
    hyperconverged_resource_scope_function,
    workers,
):
    single_arch = sorted(get_worker_node_architectures(workers=workers))[0]
    LOGGER.info(f"Restricting nodePlacement to single architecture: {single_arch}")
    hco_spec = hyperconverged_resource_scope_function.instance.to_dict()["spec"]
    initial_infra = hco_spec.get("infra", {})
    initial_workloads = hco_spec.get("workloads", {})
    node_selector = {KUBERNETES_ARCH_LABEL: single_arch}
    placement = {"nodePlacement": {"nodeSelector": node_selector}}
    apply_np_changes(
        admin_client=admin_client,
        hco=hyperconverged_resource_scope_function,
        hco_namespace=hco_namespace,
        infra_placement=placement,
        workloads_placement=placement,
    )
    yield
    apply_np_changes(
        admin_client=admin_client,
        hco=hyperconverged_resource_scope_function,
        hco_namespace=hco_namespace,
        infra_placement=initial_infra,
        workloads_placement=initial_workloads,
    )


@pytest.fixture()
def hco_with_custom_unsupported_arch_template(
    admin_client,
    hco_namespace,
    hyperconverged_resource_scope_function,
    hyperconverged_status_templates_scope_function,
    golden_images_namespace,
):
    yield from update_hco_templates_spec(
        admin_client=admin_client,
        hco_namespace=hco_namespace,
        hyperconverged_resource=hyperconverged_resource_scope_function,
        updated_template=get_unsupported_arch_template(
            common_templates=hyperconverged_status_templates_scope_function,
        ),
        custom_datasource_name=CUSTOM_MULTIARCH_DATASOURCE_NAME,
        golden_images_namespace=golden_images_namespace,
    )


@pytest.fixture()
def hco_with_custom_no_arch_annotation_template(
    admin_client,
    hco_namespace,
    hyperconverged_resource_scope_function,
    hyperconverged_status_templates_scope_function,
    golden_images_namespace,
):
    yield from update_hco_templates_spec(
        admin_client=admin_client,
        hco_namespace=hco_namespace,
        hyperconverged_resource=hyperconverged_resource_scope_function,
        updated_template=get_no_arch_annotation_template(
            common_templates=hyperconverged_status_templates_scope_function,
        ),
        custom_datasource_name=CUSTOM_MULTIARCH_DATASOURCE_NAME,
        golden_images_namespace=golden_images_namespace,
    )

import logging

import pytest
from ocp_resources.cdi import CDI
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.network_addons_config import NetworkAddonsConfig
from ocp_resources.ssp import SSP

from tests.install_upgrade_operators.constants import ENABLE_MULTI_ARCH_BOOT_IMAGE_IMPORT
from tests.install_upgrade_operators.hco_enablement_golden_image_updates.multiarch.utils import (
    CUSTOM_MULTIARCH_DATASOURCE_NAME,
    get_control_plane_architecture,
    get_no_arch_annotation_template,
    get_unsupported_arch_template,
)
from utilities.constants.cluster import KUBERNETES_ARCH_LABEL
from utilities.constants.hco import FEATURE_GATES
from utilities.hco import (
    ResourceEditorValidateHCOReconcile,
    update_hco_templates_spec,
)
from utilities.storage import verify_boot_sources_reimported

LOGGER = logging.getLogger(__name__)

_MULTIARCH_MANAGED_CRS = [SSP, KubeVirt, CDI]


@pytest.fixture(scope="class")
def disabled_multiarch_feature_gate(admin_client, golden_images_namespace, hyperconverged_resource_scope_class):
    with ResourceEditorValidateHCOReconcile(
        patches={
            hyperconverged_resource_scope_class: {"spec": {FEATURE_GATES: {ENABLE_MULTI_ARCH_BOOT_IMAGE_IMPORT: False}}}
        },
        list_resource_reconcile=_MULTIARCH_MANAGED_CRS,
        wait_for_reconcile_post_update=True,
    ):
        yield
    verify_boot_sources_reimported(admin_client=admin_client, namespace=golden_images_namespace.name)


@pytest.fixture(scope="class")
def enabled_multiarch_feature_gate(admin_client, golden_images_namespace, hyperconverged_resource_scope_class):
    feature_gates = hyperconverged_resource_scope_class.instance.spec.get(FEATURE_GATES, {})
    if feature_gates.get(ENABLE_MULTI_ARCH_BOOT_IMAGE_IMPORT):
        LOGGER.warning("Multiarch feature gate is already enabled")
        yield
    else:
        with ResourceEditorValidateHCOReconcile(
            patches={
                hyperconverged_resource_scope_class: {
                    "spec": {FEATURE_GATES: {ENABLE_MULTI_ARCH_BOOT_IMAGE_IMPORT: True}}
                }
            },
            list_resource_reconcile=_MULTIARCH_MANAGED_CRS,
            wait_for_reconcile_post_update=True,
        ):
            yield
        verify_boot_sources_reimported(admin_client=admin_client, namespace=golden_images_namespace.name)


@pytest.fixture(scope="class")
def control_plane_architecture(control_plane_nodes):
    return get_control_plane_architecture(control_plane_nodes=control_plane_nodes)


@pytest.fixture()
def single_arch_node_placement(worker_architectures, hyperconverged_resource_scope_function):
    single_arch = sorted(worker_architectures)[0]
    LOGGER.info(f"Restricting workloads nodePlacement to single architecture: {single_arch}")
    placement = {"nodePlacement": {"nodeSelector": {KUBERNETES_ARCH_LABEL: single_arch}}}
    with ResourceEditorValidateHCOReconcile(
        patches={hyperconverged_resource_scope_function: {"spec": {"workloads": placement}}},
        list_resource_reconcile=[SSP, KubeVirt, CDI, NetworkAddonsConfig],
        wait_for_reconcile_post_update=True,
    ):
        yield


@pytest.fixture()
def hco_with_custom_unsupported_arch_template(
    admin_client,
    hco_namespace,
    golden_images_namespace,
    hyperconverged_resource_scope_function,
    hyperconverged_status_templates_scope_function,
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
    golden_images_namespace,
    hyperconverged_resource_scope_function,
    hyperconverged_status_templates_scope_function,
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

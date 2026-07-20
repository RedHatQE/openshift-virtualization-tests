"""
Multi-Architecture Golden Image Tests

STP Reference:
https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-iuo/multiarch_arm_support.md

Preconditions:
    - Multi-architecture cluster with AMD64 and ARM64 worker nodes
    - "enableMultiArchBootImageImport" feature gate enabled in HCO CR
    - Prometheus is installed and running
"""

import logging

import pytest
from ocp_resources.data_import_cron import DataImportCron
from ocp_resources.data_source import DataSource

from tests.install_upgrade_operators.hco_enablement_golden_image_updates.multiarch.utils import (
    CUSTOM_MULTIARCH_DATASOURCE_NAME,
    CUSTOM_NO_ARCH_ANNOTATION_CRON_NAME,
    CUSTOM_UNSUPPORTED_ARCH_CRON_NAME,
    KUBEVIRT_HCO_DATAIMPORTCRONTEMPLATE_WITH_ARCHITECTURE_ANNOTATION_QUERY,
    KUBEVIRT_HCO_DATAIMPORTCRONTEMPLATE_WITH_SUPPORTED_ARCHITECTURES_QUERY,
    KUBEVIRT_HCO_MULTI_ARCH_BOOT_IMAGES_ENABLED,
)
from tests.install_upgrade_operators.hco_enablement_golden_image_updates.utils import verify_resource_in_ns
from utilities.jira import is_jira_open
from utilities.monitoring import validate_metrics_value

LOGGER = logging.getLogger(__name__)

pytestmark = pytest.mark.multiarch


@pytest.mark.usefixtures("disabled_multiarch_feature_gate")
class TestDisabledMultiarchGoldenImagesSupport:
    """
    Tests for boot source state and misconfiguration metrics when
    multi-architecture golden images support is disabled on a
    heterogeneous cluster.

    Preconditions:
        - "enableMultiArchBootImageImport" feature gate disabled in HCO CR
    """

    @pytest.mark.polarion("CNV-15977")
    def test_only_architecture_agnostic_golden_image_resources_exist(
        self,
        admin_client,
        golden_images_namespace,
        worker_architectures,
        subtests,
    ):
        """
        Test that only architecture-agnostic golden image resources exist
        after disabling multi-architecture golden images support.

        Steps:
            1. List DataImportCrons and DataSources in the golden images namespace.
            2. Verify no resources have architecture suffix.

        Expected:
            - No DataImportCron or DataSource resources exist with architecture suffix.
        """
        for resource_type in (DataImportCron, DataSource):
            if resource_type is DataSource and is_jira_open("CNV-68996"):
                LOGGER.warning("CNV-68996: arch-specific DataSources not cleaned up after disabling multiarch")
                continue
            with subtests.test(msg=resource_type.kind):
                resources = list(resource_type.get(client=admin_client, namespace=golden_images_namespace.name))
                arch_specific = [
                    resource.name
                    for resource in resources
                    if any(resource.name.endswith(f"-{arch}") for arch in worker_architectures)
                ]
                assert not arch_specific, (
                    f"Architecture-specific {resource_type.kind} resources found when multiarch is disabled: "
                    f"{arch_specific}"
                )

    @pytest.mark.polarion("CNV-15978")
    def test_architecture_agnostic_data_sources_rollback(
        self,
        admin_client,
        golden_images_namespace,
        default_common_templates_related_resources,
    ):
        """
        Test that architecture-agnostic (pointer) DataSources remain available after
        disabling multi-architecture golden images support, and pointing to a pvc/snapshot source.

        Steps:
            1. Get architecture-agnostic DataSources from golden images namespace.
            2. Wait for them to be in ready condition.

        Expected:
            - Architecture-agnostic DataSources reference a pvc/snapshot source.
        """
        verify_resource_in_ns(
            expected_resource_names=default_common_templates_related_resources[DataSource.kind],
            namespace=golden_images_namespace.name,
            client=admin_client,
            resource_type=DataSource,
            ready_condition=DataSource.Condition.READY,
        )
        for ds_name in default_common_templates_related_resources[DataSource.kind]:
            data_source = DataSource(
                name=ds_name,
                namespace=golden_images_namespace.name,
                client=admin_client,
            )
            source = data_source.instance.spec.source
            assert source.get("pvc") or source.get("snapshot"), (
                f"DataSource {ds_name} does not reference a pvc/snapshot source: {source}"
            )

    @pytest.mark.polarion("CNV-15979")
    def test_kubevirt_hco_multi_arch_boot_images_enabled_metric(self, prometheus):
        """
        Test that the metric is indicating that multi-arch
        golden images support is disabled on a multiarch cluster.

        Steps:
            1. Query the metric.

        Expected:
            - Metric value is 0.
        """
        validate_metrics_value(
            prometheus=prometheus,
            metric_name=KUBEVIRT_HCO_MULTI_ARCH_BOOT_IMAGES_ENABLED,
            expected_value="0",
        )

    @pytest.mark.usefixtures("single_arch_node_placement")
    @pytest.mark.polarion("CNV-15980")
    def test_kubevirt_hco_multi_arch_boot_images_enabled_metric_single_arch_node_placement(
        self,
        prometheus,
    ):
        """
        Test that the metric is not emitted when nodePlacement restricts
        workloads to a single architecture.

        Preconditions:
            - nodePlacement restricts workloads to a single architecture in HCO CR.

        Steps:
            1. Query the metric.

        Expected:
            - Metric is not emitted.
        """
        validate_metrics_value(
            prometheus=prometheus,
            metric_name=KUBEVIRT_HCO_MULTI_ARCH_BOOT_IMAGES_ENABLED,
            expected_value=0,
        )


@pytest.mark.usefixtures("enabled_multiarch_feature_gate")
class TestEnabledMultiarchGoldenImagesSupport:
    """
    Tests for architecture-specific golden image boot sources availability
    and correctness on a heterogeneous cluster.

    Preconditions:
        - "enableMultiArchBootImageImport" feature gate enabled in HCO CR
    """

    @pytest.mark.parametrize(
        "resource_type, expected_condition",
        [
            pytest.param(DataImportCron, DataImportCron.Condition.UP_TO_DATE, marks=pytest.mark.polarion("CNV-15981")),
            pytest.param(DataSource, DataSource.Condition.READY, marks=pytest.mark.polarion("CNV-15982")),
        ],
    )
    def test_architecture_specific_golden_image_resources(
        self,
        admin_client,
        golden_images_namespace,
        default_common_templates_related_resources,
        resource_type,
        expected_condition,
    ):
        """
        Test that architecture-specific golden image resources are created
        for each common DataImportCronTemplate and each supported cluster architecture.

        Parametrize:
            - resource_type, expected_condition:
                - DataImportCron, UpToDate
                - DataSource, Ready

        Steps:
            1. Get supported architectures from cluster worker nodes.
            2. List parametrized resources in the golden images namespace.

        Expected:
            - Architecture-specific golden image resources exist for each supported
              architecture matching the workers architectures and in expected condition.
        """
        verify_resource_in_ns(
            expected_resource_names=default_common_templates_related_resources[resource_type.kind],
            namespace=golden_images_namespace.name,
            client=admin_client,
            resource_type=resource_type,
            ready_condition=expected_condition,
        )

    @pytest.mark.polarion("CNV-16020")
    def test_architecture_agnostic_data_sources(
        self,
        admin_client,
        golden_images_namespace,
        default_common_template_hco_status,
        control_plane_architecture,
    ):
        """
        Test that architecture-agnostic (pointer) DataSources are referencing
        the default architecture-specific DataSource.

        Steps:
            1. Get architecture-agnostic DataSources from golden images namespace.
            2. Get control-plane architecture.

        Expected:
            - DataSources in ready condition and referencing the control-plane
              architecture-specific DataSource.
        """
        base_ds_names = {template["spec"]["managedDataSource"] for template in default_common_template_hco_status}
        verify_resource_in_ns(
            expected_resource_names=base_ds_names,
            namespace=golden_images_namespace.name,
            client=admin_client,
            resource_type=DataSource,
            ready_condition=DataSource.Condition.READY,
        )
        for ds_name in base_ds_names:
            data_source = DataSource(
                name=ds_name,
                namespace=golden_images_namespace.name,
                client=admin_client,
            )
            expected_arch_ds_prefix = f"{ds_name}-{control_plane_architecture}"
            assert data_source.source.name.startswith(expected_arch_ds_prefix), (
                f"DataSource {ds_name} does not reference a control-plane "
                f"architecture-specific DataSource (expected prefix: {expected_arch_ds_prefix}). "
                f"Actual source: {data_source.source.name}"
            )


@pytest.mark.usefixtures("enabled_multiarch_feature_gate")
class TestMultiarchGoldenImageAnnotationMetrics:
    """
    Tests for misconfiguration metrics on golden image annotation issues
    when "enableMultiArchBootImageImport" feature gate is enabled in HCO CR.

    Preconditions:
        - "enableMultiArchBootImageImport" feature gate enabled in HCO CR
    """

    @pytest.mark.usefixtures("hco_with_custom_unsupported_arch_template")
    @pytest.mark.polarion("CNV-15983")
    def test_kubevirt_hco_dataimportcrontemplate_with_supported_architectures_metric(
        self,
        prometheus,
    ):
        """
        [NEGATIVE] Test that a misconfiguration metric is reported when a golden
        image is annotated with an architecture not supported by the cluster.

        Preconditions:
            - HCO CR is patched with a custom DataImportCronTemplate annotated
              with architecture not supported by the cluster.

        Steps:
            1. Query the metric.

        Expected:
            - Metric value is 0.
        """
        validate_metrics_value(
            prometheus=prometheus,
            metric_name=KUBEVIRT_HCO_DATAIMPORTCRONTEMPLATE_WITH_SUPPORTED_ARCHITECTURES_QUERY.format(
                cron_name=CUSTOM_UNSUPPORTED_ARCH_CRON_NAME,
                ds_name=CUSTOM_MULTIARCH_DATASOURCE_NAME,
            ),
            expected_value="0",
        )

    @pytest.mark.usefixtures("hco_with_custom_no_arch_annotation_template")
    @pytest.mark.polarion("CNV-15984")
    def test_kubevirt_hco_dataimportcrontemplate_with_architecture_annotation_metric(
        self,
        prometheus,
    ):
        """
        [NEGATIVE] Test that a misconfiguration metric is reported when a golden
        image lacks an architecture annotation on a multi-architecture cluster.

        Preconditions:
            - HCO CR is patched with a custom DataImportCronTemplate annotated without
              architecture annotation.

        Steps:
            1. Query the metric.

        Expected:
            - Metric value is 0.
        """
        validate_metrics_value(
            prometheus=prometheus,
            metric_name=KUBEVIRT_HCO_DATAIMPORTCRONTEMPLATE_WITH_ARCHITECTURE_ANNOTATION_QUERY.format(
                cron_name=CUSTOM_NO_ARCH_ANNOTATION_CRON_NAME,
                ds_name=CUSTOM_MULTIARCH_DATASOURCE_NAME,
            ),
            expected_value="0",
        )

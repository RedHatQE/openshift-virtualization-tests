"""
Multi-Architecture Golden Image Tests

STP Reference:
https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-iuo/multiarch_arm_support.md

Preconditions:
    - Multi-architecture cluster with AMD64 and ARM64 worker nodes
    - Prometheus is installed and running
"""

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
    get_no_arch_annotation_template,
    get_unsupported_arch_template,
)
from tests.install_upgrade_operators.hco_enablement_golden_image_updates.utils import verify_resource_in_ns
from utilities.monitoring import validate_metrics_value

pytestmark = [pytest.mark.multiarch, pytest.mark.post_upgrade]


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
    @pytest.mark.parametrize(
        "resource_type",
        [
            pytest.param(DataImportCron),
            pytest.param(DataSource, marks=pytest.mark.jira("CNV-68996", run=False)),
        ],
    )
    def test_only_base_golden_image_resources_exist(
        self,
        admin_client,
        golden_images_namespace,
        base_common_templates_related_resources,
        expected_common_templates_related_resources,
        resource_type,
    ):
        """
        Test that only base golden image resources exist
        after disabling multi-architecture golden images support.

        Parametrize:
            - resource_type:
                - DataImportCron
                - DataSource [Markers: jira(CNV-68996)]

        Steps:
            1. Verify expected base resources exist in the golden images namespace.
            2. Verify no architecture-specific resources exist.

        Expected:
            - Only base resources of the parametrized type exist.
        """
        verify_resource_in_ns(
            expected_resource_names=expected_common_templates_related_resources[resource_type.kind],
            namespace=golden_images_namespace.name,
            client=admin_client,
            resource_type=resource_type,
        )
        base_names = base_common_templates_related_resources[resource_type.kind]
        arch_specific_resources = [
            resource.name
            for resource in resource_type.get(client=admin_client, namespace=golden_images_namespace.name)
            if any(resource.name.startswith(f"{base_name}-") for base_name in base_names)
        ]
        assert not arch_specific_resources, (
            f"Architecture-specific {resource_type.kind} resources found when multiarch is disabled: "
            f"{arch_specific_resources}"
        )

    @pytest.mark.polarion("CNV-15978")
    def test_architecture_agnostic_data_sources_rollback(
        self,
        admin_client,
        golden_images_namespace,
        expected_common_templates_related_resources,
        subtests,
    ):
        """
        Test that architecture-agnostic DataSources remain available after
        disabling multi-architecture golden images support, and point to a pvc/snapshot source.

        Steps:
            1. Get architecture-agnostic DataSources from golden images namespace.
            2. Wait for them to be in ready condition.
            3. Check the source reference of each DataSource.

        Expected:
            - Architecture-agnostic DataSources reference a pvc/snapshot source.
        """
        verify_resource_in_ns(
            expected_resource_names=expected_common_templates_related_resources[DataSource.kind],
            namespace=golden_images_namespace.name,
            client=admin_client,
            resource_type=DataSource,
            ready_condition=DataSource.Condition.READY,
        )
        for ds_name in expected_common_templates_related_resources[DataSource.kind]:
            with subtests.test(msg=ds_name):
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
            - Metric value is 0. This metric is the underlying signal for the
              corresponding alert.
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
            - Metric is not emitted. This metric is the underlying signal for the
              corresponding alert.
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
        expected_common_templates_related_resources,
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
              architecture matching the workers architectures and in the expected condition.
              For DataImportCrons, only arch-specific names are expected (base names are replaced).
              For DataSources, both architecture-agnostic pointers and arch-specific names are expected.
        """
        verify_resource_in_ns(
            expected_resource_names=expected_common_templates_related_resources[resource_type.kind],
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
        base_common_templates_related_resources,
        kubevirt_default_architecture,
        subtests,
    ):
        """
        Test that architecture-agnostic (pointer) DataSources are referencing
        the default architecture-specific DataSource.

        Steps:
            1. Get architecture-agnostic DataSources from golden images namespace.
            2. Get Kubevirt default architecture.

        Expected:
            - DataSource is referencing architecture-specific DataSource matching the Kubevirt default architecture.
        """
        verify_resource_in_ns(
            expected_resource_names=base_common_templates_related_resources[DataSource.kind],
            namespace=golden_images_namespace.name,
            client=admin_client,
            resource_type=DataSource,
            ready_condition=DataSource.Condition.READY,
        )
        for ds_name in base_common_templates_related_resources[DataSource.kind]:
            expected_arch_ds = f"{ds_name}-{kubevirt_default_architecture}"
            with subtests.test(msg=ds_name):
                data_source = DataSource(
                    name=ds_name,
                    namespace=golden_images_namespace.name,
                    client=admin_client,
                )
                assert (source := data_source.instance.spec.source.get("dataSource")), (
                    f"DataSource {ds_name} does not reference an architecture-specific DataSource."
                )
                assert source.name == expected_arch_ds, (
                    f"DataSource {ds_name} does not reference a Kubevirt default "
                    f"architecture-specific DataSource (expected: {expected_arch_ds}). "
                    f"Actual source: {source.name}"
                )


@pytest.mark.usefixtures("enabled_multiarch_feature_gate")
class TestMultiarchGoldenImageAnnotationMetrics:
    """
    Tests for misconfiguration metrics on golden image annotation issues
    when "enableMultiArchBootImageImport" feature gate is enabled in HCO CR.

    Preconditions:
        - "enableMultiArchBootImageImport" feature gate enabled in HCO CR
    """

    @pytest.mark.parametrize(
        "hco_with_custom_template",
        [pytest.param(get_unsupported_arch_template, id="unsupported_arch")],
        indirect=True,
    )
    @pytest.mark.polarion("CNV-15983")
    def test_kubevirt_hco_dataimportcrontemplate_with_supported_architectures_metric(
        self,
        hco_with_custom_template,
        prometheus,
    ):
        """
        [NEGATIVE] Test that a misconfiguration metric indicates an unsupported
        architecture annotation on a golden image.

        Preconditions:
            - HCO CR is patched with a custom DataImportCronTemplate annotated
              with architecture not supported by the cluster.

        Steps:
            1. Query the metric.

        Expected:
            - Metric is emitted with value 0, indicating the misconfiguration is
              detected. This metric is the underlying signal for the corresponding alert.
        """
        validate_metrics_value(
            prometheus=prometheus,
            metric_name=KUBEVIRT_HCO_DATAIMPORTCRONTEMPLATE_WITH_SUPPORTED_ARCHITECTURES_QUERY.format(
                cron_name=CUSTOM_UNSUPPORTED_ARCH_CRON_NAME,
                ds_name=CUSTOM_MULTIARCH_DATASOURCE_NAME,
            ),
            expected_value="0",
        )

    @pytest.mark.parametrize(
        "hco_with_custom_template",
        [pytest.param(get_no_arch_annotation_template, id="no_arch_annotation")],
        indirect=True,
    )
    @pytest.mark.polarion("CNV-15984")
    def test_kubevirt_hco_dataimportcrontemplate_with_architecture_annotation_metric(
        self,
        hco_with_custom_template,
        prometheus,
    ):
        """
        [NEGATIVE] Test that a misconfiguration metric indicates a missing
        architecture annotation on a golden image.

        Preconditions:
            - HCO CR is patched with a custom DataImportCronTemplate without
              architecture annotation.

        Steps:
            1. Query the metric.

        Expected:
            - Metric is emitted with value 0, indicating the misconfiguration is
              detected. This metric is the underlying signal for the corresponding alert.
        """
        validate_metrics_value(
            prometheus=prometheus,
            metric_name=KUBEVIRT_HCO_DATAIMPORTCRONTEMPLATE_WITH_ARCHITECTURE_ANNOTATION_QUERY.format(
                cron_name=CUSTOM_NO_ARCH_ANNOTATION_CRON_NAME,
                ds_name=CUSTOM_MULTIARCH_DATASOURCE_NAME,
            ),
            expected_value="0",
        )

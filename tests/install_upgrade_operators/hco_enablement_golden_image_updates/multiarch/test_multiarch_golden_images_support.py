"""
Multi-Architecture Golden Image Tests

STP Reference:
https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-iuo/multiarch_arm_support.md

Preconditions:
    - Multi-architecture cluster with AMD64 and ARM64 worker nodes
    - "enableMultiArchBootImageImport" feature gate enabled in HCO CR
    - Prometheus is installed and running

Markers:
    - multiarch
    - post_upgrade
"""

import pytest

__test__ = False


class TestDisabledMultiarchGoldenImagesSupport:
    """
    Tests for boot source state and misconfiguration metrics when
    multi-architecture golden images support is disabled on a
    heterogeneous cluster.

    Preconditions:
        - "enableMultiArchBootImageImport" feature gate disabled in HCO CR
    """

    @pytest.mark.polarion("CNV-15977")
    def test_only_architecture_agnostic_golden_image_resources_exist(self):
        """
        Test that only architecture-agnostic golden image resources exist
        after disabling multi-architecture golden images support.

        Parametrize:
            - resource_type:
                - DataImportCron
                - DataSource

        Steps:
            1. List resources of the parametrized type in the golden images namespace.
            2. Verify arch-suffix resources are not present.

        Expected:
            - No resources exist with architecture suffix.
        """

    @pytest.mark.polarion("CNV-15978")
    def test_architecture_agnostic_data_sources_rollback(self):
        """
        Test that architecture-agnostic (pointer) DataSources remain available after
        disabling multi-architecture golden images support, and pointing to a pvc/snapshot source.

        Steps:
            1. Get architecture-agnostic DataSources from golden images namespace.
            2. Wait for them to be in ready condition.

        Expected:
            - Architecture-agnostic DataSources reference a pvc/snapshot source.
        """

    @pytest.mark.polarion("CNV-15979")
    def test_kubevirt_hco_multi_arch_boot_images_enabled_metric(self):
        """
        Test that the metric is indicating that multi-arch
        golden images support is disabled on a multiarch cluster.

        Steps:
            1. Query the metric.

        Expected:
            - Metric value is 0.
        """

    @pytest.mark.polarion("CNV-15980")
    def test_kubevirt_hco_multi_arch_boot_images_enabled_metric_single_arch_node_placement(self):
        """
        Test that the metric is indicating that multi-arch support is enabled
        when nodePlacement restricts workloads to a single architecture.

        Preconditions:
            - nodePlacement restricts workloads to a single architecture in HCO CR.

        Steps:
            1. Query the metric.

        Expected:
            - Metric value is 1.
        """


class TestEnabledMultiarchGoldenImagesSupport:
    """
    Tests for architecture-specific golden image boot sources availability
    and correctness on a heterogeneous cluster.

    Preconditions:
        - "enableMultiArchBootImageImport" feature gate enabled in HCO CR
    """

    @pytest.mark.polarion("CNV-15981")
    def test_architecture_specific_golden_image_resources(self):
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

    @pytest.mark.polarion("CNV-15982")
    def test_architecture_agnostic_data_sources(self):
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


class TestMultiarchGoldenImageAnnotationMetrics:
    """
    Tests for misconfiguration metrics on golden image annotation issues
    when "enableMultiArchBootImageImport" feature gate is enabled in HCO CR.

    Preconditions:
        - "enableMultiArchBootImageImport" feature gate enabled in HCO CR
    """

    @pytest.mark.polarion("CNV-15983")
    def test_kubevirt_hco_dataimportcrontemplate_with_supported_architectures_metric(self):
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

    @pytest.mark.polarion("CNV-15984")
    def test_kubevirt_hco_dataimportcrontemplate_with_architecture_annotation_metric(self):
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

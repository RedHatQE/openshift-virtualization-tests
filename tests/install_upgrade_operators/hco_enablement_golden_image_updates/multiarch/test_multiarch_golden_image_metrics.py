"""
Multi-Architecture Golden Image Metrics Tests

STP Reference:
https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-iuo/multiarch_arm_support.md

Preconditions:
    - Multi-architecture cluster with AMD64 and ARM64 worker nodes
    - Prometheus is installed and running

Markers:
    - multiarch
    - post_upgrade
"""

import pytest

__test__ = False


class TestMultiarchGoldenImageAnnotationMetrics:
    """
    Tests for misconfiguration metrics on golden image annotation issues
    when "enableMultiArchBootImageImport" feature gate is enabled in HCO CR.

    Preconditions:
        - "enableMultiArchBootImageImport" feature gate enabled In HCO CR
    """

    @pytest.mark.polarion("CNV-XXXXX")
    def test_kubevirt_hco_dataimportcrontemplate_with_supported_architectures(self):
        """
        Test that a misconfiguration metric is reported when a golden
        image is annotated with an architecture not supported by the cluster.

        Steps:
            1. Add a custom golden image boot source with
               ssp.kubevirt.io/dict.architectures annotation set to an
               architecture not supported by the cluster
            2. Wait for metric evaluation

        Expected:
            - Metric should return 0.
        """

    @pytest.mark.polarion("CNV-XXXXX")
    def test_kubevirt_hco_dataimportcrontemplate_with_architecture_annotation(self):
        """
        Test that a misconfiguration metric is reported when a golden
        image lacks an architecture annotation on a multi-architecture cluster.

        Steps:
            1. Add a custom golden image boot source without an
               ssp.kubevirt.io/dict.architectures annotation
            2. Wait for metric evaluation

        Expected:
            - Metric should return 0.
        """


@pytest.mark.incremental
class TestMultiarchDisabledGoldenImages:
    """
    Tests for boot source state and misconfiguration metrics when
    multi-architecture golden images support is disabled on a
    heterogeneous cluster.

    Preconditions:
        - "enableMultiArchBootImageImport" feature gate disabled In HCO CR
    """

    @pytest.mark.polarion("CNV-XXXXX")
    def test_base_boot_source_resources_without_architecture_suffix(self):
        """
        Test that base boot source resources remain available after
        disabling multi-architecture golden images support.

        Parametrize:
            - resource_type:
                - DataImportCron
                - DataSource

        Steps:
            1. Get expected common boot sources from SSP CR common templates
            2. List resources of the parametrized type in the golden images
               namespace

        Expected:
            - Base resources exist with original names (no architecture
              suffix) and in ready condition
        """

    @pytest.mark.polarion("CNV-XXXXX")
    def test_no_architecture_specific_resources(self):
        """
        Test that architecture-specific boot source resources are removed
        after disabling multi-architecture golden images support.

        Steps:
            1. List DataImportCrons and DataSources in the golden images
               namespace

        Expected:
            - No resources exist with architecture suffix
        """

    @pytest.mark.polarion("CNV-XXXXX")
    def test_kubevirt_hco_multi_arch_boot_images_enabled(self):
        """
        Test that the disabled multi-architecture misconfiguration metric
        is active when multi-arch golden images support is disabled on a
        heterogeneous cluster.

        Steps:
            1. Query the multi-architecture misconfiguration metric

        Expected:
            - Misconfiguration metric value indicates multi-architecture
              golden images support is disabled on a multi-architecture
              cluster
        """

    @pytest.mark.polarion("CNV-XXXXX")
    def test_kubevirt_hco_multi_arch_boot_images_enabled_netgative(self):
        """
        Test that the misconfiguration metric clears when
        nodePlacement restricts workloads to a single architecture.

        Preconditions:
            - Misconfiguration metric is currently active

        Steps:
            1. Configure nodePlacement to restrict workloads to a single
               architecture
            2. Wait for metric evaluation

        Expected:
            - Misconfiguration metric is no longer active
        """

"""
Multi-Architecture Golden Image Boot Sources Tests

STP Reference:
https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-iuo/multiarch_arm_support.md

Preconditions:
    - Multi-architecture cluster with AMD64 and ARM64 worker nodes
    - "enableMultiArchBootImageImport" feature gate enabled In HCO CR

Markers:
    - multiarch
    - post_upgrade
"""

import pytest

__test__ = False


class TestMultiarchBootSources:
    """
    Tests for architecture-specific golden image boot sources availability
    and correctness on a heterogeneous cluster.

    """

    @pytest.mark.polarion("CNV-XXXXX")
    def test_architecture_specific_boot_source_resources(self):
        """
        Test that architecture-specific boot source resources are created
        for each common boot source and each supported cluster architecture.

        Parametrize:
            - resource_type:
                - DataImportCron
                - DataSource

        Steps:
            1. Get expected common boot sources from SSP CR common templates
            2. List resources of the parametrized type in the golden images
               namespace

        Expected:
            - Architecture-specific resources exist for each supported
              architecture, correctly named, labeled, and in ready condition
        """

    @pytest.mark.polarion("CNV-XXXXX")
    def test_pointer_datasources(self):
        """
        Test that architecture-agnostic pointer DataSources are created with
        the original boot source name and reference the default
        architecture-specific DataSource.

        Steps:
            1. Get expected common boot sources from SSP CR common templates
            2. List DataSources in the golden images namespace

        Expected:
            - Architecture-agnostic pointer DataSources exist with the
              original name, referencing the control-plane architecture
              DataSource, and in Ready condition
        """

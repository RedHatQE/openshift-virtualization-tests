import pytest

from utilities.constants.hco import (
    COMMON_TEMPLATES_KEY_NAME,
    SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME,
)

pytestmark = [pytest.mark.gating, pytest.mark.arm64, pytest.mark.s390x]


@pytest.mark.usefixtures("disabled_common_boot_image_import_hco_spec_scope_class")
class TestDisableCommonBootImageImport:
    def test_disable_spec_verify_hco_cr_and_ssp_cr(
        self,
        ssp_cr_spec,
    ):
        """
        Jira: https://redhat.atlassian.net/browse/CNV-11790 # <skip-jira-utils-check>
        Polarion: CNV-7473
        """
        assert SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME not in ssp_cr_spec[COMMON_TEMPLATES_KEY_NAME], (
            f"the key exists, not as expected: key={SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME} spec={ssp_cr_spec}"
        )

    def test_image_streams_disable_feature_gate(
        self,
        golden_images_namespace,
        image_stream_names,
    ):
        """
        Jira: https://redhat.atlassian.net/browse/CNV-8296 # <skip-jira-utils-check>
        Polarion: CNV-8183
        """
        assert not image_stream_names, (
            "ImageStream resources were found, not as expected: "
            f"namespace={golden_images_namespace.name} existing image streams={image_stream_names}"
        )

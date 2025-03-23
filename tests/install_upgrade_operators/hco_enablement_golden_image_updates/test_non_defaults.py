import pytest

from utilities.constants import (
    COMMON_TEMPLATES_KEY_NAME,
    SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME,
)

pytestmark = pytest.mark.gating


@pytest.mark.usefixtures("disabled_common_boot_image_import_hco_spec_scope_class")
class TestDisableCommonBootImageImport:
    @pytest.mark.polarion("CNV-7473")
    def test_disable_spec_verify_hco_cr_and_ssp_cr(
        self,
        ssp_cr_spec,
    ):
        assert SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME not in ssp_cr_spec[COMMON_TEMPLATES_KEY_NAME], (
            f"the key exists, not as expected: key={SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME} spec={ssp_cr_spec}"
        )

    @pytest.mark.polarion("CNV-8183")
    def test_image_streams_disable_feature_gate(
        self,
        golden_images_namespace,
        image_stream_names,
    ):
        assert not image_stream_names, (
            "ImageStream resources were found, not as expected: "
            f"namespace={golden_images_namespace.name} existing image streams={image_stream_names}"
        )

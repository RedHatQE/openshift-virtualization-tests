import logging

import pytest

from utilities.constants import (
    COMMON_TEMPLATES_KEY_NAME,
    ENABLE_COMMON_BOOT_IMAGE_IMPORT,
    SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME,
)
from utilities.hco import wait_for_auto_boot_config_stabilization

pytestmark = pytest.mark.gating

LOGGER = logging.getLogger(__name__)


class TestEnableCommonBootImageImport:
    @pytest.mark.polarion("CNV-7626")
    def test_set_enable_common_boot_image_import_true_ssp_cr(
        self,
        ssp_cr_spec,
    ):
        assert ssp_cr_spec[COMMON_TEMPLATES_KEY_NAME][SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME], (
            f"SSP CR commonTemplates is empty: ssp_cr_spec={ssp_cr_spec}"
        )


@pytest.mark.polarion("CNV-7778")
def test_enable_and_delete_spec_enable_common_boot_image_import_hco_cr(
    admin_client,
    hco_namespace,
    disabled_common_boot_image_import_hco_spec_scope_function,
    hyperconverged_resource_scope_function,
):
    wait_for_auto_boot_config_stabilization(admin_client=admin_client, hco_namespace=hco_namespace)
    assert not hyperconverged_resource_scope_function.instance.spec[ENABLE_COMMON_BOOT_IMAGE_IMPORT], (
        f"Spec {ENABLE_COMMON_BOOT_IMAGE_IMPORT} was not disabled in HCO."
    )

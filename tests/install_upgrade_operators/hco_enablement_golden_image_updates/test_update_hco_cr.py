from copy import deepcopy

import pytest

from tests.install_upgrade_operators.constants import CUSTOM_DATASOURCE_NAME
from tests.install_upgrade_operators.hco_enablement_golden_image_updates.utils import (
    COMMON_TEMPLATE,
    CUSTOM_CRON_TEMPLATE,
    CUSTOM_TEMPLATE,
    get_template_dict_by_name,
    get_templates_by_type_from_hco_status,
)
from utilities.hco import (
    update_hco_templates_spec,
    wait_for_auto_boot_config_stabilization,
)

pytestmark = pytest.mark.gating


def validate_custom_template_added(hyperconverged_status_templates_scope_function, ssp_spec_templates_scope_function):
    validate_template_dict(
        template_dict=hyperconverged_status_templates_scope_function,
        resource_string="HCO.status",
    )
    validate_template_dict(template_dict=ssp_spec_templates_scope_function, resource_string="SSP.spec")


def validate_template_dict(template_dict, resource_string):
    custom_template_name = CUSTOM_CRON_TEMPLATE["metadata"]["name"]
    custom_template_dict = get_template_dict_by_name(template_name=custom_template_name, templates=template_dict)
    assert custom_template_dict, (
        f"Custom template: {custom_template_name} not found in {resource_string}: {template_dict}"
    )
    template_copy = deepcopy(custom_template_dict)
    if "status" in template_copy:
        del template_copy["status"]
    del template_copy["spec"]["template"]["status"]
    assert CUSTOM_CRON_TEMPLATE == template_copy, (
        f"Custom template: {CUSTOM_CRON_TEMPLATE} is not found in hco.status: {template_copy}"
    )


@pytest.fixture(scope="class")
def updated_hco_cr_custom_template_scope_class(
    admin_client,
    hco_namespace,
    hyperconverged_resource_scope_class,
    golden_images_namespace,
):
    yield from update_hco_templates_spec(
        admin_client=admin_client,
        hco_namespace=hco_namespace,
        hyperconverged_resource=hyperconverged_resource_scope_class,
        updated_template=CUSTOM_CRON_TEMPLATE,
        custom_datasource_name=CUSTOM_DATASOURCE_NAME,
        golden_images_namespace=golden_images_namespace,
    )


@pytest.mark.usefixtures("updated_hco_cr_custom_template_scope_class")
class TestCustomTemplates:
    @pytest.mark.order(before="test_add_custom_data_import_cron_template_disable_spec")
    @pytest.mark.polarion("CNV-8707")
    def test_custom_template_status(self, hyperconverged_status_templates_scope_function):
        custom_template_name = CUSTOM_CRON_TEMPLATE["metadata"]["name"]
        custom_templates_name = [
            template["metadata"]["name"]
            for template in get_templates_by_type_from_hco_status(
                hco_status_templates=hyperconverged_status_templates_scope_function,
                template_type=CUSTOM_TEMPLATE,
            )
        ]
        assert custom_template_name in custom_templates_name, (
            f"Custom template: {custom_template_name} is not found in hco.status: {custom_templates_name}"
        )

    @pytest.mark.order(before="test_add_custom_data_import_cron_template_disable_spec")
    @pytest.mark.polarion("CNV-7884")
    def test_add_custom_data_import_cron_template(
        self,
        hyperconverged_status_templates_scope_function,
        ssp_spec_templates_scope_function,
    ):
        validate_custom_template_added(
            hyperconverged_status_templates_scope_function=hyperconverged_status_templates_scope_function,
            ssp_spec_templates_scope_function=ssp_spec_templates_scope_function,
        )

    @pytest.mark.dependency(name="test_add_custom_data_import_cron_template_disable_spec")
    @pytest.mark.polarion("CNV-7914")
    def test_add_custom_data_import_cron_template_disable_spec(
        self,
        admin_client,
        hco_namespace,
        disabled_common_boot_image_import_hco_spec_scope_function,
        hyperconverged_status_templates_scope_function,
        ssp_spec_templates_scope_function,
        image_stream_names,
    ):
        wait_for_auto_boot_config_stabilization(admin_client=admin_client, hco_namespace=hco_namespace)
        error_message_base = "With enableCommonBootImageImport spec disabled,"
        validate_custom_template_added(
            hyperconverged_status_templates_scope_function=hyperconverged_status_templates_scope_function,
            ssp_spec_templates_scope_function=ssp_spec_templates_scope_function,
        )
        common_templates = get_templates_by_type_from_hco_status(
            hco_status_templates=hyperconverged_status_templates_scope_function,
            template_type=COMMON_TEMPLATE,
        )
        assert not common_templates, (
            f"{error_message_base}, hco.status did not get updated to remove commonTemplates: {common_templates}"
        )

        assert len(ssp_spec_templates_scope_function) == 1, (
            f"{error_message_base} SSP.spec did not get updated to remove existing "
            f"commonTemplates: {ssp_spec_templates_scope_function}"
        )
        assert not image_stream_names, (
            f"{error_message_base} ImageStream resources were not removed as expected: {image_stream_names}"
        )

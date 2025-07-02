import copy
import logging

import pytest
from benedict import benedict
from kubernetes.dynamic.exceptions import ResourceNotFoundError
from ocp_resources.cdi import CDI
from ocp_resources.data_import_cron import DataImportCron
from ocp_resources.ssp import SSP

from tests.install_upgrade_operators.constants import KEY_PATH_SEPARATOR
from tests.install_upgrade_operators.hco_enablement_golden_image_updates.utils import (
    get_data_import_cron_by_name,
    get_modifed_common_template_names,
    get_template_dict_by_name,
)
from utilities.constants import (
    DATA_IMPORT_CRON_ENABLE,
    SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME,
    WILDCARD_CRON_EXPRESSION,
)
from utilities.hco import ResourceEditorValidateHCOReconcile

pytestmark = [pytest.mark.gating, pytest.mark.arm64]

COMMON_TEMPLATE_DISABLE = {DATA_IMPORT_CRON_ENABLE: "false"}
COMMON_TEMPLATE_ENABLE = {DATA_IMPORT_CRON_ENABLE: "true"}
UPDATE_TEMPLATE_SCHEDULE = {"spec->schedule": WILDCARD_CRON_EXPRESSION}
UPDATE_ONE_VALUE_IN_SPEC = {
    "spec->garbageCollect": "Never",
}
UPDATE_MULTIPLE_VALUE_IN_SPEC = {
    **UPDATE_TEMPLATE_SCHEDULE,
    **UPDATE_ONE_VALUE_IN_SPEC,
    "spec->template->spec->storage->resources->requests->storage": "40Gi",
}
UPDATE_STORAGE_CLASS_IN_SPEC = {
    "spec->template->spec->storage->storageClassName": "my-storage-class",
}
LOGGER = logging.getLogger(__name__)


def get_common_template_updated_dict(common_template, updated_dict, delete_spec=True):
    copy_common_template = benedict(copy.deepcopy(common_template), keypath_separator=KEY_PATH_SEPARATOR)
    del copy_common_template["status"]
    if delete_spec:
        del copy_common_template["spec"]
    if updated_dict:
        for key in updated_dict:
            copy_common_template[key] = updated_dict[key]
    return copy_common_template


def validate_template_change(template_dict, expected_dict):
    return [
        f"expected: {expected_dict[key]}, actual:{template_dict.get(key)},"
        for key in expected_dict
        if expected_dict[key] != template_dict.get(key)
    ]


@pytest.fixture()
def common_templates_enabled(common_templates_scope_session):
    return [
        template
        for template in common_templates_scope_session
        if template["metadata"]["annotations"].get(
            f"{DataImportCron.ApiGroup.DATA_IMPORT_CRON_TEMPLATE_KUBEVIRT_IO}/enable"
        )
        != "false"
    ]


@pytest.fixture()
def updated_template_names(updated_common_template):
    return [template["metadata"]["name"] for template in updated_common_template]


@pytest.fixture()
def updated_common_template(
    request,
    common_templates_enabled,
    hyperconverged_resource_scope_function,
    admin_client,
    hco_namespace,
    golden_images_namespace,
):
    updated_templates = []
    updated_common_template_dict_list = []

    for index in range(request.param.get("num_templates")):
        template = common_templates_enabled[index]
        updated_templates.append(template)
        updated_common_template_dict_list.append(
            get_common_template_updated_dict(
                common_template=template,
                updated_dict=request.param["update_dict"],
                delete_spec=request.param.get("delete_spec", False),
            )
        )
    LOGGER.info(f"Common templates {updated_templates}, updating to: {updated_common_template}")
    with ResourceEditorValidateHCOReconcile(
        patches={
            hyperconverged_resource_scope_function: {
                "spec": {SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME: updated_common_template_dict_list}
            }
        },
        list_resource_reconcile=[CDI, SSP],
        wait_for_reconcile_post_update=True,
    ):
        yield updated_templates

    modified_common_templates = get_modifed_common_template_names(hyperconverged=hyperconverged_resource_scope_function)
    assert not modified_common_templates, f"Following templates were not reverted back: {modified_common_templates}"


class TestModifyCommonTemplateSpec:
    @pytest.mark.parametrize(
        "updated_common_template",
        [
            pytest.param(
                {"num_templates": 1, "update_dict": None},
                marks=(
                    pytest.mark.polarion("CNV-8706"),
                    pytest.mark.dependency(name="test_common_template_status_modified"),
                ),
            ),
        ],
        indirect=["updated_common_template"],
    )
    @pytest.mark.s390x
    def test_modified_common_template(self, updated_common_template, hyperconverged_status_templates_scope_function):
        template_name = updated_common_template[0]["metadata"]["name"]
        hco_template = get_template_dict_by_name(
            template_name=template_name,
            templates=hyperconverged_status_templates_scope_function,
        )
        assert hco_template["status"].get("modified"), (
            f"Common template {template_name}, did not get marked as modified: {hco_template}"
        )

    @pytest.mark.parametrize(
        "updated_common_template, expected_value",
        [
            pytest.param(
                {"num_templates": 1, "update_dict": UPDATE_TEMPLATE_SCHEDULE},
                UPDATE_TEMPLATE_SCHEDULE,
                marks=pytest.mark.polarion("CNV-8739"),
            ),
            pytest.param(
                {"num_templates": 1, "update_dict": UPDATE_MULTIPLE_VALUE_IN_SPEC},
                UPDATE_MULTIPLE_VALUE_IN_SPEC,
                marks=pytest.mark.polarion("CNV-8734"),
            ),
            pytest.param(
                {"num_templates": 1, "update_dict": UPDATE_ONE_VALUE_IN_SPEC},
                UPDATE_ONE_VALUE_IN_SPEC,
                marks=pytest.mark.polarion("CNV-8733"),
            ),
            pytest.param(
                {"num_templates": 1, "update_dict": UPDATE_STORAGE_CLASS_IN_SPEC},
                UPDATE_STORAGE_CLASS_IN_SPEC,
                marks=pytest.mark.polarion("CNV-8740"),
            ),
        ],
        indirect=["updated_common_template"],
    )
    @pytest.mark.s390x
    def test_common_template_modify_spec(
        self,
        updated_common_template,
        updated_template_names,
        hyperconverged_status_templates_scope_function,
        ssp_spec_templates_scope_function,
        golden_images_namespace,
        expected_value,
    ):
        errors = []
        for template_name in updated_template_names:
            hco_error = validate_template_change(
                template_dict=benedict(
                    get_template_dict_by_name(
                        template_name=template_name,
                        templates=hyperconverged_status_templates_scope_function,
                    ),
                    keypath_separator=KEY_PATH_SEPARATOR,
                ),
                expected_dict=expected_value,
            )
            if hco_error:
                errors.append(f"Mismatch for template in hco.status: {template_name}: {''.join(hco_error)}.\n")
            ssp_error = validate_template_change(
                template_dict=benedict(
                    get_template_dict_by_name(
                        template_name=template_name,
                        templates=ssp_spec_templates_scope_function,
                    ),
                    keypath_separator=KEY_PATH_SEPARATOR,
                ),
                expected_dict=expected_value,
            )
            if ssp_error:
                errors.append(f"Mismatch for template in ssp.spec: {template_name}: {''.join(ssp_error)}.\n")

            data_import_cron_error = validate_template_change(
                template_dict=benedict(
                    get_data_import_cron_by_name(
                        cron_name=template_name, namespace=golden_images_namespace.name
                    ).instance.to_dict(),
                    keypath_separator=KEY_PATH_SEPARATOR,
                ),
                expected_dict=expected_value,
            )
            if data_import_cron_error:
                errors.append(
                    f"Mismatch for template: {template_name} in dataimportcron.spec: {''.join(data_import_cron_error)}."
                )
        assert not errors, "".join(errors)


@pytest.mark.usefixtures("common_templates_scope_session")
class TestCommonTemplatesEnableDisable:
    @pytest.mark.parametrize(
        "updated_common_template",
        [
            pytest.param(
                {"num_templates": 1, "update_dict": COMMON_TEMPLATE_DISABLE},
                marks=(
                    pytest.mark.polarion("CNV-8735"),
                    pytest.mark.dependency(name="test_one_common_template_config_disable"),
                ),
            ),
            pytest.param(
                {
                    "num_templates": 1,
                    "update_dict": COMMON_TEMPLATE_DISABLE,
                    "delete_spec": True,
                },
                marks=(
                    pytest.mark.polarion("CNV-8732"),
                    pytest.mark.dependency(name="test_one_common_template_config_disable_no_spec"),
                ),
            ),
            pytest.param(
                {"num_templates": 3, "update_dict": COMMON_TEMPLATE_DISABLE},
                marks=(
                    pytest.mark.polarion("CNV-8710"),
                    pytest.mark.dependency(name="test_multiple_common_templates_config_disable"),
                ),
            ),
        ],
        indirect=["updated_common_template"],
    )
    @pytest.mark.s390x
    def test_common_template_config_disable(
        self,
        updated_common_template,
        updated_template_names,
        hyperconverged_status_templates_scope_function,
        ssp_spec_templates_scope_function,
        golden_images_namespace,
    ):
        LOGGER.info(f"templates getting disabled: {updated_template_names}")
        errors = []
        for template_name in updated_template_names:
            hco_template = get_template_dict_by_name(
                template_name=template_name,
                templates=hyperconverged_status_templates_scope_function,
            )
            if hco_template:
                errors.append(
                    f"Common template {template_name}'s expected to be removed from hco, current hco "
                    f"value: {hyperconverged_status_templates_scope_function}."
                )
            ssp_template = get_template_dict_by_name(
                template_name=template_name,
                templates=ssp_spec_templates_scope_function,
            )
            if ssp_template:
                errors.append(
                    f"Common template {template_name}'s expected to be removed from ssp, current ssp "
                    f"value: {ssp_spec_templates_scope_function}."
                )

            with pytest.raises(ResourceNotFoundError):
                get_data_import_cron_by_name(cron_name=template_name, namespace=golden_images_namespace.name)
        assert not errors, (
            f"Enabling/Disabling common templates via HCO failed with following reasons: {' '.join(errors)}"
        )

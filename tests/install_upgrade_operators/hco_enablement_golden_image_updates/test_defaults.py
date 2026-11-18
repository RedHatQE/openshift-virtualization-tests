import json

import pytest

from utilities.constants.hco import SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME

pytestmark = [pytest.mark.gating, pytest.mark.arm64, pytest.mark.s390x, pytest.mark.conformance]


@pytest.mark.usefixtures("hyperconverged_spec_scope_session", "hyperconverged_status_scope_session")
def test_data_import_schedule_default_in_hco_cr(
    data_import_schedule,
):
    """
    Jira: https://redhat.atlassian.net/browse/CNV-8296 # <skip-jira-utils-check>
    Polarion: CNV-7504

    example (the first and second numbers are random):
    dataImportSchedule: 57 45/12 * * *
    """
    assert data_import_schedule, "No crontab value found"


def test_default_hco_cr_image_streams(
    admin_client,
    golden_images_namespace,
    image_stream_names,
    image_streams_from_common_templates_in_ssp_cr,
):
    """
    Jira: https://redhat.atlassian.net/browse/CNV-8296 # <skip-jira-utils-check>
    Polarion: CNV-8168
    """
    assert sorted(image_stream_names) == sorted(image_streams_from_common_templates_in_ssp_cr), (
        f"ImageStream resources data mismatch: namespace={golden_images_namespace.name} "
        f"cluster image streams={image_stream_names} "
        f"expected image streams names={image_streams_from_common_templates_in_ssp_cr} "
        "missing_image_stream_resources_names_from_ssp_cr="
        f"{set(image_streams_from_common_templates_in_ssp_cr).difference(set(image_stream_names))} "
        "additional_image_stream_names_in_ssp_cr="
        f"{set(image_stream_names).difference(set(image_streams_from_common_templates_in_ssp_cr))}"
    )


def test_no_data_import_template_in_hco_spec(
    hyperconverged_spec_scope_session,
):
    """
    Jira: https://redhat.atlassian.net/browse/CNV-15392 # <skip-jira-utils-check>
    Polarion: CNV-8935
    """
    assert SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME not in json.dumps(hyperconverged_spec_scope_session), (
        f"{SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME} found in {hyperconverged_spec_scope_session}"
    )


def test_data_import_template_defaults_hco_status(
    hyperconverged_status_scope_session,
    hyperconverged_spec_scope_session,
    modified_common_templates_scope_session,
    default_custom_templates_scope_session,
):
    """
    Jira: https://redhat.atlassian.net/browse/CNV-15392 # <skip-jira-utils-check>
    Polarion: CNV-8703
    """
    assert SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME in hyperconverged_status_scope_session, (
        f"{SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME} not found in {hyperconverged_status_scope_session}"
    )

    assert not modified_common_templates_scope_session, (
        f"Following common templates are marked as modified: "
        f"{modified_common_templates_scope_session}, hco.spec: {hyperconverged_spec_scope_session}"
    )
    assert not default_custom_templates_scope_session, (
        f"Following custom templates: {default_custom_templates_scope_session} are enabled by "
        f"default on hco: {hyperconverged_spec_scope_session}"
    )

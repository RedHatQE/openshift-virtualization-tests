import pytest
from ocp_resources.image_stream import ImageStream
from ocp_resources.pod import Pod
from ocp_utilities.infra import get_pods_by_name_prefix

from tests.install_upgrade_operators.golden_images.constants import (
    ARCH_LABEL,
    COMMON_TEMPLATE,
    CUSTOM_TEMPLATE,
    HCO_CR_DATA_IMPORT_SCHEDULE_KEY,
)
from tests.install_upgrade_operators.golden_images.utils import (
    get_modifed_common_template_names,
    get_random_minutes_hours_fields_from_data_import_schedule,
    get_templates_by_type_from_hco_status,
    get_templates_resources_names_dict,
)
from utilities.constants import (
    COMMON_TEMPLATES_KEY_NAME,
    HCO_OPERATOR,
    SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME,
)
from utilities.ssp import get_ssp_resource


@pytest.fixture()
def data_import_schedule(hyperconverged_resource_scope_function):
    return hyperconverged_resource_scope_function.instance.status.get(HCO_CR_DATA_IMPORT_SCHEDULE_KEY)


@pytest.fixture()
def data_import_schedule_minute_and_hour_values(data_import_schedule):
    return get_random_minutes_hours_fields_from_data_import_schedule(target_string=data_import_schedule)


@pytest.fixture()
def deleted_hco_operator_pod(admin_client, hco_namespace, hyperconverged_resource_scope_function):
    get_pods_by_name_prefix(client=admin_client, pod_prefix=HCO_OPERATOR, namespace=hco_namespace.name)[0].delete(
        wait=True
    )
    get_pods_by_name_prefix(client=admin_client, pod_prefix=HCO_OPERATOR, namespace=hco_namespace.name)[
        0
    ].wait_for_status(status=Pod.Status.RUNNING)
    return get_random_minutes_hours_fields_from_data_import_schedule(
        target_string=hyperconverged_resource_scope_function.instance.status.get(HCO_CR_DATA_IMPORT_SCHEDULE_KEY)
    )


@pytest.fixture()
def image_stream_names(admin_client, golden_images_namespace):
    return [
        image_stream.name
        for image_stream in ImageStream.get(client=admin_client, namespace=golden_images_namespace.name)
    ]


@pytest.fixture(scope="session")
def common_templates_from_ssp_cr(ssp_cr_spec_scope_session):
    return ssp_cr_spec_scope_session[COMMON_TEMPLATES_KEY_NAME][SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME]


@pytest.fixture(scope="session")
def ssp_cr_spec_scope_session(admin_client, hco_namespace):
    return get_ssp_resource(admin_client=admin_client, namespace=hco_namespace).instance.to_dict()["spec"]


@pytest.fixture()
def image_streams_from_common_templates_in_ssp_cr(
    common_templates_from_ssp_cr,
):
    image_streams = []
    for template in common_templates_from_ssp_cr:
        image_stream = template["spec"]["template"]["spec"]["source"]["registry"].get("imageStream")
        if image_stream:
            image_streams.append(image_stream)
    return image_streams


@pytest.fixture(scope="session")
def hyperconverged_spec_scope_session(hyperconverged_resource_scope_session):
    return hyperconverged_resource_scope_session.instance.to_dict()["spec"]


@pytest.fixture(scope="session")
def hyperconverged_status_scope_session(hyperconverged_resource_scope_session):
    return hyperconverged_resource_scope_session.instance.to_dict()["status"]


@pytest.fixture(scope="session")
def hyperconverged_status_templates_scope_session(
    hyperconverged_status_scope_session,
):
    return hyperconverged_status_scope_session[SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME]


@pytest.fixture(scope="session")
def default_custom_templates_scope_session(
    hyperconverged_status_templates_scope_session,
):
    return get_templates_by_type_from_hco_status(
        hco_status_templates=hyperconverged_status_templates_scope_session,
        template_type=CUSTOM_TEMPLATE,
    )


@pytest.fixture(scope="session")
def modified_common_templates_scope_session(hyperconverged_resource_scope_session):
    return get_modifed_common_template_names(hyperconverged=hyperconverged_resource_scope_session)


@pytest.fixture()
def ssp_spec_templates_scope_function(ssp_resource_scope_function):
    return ssp_resource_scope_function.instance.to_dict()["spec"][COMMON_TEMPLATES_KEY_NAME][
        SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME
    ]


@pytest.fixture(scope="session")
def common_templates_scope_session(hyperconverged_status_scope_session):
    return hyperconverged_status_scope_session[SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME]


@pytest.fixture(scope="session")
def control_plane_node_architectures(control_plane_nodes):
    return {node.labels[ARCH_LABEL] for node in control_plane_nodes}


@pytest.fixture(scope="session")
def worker_nodes_architectures(workers):
    return {node.labels[ARCH_LABEL] for node in workers}


@pytest.fixture(scope="session")
def default_hco_node_info(hyperconverged_status_scope_session):
    return hyperconverged_status_scope_session["nodeInfo"]


@pytest.fixture(scope="session")
def default_ssp_node_info(ssp_cr_spec_scope_session):
    return ssp_cr_spec_scope_session["cluster"]


@pytest.fixture(scope="class")
def hco_node_info_scope_class(hyperconverged_resource_scope_class):
    return hyperconverged_resource_scope_class.instance.status.get("nodeInfo")


@pytest.fixture(scope="class")
def default_common_template_hco_status(hyperconverged_status_templates_scope_class):
    return get_templates_by_type_from_hco_status(
        hco_status_templates=hyperconverged_status_templates_scope_class, template_type=COMMON_TEMPLATE
    )


@pytest.fixture(scope="class")
def default_common_templates_related_resources(default_common_template_hco_status):
    return get_templates_resources_names_dict(templates=default_common_template_hco_status)

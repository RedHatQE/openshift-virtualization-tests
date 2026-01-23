import logging

import pytest

from tests.install_upgrade_operators.pod_validation.utils import (
    assert_cnv_pod_container_env_image_not_in_upstream,
    assert_cnv_pod_container_image_not_in_upstream,
    validate_cnv_pods_priority_class_name_exists,
    validate_cnv_pods_resource_request,
    validate_priority_class_value,
)
from utilities.constants import (
    HOSTPATH_PROVISIONER_CSI,
    HPP_POOL,
    KUBEVIRT_MIGRATION_CONTROLLER,
)

pytestmark = [pytest.mark.sno, pytest.mark.arm64, pytest.mark.s390x]

LOGGER = logging.getLogger(__name__)


@pytest.fixture()
def xfail_if_jira_76659_open_and_migration_controller_pod(jira_76659_open, cnv_pods_by_type):
    if any(pod.name.startswith(KUBEVIRT_MIGRATION_CONTROLLER) for pod in cnv_pods_by_type) and jira_76659_open:
        pytest.xfail(f"{KUBEVIRT_MIGRATION_CONTROLLER} pod has no priority class name due to CNV-76659 bug")


@pytest.mark.polarion("CNV-7262")
def test_pods_priority_class_value(cnv_pods_by_type, xfail_if_jira_76659_open_and_migration_controller_pod):
    if any(pod.name.startswith((HPP_POOL, HOSTPATH_PROVISIONER_CSI)) for pod in cnv_pods_by_type):
        pytest.xfail("HPP pods don't have priority class name")
    validate_cnv_pods_priority_class_name_exists(pod_list=cnv_pods_by_type)
    validate_priority_class_value(pod_list=cnv_pods_by_type)


@pytest.mark.polarion("CNV-7306")
def test_pods_resource_request(
    cnv_pods_by_type,
    pod_resource_validation_matrix__function__,
):
    validate_cnv_pods_resource_request(
        cnv_pods=cnv_pods_by_type,
        resource=pod_resource_validation_matrix__function__,
    )


@pytest.mark.polarion("CNV-8267")
def test_cnv_pod_container_image(cnv_pods_by_type):
    assert_cnv_pod_container_image_not_in_upstream(cnv_pods_by_type=cnv_pods_by_type)
    assert_cnv_pod_container_env_image_not_in_upstream(cnv_pods_by_type=cnv_pods_by_type)

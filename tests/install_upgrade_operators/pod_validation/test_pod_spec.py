import logging

import pytest

from tests.install_upgrade_operators.pod_validation.utils import (
    assert_cnv_pod_container_env_image_not_in_upstream,
    assert_cnv_pod_container_image_not_in_upstream,
    validate_cnv_pods_priority_class_name_exists,
    validate_cnv_pods_resource_request,
    validate_priority_class_value,
)

pytestmark = [pytest.mark.sno, pytest.mark.arm64]

LOGGER = logging.getLogger(__name__)


@pytest.fixture()
def cnv_pods_by_type(cnv_pod_matrix__function__, cnv_pods):
    pod_list = [pod for pod in cnv_pods if pod.name.startswith(cnv_pod_matrix__function__)]
    assert pod_list, f"Pod {cnv_pod_matrix__function__} not found"
    return pod_list


@pytest.fixture()
def cnv_pods_by_type_no_hpp_csi_hpp_pool(cnv_pod_priority_class_matrix__function__, cnv_pods):
    pod_list = [pod for pod in cnv_pods if pod.name.startswith(cnv_pod_priority_class_matrix__function__)]
    assert pod_list, f"Pod {cnv_pod_priority_class_matrix__function__} not found"
    return pod_list


@pytest.mark.polarion("CNV-7262")
def test_pods_priority_class_value(cnv_pods_by_type_no_hpp_csi_hpp_pool):
    validate_cnv_pods_priority_class_name_exists(pod_list=cnv_pods_by_type_no_hpp_csi_hpp_pool)
    validate_priority_class_value(pod_list=cnv_pods_by_type_no_hpp_csi_hpp_pool)


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

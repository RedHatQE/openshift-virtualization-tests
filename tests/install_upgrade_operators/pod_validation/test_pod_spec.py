import logging

import pytest
from ocp_resources.job import Job

from tests.install_upgrade_operators.pod_validation.utils import (
    assert_cnv_pod_container_env_image_not_in_upstream,
    assert_cnv_pod_container_image_not_in_upstream,
    validate_cnv_pods_priority_class_name_exists,
    validate_cnv_pods_resource_request,
    validate_priority_class_value,
)
from utilities.constants import (
    ALL_CNV_PODS,
    HPP_POOL,
)

pytestmark = pytest.mark.sno

LOGGER = logging.getLogger(__name__)


@pytest.fixture()
def cnv_jobs(admin_client, hco_namespace):
    return [job.name for job in Job.get(dyn_client=admin_client, namespace=hco_namespace.name)]


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


@pytest.mark.polarion("CNV-7261")
def test_no_new_cnv_pods_added(cnv_pods, cnv_jobs):
    all_pods = ALL_CNV_PODS.copy()
    all_pods.append(HPP_POOL)

    new_pods = [
        pod.name
        for pod in cnv_pods
        if list(filter(pod.name.startswith, all_pods)) == [] and list(filter(pod.name.startswith, cnv_jobs)) == []
    ]
    assert not new_pods, f"New cnv pod: {new_pods}, has been added."


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

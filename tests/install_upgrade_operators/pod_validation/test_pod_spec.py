import logging

import pytest

from tests.install_upgrade_operators.pod_validation.utils import (
    assert_cnv_pod_container_env_image_not_in_upstream,
    assert_cnv_pod_container_image_not_in_upstream,
    validate_cnv_pods_priority_class_name_exists,
    validate_cnv_pods_resource_request,
    validate_priority_class_value,
)
from utilities.constants.components import (
    HOSTPATH_PROVISIONER_CSI,
    HPP_POOL,
    KUBEVIRT_MIGRATION_CONTROLLER,
)

pytestmark = [pytest.mark.sno, pytest.mark.arm64, pytest.mark.s390x]

LOGGER = logging.getLogger(__name__)
HPP_PREFIXES = (HPP_POOL, HOSTPATH_PROVISIONER_CSI)


@pytest.mark.polarion("CNV-7262")
def test_pods_priority_class_value(
    subtests,
    discovered_cnv_pods,
    jira_76659_open,
):
    for pod in discovered_cnv_pods:
        with subtests.test(msg=pod.name):
            if pod.name.startswith(HPP_PREFIXES):
                pytest.xfail("HPP pods don't have priority class name")
            if pod.name.startswith(KUBEVIRT_MIGRATION_CONTROLLER) and jira_76659_open:
                pytest.xfail(f"{KUBEVIRT_MIGRATION_CONTROLLER} pod has no priority class name due to CNV-76659 bug")
            validate_cnv_pods_priority_class_name_exists(pod_list=[pod])
            validate_priority_class_value(pod_list=[pod])


@pytest.mark.polarion("CNV-7306")
@pytest.mark.parametrize(
    "resource_type",
    [
        pytest.param({"cpu": 5}, id="cpu"),
        pytest.param({"memory": None}, id="memory"),
    ],
)
def test_pods_resource_request(
    subtests,
    discovered_cnv_pods,
    resource_type,
):
    for pod in discovered_cnv_pods:
        with subtests.test(msg=pod.name):
            validate_cnv_pods_resource_request(
                cnv_pods=[pod],
                resource=resource_type,
            )


@pytest.mark.polarion("CNV-8267")
def test_cnv_pod_container_image(subtests, discovered_cnv_pods):
    for pod in discovered_cnv_pods:
        with subtests.test(msg=pod.name):
            assert_cnv_pod_container_image_not_in_upstream(cnv_pods_by_type=[pod])
            assert_cnv_pod_container_env_image_not_in_upstream(cnv_pods_by_type=[pod])

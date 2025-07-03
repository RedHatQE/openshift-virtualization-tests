import logging
from collections import Counter

import pytest
from ocp_resources.pod import Pod

from tests.virt.cluster.utils import verify_pods_priority_class_value
from utilities.constants import (
    DEFAULT_RESOURCE_CONDITIONS,
    SSP_OPERATOR,
    VIRT_TEMPLATE_VALIDATOR,
)
from utilities.infra import get_pod_by_name_prefix

LOGGER = logging.getLogger(__name__)

pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno, pytest.mark.arm64]


@pytest.fixture()
def pods_list_with_given_prefix(request, admin_client, hco_namespace):
    namespace_name = hco_namespace.name
    pods_prefix_name = request.param["pods_prefix_name"]
    pods_list_by_prefix = get_pod_by_name_prefix(
        dyn_client=admin_client,
        pod_prefix=pods_prefix_name,
        namespace=namespace_name,
        get_all=True,
    )
    assert pods_list_by_prefix, f"Did not find pods with prefix: {pods_prefix_name} in namespace: {namespace_name}"
    return pods_list_by_prefix


@pytest.mark.s390x
@pytest.mark.polarion("CNV-3737")
def test_verify_ssp_cr_conditions(ssp_resource_scope_function):
    LOGGER.info("Check SSP CR conditions.")
    resource_conditions = {
        condition.type: condition.status
        for condition in ssp_resource_scope_function.instance.status.conditions
        if condition.type in DEFAULT_RESOURCE_CONDITIONS.keys()
    }
    assert resource_conditions == DEFAULT_RESOURCE_CONDITIONS, (
        f"SSP CR conditions failed. Actual: {resource_conditions}, expected: {DEFAULT_RESOURCE_CONDITIONS}."
    )


@pytest.mark.s390x
@pytest.mark.parametrize(
    "pods_list_with_given_prefix",
    [
        pytest.param({"pods_prefix_name": SSP_OPERATOR}, marks=pytest.mark.polarion("CNV-7002")),
        pytest.param(
            {"pods_prefix_name": VIRT_TEMPLATE_VALIDATOR},
            marks=pytest.mark.polarion("CNV-7003"),
        ),
    ],
    indirect=True,
)
def test_priority_class_value(pods_list_with_given_prefix):
    verify_pods_priority_class_value(pods=pods_list_with_given_prefix, expected_value="system-cluster-critical")


@pytest.fixture()
def virt_template_validator_pods(admin_client, hco_namespace):
    return list(
        Pod.get(
            dyn_client=admin_client,
            namespace=hco_namespace.name,
            label_selector="kubevirt.io=virt-template-validator",
        )
    )


@pytest.fixture()
def pods_with_same_node(virt_template_validator_pods):
    pods_node_name = {pod.name: pod.instance.spec.nodeName for pod in virt_template_validator_pods}
    node_name_count = Counter(pods_node_name.values())
    return [pod.name for pod in virt_template_validator_pods if node_name_count[pods_node_name[pod.name]] > 1]


@pytest.fixture()
def virt_template_validator_without_affinity(virt_template_validator_pods):
    return [pod.name for pod in virt_template_validator_pods if "affinity" not in pod.instance.to_dict()["spec"]]


@pytest.fixture()
def virt_template_validator_without_podantiaffinity(
    virt_template_validator_pods, virt_template_validator_without_affinity
):
    return [
        pod.name
        for pod in virt_template_validator_pods
        if (pod.name not in virt_template_validator_without_affinity)
        and ("podAntiAffinity" not in pod.instance.to_dict()["spec"]["affinity"])
    ]


@pytest.mark.s390x
@pytest.mark.polarion("CNV-8660")
def test_podantiaffinity(
    virt_template_validator_pods,
    pods_with_same_node,
    virt_template_validator_without_affinity,
    virt_template_validator_without_podantiaffinity,
):
    assert not virt_template_validator_without_affinity, (
        f"Affinity is not defined in {virt_template_validator_without_affinity}"
    )

    assert not virt_template_validator_without_podantiaffinity, (
        f"podantiaffinity not defined in {virt_template_validator_without_podantiaffinity}"
    )
    assert not pods_with_same_node, f"pods {pods_with_same_node} are getting scheduled on same nodes"

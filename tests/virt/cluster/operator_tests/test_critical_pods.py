"""
Check that KubeVirt infra pods are critical
"""

import logging

import pytest
from ocp_resources.pod import Pod

from tests.virt.cluster.utils import verify_pods_priority_class_value
from utilities.constants import VIRT_API, VIRT_CONTROLLER, VIRT_HANDLER

pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno, pytest.mark.gating, pytest.mark.arm64]


LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def virt_pods(request, admin_client, hco_namespace):
    podprefix = request.param
    pods_list = list(
        Pod.get(
            dyn_client=admin_client,
            namespace=hco_namespace.name,
            label_selector=f"kubevirt.io={podprefix}",
        )
    )
    assert pods_list, f"No pods found for {podprefix}"
    yield pods_list


@pytest.mark.s390x
@pytest.mark.parametrize(
    "virt_pods",
    [
        pytest.param(VIRT_API, marks=(pytest.mark.polarion("CNV-788"))),
        pytest.param(
            VIRT_CONTROLLER,
            marks=(pytest.mark.polarion("CNV-8867")),
        ),
        pytest.param(VIRT_HANDLER, marks=(pytest.mark.polarion("CNV-8868"))),
    ],
    indirect=True,
)
def test_kubevirt_pods_are_critical(virt_pods):
    """
    Positive: ensure infra pods are critical
    """
    verify_pods_priority_class_value(pods=virt_pods, expected_value="kubevirt-cluster-critical")

    failed_pods = {}
    for pod in virt_pods:
        LOGGER.info(f"Check that {pod.name} has CriticalAddonsOnly tolerations")
        toleration_data = pod.instance.to_dict()["spec"].get("tolerations", [])
        if not toleration_data:
            failed_pods[pod.name] = "Pod does not have assigned tolerations"
            continue
        if not [entry for entry in toleration_data if entry == {"key": "CriticalAddonsOnly", "operator": "Exists"}]:
            failed_pods[pod.name] = "Pod does not have CriticalAddonsOnly toleration"

    assert not failed_pods, f"Failed pods: {failed_pods}"

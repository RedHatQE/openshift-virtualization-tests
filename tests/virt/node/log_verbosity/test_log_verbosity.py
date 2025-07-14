"""
Low level hypervisor logs testing
"""

import logging

import pytest
from ocp_resources.pod import Pod

from tests.virt.node.log_verbosity.constants import (
    VIRT_LOG_VERBOSITY_LEVEL_6,
)
from utilities.constants import VIRT_API, VIRT_CONTROLLER, VIRT_HANDLER
from utilities.infra import get_pods

LOGGER = logging.getLogger(__name__)


def assert_log_verbosity_level_in_virt_pods(virt_pods_list):
    failed_log_verbosity_level_pods = [
        pod.name for pod in virt_pods_list if f"verbosity to {VIRT_LOG_VERBOSITY_LEVEL_6}" not in pod.log()
    ]

    assert not failed_log_verbosity_level_pods, (
        f"Not found correct verbosity setting in pods: {failed_log_verbosity_level_pods}"
    )


@pytest.fixture()
def virt_component_pods(admin_client, hco_namespace):
    virt_pods_list = []
    for virt_component in [VIRT_HANDLER, VIRT_API, VIRT_CONTROLLER]:
        virt_pods_list.extend(
            get_pods(
                dyn_client=admin_client,
                namespace=hco_namespace,
                label=f"{Pod.ApiGroup.KUBEVIRT_IO}={virt_component}",
            )
        )
    yield virt_pods_list


@pytest.fixture()
def virt_component_pods_in_first_node(worker_node1, virt_component_pods):
    return [pod for pod in virt_component_pods if pod.node.name == worker_node1.name]


@pytest.mark.s390x
@pytest.mark.parametrize(
    "updated_log_verbosity_config",
    [
        pytest.param(
            "component",
            marks=pytest.mark.polarion("CNV-8574"),
        ),
    ],
    indirect=True,
)
def test_component_log_verbosity(updated_log_verbosity_config, virt_component_pods):
    assert_log_verbosity_level_in_virt_pods(
        virt_pods_list=virt_component_pods,
    )


@pytest.mark.s390x
@pytest.mark.parametrize(
    "updated_log_verbosity_config",
    [
        pytest.param(
            "node",
            marks=pytest.mark.polarion("CNV-8576"),
        ),
    ],
    indirect=True,
)
def test_node_log_verbosity(updated_log_verbosity_config, virt_component_pods_in_first_node):
    assert_log_verbosity_level_in_virt_pods(
        virt_pods_list=virt_component_pods_in_first_node,
    )

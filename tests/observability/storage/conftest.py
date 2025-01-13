import logging
import shlex

import pytest
from ocp_resources.hostpath_provisioner import HostPathProvisioner
from ocp_resources.resource import ResourceEditor
from timeout_sampler import TimeoutExpiredError

from tests.observability.storage.constants import HPP_NOT_READY
from utilities.constants import HOSTPATH_PROVISIONER, HOSTPATH_PROVISIONER_CSI, TIMEOUT_2MIN
from utilities.infra import get_pod_by_name_prefix
from utilities.monitoring import wait_for_firing_alert_clean_up

LOGGER = logging.getLogger(__name__)

HPP_CUSTOM_NODE_SELECTOR_DICT = {
    "spec": {
        "workload": {
            "nodeSelector": {"kubernetes.io/os": "non-existent-os"},
        }
    }
}


@pytest.fixture(scope="class")
def hostpath_provisioner_scope_class():
    yield HostPathProvisioner(name=HOSTPATH_PROVISIONER)


@pytest.fixture(scope="module")
def skip_if_hpp_not_exist(hostpath_provisioner_scope_module):
    if not hostpath_provisioner_scope_module.exists:
        pytest.skip("Skipping because hostpath provisioner doesn't exist in the cluster")


@pytest.fixture(scope="module")
def hpp_condition_available_scope_module(hostpath_provisioner_scope_module):
    try:
        hostpath_provisioner_scope_module.wait_for_condition(
            condition=hostpath_provisioner_scope_module.Condition.AVAILABLE,
            status=hostpath_provisioner_scope_module.Condition.Status.TRUE,
            timeout=TIMEOUT_2MIN,
        )
    except TimeoutExpiredError:
        LOGGER.error("hostpath provisioner should be Available")
        raise


@pytest.fixture(scope="class")
def modified_hpp_non_exist_node_selector(hostpath_provisioner_scope_class, prometheus):
    with ResourceEditor(patches={hostpath_provisioner_scope_class: HPP_CUSTOM_NODE_SELECTOR_DICT}):
        hostpath_provisioner_scope_class.wait_for_condition(
            condition=hostpath_provisioner_scope_class.Condition.AVAILABLE,
            status=hostpath_provisioner_scope_class.Condition.Status.FALSE,
            timeout=TIMEOUT_2MIN,
        )
        yield
    hostpath_provisioner_scope_class.wait_for_condition(
        condition=hostpath_provisioner_scope_class.Condition.AVAILABLE,
        status=hostpath_provisioner_scope_class.Condition.Status.TRUE,
        timeout=TIMEOUT_2MIN,
    )
    wait_for_firing_alert_clean_up(prometheus=prometheus, alert_name=HPP_NOT_READY)


@pytest.fixture(scope="class")
def hpp_pod_sharing_pool_path(admin_client, hco_namespace, hostpath_provisioner_scope_class):
    storage_pools = hostpath_provisioner_scope_class.instance.spec.get("storagePools")
    assert storage_pools, "HPP CR exist but storagePools spec entry not found"
    pods = get_pod_by_name_prefix(
        dyn_client=admin_client,
        pod_prefix=HOSTPATH_PROVISIONER_CSI,
        namespace=hco_namespace.name,
        get_all=True,
    )
    # if HPP CR is ready we should find hpp-csi pods.
    assert pods, "HPP CR exist but its pods not found"

    for name in [pool.name for pool in storage_pools]:
        for pod in pods:
            if "pvc-" in pod.execute(command=shlex.split(f"ls {name}-data-dir/csi"), container=HOSTPATH_PROVISIONER):
                return
    raise AssertionError("An HPP pod should have share a path with the os")

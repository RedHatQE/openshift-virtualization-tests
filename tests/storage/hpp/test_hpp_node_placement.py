# -*- coding: utf-8 -*-

"""
HPP Node Placement test suite
"""

import logging

import pytest
from ocp_resources.virtual_machine_instance import VirtualMachineInstance

from tests.storage.hpp.utils import (
    DV_NAME,
    HCO_NODE_PLACEMENT,
    NODE_SELECTOR,
    TYPE,
    VM_NAME,
    edit_hpp_with_node_selector,
)
from utilities.constants import NODE_STR, TIMEOUT_1MIN, TIMEOUT_5MIN
from utilities.storage import check_disk_count_in_vm

LOGGER = logging.getLogger(__name__)

pytestmark = pytest.mark.usefixtures("skip_test_if_no_hpp_sc")


@pytest.mark.destructive
@pytest.mark.parametrize(
    (
        "updated_hpp_with_node_placement",
        "hyperconverged_with_node_placement",
        "cirros_vm_for_node_placement_tests",
    ),
    [
        pytest.param(
            {TYPE: NODE_SELECTOR},
            HCO_NODE_PLACEMENT,
            {DV_NAME: "dv-5711", VM_NAME: "vm-5711", NODE_STR: None},
            marks=pytest.mark.polarion("CNV-5711"),
        ),
        pytest.param(
            {TYPE: "affinity"},
            HCO_NODE_PLACEMENT,
            {DV_NAME: "dv-5712", VM_NAME: "vm-5712", NODE_STR: None},
            marks=pytest.mark.polarion("CNV-5712"),
        ),
        pytest.param(
            {TYPE: "tolerations"},
            HCO_NODE_PLACEMENT,
            {DV_NAME: "dv-5713", VM_NAME: "vm-5713", NODE_STR: None},
            marks=pytest.mark.polarion("CNV-5713"),
        ),
    ],
    indirect=True,
)
def test_create_dv_on_right_node_with_node_placement(
    worker_node1,
    update_node_labels,
    updated_hpp_with_node_placement,
    hyperconverged_with_node_placement,
    cirros_vm_for_node_placement_tests,
):
    # The VM should be created on the node that have the node labels
    assert cirros_vm_for_node_placement_tests.vmi.node.name == worker_node1.name


@pytest.mark.post_upgrade
@pytest.mark.parametrize(
    ("updated_hpp_with_node_placement", "cirros_vm_for_node_placement_tests"),
    [
        pytest.param(
            {TYPE: NODE_SELECTOR},
            {DV_NAME: "dv-5717", VM_NAME: "vm-5717", "wait_running": False},
            marks=pytest.mark.polarion("CNV-5717"),
        ),
    ],
    indirect=True,
)
@pytest.mark.s390x
def test_create_vm_on_node_without_hpp_pod_and_after_update(
    update_node_labels,
    updated_hpp_with_node_placement,
    cirros_vm_for_node_placement_tests,
):
    cirros_vm_for_node_placement_tests.vmi.wait_for_status(
        status=VirtualMachineInstance.Status.SCHEDULING,
        timeout=TIMEOUT_1MIN,
        stop_status=VirtualMachineInstance.Status.RUNNING,
    )
    assert (
        cirros_vm_for_node_placement_tests.printable_status
        == cirros_vm_for_node_placement_tests.Status.WAITING_FOR_VOLUME_BINDING
    )
    updated_hpp_with_node_placement.restore()
    cirros_vm_for_node_placement_tests.vmi.wait_for_status(
        status=VirtualMachineInstance.Status.RUNNING,
        timeout=TIMEOUT_5MIN,
    )


@pytest.mark.post_upgrade
@pytest.mark.parametrize(
    "cirros_vm_for_node_placement_tests",
    [
        pytest.param(
            {DV_NAME: "dv-5601", VM_NAME: "vm-5601"},
            marks=pytest.mark.polarion("CNV-5601"),
        ),
    ],
    indirect=True,
)
@pytest.mark.s390x
def test_vm_with_dv_on_functional_after_configuring_hpp_not_to_work_on_that_same_node(
    hostpath_provisioner_scope_module,
    update_node_labels,
    hpp_daemonset_scope_session,
    schedulable_nodes,
    cirros_vm_for_node_placement_tests,
):
    check_disk_count_in_vm(vm=cirros_vm_for_node_placement_tests)
    with edit_hpp_with_node_selector(
        hpp_resource=hostpath_provisioner_scope_module,
        hpp_daemonset=hpp_daemonset_scope_session,
        schedulable_nodes=schedulable_nodes,
    ):
        check_disk_count_in_vm(vm=cirros_vm_for_node_placement_tests)


@pytest.mark.parametrize(
    "cirros_vm_for_node_placement_tests",
    [
        pytest.param(
            {DV_NAME: "dv-5616", VM_NAME: "vm-5616"},
            marks=pytest.mark.polarion("CNV-5616"),
        ),
    ],
    indirect=True,
)
@pytest.mark.post_upgrade
@pytest.mark.s390x
def test_pv_stay_released_after_deleted_when_no_hpp_pod(
    hostpath_provisioner_scope_module,
    update_node_labels,
    hpp_daemonset_scope_session,
    schedulable_nodes,
    cirros_vm_for_node_placement_tests,
    cirros_pvc_on_hpp,
    cirros_pv_on_hpp,
):
    with edit_hpp_with_node_selector(
        hpp_resource=hostpath_provisioner_scope_module,
        hpp_daemonset=hpp_daemonset_scope_session,
        schedulable_nodes=schedulable_nodes,
    ):
        cirros_vm_for_node_placement_tests.delete()
    cirros_pvc_on_hpp.wait_deleted()
    cirros_pv_on_hpp.wait_deleted()

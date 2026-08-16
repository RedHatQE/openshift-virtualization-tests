"""
HPP Node Placement test suite
"""

import logging

import pytest

from tests.storage.hpp.utils import (
    DV_NAME,
    VM_NAME,
    edit_hpp_with_node_selector,
)
from utilities.storage import check_disk_count_in_vm

LOGGER = logging.getLogger(__name__)

pytestmark = pytest.mark.hpp


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

import pytest
from ocp_resources.virtual_machine_cluster_instancetype import (
    VirtualMachineClusterInstancetype,
)

from tests.infrastructure.instance_types.utils import assert_mismatch_vendor_label
from utilities.constants import VIRT_OPERATOR, Images
from utilities.virt import VirtualMachineForTests, running_vm


@pytest.fixture(scope="session")
def fail_if_no_huge_pages(workers):
    if not any([worker.instance.status.allocatable["hugepages-2Mi"] == "2Gi" for worker in workers]):
        pytest.fail("Only run on a Cluster with node that has enough huge pages")


@pytest.mark.sno
@pytest.mark.post_upgrade
@pytest.mark.gating
@pytest.mark.polarion("CNV-10358")
def test_common_instancetype_vendor_labels(base_vm_cluster_instancetypes):
    assert_mismatch_vendor_label(resources_list=base_vm_cluster_instancetypes)


@pytest.mark.hugepages
@pytest.mark.special_infra
@pytest.mark.tier3
@pytest.mark.polarion("CNV-10387")
def test_cx1_instancetype_profile(fail_if_no_huge_pages, unprivileged_client, namespace):
    with VirtualMachineForTests(
        client=unprivileged_client,
        name="rhel-vm-with-cx1",
        namespace=namespace.name,
        image=Images.Rhel.RHEL9_REGISTRY_GUEST_IMG,
        vm_instance_type=VirtualMachineClusterInstancetype(name="cx1.medium"),
    ) as vm:
        running_vm(vm=vm, wait_for_interfaces=False, check_ssh_connectivity=False)


@pytest.mark.post_upgrade
@pytest.mark.polarion("CNV-11288")
def test_common_instancetype_owner(base_vm_cluster_instancetypes):
    failed_ins_type = []
    for vm_cluster_instancetype in base_vm_cluster_instancetypes:
        if (
            vm_cluster_instancetype.labels[f"{vm_cluster_instancetype.ApiGroup.APP_KUBERNETES_IO}/managed-by"]
            != VIRT_OPERATOR
        ):
            failed_ins_type.append(vm_cluster_instancetype.name)
    assert not failed_ins_type, f"The following instance types do no have {VIRT_OPERATOR} owner: {failed_ins_type}"

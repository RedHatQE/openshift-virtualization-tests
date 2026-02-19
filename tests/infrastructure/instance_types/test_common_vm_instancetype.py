import pytest
from ocp_resources.virtual_machine_cluster_instancetype import (
    VirtualMachineClusterInstancetype,
)

from tests.infrastructure.instance_types.utils import (
    assert_mismatch_vendor_label,
)
from utilities.constants import VIRT_OPERATOR, Images
from utilities.ssp import wait_for_condition_message_value
from utilities.virt import VirtualMachineForTests, running_vm


@pytest.mark.sno
@pytest.mark.post_upgrade
@pytest.mark.gating
@pytest.mark.conformance
@pytest.mark.polarion("CNV-10358")
@pytest.mark.s390x
def test_common_instancetype_vendor_labels(base_vm_cluster_instancetypes):
    assert_mismatch_vendor_label(resources_list=base_vm_cluster_instancetypes)


@pytest.mark.hugepages
@pytest.mark.special_infra
@pytest.mark.tier3
@pytest.mark.polarion("CNV-10387")
def test_cx1_instancetype_profile(unprivileged_client, namespace):
    with VirtualMachineForTests(
        client=unprivileged_client,
        name="rhel-vm-with-cx1",
        namespace=namespace.name,
        image=Images.Rhel.RHEL9_REGISTRY_GUEST_IMG,
        vm_instance_type=VirtualMachineClusterInstancetype(client=unprivileged_client, name="cx1.medium1gi"),
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


@pytest.mark.usefixtures(
    "windows_validating_admission_policy",
    "windows_validating_admission_policy_binding",
)
class TestDedicatedInstancetypeProfile:
    @pytest.mark.polarion("CNV-13437")
    @pytest.mark.parametrize(
        "windows_vm_for_dedicated_cpu",
        [
            pytest.param(
                {
                    "vm_name": "windows-d1-profile",
                    "instance_type_name": "d1.large",
                },
            ),
        ],
        indirect=True,
    )
    def test_d1_instancetype_profile(
        self,
        windows_vm_for_dedicated_cpu,
    ):
        running_vm(vm=windows_vm_for_dedicated_cpu)

    @pytest.mark.polarion("CNV-13438")
    @pytest.mark.parametrize(
        "windows_vm_for_dedicated_cpu",
        [
            pytest.param(
                {
                    "vm_name": "windows-dedicated-cpu-validation",
                    "instance_type_name": "u1.large",
                },
            ),
        ],
        indirect=True,
    )
    def test_dedicated_cpu_validation_error(
        self,
        windows_vm_for_dedicated_cpu,
    ):
        windows_vm_for_dedicated_cpu.start()
        expected_message = (
            f'Failure while starting VMI: virtualmachineinstances.kubevirt.io "{windows_vm_for_dedicated_cpu.name}" '
            f"is forbidden: ValidatingAdmissionPolicy 'windows-vcpu-overcommit' with binding "
            f"'windows-vcpu-overcommit-binding' denied request: Windows VMIs require dedicated "
            f"CPU placement. Set spec.domain.cpu.dedicatedCpuPlacement to true."
        )
        wait_for_condition_message_value(resource=windows_vm_for_dedicated_cpu, expected_message=expected_message)

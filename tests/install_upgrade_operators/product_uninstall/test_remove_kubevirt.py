import pytest
from kubernetes.dynamic.exceptions import BadRequestError
from ocp_resources.cdi import CDI
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.virtual_machine import VirtualMachine
from timeout_sampler import TimeoutSampler

from utilities.constants import TIMEOUT_3MIN, TIMEOUT_4MIN
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.virt import VirtualMachineForTests, fedora_vm_body


@pytest.fixture()
def set_uninstall_strategy_remove_workloads(hyperconverged_resource_scope_function):
    with ResourceEditorValidateHCOReconcile(
        patches={hyperconverged_resource_scope_function: {"spec": {"uninstallStrategy": "RemoveWorkloads"}}},
        list_resource_reconcile=[CDI, KubeVirt],
        wait_for_reconcile_post_update=True,
    ) as edits:
        yield edits


@pytest.fixture()
def remove_kubevirt_vm(unprivileged_client, namespace):
    name = "remove-kubevirt-vm"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        body=fedora_vm_body(name=name),
        client=unprivileged_client,
    ) as vm:
        vm.start()
        vm.vmi.wait_until_running()
        yield vm


@pytest.mark.polarion("CNV-3738")
@pytest.mark.s390x
def test_validate_default_uninstall_strategy(kubevirt_resource):
    strategy = kubevirt_resource.instance.spec.uninstallStrategy
    assert strategy == "BlockUninstallIfWorkloadsExist", (
        f"Default uninstall strategy is incorrect.Expected 'BlockUninstallIfWorkloadsExist', found '{strategy}'"
    )


@pytest.mark.polarion("CNV-3718")
@pytest.mark.destructive
def test_block_removal(kubevirt_resource, remove_kubevirt_vm):
    with pytest.raises(BadRequestError):
        kubevirt_resource.delete()

    assert (
        kubevirt_resource.status == KubeVirt.Status.DEPLOYED
        and remove_kubevirt_vm.exists
        and remove_kubevirt_vm.vmi.status == remove_kubevirt_vm.vmi.Status.RUNNING
    )


@pytest.mark.destructive
@pytest.mark.polarion("CNV-3684")
def test_remove_workloads(
    set_uninstall_strategy_remove_workloads,
    kubevirt_resource,
    remove_kubevirt_vm,
    admin_client,
):
    """WARNING: DESTRUCTIVE; DELETES ALL RUNNING CNV WORKLOADS"""

    # deletion is hard to catch with this resource because HCO re-raises it instantly
    # so we'll validate its deletion by comparing the uid before and after the
    # deletion command is sent
    old_uid = kubevirt_resource.instance.metadata.uid

    kubevirt_resource.delete()

    # ensure deletion instruction to KubeVirt resource resulted in deletion of the
    # kubevirt cr AND all vms in the cluster
    for sample in TimeoutSampler(
        wait_timeout=TIMEOUT_3MIN,
        sleep=5,
        func=lambda: list(VirtualMachine.get(dyn_client=admin_client)) or kubevirt_resource.instance.uid == old_uid,
    ):
        if not sample:
            break

    # HCO should redeploy the kubevirt cr; wait for this to finish
    kubevirt_resource.wait_for_status(status=KubeVirt.Status.DEPLOYED, timeout=TIMEOUT_4MIN)


@pytest.mark.order(after="test_remove_workloads")
@pytest.mark.polarion("CNV-3739")
@pytest.mark.destructive
def test_raise_vm_after_removal(remove_kubevirt_vm):
    assert remove_kubevirt_vm.exists and remove_kubevirt_vm.vmi.status == remove_kubevirt_vm.vmi.Status.RUNNING

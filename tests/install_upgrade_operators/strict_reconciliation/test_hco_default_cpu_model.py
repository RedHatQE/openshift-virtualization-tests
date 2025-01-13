import pytest
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.virtual_machine import VirtualMachine

from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm

HCO_CPU_MODEL_KEY = "defaultCPUModel"
KUBEVIRT_CPU_MODEL_KEY = "cpuModel"
VMI_CPU_MODEL_KEY = "host-model"

pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno]


def assert_updated_hco_default_cpu_model(hco_resource, expected_cpu_model):
    hco_cpu_model = hco_resource.instance.spec.get(HCO_CPU_MODEL_KEY)
    assert hco_cpu_model == expected_cpu_model, (
        f"HCO CPU model: '{hco_cpu_model}' doesn't match with expected CPU model: '{expected_cpu_model}"
    )


def assert_vmi_cpu_model(vmi_resource, expected_cpu_model):
    vmi_cpu_model = vmi_resource.vmi.instance.spec.domain.cpu.get("model")
    assert vmi_cpu_model == expected_cpu_model, (
        f"VMI CPU model '{vmi_cpu_model}' doesn't match with expected CPU model: '{expected_cpu_model}'"
    )


def assert_kubevirt_cpu_model(kubevirt_resource, hco_resource):
    hco_cpu_model = hco_resource.instance.spec.get(HCO_CPU_MODEL_KEY)
    kubevirt_cpu_model = kubevirt_resource.instance.spec.configuration.get(KUBEVIRT_CPU_MODEL_KEY)
    assert kubevirt_cpu_model == hco_cpu_model, (
        f"Kubevirt CPU model '{kubevirt_cpu_model}' doesn't match with the expected CPU model '{hco_cpu_model}'"
    )


def create_vm(client, namespace):
    name = "fedora-vm-for-test"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        body=fedora_vm_body(name=name),
        client=client,
        run_strategy=VirtualMachine.RunStrategy.ALWAYS,
    ) as vm:
        running_vm(
            vm=vm,
            wait_for_interfaces=False,
            check_ssh_connectivity=False,
        )
        yield vm


@pytest.fixture(scope="module")
def fedora_vm_scope_module(unprivileged_client, namespace):
    yield from create_vm(client=unprivileged_client, namespace=namespace)


@pytest.fixture()
def fedora_vm_scope_function(unprivileged_client, namespace):
    yield from create_vm(client=unprivileged_client, namespace=namespace)


@pytest.fixture()
def hco_with_default_cpu_model_set(
    hyperconverged_resource_scope_function,
    cluster_common_node_cpu,
):
    with ResourceEditorValidateHCOReconcile(
        patches={
            hyperconverged_resource_scope_function: {
                "spec": {
                    HCO_CPU_MODEL_KEY: cluster_common_node_cpu,
                },
            }
        },
        wait_for_reconcile_post_update=True,
        list_resource_reconcile=[KubeVirt],
    ):
        yield cluster_common_node_cpu


@pytest.mark.polarion("CNV-9024")
def test_default_value_for_cpu_model(
    hco_spec_scope_module,
    kubevirt_hyperconverged_spec_scope_module,
    fedora_vm_scope_module,
):
    """
    Default value for defaultCPUModel should be 'None' in HCO
    Default value for CPU model in kubevirt should be 'None'
    and for VMI should be 'host-model'
    """
    assert HCO_CPU_MODEL_KEY not in hco_spec_scope_module, (
        f"HCO is not expected to contain default value for '{HCO_CPU_MODEL_KEY}', "
        f"HCO spec values are: {hco_spec_scope_module}"
    )
    assert KUBEVIRT_CPU_MODEL_KEY not in kubevirt_hyperconverged_spec_scope_module["configuration"], (
        f"Kubevirt is not expected to default value for '{KUBEVIRT_CPU_MODEL_KEY}', "
        f"kubevirt spec values are: {kubevirt_hyperconverged_spec_scope_module}"
    )
    assert_vmi_cpu_model(
        vmi_resource=fedora_vm_scope_module,
        expected_cpu_model=VMI_CPU_MODEL_KEY,
    )


@pytest.mark.polarion("CNV-9025")
def test_set_hco_default_cpu_model(
    hyperconverged_resource_scope_function,
    hco_with_default_cpu_model_set,
    fedora_vm_scope_function,
    kubevirt_resource,
):
    """
    After HCO defaultCPUModel is set, it should reflect in
    kubevirt. New VM created should also reflect that in VMI
    """
    assert_updated_hco_default_cpu_model(
        hco_resource=hyperconverged_resource_scope_function,
        expected_cpu_model=hco_with_default_cpu_model_set,
    )
    assert_kubevirt_cpu_model(
        kubevirt_resource=kubevirt_resource,
        hco_resource=hyperconverged_resource_scope_function,
    )
    assert_vmi_cpu_model(
        vmi_resource=fedora_vm_scope_function,
        expected_cpu_model=hco_with_default_cpu_model_set,
    )


@pytest.mark.polarion("CNV-9026")
def test_set_hco_default_cpu_model_with_existing_vm(
    hyperconverged_resource_scope_function,
    fedora_vm_scope_module,
    hco_with_default_cpu_model_set,
    kubevirt_resource,
):
    """
    When HCO defaultCPUModel is set, it should reflect in kubevirt
    and also with VMI. If VM is already running even before updating
    defaultCPUModel in HCO,then restarting the VM should reflect the
    new CPU model in VMI
    """
    assert_updated_hco_default_cpu_model(
        hco_resource=hyperconverged_resource_scope_function,
        expected_cpu_model=hco_with_default_cpu_model_set,
    )
    assert_kubevirt_cpu_model(
        kubevirt_resource=kubevirt_resource,
        hco_resource=hyperconverged_resource_scope_function,
    )
    assert_vmi_cpu_model(
        vmi_resource=fedora_vm_scope_module,
        expected_cpu_model=VMI_CPU_MODEL_KEY,
    )
    fedora_vm_scope_module.restart(wait=True)
    assert_vmi_cpu_model(
        vmi_resource=fedora_vm_scope_module,
        expected_cpu_model=hco_with_default_cpu_model_set,
    )

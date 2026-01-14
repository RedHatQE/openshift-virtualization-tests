import logging

import pytest
from ocp_resources.resource import Resource
from ocp_resources.virtual_machine import VirtualMachine

from tests.observability.metrics.constants import KUBEVIRT_VMI_NODE_CPU_AFFINITY
from tests.observability.metrics.utils import toggle_emulation_in_hco, validate_vmi_node_cpu_affinity_with_prometheus
from tests.observability.utils import validate_metrics_value
from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm

KUBEVIRT_VM_TAG = f"{Resource.ApiGroup.KUBEVIRT_IO}/vm"
LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="class")
def fedora_vm_without_name_in_label(
    namespace,
    unprivileged_client,
):
    vm_name = "test-vm-label-fedora-vm"
    vm_body = fedora_vm_body(name=vm_name)
    virt_launcher_pod_labels = vm_body["spec"]["template"]["metadata"].get("labels")
    vm_label = vm_body["metadata"].get("labels")

    # Remove the label 'kubevirt.io/vm' from virt-launcher pod labels, if present
    if virt_launcher_pod_labels and virt_launcher_pod_labels.get(KUBEVIRT_VM_TAG):
        del virt_launcher_pod_labels[KUBEVIRT_VM_TAG]

    if vm_label and vm_label.get(KUBEVIRT_VM_TAG):
        del vm_label[KUBEVIRT_VM_TAG]

    # Create VM, after removal of label 'kubevirt.io/vm' from virt-launcher pod
    with VirtualMachineForTests(
        name=vm_name,
        namespace=namespace.name,
        body=vm_body,
        client=unprivileged_client,
        run_strategy=VirtualMachine.RunStrategy.ALWAYS,
    ) as vm:
        running_vm(vm=vm, wait_for_interfaces=False, check_ssh_connectivity=False)
        yield vm


class TestVmiNodeCpuAffinityLinux:
    @pytest.mark.polarion("CNV-7295")
    @pytest.mark.s390x
    def test_kubevirt_vmi_node_cpu_affinity(
        self,
        prometheus,
        vm_with_cpu_spec,
        expected_cpu_affinity_metric_value,
    ):
        validate_metrics_value(
            prometheus=prometheus,
            metric_name=KUBEVIRT_VMI_NODE_CPU_AFFINITY.format(vm_name=vm_with_cpu_spec.name),
            expected_value=expected_cpu_affinity_metric_value,
        )


@pytest.mark.tier3
class TestVmiNodeCpuAffinityWindows:
    @pytest.mark.polarion("CNV-11883")
    def test_kubevirt_vmi_node_cpu_affinity_windows_vm(self, prometheus, windows_vm_for_test):
        validate_vmi_node_cpu_affinity_with_prometheus(
            vm=windows_vm_for_test,
            prometheus=prometheus,
        )


class TestVmNameInLabel:
    @pytest.mark.polarion("CNV-8582")
    @pytest.mark.s390x
    def test_vm_name_in_virt_launcher_label(self, fedora_vm_without_name_in_label):
        """
        when VM created from vm.yaml,for the kind=VirtualMachine, doesn't have
        the VM name in label, then virt-launcher pod should have the
        VM name in the label populated automatically
        """
        # Get the label of virt-launcher pod
        virt_launcher_pod_labels = fedora_vm_without_name_in_label.vmi.virt_launcher_pod.labels
        vm_name = fedora_vm_without_name_in_label.name
        assert virt_launcher_pod_labels.get(f"{Resource.ApiGroup.VM_KUBEVIRT_IO}/name") == vm_name, (
            f"VM name {vm_name} is missing in the virt-launcher pod label"
            f"Content of virt-launcher pod label: {virt_launcher_pod_labels}"
        )


class TestVirtHCOSingleStackIpv6:
    @pytest.mark.ipv6
    @pytest.mark.polarion("CNV-11740")
    @pytest.mark.s390x
    def test_metric_kubevirt_hco_single_stack_ipv6(self, prometheus, ipv6_single_stack_cluster):
        validate_metrics_value(
            prometheus=prometheus,
            metric_name="kubevirt_hco_single_stack_ipv6",
            expected_value="1" if ipv6_single_stack_cluster else "0",
        )


class TestConfigurationEmulationEnabled:
    @pytest.mark.polarion("CNV-99999")
    def test_kubevirt_configuration_emulation_enabled(
        self,
        admin_client,
        hco_namespace,
        prometheus,
        hyperconverged_resource_scope_class,
        emulation_config_value,
    ):
        new_emulation_value = not emulation_config_value
        with toggle_emulation_in_hco(
            admin_client=admin_client,
            hco_namespace=hco_namespace,
            hyperconverged_resource=hyperconverged_resource_scope_class,
            enable_emulation=new_emulation_value,
        ):
            validate_metrics_value(
                prometheus=prometheus,
                metric_name="kubevirt_configuration_emulation_enabled",
                expected_value="1" if new_emulation_value else "0",
            )

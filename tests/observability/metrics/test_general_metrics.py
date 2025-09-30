import logging

import pytest
from ocp_resources.resource import Resource
from ocp_resources.virtual_machine import VirtualMachine
from pytest_testconfig import config as py_config

from tests.observability.metrics.utils import (
    validate_vmi_node_cpu_affinity_with_prometheus,
)
from tests.observability.utils import validate_metrics_value
from tests.os_params import RHEL_LATEST, RHEL_LATEST_LABELS, RHEL_LATEST_OS
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
        running_vm(vm=vm, check_ssh_connectivity=False)
        yield vm


class TestVmiNodeCpuAffinityLinux:
    @pytest.mark.parametrize(
        "golden_image_data_volume_scope_class, vm_from_template_scope_class",
        [
            pytest.param(
                {
                    "dv_name": RHEL_LATEST_OS,
                    "image": RHEL_LATEST["image_path"],
                    "storage_class": py_config["default_storage_class"],
                    "dv_size": RHEL_LATEST["dv_size"],
                },
                {
                    "vm_name": "rhel-latest",
                    "template_labels": RHEL_LATEST_LABELS,
                    "guest_agent": False,
                    "ssh": False,
                },
            ),
        ],
        indirect=True,
    )
    @pytest.mark.polarion("CNV-7295")
    @pytest.mark.s390x
    def test_kubevirt_vmi_node_cpu_affinity(self, prometheus, vm_from_template_scope_class):
        validate_vmi_node_cpu_affinity_with_prometheus(
            vm=vm_from_template_scope_class,
            prometheus=prometheus,
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

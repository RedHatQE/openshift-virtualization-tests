# -*- coding: utf-8 -*-

"""
HA VM reboot and provisioning scenario tests.
"""

import logging

import pytest
from ocp_resources.machine_health_check import MachineHealthCheck
from ocp_resources.template import Template
from pytest_testconfig import config as py_config

from utilities.constants import TIMEOUT_20MIN
from utilities.infra import ExecCommandOnPod, wait_for_node_status
from utilities.virt import (
    VirtualMachineForTests,
    VirtualMachineForTestsFromTemplate,
    fedora_vm_body,
    running_vm,
)

pytestmark = pytest.mark.destructive

LOGGER = logging.getLogger(__name__)
DV_DICT = {
    "dv_name": py_config["latest_fedora_os_dict"]["template_labels"]["os"],
    "image": py_config["latest_fedora_os_dict"]["image_path"],
    "dv_size": py_config["latest_fedora_os_dict"]["dv_size"],
    "storage_class": "nfs",
    "access_modes": "ReadWriteMany",
    "volume_mode": "Filesystem",
}


@pytest.fixture()
def machine_health_check_reboot(worker_machine1):
    with MachineHealthCheck(
        name="ha-vm-mhc",
        namespace=worker_machine1.namespace,
        cluster_name=worker_machine1.cluster_name,
        machineset_name=worker_machine1.machineset_name,
        unhealthy_timeout="60s",
        reboot_strategy=True,
    ) as mhc:
        yield mhc


@pytest.fixture()
def ha_vm_container_disk(request, unprivileged_client, namespace):
    run_strategy = request.param["run_strategy"]
    name = f"ha-vm-container-disk-{run_strategy}".lower()
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        body=fedora_vm_body(name=name),
        client=unprivileged_client,
        run_strategy=run_strategy,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture()
def ha_vm_dv_disk(request, unprivileged_client, namespace, golden_image_data_source_scope_function):
    run_strategy = request.param["run_strategy"]
    name = f"ha-vm-dv-disk-{run_strategy}".lower()
    with VirtualMachineForTestsFromTemplate(
        name=name,
        namespace=namespace.name,
        client=unprivileged_client,
        labels=Template.generate_template_labels(**py_config["latest_fedora_os_dict"]["template_labels"]),
        data_source=golden_image_data_source_scope_function,
        run_strategy=run_strategy,
    ) as vm:
        running_vm(vm=vm)
        yield vm


def stop_kubelet_on_node(utility_pods, node):
    LOGGER.info(f"Stopping kubelet on node {node.name}")
    ExecCommandOnPod(utility_pods=utility_pods, node=node).exec(command="sudo systemctl stop kubelet.service")
    wait_for_node_status(node=node, status=False)


def wait_and_verify_vmi_failover(vm):
    LOGGER.info(f"Waiting VMI {vm.vmi.name} failover to new node")
    old_uid = vm.vmi.instance.metadata.uid
    old_node = vm.vmi.node

    if vm.instance.spec.runStrategy == "Manual":
        vm.vmi.wait_for_status(status="Failed")
    else:
        vm.vmi.wait_for_status(status="Scheduling")
    running_vm(vm=vm)

    new_uid = vm.vmi.instance.metadata.uid
    new_node = vm.vmi.node

    assert old_uid != new_uid, "Old VMI still exists"
    assert old_node.name != new_node.name, "VMI still on old node"
    vm.ssh_exec.run_command(command=["cat", "/etc/os-release"])


def wait_node_restored(node):
    LOGGER.info(f"Waiting node {node.name} to be added to cluster and Ready")
    node.wait(timeout=TIMEOUT_20MIN)
    wait_for_node_status(node=node)


@pytest.mark.parametrize(
    "ha_vm_container_disk",
    [
        pytest.param(
            {"run_strategy": "Always"},
            marks=pytest.mark.polarion("CNV-4152"),
            id="case: Always",
        ),
        pytest.param(
            {"run_strategy": "RerunOnFailure"},
            marks=pytest.mark.polarion("CNV-4154"),
            id="case: RerunOnFailure",
        ),
        pytest.param(
            {"run_strategy": "Manual"},
            marks=pytest.mark.polarion("CNV-4155"),
            id="case: Manual",
        ),
    ],
    indirect=True,
)
def test_ha_vm_container_disk_reboot(
    workers_utility_pods,
    machine_health_check_reboot,
    ha_vm_container_disk,
):
    orig_node = ha_vm_container_disk.vmi.node
    stop_kubelet_on_node(utility_pods=workers_utility_pods, node=orig_node)
    wait_and_verify_vmi_failover(vm=ha_vm_container_disk)
    wait_node_restored(node=orig_node)


@pytest.mark.parametrize(
    "golden_image_data_volume_scope_function, ha_vm_dv_disk",
    [
        pytest.param(
            DV_DICT,
            {"run_strategy": "Always"},
            marks=pytest.mark.polarion("CNV-5212"),
            id="case: Always",
        ),
        pytest.param(
            DV_DICT,
            {"run_strategy": "RerunOnFailure"},
            marks=pytest.mark.polarion("CNV-5213"),
            id="case: RerunOnFailure",
        ),
        pytest.param(
            DV_DICT,
            {"run_strategy": "Manual"},
            marks=pytest.mark.polarion("CNV-5214"),
            id="case: Manual",
        ),
    ],
    indirect=True,
)
def test_ha_vm_dv_disk_reboot(
    workers_utility_pods,
    machine_health_check_reboot,
    ha_vm_dv_disk,
):
    orig_node = ha_vm_dv_disk.vmi.node
    ha_vm_dv_disk.ssh_exec.run_command(command=["echo", "test", ">>", "ha-test"])
    stop_kubelet_on_node(utility_pods=workers_utility_pods, node=orig_node)
    wait_and_verify_vmi_failover(vm=ha_vm_container_disk)
    wait_node_restored(node=orig_node)
    assert "test" in ha_vm_dv_disk.ssh_exec.run_command(["cat", "ha-test"])[1], (
        "Content of file lost during VM failover"
    )

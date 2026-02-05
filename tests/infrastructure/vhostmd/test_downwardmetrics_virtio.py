import logging
import re
import shlex
from xml.etree import ElementTree

import pytest
from kubernetes.dynamic.exceptions import (
    ResourceNotFoundError,
    UnprocessibleEntityError,
)
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.resource import Resource
from ocp_resources.virtual_machine import VirtualMachine
from ocp_resources.virtual_machine_cluster_instancetype import (
    VirtualMachineClusterInstancetype,
)
from ocp_resources.virtual_machine_cluster_preference import (
    VirtualMachineClusterPreference,
)
from pyhelper_utils.shell import run_ssh_commands

from utilities.constants import OS_FLAVOR_RHEL
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.virt import VirtualMachineForTests, wait_for_running_vm

LOGGER = logging.getLogger(__name__)

EXPECTED_METRICS = {
    ("HostName", "string", "host"),
    ("HostSystemInfo", "string", "host"),
    ("VirtualizationVendor", "string", "host"),
    ("VirtProductInfo", "string", "host"),
    ("TotalCPUTime", "real64", "vm"),
    ("ResourceProcessorLimit", "uint64", "vm"),
    ("PhysicalMemoryAllocatedToVirtualSystem", "uint64", "vm"),
    ("ResourceMemoryLimit", "uint64", "vm"),
    ("NumberOfPhysicalCPUs", "int64", "host"),
    ("TotalCPUTime", "real64", "host"),
    ("FreePhysicalMemory", "uint64", "host"),
    ("FreeVirtualMemory", "uint64", "host"),
    ("MemoryAllocatedToVirtualServers", "uint64", "host"),
    ("UsedVirtualMemory", "uint64", "host"),
    ("PagedInMemory", "uint64", "host"),
    ("PagedOutMemory", "uint64", "host"),
    ("Time", "int64", "host"),
}


class VirtualMachineWithDownwardMetrics(VirtualMachineForTests):
    """
    class represents a virtual machine with downward metrics
    Refer: https://kubevirt.io/user-guide/virtual_machines/disks_and_volumes/#virtio-serial-port
    """

    def to_dict(self):
        super().to_dict()
        self.res["spec"]["template"]["spec"]["domain"]["devices"]["downwardMetrics"] = {}


def parse_metrics_collected(metrics_collected):
    return {
        (metric.find("name").text, metric.get("type"), metric.get("context"))
        for metric in ElementTree.fromstring(metrics_collected).findall(".//metric")
    }


def parsed_metrics_command_data(vm):
    """
    Collect metrics from a VM using the vhostmd interface.
    To collect XML-formatted metrics data from the virtio-port /dev/virtio-ports/org.github.vhostmd.1
    RHEL9 doesn't support vm-metric-dump

    1. Send a GET request to the /metrics/XML endpoint.
    2. awk to read the content of the file till we get </metrics> and exit.

    Args:
        vm : The VM object to collect metrics from.

    Returns:
        dict: dictionary containing the parsed metrics.
    """
    virtio_file = "/dev/virtio-ports/org.github.vhostmd.1"
    return parse_metrics_collected(
        metrics_collected=run_ssh_commands(
            host=vm.ssh_exec,
            commands=shlex.split(
                f"sudo sh -c 'printf \"GET /metrics/XML\\n\\n\" > {virtio_file}' "
                f"&& sudo awk '/<\\/metrics>/{{print; exit}} 1' {virtio_file}"
            ),
        )[0]
    )


@pytest.fixture()
def enabled_feature_gate_for_downward_metrics_scope_function(
    hyperconverged_resource_scope_function,
):
    with ResourceEditorValidateHCOReconcile(
        patches={hyperconverged_resource_scope_function: {"spec": {"featureGates": {"downwardMetrics": True}}}},
        list_resource_reconcile=[KubeVirt],
        wait_for_reconcile_post_update=True,
    ):
        yield


@pytest.fixture()
def rhel_version(cnv_rhel_container_disk_images_matrix__function__):
    return next(iter(cnv_rhel_container_disk_images_matrix__function__))


@pytest.fixture()
def rhel_container_disk_image(rhel_version, cnv_rhel_container_disk_images_matrix__function__):
    return cnv_rhel_container_disk_images_matrix__function__[rhel_version]["RHEL_CONTAINER_DISK_IMAGE"]


@pytest.fixture()
def preferred_cluster_instance_type(unprivileged_client):
    instance_type_selector = (
        f"{Resource.ApiGroup.INSTANCETYPE_KUBEVIRT_IO}/class=general.purpose, "
        f"{Resource.ApiGroup.INSTANCETYPE_KUBEVIRT_IO}/cpu=1, "
        f"{Resource.ApiGroup.INSTANCETYPE_KUBEVIRT_IO}/memory in (2Gi, 4Gi)"
    )
    return next(
        VirtualMachineClusterInstancetype.get(client=unprivileged_client, label_selector=instance_type_selector)
    )


@pytest.fixture()
def preferred_preference_for_rhel_version(rhel_version, unprivileged_client):
    preference_name = re.sub(r"(\D+)(\d+)", r"\1.\2", rhel_version)
    preference_object = VirtualMachineClusterPreference(name=preference_name, client=unprivileged_client)
    if preference_object.exists:
        return preference_object
    raise ResourceNotFoundError(f"VirtualMachineClusterPreference {preference_name} not found")


@pytest.fixture()
def vm_parameters_for_virtio_downward_metrics(
    namespace,
    unprivileged_client,
    rhel_version,
    preferred_preference_for_rhel_version,
    preferred_cluster_instance_type,
    rhel_container_disk_image,
):
    return {
        "name": f"{rhel_version}-vm-downwardmetrics",
        "namespace": namespace.name,
        "client": unprivileged_client,
        "vm_preference": preferred_preference_for_rhel_version,
        "vm_instance_type": preferred_cluster_instance_type,
        "image": rhel_container_disk_image,
        "os_flavor": OS_FLAVOR_RHEL,
        "run_strategy": VirtualMachine.RunStrategy.ALWAYS,
    }


@pytest.fixture()
def vm_ready_for_tests(vm_parameters_for_virtio_downward_metrics):
    with VirtualMachineWithDownwardMetrics(**vm_parameters_for_virtio_downward_metrics) as vm:
        wait_for_running_vm(vm=vm)
        yield vm


@pytest.mark.polarion("CNV-10937")
@pytest.mark.s390x
def test_downward_metrics_virtio_serial_port_default(
    vm_parameters_for_virtio_downward_metrics,
):
    with pytest.raises(
        UnprocessibleEntityError,
        match=r".*DownwardMetrics feature gate is not enabled*",
    ):
        with VirtualMachineWithDownwardMetrics(**vm_parameters_for_virtio_downward_metrics):
            pytest.fail("Expected Failure due to UnprocessibleEntityError")


@pytest.mark.polarion("CNV-10808")
def test_downward_metrics_virtio_serial_port(
    enabled_feature_gate_for_downward_metrics_scope_function, vm_ready_for_tests
):
    metrics_collected = parsed_metrics_command_data(vm=vm_ready_for_tests)
    assert EXPECTED_METRICS == metrics_collected, (
        "Both metrics are not equal. Here are the details:\n"
        f"Expected Metrics: {EXPECTED_METRICS}\n"
        f"Collected Metrics: {metrics_collected}\n"
        f"Extra metrics in collected metrics: {metrics_collected - EXPECTED_METRICS}"
    )

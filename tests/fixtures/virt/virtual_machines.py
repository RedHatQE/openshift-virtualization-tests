import bitmath
import pytest
from pytest_testconfig import config as py_config

from utilities.artifactory import get_test_artifact_server_url
from utilities.constants.virt import NODE_HUGE_PAGES_1GI_KEY, VIRTIO
from utilities.virt import (
    VirtualMachineForTests,
    fedora_vm_body,
    running_vm,
    start_and_fetch_processid_on_linux_vm,
    vm_instance_from_template,
    wait_for_windows_vm,
)


@pytest.fixture(scope="session")
def rhel_latest_os_params():
    """This fixture is needed as during collection pytest_testconfig is empty.
    os_params or any globals using py_config in conftest cannot be used.
    """
    if latest_rhel_dict := py_config.get("latest_rhel_os_dict"):
        return {
            "rhel_image_path": f"{get_test_artifact_server_url()}{latest_rhel_dict['image_path']}",
            "rhel_dv_size": latest_rhel_dict["dv_size"],
            "rhel_template_labels": latest_rhel_dict["template_labels"],
        }

    raise ValueError("Failed to get latest RHEL OS parameters")


@pytest.fixture(scope="class")
def vm_for_migration_test(request, namespace, unprivileged_client, cpu_for_migration):
    vm_name = request.param
    with VirtualMachineForTests(
        client=unprivileged_client,
        name=vm_name,
        body=fedora_vm_body(name=vm_name),
        cpu_model=cpu_for_migration,
        namespace=namespace.name,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture(scope="class")
def vm_for_test(request, namespace, unprivileged_client):
    vm_name = request.param
    with VirtualMachineForTests(
        client=unprivileged_client,
        name=vm_name,
        body=fedora_vm_body(name=vm_name),
        namespace=namespace.name,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture(scope="class")
def running_metric_vm(namespace, unprivileged_client):
    name = "running-metrics-vm"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        body=fedora_vm_body(name=name),
        client=unprivileged_client,
        network_model=VIRTIO,
    ) as vm:
        running_vm(vm=vm, wait_for_cloud_init=True)
        yield vm


@pytest.fixture()
def vm_from_template_with_existing_dv(
    request,
    unprivileged_client,
    namespace,
    data_volume_scope_function,
):
    """create VM from template using an existing DV (and not a golden image)"""
    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        existing_data_volume=data_volume_scope_function,
    ) as vm:
        yield vm


@pytest.fixture()
def started_windows_vm(
    request,
    vm_instance_from_template_multi_storage_scope_function,
):
    wait_for_windows_vm(
        vm=vm_instance_from_template_multi_storage_scope_function,
        version=request.param["os_version"],
    )


@pytest.fixture(scope="module")
def skip_if_no_cpumanager_workers(schedulable_nodes):
    if not any([node.labels.cpumanager == "true" for node in schedulable_nodes]):
        pytest.skip("Test should run on cluster with CPU Manager")


@pytest.fixture(scope="class")
def ping_process_in_rhel_os():
    def _start_ping(vm):
        return start_and_fetch_processid_on_linux_vm(
            vm=vm,
            process_name="ping",
            args="localhost",
        )

    return _start_ping


@pytest.fixture(scope="session")
def hugepages_gib_values(workers):
    """Return the list of hugepage sizes (in GiB) across all worker nodes."""
    return [
        int(bitmath.parse_string(value, strict=False).GiB)
        for worker in workers
        if (value := worker.instance.status.allocatable.get(NODE_HUGE_PAGES_1GI_KEY))
    ]

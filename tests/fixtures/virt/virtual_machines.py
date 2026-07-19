import pytest
from ocp_resources.virtual_machine_cluster_instancetype import VirtualMachineClusterInstancetype
from ocp_resources.virtual_machine_cluster_preference import VirtualMachineClusterPreference
from pytest_testconfig import config as py_config

from utilities.artifactory import get_test_artifact_server_url
from utilities.constants import Images
from utilities.constants.images import OS_FLAVOR_RHEL
from utilities.constants.instance_types import (
    EXPECTED_CLUSTER_INSTANCE_TYPE_LABELS,
    INSTANCE_TYPE_STR,
    PREFERENCE_STR,
)
from utilities.constants.timeouts import TIMEOUT_5MIN
from utilities.constants.virt import VIRTIO
from utilities.virt import (
    VirtualMachineForTests,
    fedora_vm_body,
    running_vm,
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


@pytest.fixture(scope="class")
def rhel_vm_with_instance_type_and_preference(
    namespace,
    unprivileged_client,
    instance_type_for_test_scope_class,
    vm_preference_for_test,
):
    with (
        instance_type_for_test_scope_class as vm_instance_type,
        vm_preference_for_test as vm_preference,
    ):
        with VirtualMachineForTests(
            client=unprivileged_client,
            name="rhel-vm-with-instance-type",
            namespace=namespace.name,
            image=Images.Rhel.RHEL9_REGISTRY_GUEST_IMG,
            vm_instance_type=vm_instance_type,
            vm_preference=vm_preference,
        ) as vm:
            yield vm


@pytest.fixture(scope="class")
def rhel_vm_with_cluster_instance_type_and_preference(namespace, unprivileged_client):
    with VirtualMachineForTests(
        name="rhel-vm-with-clustertype-resources",
        image=Images.Rhel.RHEL9_REGISTRY_GUEST_IMG,
        namespace=namespace.name,
        client=unprivileged_client,
        vm_instance_type=VirtualMachineClusterInstancetype(
            name=EXPECTED_CLUSTER_INSTANCE_TYPE_LABELS[INSTANCE_TYPE_STR]
        ),
        vm_preference=VirtualMachineClusterPreference(name=EXPECTED_CLUSTER_INSTANCE_TYPE_LABELS[PREFERENCE_STR]),
        os_flavor=OS_FLAVOR_RHEL,
    ) as vm:
        running_vm(
            vm=vm,
            wait_for_interfaces=False,
            ssh_timeout=TIMEOUT_5MIN,
            wait_for_cloud_init=True,
        )
        yield vm

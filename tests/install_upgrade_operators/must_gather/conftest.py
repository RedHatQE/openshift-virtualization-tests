import logging
import os
import re
import shlex

import pytest
import yaml
from kubernetes.dynamic.exceptions import ResourceNotFoundError
from ocp_resources.config_map import ConfigMap
from ocp_resources.custom_resource_definition import CustomResourceDefinition
from ocp_resources.pod import Pod
from ocp_resources.resource import Resource
from ocp_resources.virtual_machine_instancetype import VirtualMachineInstancetype
from ocp_resources.virtual_machine_preference import VirtualMachinePreference

from tests.install_upgrade_operators.constants import FILE_SUFFIX, SECTION_TITLE
from tests.install_upgrade_operators.must_gather.utils import (
    BRIDGE_COMMAND,
    MUST_GATHER_VM_NAME_PREFIX,
    clean_up_collected_must_gather,
    get_must_gather_dir,
)
from tests.utils import create_vms
from utilities.constants import LINUX_BRIDGE
from utilities.exceptions import MissingResourceException
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.infra import (
    create_ns,
    get_node_selector_dict,
)
from utilities.must_gather import collect_must_gather, run_must_gather
from utilities.network import (
    network_device,
    network_nad,
    wait_for_node_marked_by_bridge,
)
from utilities.storage import add_dv_to_vm
from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm

LOGGER = logging.getLogger(__name__)
LONG_VM_NAME = "v" * 63


@pytest.fixture(scope="module")
def must_gather_tmpdir_scope_module(tmpdir_factory):
    return get_must_gather_dir(directory_name="must_gather_scope_module")


@pytest.fixture(scope="module")
def must_gather_tmpdir_all_images(tmpdir_factory):
    return get_must_gather_dir(directory_name="must_gather_all_images")


@pytest.fixture()
def must_gather_tmpdir_scope_function(request, tmpdir_factory):
    return get_must_gather_dir(directory_name=f"must_gather_{request.node.callspec.id}")


@pytest.fixture(scope="module")
def collected_cluster_must_gather(
    request,
    must_gather_tmpdir_scope_module,
    must_gather_image_url,
):
    before_fail_count = request.session.testsfailed
    LOGGER.warning(f"Before fixture failures {before_fail_count}")
    target_path = os.path.join(must_gather_tmpdir_scope_module, "collected_cluster_must_gather_module")
    yield collect_must_gather(
        must_gather_tmpdir=target_path,
        must_gather_image_url=must_gather_image_url,
    )
    clean_up_collected_must_gather(failed=(request.session.testsfailed - before_fail_count), target_path=target_path)


@pytest.fixture(scope="class")
def collected_cluster_must_gather_with_vms(
    request,
    must_gather_tmpdir_scope_module,
    must_gather_image_url,
    must_gather_vm,
):
    before_fail_count = request.session.testsfailed
    target_path = os.path.join(must_gather_tmpdir_scope_module, "collected_cluster_must_gather_with_vms")
    yield collect_must_gather(
        must_gather_tmpdir=target_path,
        must_gather_image_url=must_gather_image_url,
    )
    clean_up_collected_must_gather(failed=(request.session.testsfailed - before_fail_count), target_path=target_path)


@pytest.fixture(scope="class")
def collected_vm_details_must_gather(
    request,
    must_gather_tmpdir_scope_module,
    must_gather_image_url,
):
    before_fail_count = request.session.testsfailed
    target_path = os.path.join(must_gather_tmpdir_scope_module, "collected_must_gather_vm_details_class")
    yield collect_must_gather(
        must_gather_tmpdir=target_path,
        must_gather_image_url=must_gather_image_url,
        flag_names="vms_details",
    )
    clean_up_collected_must_gather(failed=(request.session.testsfailed - before_fail_count), target_path=target_path)


@pytest.fixture()
def collected_vm_details_must_gather_function_scope(
    request,
    must_gather_tmpdir_scope_module,
    must_gather_image_url,
):
    before_fail_count = request.session.testsfailed
    target_path = os.path.join(must_gather_tmpdir_scope_module, "collected_vm_details_must_gather_function_scope")
    yield collect_must_gather(
        must_gather_tmpdir=target_path,
        must_gather_image_url=must_gather_image_url,
        flag_names="vms_details",
    )
    clean_up_collected_must_gather(failed=(request.session.testsfailed - before_fail_count), target_path=target_path)


@pytest.fixture(scope="module")
def custom_resource_definitions(admin_client):
    yield list(CustomResourceDefinition.get(dyn_client=admin_client))


@pytest.fixture(scope="module")
def kubevirt_crd_resources(admin_client, custom_resource_definitions):
    kubevirt_resources = []
    for resource in custom_resource_definitions:
        if "kubevirt.io" in resource.instance.spec.group:
            kubevirt_resources.append(resource)
    return kubevirt_resources


@pytest.fixture(scope="module")
def kubevirt_crd_names(kubevirt_crd_resources):
    return [crd.name for crd in kubevirt_crd_resources]


@pytest.fixture()
def kubevirt_crd_by_type(cnv_crd_matrix__function__, kubevirt_crd_resources, kubevirt_crd_names):
    for crd in kubevirt_crd_resources:
        if crd.name == cnv_crd_matrix__function__:
            return crd
    raise ResourceNotFoundError(f"CRD: {cnv_crd_matrix__function__} not found in kubevirt crds: {kubevirt_crd_names}")


@pytest.fixture(scope="package")
def must_gather_nad(must_gather_bridge, node_gather_unprivileged_namespace, worker_node1):
    with network_nad(
        nad_type=must_gather_bridge.bridge_type,
        nad_name=must_gather_bridge.bridge_name,
        interface_name=must_gather_bridge.bridge_name,
        namespace=node_gather_unprivileged_namespace,
    ) as must_gather_nad:
        wait_for_node_marked_by_bridge(bridge_nad=must_gather_nad, node=worker_node1)
        yield must_gather_nad


@pytest.fixture(scope="package")
def must_gather_bridge(worker_node1):
    with network_device(
        interface_type=LINUX_BRIDGE,
        nncp_name="must-gather-br",
        interface_name="mg-br1",
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
    ) as br:
        yield br


@pytest.fixture(scope="module")
def running_hco_containers(admin_client, hco_namespace):
    pods = []
    for pod in Pod.get(dyn_client=admin_client, namespace=hco_namespace.name):
        for container in pod.instance["status"].get("containerStatuses", []):
            if container["ready"]:
                pods.append((pod, container))
    assert pods, f"No running pods in the {hco_namespace.name} namespace were found."
    return pods


@pytest.fixture(scope="package")
def node_gather_unprivileged_namespace(unprivileged_client):
    yield from create_ns(
        unprivileged_client=unprivileged_client,
        name="node-gather-unprivileged",
    )


@pytest.fixture(scope="package")
def must_gather_vm(
    node_gather_unprivileged_namespace,
    must_gather_bridge,
    must_gather_nad,
    unprivileged_client,
):
    name = f"{MUST_GATHER_VM_NAME_PREFIX}-2"
    networks = {must_gather_bridge.bridge_name: must_gather_bridge.bridge_name}

    with VirtualMachineForTests(
        client=unprivileged_client,
        namespace=node_gather_unprivileged_namespace.name,
        name=name,
        networks=networks,
        interfaces=sorted(networks.keys()),
        body=fedora_vm_body(name=name),
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture(scope="class")
def must_gather_vm_scope_class(
    node_gather_unprivileged_namespace,
    must_gather_bridge,
    must_gather_nad,
    unprivileged_client,
):
    name = f"{MUST_GATHER_VM_NAME_PREFIX}-enabled-guest-console-log"
    networks = {must_gather_bridge.bridge_name: must_gather_bridge.bridge_name}

    with VirtualMachineForTests(
        client=unprivileged_client,
        namespace=node_gather_unprivileged_namespace.name,
        name=name,
        networks=networks,
        interfaces=sorted(networks.keys()),
        body=fedora_vm_body(name=name),
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture(scope="function")
def resource_type(request, admin_client):
    resource_type = request.param
    if not next(resource_type.get(dyn_client=admin_client), None):
        raise MissingResourceException(resource_type.__name__)
    return resource_type


@pytest.fixture(scope="function")
def config_map_by_name(request, admin_client):
    cm_name, cm_namespace = request.param
    return ConfigMap(name=cm_name, namespace=cm_namespace)


@pytest.fixture(scope="class")
def config_maps_file(hco_namespace, collected_cluster_must_gather):
    with open(
        f"{collected_cluster_must_gather}/namespaces/{hco_namespace.name}/core/configmaps.yaml",
        "r",
    ) as config_map_file:
        return yaml.safe_load(config_map_file)


@pytest.fixture(scope="package")
def nad_mac_address(must_gather_nad, must_gather_vm):
    return [
        interface["macAddress"]
        for interface in must_gather_vm.get_interfaces()
        if interface["name"] == must_gather_nad.name
    ][0]


@pytest.fixture(scope="package")
def vm_interface_name(nad_mac_address, must_gather_vm):
    bridge_command = f"bridge fdb show | grep {nad_mac_address}"
    output = (
        must_gather_vm.privileged_vmi.virt_launcher_pod.execute(
            command=shlex.split(f"bash -c {shlex.quote(bridge_command)}"),
            container="compute",
        )
        .splitlines()[0]
        .strip()
    )
    return output.split(" ")[-1]


@pytest.fixture()
def extracted_data_from_must_gather_file(
    request,
    collected_vm_details_must_gather,
    must_gather_vm,
    nftables_ruleset_from_utility_pods,
):
    virt_launcher = must_gather_vm.vmi.virt_launcher_pod
    namespace = virt_launcher.namespace
    vm_name = must_gather_vm.name
    file_suffix = request.param[FILE_SUFFIX]
    section_title = request.param[SECTION_TITLE]
    base_path = os.path.join(
        collected_vm_details_must_gather,
        f"namespaces/{namespace}/vms/{vm_name}",
    )
    if file_suffix == "qemu.log":
        gathered_data_path = os.path.join(
            base_path,
            f"{namespace}_{vm_name}.log",
        )
    else:
        gathered_data_path = os.path.join(
            base_path,
            f"{virt_launcher.name}.{file_suffix}",
        )
    assert os.path.exists(gathered_data_path), f"Have not found gathered data file on given path {gathered_data_path}"

    with open(gathered_data_path) as _file:
        gathered_data = _file.read()
        # If the gathered data file consists of multiple sections, extract the one
        # we are interested in.
        if section_title:
            # if section_title is present in the file getting checked out, we would then collect
            # only the sample section, for further checking:
            # bridge fdb show:
            # ###################################
            # 33:33:00:00:00:01 dev eth0 self permanent
            # 01:00:5e:00:00:01 dev eth0 self permanent
            matches = re.findall(
                f"^{section_title}\n^#+\n(.*?)(?:^#+\n|\\Z)",
                gathered_data,
                re.MULTILINE | re.DOTALL,
            )
            assert matches, (
                "Section has not been found in gathered data.\n"
                f"Section title: {section_title}\n"
                f"Gathered data: {gathered_data}"
            )
            gathered_data = matches[0]
        return gathered_data


@pytest.fixture(scope="class")
def executed_bridge_link_show_command(must_gather_vm):
    output = (
        must_gather_vm.privileged_vmi.virt_launcher_pod.execute(
            command=shlex.split(f"bash -c {shlex.quote(BRIDGE_COMMAND)}"),
            container="compute",
        )
        .splitlines()[0]
        .strip()
    )
    LOGGER.info(f"Bridge command output: {output}")
    return output.split(" ")[-1]


@pytest.fixture()
def collected_nft_files_must_gather(workers_utility_pods, must_gather_for_test):
    expected_files_dict = {
        pod.node.name: f"{must_gather_for_test}/nodes/{pod.node.name}/nftables" for pod in workers_utility_pods
    }
    files_not_found = [file for file in expected_files_dict.values() if not os.path.exists(file)]
    assert not files_not_found, f"Missing nftable files: {files_not_found}"
    return expected_files_dict


@pytest.fixture()
def nftables_from_utility_pods(workers_utility_pods):
    return {
        pod.node.name: pod.execute(
            command=shlex.split(f"bash -c {shlex.quote('nft list tables 2>/dev/null')}")
        ).splitlines()
        for pod in workers_utility_pods
    }


@pytest.fixture()
def collected_vm_details_must_gather_with_params(
    request,
    must_gather_image_url,
    must_gather_vm,
    must_gather_tmpdir_scope_function,
    must_gather_alternate_namespace,
    must_gather_vms_from_alternate_namespace,
):
    before_fail_count = request.session.testsfailed
    command = request.param["command"]
    if "vm_name" in command:
        command = command.format(
            alternate_namespace=must_gather_alternate_namespace.name,
            vm_name=must_gather_vms_from_alternate_namespace[0].name,
        )
    elif "vm_list" in command:
        command = command.format(
            alternate_namespace=must_gather_alternate_namespace.name,
            vm_list=f"{must_gather_vms_from_alternate_namespace[0].name},"
            f"{must_gather_vms_from_alternate_namespace[1].name},"
            f"{must_gather_vms_from_alternate_namespace[2].name}",
        )
    else:
        command = command.format(alternate_namespace=must_gather_alternate_namespace.name)
    target_path = os.path.join(must_gather_tmpdir_scope_function, "collected_vm_details_must_gather_with_params")

    yield collect_must_gather(
        must_gather_tmpdir=target_path,
        must_gather_image_url=must_gather_image_url,
        script_name=f"{command} /usr/bin/gather",
        flag_names="vms_details",
    )
    clean_up_collected_must_gather(failed=(request.session.testsfailed - before_fail_count), target_path=target_path)


@pytest.fixture(scope="class")
def must_gather_alternate_namespace(unprivileged_client):
    yield from create_ns(
        unprivileged_client=unprivileged_client,
        name="must-gather-alternate",
    )


@pytest.fixture(scope="class")
def must_gather_vms_alternate_namespace_base_path(collected_vm_details_must_gather, must_gather_alternate_namespace):
    return f"{collected_vm_details_must_gather}/namespaces/{must_gather_alternate_namespace.name}/"


@pytest.fixture(scope="class")
def must_gather_vms_from_alternate_namespace(
    must_gather_alternate_namespace,
    unprivileged_client,
):
    vms_list = create_vms(
        name_prefix=MUST_GATHER_VM_NAME_PREFIX,
        namespace_name=must_gather_alternate_namespace.name,
        vm_count=5,
    )
    for vm in vms_list:
        running_vm(vm=vm)
    yield vms_list
    for vm in vms_list:
        vm.clean_up()


@pytest.fixture(scope="class")
def must_gather_stopped_vms(must_gather_vms_from_alternate_namespace):
    # 'must_gather_stopped_vms' stopping first 3 VM's from the 'must_gather_vms_from_alternate_namespace' fixture.
    stopped_vms_list = []
    for vm in must_gather_vms_from_alternate_namespace[:3]:
        vm.stop()
    for vm in must_gather_vms_from_alternate_namespace[:3]:
        if vm.ready:
            vm.wait_for_ready_status(status=None)
        stopped_vms_list.append(vm)
    yield stopped_vms_list
    for vm in stopped_vms_list:
        vm.start()
    for vm in stopped_vms_list:
        running_vm(vm=vm)


@pytest.fixture(scope="class")
def must_gather_long_name_vm(node_gather_unprivileged_namespace, unprivileged_client):
    with VirtualMachineForTests(
        client=unprivileged_client,
        namespace=node_gather_unprivileged_namespace.name,
        name=LONG_VM_NAME,
        body=fedora_vm_body(name=LONG_VM_NAME),
        generate_unique_name=False,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture(scope="class")
def gathered_images(
    request,
    must_gather_tmpdir_scope_module,
    must_gather_image_url,
):
    before_fail_count = request.session.testsfailed
    target_path = os.path.join(must_gather_tmpdir_scope_module, "gathered_images")
    yield collect_must_gather(
        must_gather_tmpdir=target_path,
        must_gather_image_url=must_gather_image_url,
        flag_names="images",
    )
    clean_up_collected_must_gather(failed=(request.session.testsfailed - before_fail_count), target_path=target_path)


@pytest.fixture(scope="class")
def gathered_instancetypes(
    request,
    must_gather_tmpdir_scope_module,
    must_gather_image_url,
):
    before_fail_count = request.session.testsfailed
    target_path = os.path.join(must_gather_tmpdir_scope_module, "gathered_instancetypes")
    yield collect_must_gather(
        must_gather_tmpdir=target_path,
        must_gather_image_url=must_gather_image_url,
        flag_names="instancetypes",
    )
    clean_up_collected_must_gather(failed=(request.session.testsfailed - before_fail_count), target_path=target_path)


@pytest.fixture(scope="class")
def must_gather_instance_type(instance_type_for_test_scope_class):
    with instance_type_for_test_scope_class as instance:
        yield instance


@pytest.fixture(scope="class")
def must_gather_preference(vm_preference_for_test):
    with vm_preference_for_test as preference:
        yield preference


@pytest.fixture(scope="class")
def resource_types_and_pathes_dict(must_gather_preference, must_gather_instance_type):
    return {
        VirtualMachineInstancetype: f"namespaces/{must_gather_instance_type.namespace}"
        f"/{Resource.ApiGroup.INSTANCETYPE_KUBEVIRT_IO}"
        f"/virtualmachineinstancetypes/{must_gather_instance_type.name}.yaml",
        VirtualMachinePreference: f"namespaces/{must_gather_instance_type.namespace}"
        f"/{Resource.ApiGroup.INSTANCETYPE_KUBEVIRT_IO}"
        f"/virtualmachinepreferences/{must_gather_preference.name}.yaml",
    }


@pytest.fixture(scope="class")
def gathered_kubevirt_logs(
    request,
    must_gather_tmpdir_scope_module,
    must_gather_image_url,
):
    before_fail_count = request.session.testsfailed
    target_path = os.path.join(must_gather_tmpdir_scope_module, "gathered_kubevirt_logs")
    yield collect_must_gather(
        must_gather_tmpdir=target_path,
        must_gather_image_url=must_gather_image_url,
        flag_names="vms_details",
    )
    clean_up_collected_must_gather(failed=(request.session.testsfailed - before_fail_count), target_path=target_path)


@pytest.fixture(scope="class")
def nftables_ruleset_from_utility_pods(workers_utility_pods):
    return {
        pod.node.name: pod.execute(
            command=shlex.split(f"bash -c {shlex.quote('nft list ruleset 2>/dev/null')}")
        ).splitlines()
        for pod in workers_utility_pods
    }


@pytest.fixture(scope="class")
def multiple_disks_vm(namespace, unprivileged_client, data_volume_scope_class):
    vm_name = "must-gather-multiple-disks-vm"
    with VirtualMachineForTests(
        client=unprivileged_client,
        name=vm_name,
        body=fedora_vm_body(name=vm_name),
        namespace=namespace.name,
    ) as vm:
        add_dv_to_vm(vm=vm, dv_name=data_volume_scope_class.name)
        running_vm(vm=vm, wait_for_interfaces=False, check_ssh_connectivity=False)
        yield vm


@pytest.fixture()
def extracted_data_from_must_gather_file_multiple_disks(
    multiple_disks_vm,
    collected_vm_details_must_gather_function_scope,
    nftables_ruleset_from_utility_pods,
):
    virt_launcher = multiple_disks_vm.vmi.virt_launcher_pod
    file_suffix = "blockjob.txt"
    base_path = os.path.join(
        collected_vm_details_must_gather_function_scope,
        f"namespaces/{virt_launcher.namespace}/vms/{multiple_disks_vm.name}",
    )
    gathered_data_path = os.path.join(
        base_path,
        f"{virt_launcher.name}.{file_suffix}",
    )
    try:
        with open(gathered_data_path) as _file:
            return _file.read()
    except FileNotFoundError:
        LOGGER.error(f"Missing gathered data file on given path {gathered_data_path}")
        raise


@pytest.fixture(scope="class")
def disks_from_multiple_disks_vm(multiple_disks_vm):
    disk_names = [name["name"] for name in multiple_disks_vm.instance.spec.template.spec.domain.devices.disks]
    cloud_init_disk = "cloudinitdisk"
    if cloud_init_disk in disk_names:
        disk_names.remove(cloud_init_disk)
        disk_names.append(f"{multiple_disks_vm.namespace}/{multiple_disks_vm.name}")
    LOGGER.info(f"Disks in vm: {disk_names}")
    return disk_names


@pytest.fixture(scope="class")
def collected_vm_details_must_gather_from_vm_node(
    request,
    must_gather_tmpdir_scope_module,
    must_gather_image_url,
    must_gather_vm,
):
    before_fail_count = request.session.testsfailed
    target_path = os.path.join(must_gather_tmpdir_scope_module, "collected_vm_gather_from_vm_node")
    yield collect_must_gather(
        must_gather_tmpdir=target_path,
        must_gather_image_url=must_gather_image_url,
        flag_names=f"node-name={must_gather_vm.vmi.node.name},vms_details",
    )
    clean_up_collected_must_gather(failed=(request.session.testsfailed - before_fail_count), target_path=target_path)


@pytest.fixture()
def must_gather_vm_files_path(collected_vm_details_must_gather, vm_for_migration_test):
    return [
        file
        for file in os.listdir(
            os.path.join(
                collected_vm_details_must_gather,
                f"namespaces/{vm_for_migration_test.namespace}/vms/{vm_for_migration_test.name}",
            )
        )
    ]


@pytest.fixture(scope="class")
def updated_disable_serial_console_log_false(hyperconverged_resource_scope_class):
    if hyperconverged_resource_scope_class.instance.spec.virtualMachineOptions.disableSerialConsoleLog:
        with ResourceEditorValidateHCOReconcile(
            patches={
                hyperconverged_resource_scope_class: {
                    "spec": {"virtualMachineOptions": {"disableSerialConsoleLog": False}}
                }
            }
        ):
            yield
    else:
        yield


@pytest.fixture()
def extracted_controller_revision_from_must_gather(
    collected_vm_details_must_gather,
    rhel_vm_with_cluster_instance_type_and_preference,
):
    base_path = os.path.join(
        collected_vm_details_must_gather,
        f"namespaces/{rhel_vm_with_cluster_instance_type_and_preference.namespace}/apps/controllerrevisions",
    )
    path_to_controller_revision_file = os.path.join(base_path, os.listdir(base_path)[0])
    assert os.path.exists(path_to_controller_revision_file), (
        f"Have not found gathered data file on given path {path_to_controller_revision_file}"
    )

    return path_to_controller_revision_file


@pytest.fixture(scope="module")
def collected_must_gather_all_images(
    request,
    must_gather_tmpdir_all_images,
):
    before_fail_count = request.session.testsfailed
    output = run_must_gather(
        target_base_dir=must_gather_tmpdir_all_images,
        flag_names="all-images",
    )
    with open(os.path.join(must_gather_tmpdir_all_images, "output.log"), "w") as _file:
        _file.write(output)
    all_images_dirs = []
    for item in os.listdir(must_gather_tmpdir_all_images):
        new_path = os.path.join(must_gather_tmpdir_all_images, item)
        if os.path.isdir(new_path):
            all_images_dirs.append(new_path)
    assert all_images_dirs, f"No log directories was created in '{must_gather_tmpdir_all_images}'"
    yield all_images_dirs
    clean_up_collected_must_gather(
        failed=(request.session.testsfailed - before_fail_count), target_path=must_gather_tmpdir_all_images
    )


@pytest.fixture(scope="module")
def cnv_image_path_must_gather_all_images(collected_must_gather_all_images):
    for path in collected_must_gather_all_images:
        if "container-native-virtualization-cnv-must-gather" in path:
            return path
    raise FileNotFoundError("The path for cnv folder not found")


@pytest.fixture()
def must_gather_for_test(
    cnv_must_gather_matrix__function__, collected_cluster_must_gather, cnv_image_path_must_gather_all_images
):
    if cnv_must_gather_matrix__function__ == "cnv-gather":
        return collected_cluster_must_gather
    else:
        return cnv_image_path_must_gather_all_images

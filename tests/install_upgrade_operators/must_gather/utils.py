# -*- coding: utf-8 -*-
import difflib
import glob
import logging
import os
import re
import shutil
from collections import defaultdict

import pytest
import yaml
from kubernetes.dynamic.client import ResourceField
from ocp_resources.resource import Resource
from ocp_resources.service import Service

from utilities.constants import NamespacesNames
from utilities.data_collector import get_data_collector_base_directory
from utilities.infra import ResourceMismatch

LOGGER = logging.getLogger(__name__)
MUST_GATHER_VM_NAME_PREFIX = "must-gather-vm"
VM_FILE_SUFFIX = ["bridge.txt", "ip.txt", "ruletables.txt", "dumpxml.xml"]
VALIDATE_UID_NAME = (("metadata", "uid"), ("metadata", "name"))
VALIDATE_FIELDS = (("spec",),) + VALIDATE_UID_NAME
TABLE_IP_FILTER = "table ip filter"
TABLE_IP_NAT = "table ip nat"
BRIDGE_COMMAND = "bridge link show"
BLOCKJOB_TXT = "blockjob.txt"
BRIDGE_TXT = "bridge.txt"
CAPABILITIES_XML = "capabilities.xml"
DOMBLKLIST_TXT = "domblklist.txt"
DOMCAPABILITIES_XML = "domcapabilities.xml"
DOMJOBINFO_TXT = "domjobinfo.txt"
DUMPXML_XML = "dumpxml.xml"
IP_TXT = "ip.txt"
LIST_TXT = "list.txt"
RULETABLES_TXT = "ruletables.txt"
FILE_NAMES_TO_CHECK = [
    BLOCKJOB_TXT,
    BRIDGE_TXT,
    CAPABILITIES_XML,
    DOMBLKLIST_TXT,
    DOMCAPABILITIES_XML,
    DOMJOBINFO_TXT,
    DUMPXML_XML,
    IP_TXT,
    LIST_TXT,
    RULETABLES_TXT,
]
# TODO: this is a workaround for an openshift bug
# An issue was opened in openshift for this:
# https://github.com/openshift/openshift-restclient-python/issues/320
# To be removed after the issue is fixed in openshift


class ResourceFieldEqBugWorkaround(object):
    def __enter__(self):
        self.prev_eq_func = ResourceField.__eq__

        def new_eq_func(self, other):
            if isinstance(other, dict):
                return self.__dict__ == other
            return self.prev_eq_func(self, other)

        ResourceField.__eq__ = new_eq_func

    def __exit__(self, *args):
        ResourceField.__eq__ = self.prev_eq_func


def compare_resource_values(resource, path, checks):
    with open(path) as resource_file:
        file_content = yaml.safe_load(resource_file.read())
    compare_resource_contents(resource=resource, file_content=file_content, checks=checks)


def compare_resource_contents(resource, file_content, checks):
    for check in checks:
        oc_part = resource.instance
        file_part = file_content

        for part in check:
            oc_part = getattr(oc_part, part)
            file_part = file_part[part]
        with ResourceFieldEqBugWorkaround():
            if oc_part != file_part:
                raise ResourceMismatch(
                    f"Comparison of resource {resource.name} "
                    f"(namespace: {resource.namespace}) "
                    f"failed for element {check}."
                    f"Mismatched values: \n {oc_part}\n{file_part}"
                )


def compare_resources(resource_instance, temp_dir, resource_path, checks):
    path = os.path.join(
        temp_dir,
        resource_path.format(
            name=resource_instance.name,
            namespace=resource_instance.namespace or NamespacesNames.DEFAULT,
        ),
    )
    compare_resource_values(resource=resource_instance, path=path, checks=checks)


def check_list_of_resources(
    dyn_client,
    resource_type,
    temp_dir,
    resource_path,
    checks,
    namespace=None,
    label_selector=None,
    filter_resource=None,
):
    list_of_resources = resource_type.get(dyn_client=dyn_client, namespace=namespace, label_selector=label_selector)
    assert list_of_resources, f"{resource_type} is empty"
    for resource_instance in list_of_resources:
        if filter_resource is None or filter_resource in resource_instance.name:
            compare_resources(
                resource_instance=resource_instance,
                temp_dir=temp_dir,
                resource_path=resource_path,
                checks=checks,
            )


def check_resource(resource, resource_name, temp_dir, resource_path, checks):
    resource_instance = resource(name=resource_name)
    compare_resources(
        resource_instance=resource_instance,
        temp_dir=temp_dir,
        resource_path=resource_path,
        checks=checks,
    )


class NodeResourceException(Exception):
    def __init__(self, diff):
        self.diff = diff

    def __str__(self):
        return (
            f"File content created by must-gather is different from the expected command output:\n{''.join(self.diff)}"
        )


def nft_chains(raw_str):
    return [line for line in raw_str.splitlines(keepends=True) if line.startswith("\tchain")]


def compare_node_data(file_content, cmd_output, compare_method):
    if compare_method == "simple_compare":
        diff = list(
            difflib.ndiff(
                file_content.splitlines(keepends=True),
                cmd_output.splitlines(keepends=True),
            )
        )
    elif compare_method == "not_empty":
        if len(file_content) == 0:
            raise NodeResourceException("File is Empty")
        return
    elif compare_method == "nft_compare":
        diff = list(
            difflib.ndiff(
                nft_chains(raw_str=file_content),
                nft_chains(raw_str=cmd_output),
            )
        )
    else:
        raise NotImplementedError(f"{compare_method} not implemented")

    if any(line.startswith(("- ", "+ ")) for line in diff):
        raise NodeResourceException(diff)


def check_node_resource(temp_dir, cmd, utility_pod, results_file, compare_method):
    cmd_output = utility_pod.execute(command=cmd)
    file_name = f"{temp_dir}/nodes/{utility_pod.node.name}/{results_file}"
    with open(file_name) as result_file:
        file_content = result_file.read()
        compare_node_data(
            file_content=file_content,
            cmd_output=cmd_output,
            compare_method=compare_method,
        )


def _pod_logfile_path(pod_name, container_name, previous, cnv_must_gather_path, namespace):
    log = "previous" if previous else "current"
    return (
        f"{cnv_must_gather_path}/namespaces/{namespace}/pods/{pod_name}/"
        f"{container_name}/{container_name}/logs/{log}.log"
    )


def pod_logfile(pod_name, container_name, previous, cnv_must_gather_path, namespace):
    path = _pod_logfile_path(
        pod_name=pod_name,
        container_name=container_name,
        previous=previous,
        cnv_must_gather_path=cnv_must_gather_path,
        namespace=namespace,
    )
    LOGGER.info(f"Checking log: {path}")
    with open(path) as log_file:
        return log_file.read()


def pod_logfile_size(pod_name, container_name, previous, cnv_must_gather_path, namespace):
    return os.path.getsize(_pod_logfile_path(pod_name, container_name, previous, cnv_must_gather_path, namespace))


def filter_pods(running_hco_containers, labels):
    for pod, container in running_hco_containers:
        if labels:
            for k, v in labels.items():
                if pod.labels.get(k) == v:
                    yield pod, container
        else:
            yield pod, container


def check_logs(cnv_must_gather, running_hco_containers, namespace, label_selector=None):
    for pod, container in filter_pods(running_hco_containers, label_selector):
        container_name = container["name"]
        for is_previous in (True, False):
            log_size = pod_logfile_size(
                pod_name=pod.name,
                container_name=container_name,
                previous=is_previous,
                cnv_must_gather_path=cnv_must_gather,
                namespace=namespace,
            )
            # Skip comparison of empty/large files. Large files could be ratated, and hence not equal.
            if log_size > 10000 or log_size == 0:
                continue
            pod_log = pod.log(previous=is_previous, container=container_name, timestamps=True)
            log_file = pod_logfile(
                pod_name=pod.name,
                container_name=container_name,
                previous=is_previous,
                cnv_must_gather_path=cnv_must_gather,
                namespace=namespace,
            )
            assert log_file in pod_log, f"Log file are different for pod/container {pod.name}/{container_name}"


def compare_webhook_svc_contents(webhook_resources, cnv_must_gather, dyn_client, checks):
    for webhook_resource in webhook_resources:
        if webhook_resource.kind == "MutatingWebhookConfiguration":
            service_file = os.path.join(
                cnv_must_gather,
                f"webhooks/mutating/{webhook_resource.name}/service.yaml",
            )
        elif webhook_resource.kind == "ValidatingWebhookConfiguration":
            service_file = os.path.join(
                cnv_must_gather,
                f"webhooks/validating/{webhook_resource.name}/service.yaml",
            )
        webhooks_resource_instance_service = webhook_resource.instance.webhooks[0]["clientConfig"].get("service")
        if webhooks_resource_instance_service:
            webhooks_svc_name = webhooks_resource_instance_service["name"]
            webhooks_svc_namespace = webhooks_resource_instance_service["namespace"]
            svc_resources = list(Service.get(dyn_client=dyn_client, namespace=webhooks_svc_namespace))
            for svc_resource in svc_resources:
                if webhooks_svc_name == svc_resource.name:
                    compare_resource_values(resource=svc_resource, path=service_file, checks=checks)
        else:
            continue


def validate_files_collected(base_path, vm_list, nftables_ruleset_from_utility_pods):
    errors = defaultdict(dict)
    for vm in vm_list:
        virt_launcher = vm.vmi.virt_launcher_pod
        namespace = virt_launcher.namespace
        vm_name = vm.name
        folder_path = os.path.join(base_path, "namespaces", namespace, "vms", vm_name)
        LOGGER.info(f"Checking folder: {folder_path}")
        if os.path.isdir(folder_path):
            files_collected = glob.glob(f"{folder_path}/*")
            files_not_found = [
                file_suffix
                for file_suffix in VM_FILE_SUFFIX
                if f"{folder_path}/{virt_launcher.name}.{file_suffix}" not in files_collected
            ]
            if f"{folder_path}/{namespace}_{vm_name}.log" not in files_collected:
                files_not_found.append("qemu.log")
            if files_not_found:
                errors["file_not_found"][vm.name] = files_not_found

            empty_files = []
            for file_name in files_collected:
                file_size = os.stat(file_name).st_size
                if file_size < 2:
                    if "ruletables.txt" in file_name and not nftables_ruleset_from_utility_pods.values():
                        LOGGER.warning(
                            f"For file: {file_name}, found empty file, while nftables"
                            f" output: {nftables_ruleset_from_utility_pods}"
                        )
                    else:
                        empty_files.append(f"file {file_name}: size {file_size}")
            if empty_files:
                errors["empty_file"][vm.name] = empty_files
        else:
            errors["path_not_found"][vm.name] = folder_path

    assert not errors, f"Following errors found in must-gather {errors.keys()}. {errors}"


def assert_files_exists_for_running_vms(base_path, running_vms):
    # Check all files are present in the running VM.
    files_not_collected = defaultdict(dict)
    files_info = collect_path_and_files_for_all_vms(base_path=base_path, vms_list=running_vms)
    for vm in running_vms:
        files_not_present = [
            file_suffix for file_suffix in VM_FILE_SUFFIX if file_suffix not in str(files_info[vm.name]["files"])
        ]
        if files_not_present:
            files_not_collected[vm.name] = files_not_present

    assert not files_not_collected, (
        f"Files are not present:{files_not_collected} for running VM's. Current data:{files_info}"
    )


def assert_path_not_exists_for_stopped_vms(base_path, stopped_vms):
    # Check path is absent for stopped VM's.
    path_info = collect_path_and_files_for_all_vms(base_path=base_path, vms_list=stopped_vms)
    path_exists_for_vm = [vm.name for vm in stopped_vms if path_info[vm.name]["path_present"]]
    assert not path_exists_for_vm, f"Path exists for Stopped VM's {path_exists_for_vm}. Current data:{path_info}"


def collect_path_and_files_for_all_vms(base_path, vms_list):
    path_files_info = defaultdict(list)
    for vm in vms_list:
        vm_name = vm.name
        folder_path = os.path.join(base_path, "vms", vm_name)
        LOGGER.info(f"Checking VM {vm_name}'s folder: {folder_path}")
        path_exists = os.path.isdir(folder_path)
        path_files_info[vm.name] = {"path_present": path_exists}
        if path_exists:
            path_files_info[vm.name]["files"] = glob.glob(f"{folder_path}/*")
    return path_files_info


def validate_must_gather_vm_file_collection(
    collected_vm_details_must_gather_with_params,
    expected,
    must_gather_vm,
    must_gather_vms_from_alternate_namespace,
    nftables_ruleset_from_utility_pods,
):
    vm_list = get_vm_list_for_validation(
        expected=expected,
        must_gather_vm=must_gather_vm,
        must_gather_vms_from_alternate_namespace=must_gather_vms_from_alternate_namespace,
    )

    LOGGER.info(f"Validating path for vms: {[vm.name for vm in vm_list['vms_collected']]}")
    validate_files_collected(
        base_path=collected_vm_details_must_gather_with_params,
        vm_list=vm_list["vms_collected"],
        nftables_ruleset_from_utility_pods=nftables_ruleset_from_utility_pods,
    )
    not_collected_vm_names = [vm.name for vm in vm_list["vms_not_collected"]]
    LOGGER.info(f"Validating following vms were not collected: {not_collected_vm_names}")
    with pytest.raises(AssertionError) as exeption_found:
        validate_files_collected(
            base_path=collected_vm_details_must_gather_with_params,
            vm_list=vm_list["vms_not_collected"],
            nftables_ruleset_from_utility_pods=nftables_ruleset_from_utility_pods,
        )
    assert all(entry in str(exeption_found.value) for entry in not_collected_vm_names + ["path_not_found"]), (
        f"Failed to find {not_collected_vm_names} in exception message: {str(exeption_found.value)}"
    )


def assert_must_gather_stopped_vm_yaml_file_collection(base_path, must_gather_stopped_vms):
    # Check "'running': False" in the stopped VM's yaml file.
    vms_path_and_running_status = defaultdict(dict)
    for vm in must_gather_stopped_vms:
        vm_name = vm.name
        vm_yaml_file_path = os.path.join(
            base_path,
            f"{Resource.ApiGroup.KUBEVIRT_IO}",
            "virtualmachines/custom/",
            f"{vm.name}.yaml",
        )
        LOGGER.info(f"Checking VM {vm_name}'s folder: {vm_yaml_file_path}")
        vm_yaml_file_path_exists = os.path.isfile(vm_yaml_file_path)
        if vm_yaml_file_path_exists:
            with open(vm_yaml_file_path) as vm_yaml:
                file_content = yaml.safe_load(vm_yaml.read())
                # VM's ["status"]["ready"] has boolean value.
                if file_content.get("status", {}).get("ready"):
                    vms_path_and_running_status["vm_running_status"][vm_name] = vm.ready or False
        else:
            vms_path_and_running_status["path_not_exists"][vm_name] = vm_yaml_file_path_exists
    assert not vms_path_and_running_status, (
        f"Stopped VM's validation failed due to {vms_path_and_running_status.keys()}. "
        f"All data: {vms_path_and_running_status}"
    )


def get_vm_list_for_validation(
    expected,
    must_gather_vm,
    must_gather_vms_from_alternate_namespace,
):
    if expected and "alt_ns_vm" in expected:
        vm_list_collected = [must_gather_vms_from_alternate_namespace[index] for index in expected["alt_ns_vm"]]
        vm_list_not_collected = [vm for vm in must_gather_vms_from_alternate_namespace if vm not in vm_list_collected]
        if "must_gather_ns_vm" in expected:
            vm_list_collected.append(must_gather_vm)
        else:
            vm_list_not_collected.append(must_gather_vm)

    else:
        vm_list_collected = [vm for vm in must_gather_vms_from_alternate_namespace]
        vm_list_not_collected = [must_gather_vm]
    return {
        "vms_collected": vm_list_collected,
        "vms_not_collected": vm_list_not_collected,
    }


def get_must_gather_dir(directory_name):
    return os.path.join(get_data_collector_base_directory(), directory_name)


def clean_up_collected_must_gather(failed, target_path):
    if failed:
        LOGGER.warning(f"{failed} tests using this fixture failed. Not removing must-gather")
    else:
        LOGGER.warning(f"No tests using this must gather collection failed. Removing data collected {target_path}")
        shutil.rmtree(
            target_path,
            ignore_errors=True,
        )


def validate_guest_console_logs_collected(collected_vm_details_must_gather, vm):
    virt_launcher_pod = vm.vmi.virt_launcher_pod
    guest_console_log = "guest-console-log"
    base_path = os.path.join(
        collected_vm_details_must_gather,
        f"namespaces/{virt_launcher_pod.namespace}/pods/"
        f"{virt_launcher_pod.name}/{guest_console_log}/{guest_console_log}/logs/",
    )
    missing_files = []
    files_to_search_path = [
        f"{os.path.join(base_path, 'current.log')}",
        f"{os.path.join(base_path, 'previous.log')}",
    ]
    for path in files_to_search_path:
        if not os.path.exists(path):
            missing_files.append(path)
    assert not (missing_files), f"Following guest-console-log files are missing: {missing_files}"
    assert os.path.getsize(files_to_search_path[0]) > 0


def check_disks_exists_in_blockjob_file(
    disks_from_multiple_disks_vm, extracted_data_from_must_gather_file_multiple_disks
):
    assert disks_from_multiple_disks_vm
    mismatches = []
    for disk in disks_from_multiple_disks_vm:
        # Make sure that gathered data roughly matches expected format.
        matches = re.search(
            disk,
            extracted_data_from_must_gather_file_multiple_disks,
            re.MULTILINE | re.IGNORECASE,
        )
        LOGGER.info(f"Results from search: {matches}")
        if not matches:
            mismatches.append(disk)

    assert not mismatches, (
        f"Gathered disks that not matching expected format:\n {mismatches}, "
        f"data extracted: {extracted_data_from_must_gather_file_multiple_disks}"
    )


def extracted_data_from_must_gather_on_vm_node(
    collected_vm_details_must_gather_from_vm_node,
    must_gather_vm,
):
    virt_launcher = must_gather_vm.vmi.virt_launcher_pod
    base_path = os.path.join(
        collected_vm_details_must_gather_from_vm_node,
        f"namespaces/{virt_launcher.namespace}/vms/{must_gather_vm.name}",
    )
    empty_files = []
    missing_files = []
    for file in FILE_NAMES_TO_CHECK:
        gathered_data_path = os.path.join(
            base_path,
            f"{virt_launcher.name}.{file}",
        )
        if not os.path.exists(gathered_data_path):
            missing_files.append(file)
        if not os.path.getsize(gathered_data_path):
            empty_files.append(file)
    assert not (empty_files or missing_files), (
        f"There are missing/empty files: Missing:{missing_files}, empty: {empty_files}"
    )


def missing_and_duplicate_files(missing_files, duplicate_files, file_name, file_str, must_gather_vm_file_list):
    file_counter = [file for file in must_gather_vm_file_list if file.endswith(file_str)]
    if not file_counter:
        missing_files.append(file_name)
    elif len(file_counter) > 1:
        duplicate_files.append(file_name)


def check_no_duplicate_and_missing_files_collected_from_migrated_vm(must_gather_vm_file_list, vm_namespace, vm_name):
    missing_files = []
    duplicate_files = []
    missing_and_duplicate_files(
        missing_files=missing_files,
        duplicate_files=duplicate_files,
        file_name=f"{vm_namespace}_{vm_name}.log",
        file_str=f"{vm_name}.log",
        must_gather_vm_file_list=must_gather_vm_file_list,
    )
    for file in FILE_NAMES_TO_CHECK:
        missing_and_duplicate_files(
            missing_files=missing_files,
            duplicate_files=duplicate_files,
            file_name=file,
            file_str=f".{file}",
            must_gather_vm_file_list=must_gather_vm_file_list,
        )
    assert not (duplicate_files or missing_files), (
        f"Possible missing/duplicate files found for migrated vm {vm_name}, duplicates: {duplicate_files},"
        f" missing: {missing_files}"
    )


def validate_no_empty_files_collected_must_gather_vm(vm, must_gather_vm_file_list, must_gather_vm_path):
    namespace = vm.namespace
    vm_name = vm.name
    empty_files = []
    base_path = os.path.join(
        must_gather_vm_path,
        f"namespaces/{namespace}/vms/{vm_name}",
    )
    for file in must_gather_vm_file_list:
        if file == "log":
            continue
        if not os.path.getsize(os.path.join(base_path, file)):
            empty_files.append(file)
    assert not empty_files, f"Empty files gathered: {empty_files}"

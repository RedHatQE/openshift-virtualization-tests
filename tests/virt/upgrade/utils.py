import logging
import shlex
from datetime import datetime

import pytest
from ocp_resources.datavolume import DataVolume
from ocp_resources.virtual_machine import VirtualMachine
from ocp_resources.virtual_machine_instance_migration import (
    VirtualMachineInstanceMigration,
)
from pyhelper_utils.shell import run_ssh_commands
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from utilities.constants import (
    DATA_SOURCE_NAME,
    TIMEOUT_3MIN,
    TIMEOUT_10SEC,
    TIMEOUT_180MIN,
)
from utilities.exceptions import ResourceMissingFieldError
from utilities.infra import (
    get_csv_by_name,
    get_pod_disruption_budget,
    get_related_images_name_and_version,
)
from utilities.virt import wait_for_ssh_connectivity

LOGGER = logging.getLogger(__name__)

TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def verify_vms_ssh_connectivity(vms_list):
    ssh_timeout = TIMEOUT_3MIN
    ssh_failed = {}

    for vm in vms_list:
        try:
            wait_for_ssh_connectivity(vm=vm, timeout=ssh_timeout, tcp_timeout=ssh_timeout)
        except TimeoutExpiredError as exp:
            ssh_failed[vm.name] = exp

    assert not ssh_failed, f"No ssh connectivity for VMs:\n {ssh_failed}"


def mismatching_src_pvc_names(pre_upgrade_templates, post_upgrade_templates):
    mismatched_templates = {}
    for template in post_upgrade_templates:
        matching_template = [temp for temp in pre_upgrade_templates if temp.name == template.name]

        if matching_template:
            expected = get_src_pvc_default_name(template=matching_template[0])
            found = get_src_pvc_default_name(template=template)

            if found != expected:
                mismatched_templates[template.name] = {
                    "expected": expected,
                    "found": found,
                }

    return mismatched_templates


def get_src_pvc_default_name(template):
    param_value_list = [param["value"] for param in template.instance.parameters if param["name"] == DATA_SOURCE_NAME]

    if param_value_list:
        return param_value_list[0]

    raise ResourceMissingFieldError(f"Template {template.name} does not have a parameter {DATA_SOURCE_NAME}")


def get_all_migratable_vms(admin_client, namespaces):
    # Check pod disruption budget associated with given namespaces. Collect associated vm names. These vms are
    # the only migratable ones
    pod_disruption_budget_list = [
        pod_disruption_budget
        for ns in namespaces
        for pod_disruption_budget in get_pod_disruption_budget(admin_client=admin_client, namespace_name=ns.name)
    ]
    pod_disruption_budget_info = {
        pod_disruption_budget.name: pod_disruption_budget.instance.metadata.ownerReferences[0]["name"]
        for pod_disruption_budget in pod_disruption_budget_list
    }
    LOGGER.info(f"PodDisruptionBudgets: {pod_disruption_budget_info}")

    return [
        VirtualMachine(
            client=admin_client,
            namespace=pod_disruption_budget.namespace,
            name=pod_disruption_budget.instance.metadata.ownerReferences[0]["name"],
        )
        for pod_disruption_budget in pod_disruption_budget_list
    ]


def get_workload_update_migrations_list(namespaces):
    workload_migrations = {}
    for namespace in namespaces:
        for migration_job in list(VirtualMachineInstanceMigration.get(namespace=namespace)):
            if migration_job.name.startswith("kubevirt-workload-update"):
                job_instance = migration_job.instance
                vmi_name = job_instance.spec.vmiName
                if vmi_name not in workload_migrations.keys() or datetime.strptime(
                    job_instance.metadata.creationTimestamp, TIMESTAMP_FORMAT
                ) > datetime.strptime(
                    workload_migrations[vmi_name].metadata.creationTimestamp,
                    TIMESTAMP_FORMAT,
                ):
                    workload_migrations[vmi_name] = job_instance

    jobs = {
        migration_job.spec.vmiName: f"{migration_job.metadata.name}-{migration_job.status.phase}"
        for migration_job in workload_migrations.values()
    }
    LOGGER.info(f"Workload migration jobs: {jobs}")

    return list(workload_migrations.values())


def vms_auto_migration_with_status_success(namespaces):
    workload_migrations = get_workload_update_migrations_list(namespaces=namespaces)
    return [
        migration_job.spec.vmiName
        for migration_job in workload_migrations
        if migration_job.status.phase == VirtualMachineInstanceMigration.Status.SUCCEEDED
    ]


def wait_for_automatic_vm_migrations(vm_list):
    vm_names = [vm.name for vm in vm_list]
    vm_namespaces = list({vm.namespace for vm in vm_list})
    LOGGER.info(f"Checking VMIMs for vms: {vm_names}")

    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_180MIN,
        sleep=TIMEOUT_10SEC,
        func=vms_auto_migration_with_status_success,
        namespaces=vm_namespaces,
    )

    sample = None
    try:
        for sample in samples:
            LOGGER.info(f"Current migration state for vms:{vm_names}: {sample}")
            if all(vm in sample for vm in vm_names):
                return True
    except TimeoutExpiredError:
        vms_with_failed_vmim = list(set(vm_names) - set(sample))
        LOGGER.error(
            f"Migratable vms: {vm_names}, vms with completed automatic workload update: "
            f"{sample}, and vms with failed automatic workload update: {vms_with_failed_vmim}"
        )
        raise


def validate_vms_pod_updated(admin_client, hco_namespace, hco_target_csv_name, vm_list):
    csv = get_csv_by_name(
        admin_client=admin_client,
        namespace=hco_namespace.name,
        csv_name=hco_target_csv_name,
    )
    target_related_images = get_related_images_name_and_version(csv=csv)
    return [
        {pod.name: pod.instance.spec.containers[0].image}
        for pod in [vm.vmi.virt_launcher_pod for vm in vm_list]
        if pod.instance.spec.containers[0].image not in target_related_images.values()
    ]


def verify_run_strategy_vmi_status(run_strategy_vmi_list):
    vmi_failed = {}
    for vm in run_strategy_vmi_list[:]:
        vm_instance = vm.instance
        # Non-migratable VM with Manual runStrategy will be stopped during the upgrade
        if vm_instance.spec.runStrategy == "Manual" and "cannot migrate VMI" in str(vm_instance.status.conditions):
            LOGGER.warning("VM with runStrategy=Manual is non-migratable, skipping from check")
            run_strategy_vmi_list.remove(vm)
        else:
            vm_status = vm.printable_status
            if vm_status != VirtualMachine.Status.RUNNING:
                vmi_failed[vm.name] = vm_status

    if vmi_failed:
        pytest.fail(f"VMI in wrong state:\n {vmi_failed}")
    return run_strategy_vmi_list


def vm_is_migrateable(vm):
    vm_spec = vm.instance.spec
    vm_access_modes = (
        vm.get_storage_configuration()
        if (vm_spec.get("instancetype") or vm_spec.get("preference"))
        else vm.access_modes
    )
    if DataVolume.AccessMode.RWO in vm_access_modes:
        LOGGER.info(f"Cannot migrate a VM {vm.name} with RWO PVC.")
        return False
    return True


def get_vm_boot_time(vm):
    boot_command = 'net statistics workstation | findstr "Statistics since"' if "windows" in vm.name else "who -b"
    return run_ssh_commands(host=vm.ssh_exec, commands=shlex.split(boot_command))[0]


def verify_linux_boot_time(vm_list, initial_boot_time):
    rebooted_vms = {}
    for vm in vm_list:
        if vm_is_migrateable(vm=vm):
            current_boot_time = get_vm_boot_time(vm=vm)
            if initial_boot_time[vm.name] != current_boot_time:
                rebooted_vms[vm.name] = {"initial": initial_boot_time[vm.name], "current": current_boot_time}
    assert not rebooted_vms, f"Boot time changed for VMs:\n {rebooted_vms}"


def verify_windows_boot_time(windows_vm, initial_boot_time):
    if vm_is_migrateable(vm=windows_vm):
        current_boot_time = get_vm_boot_time(vm=windows_vm)
        assert initial_boot_time == current_boot_time, (
            f"Boot time for Windows VM changed:\n initial: {initial_boot_time}\n current: {current_boot_time}"
        )

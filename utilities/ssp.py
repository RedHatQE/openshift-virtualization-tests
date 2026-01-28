import json
import logging
import os
import re
import shlex
import urllib.request
from contextlib import contextmanager
from typing import TYPE_CHECKING

from kubernetes.dynamic import DynamicClient
from kubernetes.dynamic.exceptions import NotFoundError
from ocp_resources.data_import_cron import DataImportCron
from ocp_resources.namespace import Namespace
from ocp_resources.ssp import SSP
from ocp_resources.template import Template
from ocp_resources.virtual_machine_cluster_instancetype import VirtualMachineClusterInstancetype
from pytest_testconfig import config as py_config
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from utilities.ssh import run_ssh_commands

if TYPE_CHECKING:
    from utilities.virt import VirtualMachineForTests

import utilities.infra
import utilities.storage
import utilities.virt
from utilities.constants import (
    DEFAULT_RESOURCE_CONDITIONS,
    EIGHT_CPU_SOCKETS,
    FOUR_GI_MEMORY,
    SSP_KUBEVIRT_HYPERCONVERGED,
    SSP_OPERATOR,
    TCP_TIMEOUT_30SEC,
    TIMEOUT_2MIN,
    TIMEOUT_3MIN,
    TIMEOUT_5MIN,
    TIMEOUT_5SEC,
    TIMEOUT_6MIN,
    TIMEOUT_10SEC,
)

LOGGER = logging.getLogger(__name__)


def wait_for_deleted_data_import_crons(data_import_crons):
    def _get_existing_data_import_crons(_data_import_crons, _auto_boot_data_import_cron_prefixes):
        return [
            data_import_cron.name
            for data_import_cron in _data_import_crons
            if data_import_cron.exists
            and re.sub(utilities.storage.DATA_IMPORT_CRON_SUFFIX, "", data_import_cron.name)
            in _auto_boot_data_import_cron_prefixes
        ]

    LOGGER.info("Wait for DataImportCrons deletion.")
    auto_boot_data_import_cron_prefixes = matrix_auto_boot_data_import_cron_prefixes()
    sample = None
    try:
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_2MIN,
            sleep=5,
            func=_get_existing_data_import_crons,
            _data_import_crons=data_import_crons,
            _auto_boot_data_import_cron_prefixes=auto_boot_data_import_cron_prefixes,
        ):
            if not sample:
                return
    except TimeoutExpiredError:
        LOGGER.error(f"Some DataImportCrons are not deleted: {sample}")
        raise


def wait_for_at_least_one_auto_update_data_import_cron(admin_client, namespace):
    try:
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_2MIN,
            sleep=5,
            func=get_data_import_crons,
            admin_client=admin_client,
            namespace=namespace,
        ):
            if sample:
                return
    except TimeoutExpiredError:
        LOGGER.error(f"No DataImportCrons found in {namespace.name}")
        raise


def matrix_auto_boot_data_import_cron_prefixes():
    data_import_cron_prefixes = []
    for data_source_matrix_entry in py_config["auto_update_data_source_matrix"]:
        data_source_name = [*data_source_matrix_entry][0]
        data_import_cron_prefixes.append(
            data_source_matrix_entry[data_source_name].get("data_import_cron_prefix", data_source_name)
        )

    return data_import_cron_prefixes


def get_data_import_crons(admin_client, namespace):
    return list(DataImportCron.get(client=admin_client, namespace=namespace.name))


def get_ssp_resource(admin_client, namespace):
    try:
        for ssp in SSP.get(
            client=admin_client,
            name=SSP_KUBEVIRT_HYPERCONVERGED,
            namespace=namespace.name,
        ):
            return ssp
    except NotFoundError:
        LOGGER.error(f"SSP CR {SSP_KUBEVIRT_HYPERCONVERGED} was not found in namespace {namespace.name}")
        raise


def wait_for_ssp_conditions(
    admin_client,
    hco_namespace,
    polling_interval=5,
    consecutive_checks_count=3,
    expected_conditions=None,
):
    utilities.infra.wait_for_consistent_resource_conditions(
        dynamic_client=admin_client,
        namespace=hco_namespace.name,
        expected_conditions=expected_conditions or DEFAULT_RESOURCE_CONDITIONS,
        resource_kind=SSP,
        condition_key1="type",
        condition_key2="status",
        total_timeout=TIMEOUT_3MIN,
        polling_interval=polling_interval,
        consecutive_checks_count=consecutive_checks_count,
    )


def wait_for_condition_message_value(resource, expected_message):
    LOGGER.info(f"Verify {resource.name} conditions contain expected message: {expected_message}")
    sample = None
    try:
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_5MIN,
            sleep=TIMEOUT_5SEC,
            func=lambda: resource.instance.status.conditions,
        ):
            if any([condition["message"] == expected_message for condition in sample]):
                return
    except TimeoutExpiredError:
        LOGGER.error(
            f"{resource.name} condition message does not match expected message {expected_message}, conditions: "
            f"{sample}"
        )
        raise


@contextmanager
def create_custom_template_from_url(url, template_name, template_dir, namespace, client):
    template_filepath = os.path.join(template_dir, template_name)
    urllib.request.urlretrieve(
        url=url,
        filename=template_filepath,
    )
    with Template(
        yaml_file=template_filepath,
        namespace=namespace,
        client=client,
    ) as template:
        yield template


def guest_agent_version_parser(version_string):
    # Return qemu-guest-agent version (including build number, e.g: "4.2.0-34" or "100.0.0.0" or "100.0.0" for Windows)
    return re.search(r"[0-9]+\.[0-9]+\.[0-9]+(?:[.|-][0-9]+)?", version_string).group(0)


def get_windows_timezone(vm: "VirtualMachineForTests", get_standard_name: bool = False) -> str:
    """Get Windows timezone from VM.

    Args:
        vm: VirtualMachine instance with SSH connectivity.
        get_standard_name: If True, get only Windows StandardName.

    Returns:
        Windows timezone string.
    """
    standard_name_cmd = '| findstr "StandardName"' if get_standard_name else ""
    timezone_cmd = shlex.split(f'powershell -command "Get-TimeZone {standard_name_cmd}"')
    return run_ssh_commands(vm=vm, commands=timezone_cmd, timeout=TCP_TIMEOUT_30SEC)[0]


def get_ga_version(vm: "VirtualMachineForTests") -> str:
    """Get QEMU guest agent version from Windows VM.

    Args:
        vm: VirtualMachine instance with SSH connectivity.

    Returns:
        Guest agent version string.
    """
    return run_ssh_commands(
        vm=vm,
        commands=[
            "powershell",
            "-Command",
            "(Get-Item",
            "'C:\\Program Files\\Qemu-ga\\qemu-ga.exe').VersionInfo.FileVersion",
        ],
        timeout=TCP_TIMEOUT_30SEC,
    )[0].strip()


def get_cim_instance_json(vm: "VirtualMachineForTests") -> dict:
    """Get CIM instance information from Windows VM as JSON.

    Args:
        vm: VirtualMachine instance with SSH connectivity.

    Returns:
        Dictionary containing Win32_OperatingSystem CIM instance data.
    """
    return json.loads(
        run_ssh_commands(
            vm=vm,
            commands=shlex.split('powershell -c "Get-CimInstance -Class Win32_OperatingSystem | ConvertTo-Json"'),
        )[0]
    )


def get_reg_product_name(vm: "VirtualMachineForTests") -> str:
    """Get Windows product name from registry.

    Args:
        vm: VirtualMachine instance with SSH connectivity.

    Returns:
        Registry product name string.
    """
    return run_ssh_commands(
        vm=vm,
        commands=shlex.split(
            'REG QUERY "HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion" /v "ProductName"'
        ),
        timeout=TCP_TIMEOUT_30SEC,
    )[0]


def get_windows_os_info(vm: "VirtualMachineForTests") -> dict:
    """Get comprehensive Windows OS information from VM.

    Args:
        vm: VirtualMachine instance with SSH connectivity.

    Returns:
        Dictionary containing guest agent version, hostname, OS details, and timezone.
    """
    cim_instance_json = get_cim_instance_json(vm=vm)
    caption = cim_instance_json["Caption"]
    version_str = cim_instance_json["Version"]
    reg_product_name = get_reg_product_name(vm=vm)

    version_match = re.search(r"(.+\d+)", caption)
    if version_match is None:
        raise ValueError(f"Failed to extract version from Caption: {caption}")

    pretty_name_match = re.search(r"REG_SZ\s+(.+)\r\n", reg_product_name)
    if pretty_name_match is None:
        raise ValueError(f"Failed to extract pretty name from registry: {reg_product_name}")

    version_id_match = re.search(r"\D+(\d+)", caption)
    if version_id_match is None:
        raise ValueError(f"Failed to extract version ID from Caption: {caption}")

    kernel_version_match = re.search(r"(\d+\.\d+)\.", version_str)
    if kernel_version_match is None:
        raise ValueError(f"Failed to extract kernel version from Version: {version_str}")

    return {
        "guestAgentVersion": guest_agent_version_parser(version_string=get_ga_version(vm=vm)),
        "hostname": cim_instance_json["CSName"],
        "os": {
            "name": "Microsoft Windows",
            "kernelRelease": cim_instance_json["BuildNumber"],
            "version": version_match.group(1),
            "prettyName": pretty_name_match.group(1),
            "versionId": version_id_match.group(1),
            "kernelVersion": kernel_version_match.group(1),
            "machine": "x86_64" if "64" in cim_instance_json["OSArchitecture"] else "x86",
            "id": "mswindows",
        },
        "timezone": get_windows_timezone(vm=vm),
    }


def validate_os_info_vmi_vs_windows_os(vm: "VirtualMachineForTests") -> None:
    """Validate OS information from VMI matches Windows guest OS.

    Args:
        vm: VirtualMachine instance with SSH connectivity.

    Raises:
        AssertionError: If VMI has no guest agent data or if OS data mismatches.
    """
    vmi_info = utilities.virt.get_guest_os_info(vmi=vm.vmi)
    assert vmi_info, "VMI doesn't have guest agent data"
    windows_info = get_windows_os_info(vm=vm)["os"]

    data_mismatch = []
    for os_param_name, os_param_value in vmi_info.items():
        if os_param_value not in windows_info[os_param_name]:
            data_mismatch.append(f"OS data mismatch - {os_param_name}")

    assert not data_mismatch, f"Data mismatch {data_mismatch}!\nVMI: {vmi_info}\nOS: {windows_info}"


def is_ssp_pod_running(client: DynamicClient, hco_namespace: Namespace) -> bool:
    pod = utilities.infra.get_pod_by_name_prefix(
        client=client,
        pod_prefix=SSP_OPERATOR,
        namespace=hco_namespace.name,
    )
    return pod.status == pod.Status.RUNNING and pod.instance.status.containerStatuses[0]["ready"]


def verify_ssp_pod_is_running(
    client: DynamicClient,
    hco_namespace: Namespace,
    wait_timeout: int = TIMEOUT_6MIN,
    sleep: int = TIMEOUT_10SEC,
    consecutive_checks_count: int = 3,
):
    """
    Verifies that SSP pod is up and running

    This function polls for the status of SSP pod every 'sleep' seconds for
    the maximum time duration of 'wait_timeout', before it raises
    'TimeoutExpiredError'. Also this function makes sure that SSP pod
    is up and running for at least 'consecutive_checks_count'

    Args:
        client (DynamicClient): Dynamic client object
        hco_namespace (Namespace): Namespace object
        wait_timeout (int) : Maximum time to wait till SSP pod is up
        sleep (int): polling interval
        consecutive_checks_count (int): Minimum repetitive check iteration before
            assuring that SSP pod is up.

    Raises:
        'TimeoutExpiredError' when SSP pod is not up and running
         for the time duration of 'wait_timeout'
    """
    sampler = TimeoutSampler(
        wait_timeout=wait_timeout,
        sleep=sleep,
        func=is_ssp_pod_running,
        client=client,
        hco_namespace=hco_namespace,
    )
    sample = None
    checks_count = 0
    try:
        for sample in sampler:
            if sample:
                checks_count += 1
                if checks_count == consecutive_checks_count:
                    return
            else:
                checks_count = 0
    except TimeoutExpiredError:
        if sample:
            LOGGER.warning(f"SSP pod is up, but not for the last {consecutive_checks_count} consecutive checks")
        else:
            LOGGER.error(f"SSP pod was not running for last {TIMEOUT_6MIN} seconds")
            raise


def cluster_instance_type_for_hot_plug(
    client: DynamicClient, guest_sockets: int, cpu_model: str | None
) -> VirtualMachineClusterInstancetype:
    return VirtualMachineClusterInstancetype(
        client=client,
        name=f"hot-plug-{guest_sockets}-cpu-instance-type",
        memory={"guest": FOUR_GI_MEMORY},
        cpu={
            "guest": guest_sockets,
            "model": cpu_model,
            "maxSockets": EIGHT_CPU_SOCKETS,
        },
    )

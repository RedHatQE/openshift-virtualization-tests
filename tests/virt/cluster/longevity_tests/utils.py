import logging
import shlex
import shutil
import socket
from threading import Thread

from ocp_resources import pod
from ocp_resources.data_source import DataSource
from ocp_resources.datavolume import DataVolume
from ocp_resources.template import Template
from pyhelper_utils.shell import run_ssh_commands
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.virt.cluster.longevity_tests.constants import (
    PROC_PER_OS_DICT,
    WINDOWS_OS_PREFIX,
)
from tests.virt.utils import migrate_and_verify_multi_vms, verify_wsl2_guest_works
from utilities.constants import TCP_TIMEOUT_30SEC, TIMEOUT_5MIN, TIMEOUT_30MIN, TIMEOUT_40MIN, TIMEOUT_60MIN, WIN_10
from utilities.infra import (
    cleanup_artifactory_secret_and_config_map,
    get_artifactory_config_map,
    get_artifactory_secret,
)
from utilities.storage import get_test_artifact_server_url
from utilities.virt import (
    VirtualMachineForTests,
    VirtualMachineForTestsFromTemplate,
    fedora_vm_body,
    running_vm,
    wait_for_ssh_connectivity,
)

LOGGER = logging.getLogger(__name__)
ADMIN_DOWNLOADS_FOLDER_PATH = r"C:\Users\Administrator\Downloads"


def decorate_log(msg):
    terminal_width = int(shutil.get_terminal_size(fallback=(120, 40))[0])
    msg_decor = "-" * round(terminal_width / 4 - 30)
    return f"{msg_decor}{msg}{msg_decor}"


def run_migration_loop(iterations, vms_with_pids, os_type, wsl2_guest=False):
    for iteration in range(iterations):
        LOGGER.info(decorate_log(f"Iteration {iteration + 1}"))

        LOGGER.info(decorate_log("VM Migration"))
        vm_list = [vms_with_pids[vm_name]["vm"] for vm_name in vms_with_pids]
        migrate_and_verify_multi_vms(vm_list=vm_list)

        LOGGER.info(decorate_log("PID check"))
        verify_pid_after_migrate_multi_vms(vms_with_pids=vms_with_pids, os_type=os_type)
        if wsl2_guest:
            verify_wsl2_guest_works_multi_vm(vm_list=vm_list)


def run_windows_upgrade_storm(vms_with_pids):
    LOGGER.info(decorate_log("Windows Upgrade"))
    vm_list = [vms_with_pids[vm_name]["vm"] for vm_name in vms_with_pids]
    start_win_upgrade_multi_vms(vm_list=vm_list)
    wait_windows_reboot_multi_vm(vm_list=vm_list)

    LOGGER.info(decorate_log("Upgrade Check"))
    verify_windows_upgraded_recently_multi_vms(vm_list=vm_list)
    verify_wsl2_guest_works_multi_vm(vm_list=vm_list)


def start_process_in_guest(vm, os_type):
    vm_and_pid = {}
    os_dict = PROC_PER_OS_DICT[os_type]
    params = {"vm": vm, "process_name": os_dict["proc_name"]}
    if os_dict.get("proc_args"):
        params.update({"args": os_dict["proc_args"]})

    vm_and_pid[vm.name] = {"vm": vm, "pid": os_dict["create_proc"](**params)}
    return vm_and_pid


def reboot_vm(vm):
    try:
        run_ssh_commands(
            host=vm.ssh_exec,
            commands=shlex.split("powershell restart-computer -force"),
            tcp_timeout=TCP_TIMEOUT_30SEC,
        )[0]
    # When a reboot command is executed, a resources.pod.ExecOnPodError exception is raised:
    # "connection reset by peer"
    except pod.ExecOnPodError as e:
        if "connection reset by peer" in e.out:
            return


def start_win_upgrade_multi_vms(vm_list):
    def _set_interface_mtu(vm):
        interface_name = "Ethernet 2" if WIN_10 in vm.name else "Ethernet Instance 0"
        run_ssh_commands(
            host=vm.ssh_exec,
            commands=shlex.split(f'netsh interface ipv4 set subinterface "{interface_name}" mtu=1400 store=persistent'),
        )

    def _prepare_win_upgrade(vm):
        LOGGER.info(f"VM {vm.name}: Installing upgrade tools")
        win_upgrade_prepare_cmds = [
            shlex.split('powershell -c "Set-ExecutionPolicy RemoteSigned -Force"'),
            shlex.split('powershell -c "Install-PackageProvider -Name NuGet -MinimumVersion 2.8.5.201 -Force"'),
            shlex.split('powershell -c "Install-Module PSWindowsUpdate -Force"'),
            # workaround until Windows images are updated
            shlex.split(
                r'powershell -c "Invoke-WebRequest -Uri https://download.sysinternals.com/files/PSTools.zip '
                rf'-OutFile {ADMIN_DOWNLOADS_FOLDER_PATH}\psexec.zip"'
            ),
            shlex.split(
                rf'powershell -c "Expand-Archive -Path {ADMIN_DOWNLOADS_FOLDER_PATH}\psexec.zip '
                rf'-DestinationPath {ADMIN_DOWNLOADS_FOLDER_PATH}\PSExec"'
            ),
        ]
        run_ssh_commands(host=vm.ssh_exec, commands=win_upgrade_prepare_cmds)

    def _start_win_upgrade(vm):
        LOGGER.info(f"VM {vm.name}: Starting upgrade process")
        win_upgrade_psexec_trigger_cmd = shlex.split(
            rf'"{ADMIN_DOWNLOADS_FOLDER_PATH}\PSExec\PsExec.exe" -nobanner -accepteula -s '
            r'powershell -c "Get-WindowsUpdate -AcceptAll -Install -IgnoreReboot"'
        )

        # Windows upgrade consists of several stages:
        # 1. download/install of updates
        # 2. OS reboot and finish of installation
        # 3. OS boot and finalization of install (checks/clean-ups)
        # Here stage #1 occures

        try:
            run_ssh_commands(
                host=vm.ssh_exec,
                commands=win_upgrade_psexec_trigger_cmd,
                timeout=TIMEOUT_40MIN,
            )
            LOGGER.info(f"VM {vm.name}: Finished upgrades download/install stage")
        except socket.timeout:
            LOGGER.warning(f"VM {vm.name}: Finished upgrades download/install stage but the script was stuck")

    upgrade_threads_list = []

    # make all the upgrade preparations in separate loop for more clear logging
    # (threads will mess up logs order)
    for vm in vm_list:
        _set_interface_mtu(vm=vm)
        _prepare_win_upgrade(vm=vm)

    for vm in vm_list:
        sub_thread = Thread(target=_start_win_upgrade, args=[vm], name=vm.name)
        sub_thread.start()
        upgrade_threads_list.append(sub_thread)

    for thread in upgrade_threads_list:
        thread.join()

    LOGGER.info("Restarting all VMs to finish installation process and perform finalization stage")
    for vm in vm_list:
        reboot_vm(vm=vm)


def verify_pid_after_migrate_multi_vms(vms_with_pids, os_type):
    vms_with_wrong_pids_dict = {}
    os_dict = PROC_PER_OS_DICT[os_type]

    for vm_name in vms_with_pids:
        orig_pid = vms_with_pids[vm_name]["pid"]
        new_pid = None
        try:
            new_pid = os_dict["fetch_pid"](vm=vms_with_pids[vm_name]["vm"], process_name=os_dict["proc_name"])
        except (AssertionError, ValueError):
            vms_with_wrong_pids_dict[vm_name] = {
                "orig_pid": orig_pid,
                "new_pid": new_pid,
            }
            continue
        if orig_pid != new_pid:
            vms_with_wrong_pids_dict[vm_name] = {
                "orig_pid": orig_pid,
                "new_pid": new_pid,
            }

    assert not vms_with_wrong_pids_dict, f"Some VMs have wrong pids after migration - {vms_with_wrong_pids_dict}"


def verify_wsl2_guest_works_multi_vm(vm_list):
    failed_vm_list = []
    for vm in vm_list:
        try:
            running_vm(vm=vm)
            verify_wsl2_guest_works(vm=vm)
        except TimeoutExpiredError:
            failed_vm_list.append(vm.name)
    assert not failed_vm_list, f"Some VMs have no WSL2 guests running! Failed VMs: {failed_vm_list}"


def verify_windows_upgraded_recently_multi_vms(vm_list):
    get_upgrade_history_cmd = shlex.split('powershell -c "Get-WUHistory -MaxDate (Get-Date).AddDays(-1) -Last 5"')

    failed_vms_list = []
    for vm in vm_list:
        if not run_ssh_commands(host=vm.ssh_exec, commands=get_upgrade_history_cmd)[0]:
            failed_vms_list.append(vm.name)

    assert not failed_vms_list, f"Some VMs failed to upgrade! Falied VMs: {failed_vms_list}"


def wait_vms_booted_and_start_processes(vms_list, os_type, wsl2_guest=False):
    vms_and_pids = {}

    for vm in vms_list:
        running_vm(vm=vm)
        if wsl2_guest:
            verify_wsl2_guest_works(vm=vm)
        vms_and_pids.update(start_process_in_guest(vm=vm, os_type=os_type))

    return vms_and_pids


def wait_windows_reboot_multi_vm(vm_list):
    def _check_vms_rebooted(_vm_list):
        os_dict = PROC_PER_OS_DICT[WINDOWS_OS_PREFIX]
        rebooted_vms = []
        for vm in _vm_list:
            try:
                wait_for_ssh_connectivity(vm=vm)
                os_dict["fetch_pid"](vm=vm, process_name=os_dict["proc_name"])
            except (AssertionError, ValueError, TimeoutExpiredError):
                rebooted_vms.append(vm.name)
        return rebooted_vms

    upgrading_vms = []
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_60MIN,
        sleep=TIMEOUT_5MIN,
        func=_check_vms_rebooted,
        _vm_list=vm_list,
    )
    try:
        for sample in samples:
            if len(vm_list) == len(sample):
                LOGGER.info("All VMs rebooted and finalized upgrade")
                return
            else:
                upgrading_vms = [vm.name for vm in vm_list if vm.name not in sample]
                LOGGER.info(f"Not all VMs rebooted\nVMs still upgrading: {upgrading_vms}\nVMs rebooted: {sample}")
    except TimeoutExpiredError:
        LOGGER.error(f"Some VMs failed to reboot\nVMs still upgrading: {upgrading_vms}\nVMs rebooted: {sample}")
        raise


def deploy_and_start_vms(vm_list):
    try:
        for vm in vm_list:
            vm.deploy()
            vm.start()
        yield vm_list
    finally:
        for vm in vm_list:
            vm.clean_up()


def deploy_and_wait_for_dvs(dv_dict):
    dv_list = dv_dict.values()
    try:
        for dv in dv_list:
            dv.deploy()
        for dv in dv_list:
            dv.wait_for_dv_success(timeout=TIMEOUT_30MIN)
        yield dv_dict
    finally:
        for dv in dv_list:
            dv.clean_up()


def deploy_datasources(datasource_dict):
    datasource_list = datasource_dict.values()
    try:
        for ds in datasource_list:
            ds.deploy()
        yield datasource_dict
    finally:
        for ds in datasource_list:
            ds.clean_up()


def create_containerdisk_vms(vm_deploys, client, name, namespace):
    vms = [
        VirtualMachineForTests(
            name=f"{name}-{deployment + 1}",
            namespace=namespace.name,
            body=fedora_vm_body(name=name),
            client=client,
        )
        for deployment in range(vm_deploys)
    ]

    yield from deploy_and_start_vms(vm_list=vms)


def create_dv_vms(
    vm_deploys,
    client,
    namespace,
    vm_params,
    datasources,
    nodes_common_cpu_model=None,
    cpu_flags=None,
):
    vms = []
    for vm in vm_params:
        vm_name = [*vm][0]
        vms_per_type = [
            VirtualMachineForTestsFromTemplate(
                name=f"{vm_name}-{deployment + 1}",
                labels=Template.generate_template_labels(**vm[vm_name].get("os_labels")),
                namespace=namespace.name,
                client=client,
                termination_grace_period=0,
                cpu_cores=vm[vm_name].get("cpu_cores"),
                cpu_threads=vm[vm_name].get("cpu_threads"),
                memory_guest=vm[vm_name].get("memory_guest"),
                cpu_flags=cpu_flags,
                cpu_model=nodes_common_cpu_model,
                data_source=datasources[vm[vm_name].get("datasource_name")],
                cloud_init_data=vm[vm_name].get("cloud_init_data"),
                attached_secret=vm[vm_name].get("attached_secret"),
            )
            for deployment in range(vm_deploys)
        ]
        vms.extend(vms_per_type)

    yield from deploy_and_start_vms(vm_list=vms)


def create_multi_dvs(namespace, client, dv_params):
    namespace_name = namespace.name
    artifactory_secret = get_artifactory_secret(namespace=namespace_name)
    artifactory_config_map = get_artifactory_config_map(namespace=namespace_name)
    dvs = {}
    for dv in dv_params:
        dv_name = [*dv][0]
        dvs[dv_name] = DataVolume(
            name=dv_name,
            client=client,
            namespace=namespace_name,
            source="http",
            size=dv[dv_name].get("dv_size"),
            storage_class=dv[dv_name].get("storage_class"),
            url=f"{get_test_artifact_server_url()}{dv[dv_name].get('image_path')}",
            api_name="storage",
            secret=artifactory_secret,
            cert_configmap=artifactory_config_map.name,
        )

    yield from deploy_and_wait_for_dvs(dv_dict=dvs)
    cleanup_artifactory_secret_and_config_map(
        artifactory_secret=artifactory_secret, artifactory_config_map=artifactory_config_map
    )


def create_multi_datasources(client, dvs):
    datasources_dict = {}
    for dv_name in dvs:
        datasources_dict[dv_name] = DataSource(
            name=dv_name,
            namespace=dvs[dv_name].namespace,
            client=client,
            source={"pvc": {"name": dv_name, "namespace": dvs[dv_name].namespace}},
        )

    yield from deploy_datasources(datasource_dict=datasources_dict)

import http
import logging
import re
import shlex
import tarfile
from contextlib import contextmanager
from io import BytesIO
from typing import Generator, Optional

import bitmath
import requests
import xmltodict
from bs4 import BeautifulSoup
from kubernetes.dynamic import DynamicClient
from kubernetes.dynamic.exceptions import ResourceNotFoundError
from ocp_resources.datavolume import DataVolume
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.resource import ResourceEditor
from ocp_resources.virtual_machine import VirtualMachine
from ocp_resources.virtual_machine_instance_migration import VirtualMachineInstanceMigration
from pyhelper_utils.shell import run_ssh_commands
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from utilities.constants import (
    DISK_SERIAL,
    HCO_DEFAULT_CPU_MODEL_KEY,
    RHSM_SECRET_NAME,
    TIMEOUT_1SEC,
    TIMEOUT_5SEC,
    TIMEOUT_10MIN,
    TIMEOUT_10SEC,
    TIMEOUT_30MIN,
    Images,
)
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.infra import (
    ExecCommandOnPod,
    get_artifactory_config_map,
    get_artifactory_header,
    get_artifactory_secret,
    get_http_image_url,
)
from utilities.virt import (
    VirtualMachineForTests,
    fedora_vm_body,
    get_created_migration_job,
    prepare_cloud_init_user_data,
    running_vm,
    wait_for_migration_finished,
    wait_for_ssh_connectivity,
    wait_for_updated_kv_value,
)

NUM_TEST_VMS = 3
NOT_PUBLISHED_MESSAGE = (
    "This documentation is a work in progress that aligns to preview releases of the next pending "
    "OpenShift Container Platform version"
)
LOGGER = logging.getLogger(__name__)


def create_vms(
    name_prefix,
    namespace_name,
    vm_count=NUM_TEST_VMS,
    client=None,
    ssh=True,
    node_selector_labels=None,
):
    """
    Create n number of fedora vms.

    Args:
        name_prefix (str): prefix to be used to name virtualmachines
        namespace_name (str): Namespace to be used for vm creation
        vm_count (int): Number of vms to be created
        node_selector_labels (str): Labels for node selector.
        client (DynamicClient): DynamicClient object
        ssh (bool): enable SSH on the VM

    Returns:
        list: List of VirtualMachineForTests
    """
    vms_list = []
    for idx in range(vm_count):
        vm_name = f"{name_prefix}-{idx}"
        with VirtualMachineForTests(
            name=vm_name,
            namespace=namespace_name,
            body=fedora_vm_body(name=vm_name),
            node_selector_labels=node_selector_labels,
            teardown=False,
            run_strategy=VirtualMachine.RunStrategy.ALWAYS,
            ssh=ssh,
            client=client,
        ) as vm:
            vms_list.append(vm)
    return vms_list


def wait_for_cr_labels_change(expected_value, component, timeout=TIMEOUT_10MIN):
    """
    Waits for CR metadata.labels to reach expected values

    Args:
        expected_value (dict): expected value for metadata.labels
        component (Resource): Resource object

    Raises:
        TimeoutExpiredError: If the CR's metadata.labels does not match with expected value.
    """
    samplers = TimeoutSampler(
        wait_timeout=timeout,
        sleep=TIMEOUT_5SEC,
        func=lambda: component.labels,
    )
    label = None
    try:
        for label in samplers:
            if label == expected_value:
                LOGGER.info(f"For {component.name}: Found expected spec values: '{expected_value}'")
                return

    except TimeoutExpiredError:
        LOGGER.error(
            f"{component.name}: Timed out waiting for CR labels to reach expected value: '{expected_value}'"
            f" current value:'{label}'"
        )
        raise


def validate_runbook_url_exists(url, alert_name=None, production=False):
    response = requests.get(url, allow_redirects=False)
    LOGGER.info(response)
    if response.status_code != http.HTTPStatus.OK:
        return f"{url} validation failed: {response}"
    if production:
        assert alert_name
        url_link = f"#virt-runbook-{alert_name}"
        if NOT_PUBLISHED_MESSAGE in response.text:
            LOGGER.error(f"{url} found with message {NOT_PUBLISHED_MESSAGE}: {response.content}")
            return f"{url} not published yet."
        soup = BeautifulSoup(response.content)
        for link in soup.findAll("a"):
            url_str = link.get("href")
            if url_str and url_str.endswith(url_link):
                LOGGER.info(f"Alert link is found : {link}")
                return
        LOGGER.warning(f"Alert url {url} not found for alert {alert_name}")
        return f"Alert url {url} not found"


def get_image_from_csv(image_string, csv_related_images):
    for image in csv_related_images:
        if image_string in image["image"]:
            return image["image"]

    raise ResourceNotFoundError(f"no image with the string {image_string} was found in the csv_dict")


def get_image_name_from_csv(image_string, csv_related_images):
    for image in csv_related_images:
        if image_string in image["name"]:
            return image["name"]

    raise ResourceNotFoundError(f"no image with the string {image_string} was found in the csv_dict")


def hotplug_spec_vm_and_verify_hotplug(vm, client, sockets=None, memory_guest=None):
    assert sockets or memory_guest, "No resource for update provided!!!"
    hotplug_spec_vm(vm=vm, sockets=sockets, memory_guest=memory_guest)
    verify_hotplug(vm=vm, client=client, sockets=sockets, memory_guest=memory_guest)


def hotplug_instance_type_vm_and_verify(vm, client, instance_type):
    instance_type_spec = instance_type.instance.spec
    update_vm_instancetype_name(vm=vm, instance_type_name=instance_type.name)
    verify_hotplug(
        vm=vm, client=client, sockets=instance_type_spec.cpu.guest, memory_guest=instance_type_spec.memory.guest
    )


def verify_hotplug(vm, client, sockets=None, memory_guest=None):
    vmim = get_created_migration_job(vm=vm, client=client)
    wait_for_migration_finished(
        namespace=vm.namespace, migration=vmim, timeout=TIMEOUT_30MIN if "windows" in vm.name else TIMEOUT_10MIN
    )
    wait_for_ssh_connectivity(vm=vm)
    vmi_spec_domain = vm.vmi.instance.spec.domain
    if sockets:
        assert vmi_spec_domain.cpu.sockets == sockets, (
            f"Hotplug CPU not added to VMI spec! VMI spec {vmi_spec_domain.cpu}"
        )
    if memory_guest:
        assert vmi_spec_domain.memory.guest == memory_guest, (
            f"Hotplug memory not added to VMI spec! VMI spec: {vmi_spec_domain.memory}"
        )


def hotplug_spec_vm(vm, sockets=None, memory_guest=None):
    patch = {
        vm: {
            "spec": {
                "template": {
                    "spec": {
                        "domain": {"cpu": {"sockets": sockets}} if sockets else {"memory": {"guest": memory_guest}}
                    }
                }
            }
        }
    }
    ResourceEditor(patches=patch).update()


def update_vm_instancetype_name(vm, instance_type_name):
    patch = {vm: {"spec": {"instancetype": {"name": instance_type_name}}}}
    ResourceEditor(patches=patch).update()


def clean_up_migration_jobs(client, vm):
    for migration_job in VirtualMachineInstanceMigration.get(dyn_client=client, namespace=vm.namespace):
        migration_job.clean_up()


def get_os_cpu_count(vm):
    if "windows" in vm.name:
        cmd = shlex.split("echo %NUMBER_OF_PROCESSORS%")
    else:
        cmd = shlex.split("nproc --all")
    return int(run_ssh_commands(host=vm.ssh_exec, commands=cmd)[0].strip())


def get_os_memory_value(vm):
    if "windows" in vm.name:
        cmd = shlex.split("wmic ComputerSystem get TotalPhysicalMemory")
        wmic_total_mem = run_ssh_commands(host=vm.ssh_exec, commands=cmd)[0].strip().split()[1]
        return f"{round(float(bitmath.Bit(int(wmic_total_mem)).to_Gib()))}Gi"
    else:
        cmd = shlex.split("awk \"'{print$2/1024/1024;exit}'\" /proc/meminfo")
        meminfo = run_ssh_commands(host=vm.ssh_exec, commands=cmd)[0].strip()
        return f"{round(float(meminfo))}Gi"


def assert_guest_os_cpu_count(vm, spec_cpu_amount):
    guest_os_cpu_amount = get_os_cpu_count(vm=vm)
    assert guest_os_cpu_amount == spec_cpu_amount, (
        f"Wrong amount of CPUs! Guest: {guest_os_cpu_amount}; VMI: {spec_cpu_amount}"
    )


def assert_guest_os_memory_amount(vm, spec_memory_amount):
    guest_os_memory_amount = get_os_memory_value(vm=vm)
    assert guest_os_memory_amount == spec_memory_amount, (
        f"Wrong amount of memory! Guest: {guest_os_memory_amount}; VMI: {spec_memory_amount}"
    )


def assert_restart_required_condition(vm, expected_message):
    sampler = TimeoutSampler(
        wait_timeout=TIMEOUT_10SEC,
        sleep=TIMEOUT_1SEC,
        func=vm.get_condition_message,
        condition_type="RestartRequired",
        condition_status=vm.Condition.Status.TRUE,
    )
    try:
        for sample in sampler:
            if sample == expected_message:
                return
    except TimeoutExpiredError:
        LOGGER.error("No RestartRequired condition found on VM!")
        raise


@contextmanager
def update_cluster_cpu_model(admin_client, hco_namespace, hco_resource, cpu_model):
    with ResourceEditorValidateHCOReconcile(
        patches={hco_resource: {"spec": {HCO_DEFAULT_CPU_MODEL_KEY: cpu_model}}},
        list_resource_reconcile=[KubeVirt],
        wait_for_reconcile_post_update=True,
    ):
        wait_for_updated_kv_value(
            admin_client=admin_client,
            hco_namespace=hco_namespace,
            path=["cpuModel"],
            value=cpu_model,
            timeout=30,
        )
        yield


def get_vm_cpu_list(vm):
    vcpuinfo = vm.privileged_vmi.virt_launcher_pod.execute(
        command=shlex.split(f"virsh vcpuinfo {vm.namespace}_{vm.name}")
    )

    return [cpu.split()[1] for cpu in vcpuinfo.split("\n") if re.search(r"^CPU:", cpu)]


def get_numa_node_cpu_dict(vm):
    """
    Extract NUMA nodes from libvirt

    Args:
        vm (VirtualMachine): VM

    Returns:
        dict with numa id as key and cpu list as value.
        Example:
            {'<numa_node_id>': [cpu_list]}
    """
    out = vm.privileged_vmi.virt_launcher_pod.execute(command=shlex.split("virsh capabilities"))
    numa = xmltodict.parse(out)["capabilities"]["host"]["cache"]["bank"]

    return {elem["@id"]: elem["@cpus"].split(",") for elem in numa}


def get_numa_cpu_allocation(vm_cpus, numa_nodes):
    """
    Find NUMA node # where VM CPUs are allocated.
    """

    def _parse_ranges_to_list(ranges):
        cpus = []
        for elem in ranges:
            if "-" in elem:
                start, end = elem.split("-")
                cpus.extend([str(num) for num in range(int(start), int(end) + 1)])
            else:
                cpus.append(elem)
        return cpus

    for node in numa_nodes.keys():
        if all(cpu in _parse_ranges_to_list(ranges=numa_nodes[node]) for cpu in vm_cpus):
            return node


def get_sriov_pci_address(vm):
    """
    Get PCI address of SRIOV device in virsh.

    Args:
        vm (VirtualMachine): VM object

    Returns:
        list: PCI address(es) of SRIOV device
        Example:
            ['0000:3b:0a.2']
    """
    sriov_pci_addresses = []
    hostdev_devices = vm.privileged_vmi.xml_dict["domain"]["devices"]["hostdev"]
    for device in hostdev_devices:
        addr = device["source"]["address"]
        sriov_pci_addresses.append(
            f"{addr['@domain'][2:]}:{addr['@bus'][2:]}:{addr['@slot'][2:]}.{addr['@function'][2:]}"
        )

    return sriov_pci_addresses


def get_numa_sriov_allocation(vm, utility_pods):
    """
    Find NUMA node number where SR-IOV device is allocated.
    """
    sriov_alocation_list = []
    sriov_addresses = get_sriov_pci_address(vm=vm)
    for address in sriov_addresses:
        sriov_alocation_list.append(
            ExecCommandOnPod(utility_pods=utility_pods, node=vm.vmi.node)
            .exec(command=f"cat /sys/bus/pci/devices/{address}/numa_node")
            .strip()
        )

    return sriov_alocation_list


def validate_dedicated_emulatorthread(vm):
    cpu = vm.instance.spec.template.spec.domain.cpu
    template_flavor_expected_cpu_count = cpu.threads * cpu.cores * cpu.sockets
    nproc_output = int(
        re.match(
            r"(\d+)",
            run_ssh_commands(
                host=vm.ssh_exec,
                commands=["nproc"],
            )[0],
        ).group(1)
    )
    assert nproc_output == template_flavor_expected_cpu_count, (
        f"Guest CPU count {nproc_output} is not as expected, {template_flavor_expected_cpu_count}"
    )
    LOGGER.info("Verify VM XML - Isolate Emulator Thread.")
    cputune = vm.privileged_vmi.xml_dict["domain"]["cputune"]
    emulatorpin_cpuset = cputune["emulatorpin"]["@cpuset"]
    if template_flavor_expected_cpu_count == 1:
        vcpupin_cpuset = cputune["vcpupin"]["@cpuset"]
        # When isolateEmulatorThread is set to True,
        # Ensure that KubeVirt will allocate one additional dedicated CPU,
        # exclusively for the emulator thread.
        assert emulatorpin_cpuset != vcpupin_cpuset, assert_msg(emulatorpin=emulatorpin_cpuset, vcpupin=vcpupin_cpuset)
    else:
        vcpupin_cpuset = [pcpu_id["@cpuset"] for pcpu_id in cputune["vcpupin"]]
        assert emulatorpin_cpuset not in vcpupin_cpuset, assert_msg(
            emulatorpin=emulatorpin_cpuset, vcpupin=vcpupin_cpuset
        )


def validate_iothreads_emulatorthread_on_same_pcpu(vm):
    LOGGER.info(f"Verify IO Thread Policy in VM {vm.name} domain XML.")
    cputune = vm.privileged_vmi.xml_dict["domain"]["cputune"]
    emulatorpin_cpuset = cputune["emulatorpin"]["@cpuset"]
    iothreadpin_cpuset = cputune["iothreadpin"]["@cpuset"]
    # When dedicatedCPUPlacement is True, isolateEmulatorThread is True,
    # dedicatedIOThread is True and ioThreadsPolicy is set "auto".
    # Ensure that KubeVirt will allocate ioThreads to the same
    # physical cpu of the QEMU Emulator Thread.
    assert iothreadpin_cpuset == emulatorpin_cpuset, (
        f"If isolateEmulatorThread=True and also ioThreadsPolicy is 'auto',"
        f"KubeVirt should allocate same physical cpu."
        f"Expected: iothreadspin cpuset {iothreadpin_cpuset} equals emulatorpin cpuset {emulatorpin_cpuset}."
    )


def assert_msg(emulatorpin, vcpupin):
    return (
        f"If isolateEmulatorThread=True, KubeVirt shouldn't allocate same pcpu "
        f"for both vcpupin {vcpupin} and emulatorpin {emulatorpin}"
    )


def assert_virt_launcher_pod_cpu_manager_node_selector(virt_launcher_pod):
    assert virt_launcher_pod.spec.nodeSelector.cpumanager, "NUMA Pod doesn't have cpumanager node selector"


def assert_numa_cpu_allocation(vm_cpus, numa_nodes):
    assert get_numa_cpu_allocation(vm_cpus=vm_cpus, numa_nodes=numa_nodes), (
        f"Not all vCPUs are pinned in one numa node! VM vCPUS {vm_cpus}, NUMA node CPU lists {numa_nodes}"
    )


def assert_cpus_and_sriov_on_same_node(vm, utility_pods):
    cpu_alloc = get_numa_cpu_allocation(
        vm_cpus=get_vm_cpu_list(vm=vm),
        numa_nodes=get_numa_node_cpu_dict(vm=vm),
    )
    sriov_alloc = get_numa_sriov_allocation(vm=vm, utility_pods=utility_pods)

    assert set(cpu_alloc) == set(sriov_alloc), (
        f"SR-IOV and CPUs are on different NUMA nodes! CPUs allocated to node {cpu_alloc}, SR-IOV to node {sriov_alloc}"
    )


def get_parameters_from_template(template, parameter_subset):
    """Returns a dict with matching template parameters.

    Args:
        template (Template): Template
        parameter_subset (str): Parameter name subset; may apply to a number of parameters

    Returns:
        dict: {parameter name: parameter value}
    """
    return {
        parameter["name"]: parameter["value"]
        for parameter in template.instance.parameters
        if parameter_subset in parameter["name"]
    }


def download_and_extract_tar(tarfile_url, dest_path):
    """Download and Extract the tar file."""
    artifactory_header = get_artifactory_header()
    request = requests.get(tarfile_url, verify=False, headers=artifactory_header)
    thetarfile = tarfile.open(fileobj=BytesIO(request.content), mode="r|xz")
    thetarfile.extractall(path=dest_path)


@contextmanager
def update_hco_with_persistent_storage_config(hco_cr, storage_class):
    with ResourceEditorValidateHCOReconcile(
        patches={hco_cr: {"spec": {"vmStateStorageClass": storage_class}}},
        list_resource_reconcile=[KubeVirt],
        wait_for_reconcile_post_update=True,
    ):
        yield


def generate_attached_rhsm_secret_dict():
    return {
        "volume_name": "rhsm-secret-vol",
        "serial": DISK_SERIAL,
        "secret_name": RHSM_SECRET_NAME,
    }


def generate_rhsm_cloud_init_data():
    bootcmds = [
        f"mkdir /mnt/{RHSM_SECRET_NAME}",
        f'mount /dev/$(lsblk --nodeps -no name,serial | grep {DISK_SERIAL} | cut -f1 -d" ") /mnt/{RHSM_SECRET_NAME}',
        "subscription-manager config --rhsm.auto_enable_yum_plugins=0",
    ]

    return prepare_cloud_init_user_data(section="bootcmd", data=bootcmds)


def register_vm_to_rhsm(vm):
    LOGGER.info("Register the VM with RedHat Subscription Manager")

    run_ssh_commands(
        host=vm.ssh_exec,
        commands=shlex.split(
            "sudo subscription-manager register "
            "--serverurl=subscription.rhsm.stage.redhat.com:443/subscription "
            "--baseurl=https://cdn.stage.redhat.com "
            f"--username=`sudo cat /mnt/{RHSM_SECRET_NAME}/username` "
            f"--password=`sudo cat /mnt/{RHSM_SECRET_NAME}/password` "
            "--auto-attach"
        ),
    )


@contextmanager
def create_cirros_vm(
    storage_class: str,
    namespace: str,
    client: DynamicClient,
    dv_name: str,
    vm_name: str,
    node: Optional[str] = None,
    wait_running: Optional[bool] = True,
    volume_mode: Optional[str] = None,
    cpu_model: Optional[str] = None,
    annotations: Optional[str] = None,
) -> Generator[VirtualMachineForTests, None, None]:
    artifactory_secret = get_artifactory_secret(namespace=namespace)
    artifactory_config_map = get_artifactory_config_map(namespace=namespace)

    dv = DataVolume(
        name=dv_name,
        namespace=namespace,
        source="http",
        url=get_http_image_url(image_directory=Images.Cirros.DIR, image_name=Images.Cirros.QCOW2_IMG),
        storage_class=storage_class,
        size=Images.Cirros.DEFAULT_DV_SIZE,
        api_name="storage",
        volume_mode=volume_mode,
        secret=artifactory_secret,
        cert_configmap=artifactory_config_map.name,
    )
    dv.to_dict()
    dv_metadata = dv.res["metadata"]
    with VirtualMachineForTests(
        client=client,
        name=vm_name,
        namespace=dv_metadata["namespace"],
        os_flavor=Images.Cirros.OS_FLAVOR,
        memory_guest=Images.Cirros.DEFAULT_MEMORY_SIZE,
        data_volume_template={"metadata": dv_metadata, "spec": dv.res["spec"]},
        node_selector=node,
        run_strategy=VirtualMachine.RunStrategy.ALWAYS,
        cpu_model=cpu_model,
        annotations=annotations,
    ) as vm:
        if wait_running:
            running_vm(vm=vm, wait_for_interfaces=False)
        yield vm

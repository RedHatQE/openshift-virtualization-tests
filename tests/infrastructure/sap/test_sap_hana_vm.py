import logging
import re
import shlex
from copy import deepcopy

import bitmath
import pytest
import xmltodict
from ocp_resources.node import Node
from ocp_resources.sriov_network_node_policy import SriovNetworkNodePolicy
from ocp_resources.template import Template
from pyhelper_utils.shell import run_ssh_commands

from tests.utils import (
    assert_cpus_and_sriov_on_same_node,
    assert_numa_cpu_allocation,
    assert_virt_launcher_pod_cpu_manager_node_selector,
    generate_attached_rhsm_secret_dict,
    generate_rhsm_cloud_init_data,
    get_numa_node_cpu_dict,
    get_parameters_from_template,
    get_vm_cpu_list,
    register_vm_to_rhsm,
    validate_dedicated_emulatorthread,
    validate_iothreads_emulatorthread_on_same_pcpu,
)
from utilities.constants import (
    CNV_SUPPLEMENTAL_TEMPLATES_URL,
    PUBLIC_DNS_SERVER_IP,
    SRIOV,
    TSC_FREQUENCY,
    VIRTIO,
    NamespacesNames,
    StorageClassNames,
)
from utilities.infra import ExecCommandOnPod
from utilities.network import is_destination_pingable_from_vm, network_nad
from utilities.ssp import create_custom_template_from_url
from utilities.virt import (
    VirtualMachineForTestsFromTemplate,
    prepare_cloud_init_user_data,
    running_vm,
    wait_for_console,
)

LOGGER = logging.getLogger(__name__)
SAP_HANA_VM_TEST_NAME = "TestSAPHANAVirtualMachine::test_sap_hana_running_vm"
SAP_HANA_VM_NAME = "sap-hana-vm"
INVTSC = "invtsc"
CPU_TIMER_LABEL_PREFIX = "cpu-timer.node.kubevirt.io"
LSCPU_CMD = "lscpu"
REQUIRED_NUMBER_OF_NETWORKS = 3
WORKLOAD_NODE_LABEL_NAME = f"{Node.ApiGroup.KUBEVIRT_IO}/workload"
WORKLOAD_NODE_LABEL_VALUE = "hana"


pytestmark = [
    pytest.mark.usefixtures("fail_if_not_hana_cluster"),
    pytest.mark.special_infra,
    pytest.mark.cpu_manager,
    pytest.mark.sap_hana,
]


class SAPHANAVirtaulMachine(VirtualMachineForTestsFromTemplate):
    volume_name = "rhsm-secret-vol"

    def __init__(
        self,
        name,
        namespace,
        client,
        labels,
        cloud_init_data,
        data_volume_template,
        template_params,
        cpu_cores=None,
        attached_rhsm_secret=False,
        network_multiqueue=True,
    ):
        super().__init__(
            name=name,
            namespace=namespace,
            client=client,
            labels=labels,
            cloud_init_data=cloud_init_data,
            data_volume_template=data_volume_template,
            attached_secret=attached_rhsm_secret,
            template_params=template_params,
            cpu_cores=cpu_cores,
            network_multiqueue=network_multiqueue,
        )
        self.attached_rhsm_secret = attached_rhsm_secret

    def to_dict(self):
        super().to_dict()
        if self.attached_rhsm_secret:
            spec_template = self.res["spec"]["template"]["spec"]
            disks = spec_template["domain"]["devices"]["disks"]
            secret_disk = [disk for disk in disks if disk["name"] == SAPHANAVirtaulMachine.volume_name][0]
            secret_disk["disk"]["bus"] = VIRTIO


def get_node_labels_by_name_subset(node, label_name_subset):
    return {
        label_name: label_value for label_name, label_value in node.labels.items() if label_name_subset in label_name
    }


def assert_node_label_exists(node, label_name):
    assert label_name, f"Node {node.name} does not have {label_name} label."


def verify_vm_cpu_topology(vm, vmi_xml_dict, guest_cpu_config, template):
    LOGGER.info(f"Verify {vm.name} CPU configuration in libvirt and guest")
    vm_cpu_config = vmi_xml_dict["cpu"]["topology"]
    template_cpu_config = get_parameters_from_template(template=template, parameter_subset="CPU_")

    failed_cpu_configuration = []
    if not (vm_cpu_config["@sockets"] == template_cpu_config["CPU_SOCKETS"] == guest_cpu_config["sockets"]):
        failed_cpu_configuration.append("sockets")
    if not (vm_cpu_config["@cores"] == template_cpu_config["CPU_CORES"] == guest_cpu_config["cores"]):
        failed_cpu_configuration.append("cores")
    if not (vm_cpu_config["@threads"] == template_cpu_config["CPU_THREADS"] == guest_cpu_config["threads"]):
        failed_cpu_configuration.append("threads")

    assert not failed_cpu_configuration, (
        f"VM failed {failed_cpu_configuration} CPU topology configuration:\n expected: {template_cpu_config}\n "
        f"libvirt spec:{vm_cpu_config}\n guest spec: {guest_cpu_config}"
    )


def extract_lscpu_info(lscpu_output):
    """
    Extract data fom lscpu command executed guest

    Args:
        lscpu_output (str): output of lscpu command

    Returns:
        dict with command output for CPU threads, cores, sockets, numa nodes, CPU name and CPU flags.

    Example:
        {'threads': '1',
         'cores': '4',
         'sockets': '1',
         'numa_nodes': '1',
         'model_name': 'Intel(R) Xeon(R) Gold 6238L CPU @ 2.10GHz',
         'cpu_flags': 'fpu vme de pse tsc msr pae mce cx8 apic sep mtrr pge'}
    """

    return re.search(
        r".*Thread\(s\) per core:\s+(?P<threads>\d+).*Core\(s\) per socket:\s+(?P<cores>\d+).*Socket\(s\):\s+"
        r"(?P<sockets>\d+).*NUMA node\(s\):\s+(?P<numa_nodes>\d+).*Model name:\s+(?P<model_name>.*)\nStepping"
        r".*Flags:\s+(?P<cpu_flags>.*).*",
        lscpu_output,
        re.DOTALL,
    ).groupdict()


def assert_libvirt_cpu_host_passthrough(vm, vmi_xml_dict):
    host_passthrough = "host-passthrough"
    LOGGER.info(f"Verify {vm.name} CPU {host_passthrough}")
    libvirt_cpu_mode = vmi_xml_dict["cpu"]["@mode"]
    assert libvirt_cpu_mode == host_passthrough, f"CPU mode is {libvirt_cpu_mode}, expected: {host_passthrough}, "


def assert_vm_cpu_matches_node_cpu(node_lscpu_configuration, guest_cpu_config):
    # Verify host-passthrough configuration is enforced and VM CPU model is identical to the host's CPU model
    node_cpu_model = node_lscpu_configuration["model_name"]
    guest_cpu_model = guest_cpu_config["model_name"]
    assert node_cpu_model == guest_cpu_model, (
        f"Guest CPU model {guest_cpu_model} does not match host CPU model {node_cpu_model}"
    )


def verify_libvirt_huge_pages_configuration(template, vmi_xml_dict):
    template_huge_pages_param_subset_str = "HUGEPAGES_PAGE_SIZE"
    expected_huge_pages = get_parameters_from_template(
        template=template, parameter_subset=template_huge_pages_param_subset_str
    )[template_huge_pages_param_subset_str]
    libvirt_huge_pages = vmi_xml_dict["memoryBacking"]["hugepages"]["page"]
    libvirt_hugepages_size = bitmath.parse_string(
        f"{libvirt_huge_pages['@size']}{libvirt_huge_pages['@unit']}"
    ).to_GiB()
    assert libvirt_hugepages_size == bitmath.parse_string_unsafe(expected_huge_pages), (
        f"Wrong huge pages configuration. Expected: {expected_huge_pages}, actual: {libvirt_hugepages_size}"
    )


def verify_libvirt_memory_configuration(expected_memory, vmi_xml_dict):
    libvirt_expected_memory = vmi_xml_dict["memory"]
    calculated_libvirt_memory = bitmath.parse_string(
        f"{libvirt_expected_memory['#text']}{libvirt_expected_memory['@unit']}"
    ).to_GiB()
    assert calculated_libvirt_memory == bitmath.parse_string_unsafe(expected_memory), (
        f"Wrong memory configuration. Expected: {expected_memory}, actual: {libvirt_expected_memory}"
    )


def assert_node_huge_pages_size(utility_pods, sap_hana_node, vm):
    node_huge_pages = ExecCommandOnPod(utility_pods=utility_pods, node=sap_hana_node).exec(
        command="grep HugePages_ /proc/meminfo"
    )
    node_huge_pages_dict = re.search(
        r"HugePages_Total:\s+(?P<total_huge_pages>\d+).*HugePages_Free:\s+(?P<free_huge_pages>\d+).*",
        node_huge_pages,
        re.DOTALL,
    ).groupdict()
    node_allocated_huge_pages = int(node_huge_pages_dict["total_huge_pages"]) - int(
        node_huge_pages_dict["free_huge_pages"]
    )

    vm_memory_size = vm.instance.spec.template.spec.domain.memory.guest
    formatted_vm_memory_size = int(re.match(r"(\d+).*", vm_memory_size).group(1))
    assert node_allocated_huge_pages == formatted_vm_memory_size, (
        f"Node huge pages allocation  {node_allocated_huge_pages} does not match VM's memory {formatted_vm_memory_size}"
    )


def get_num_cores_from_domain_xml(vmi_xml_dict):
    return int(vmi_xml_dict["cpu"]["topology"]["@cores"])


def assert_vm_devices_queues(vm, vmi_xml_dict, libvirt_disks):
    vm_cores = get_num_cores_from_domain_xml(vmi_xml_dict=vmi_xml_dict)
    vm_boot_disk = [disk for disk in libvirt_disks if disk["alias"]["@name"].strip("ua-") in vm.name][0]
    boot_disk_queues = int(vm_boot_disk["driver"]["@queues"])
    assert vm_cores == boot_disk_queues, (
        f"VM disks number of queues {boot_disk_queues} does not match its number of cores {vm_cores}"
    )


def assert_vm_spec_memory_configuration(expected_memory_configuration, vm):
    vm_memory = vm.instance.spec.template.spec.domain.memory.guest
    expected_memory = expected_memory_configuration["MEMORY"]
    assert vm_memory == expected_memory, (
        f"VM memory {vm_memory} does not match 'MEMORY' template parameter value {expected_memory}"
    )


def assert_vm_memory_dump_metrics(metrics_dict, vmi_xml_dict):
    vm_allocated_memory = {
        name: value
        for metric in metrics_dict
        for name, value in metric.items()
        if metric["name"] == "PhysicalMemoryAllocatedToVirtualSystem"
    }["value"]
    libvirt_expected_memory = vmi_xml_dict["memory"]["#text"]
    assert vm_allocated_memory == libvirt_expected_memory, (
        f"VM metrics memeory {vm_allocated_memory} does not match expected value {libvirt_expected_memory}"
    )


def assert_vm_cpu_dump_metrics(metrics_dict, vmi_xml_dict):
    vm_allocated_cpus = {
        name: value
        for metric in metrics_dict
        for name, value in metric.items()
        if metric["name"] == "NumberOfPhysicalCPUs"
    }["value"]
    libvirt_expected_num_cores = get_num_cores_from_domain_xml(vmi_xml_dict=vmi_xml_dict)
    assert int(vm_allocated_cpus) == libvirt_expected_num_cores, (
        f"VM metrics cpu count {vm_allocated_cpus} does not match expected count {libvirt_expected_num_cores}"
    )


def get_template_params_dict(sriov_nads):
    template_params_dict = {"WORKLOAD_NODE_LABEL_VALUE": WORKLOAD_NODE_LABEL_VALUE}
    vm_network_sriov_name_prefix = "SRIOV_NETWORK_NAME"
    for nad_index, nad in enumerate(sriov_nads):
        template_params_dict.update({
            f"{vm_network_sriov_name_prefix}{nad_index + 1}": f"{nad.instance.spec.networkNamespace}/{nad.name}"
        })

    return template_params_dict


def assert_vm_disks_virtio_bus(libvirt_disks):
    libvirt_disks_bus_type = [disk["target"]["@bus"] for disk in libvirt_disks]
    assert set(libvirt_disks_bus_type) == {VIRTIO}, f"Some disks bus type is not {VIRTIO}, disks: {libvirt_disks}"


def assert_vm_downwardapi_disk(libvirt_disks):
    downwardapi = "downwardapi"
    assert any([f"{downwardapi}-disks" in disk["source"]["@file"] for disk in libvirt_disks]), (
        f"Missing {downwardapi} disk, disks: {libvirt_disks}"
    )


def verify_vm_reserved_cpus_on_node(vm_cpu_list, crio_cpuset):
    # node_cpuset contains a CPU dedicated for emulator thread along with VM's dedicated CPUs
    assert set(vm_cpu_list).issubset(crio_cpuset), (
        f"VM CPUs {vm_cpu_list} are not reserved, CPUs on the node: {crio_cpuset}"
    )


def calculate_first_numa_num_cpus(utility_pods, node):
    lscpu_ouput = get_node_lscpu(utility_pods=utility_pods, node=node)
    first_numa_num_cpus = re.search(r"NUMA node0 CPU\(s\):\s+(?P<numa_cpu>.*)\n.*", lscpu_ouput)["numa_cpu"]
    return len(first_numa_num_cpus.split(","))


def get_node_lscpu(utility_pods, node):
    return ExecCommandOnPod(utility_pods=utility_pods, node=node).exec(command=LSCPU_CMD)


@pytest.fixture(scope="class")
def sap_hana_data_volume_templates(sap_hana_template):
    data_volume_templates = deepcopy(sap_hana_template.instance.to_dict()["objects"][0]["spec"]["dataVolumeTemplates"])[
        0
    ]
    data_volume_templates["metadata"]["name"] = SAP_HANA_VM_NAME
    data_volume_templates["spec"]["storage"]["storageClassName"] = StorageClassNames.NFS

    src_containerdisk_str = "SRC_CONTAINERDISK"
    data_volume_templates["spec"]["source"]["registry"]["url"] = get_parameters_from_template(
        template=sap_hana_template, parameter_subset=src_containerdisk_str
    )[src_containerdisk_str]

    return data_volume_templates


@pytest.fixture(scope="class")
def sriov_network_node_policy(admin_client, sriov_namespace):
    """SriovNetworkNodePolicy (named "sriov-network-policy") is deployed as part of SAP HANA jenkins job"""
    sriov_available_node_policies = [
        policy
        for policy in SriovNetworkNodePolicy.get(
            dyn_client=admin_client,
            namespace=sriov_namespace.name,
        )
        if "sriov-network-policy" in policy.name
    ]
    assert len(sriov_available_node_policies) == REQUIRED_NUMBER_OF_NETWORKS, (
        f"Cluster should be configured with {REQUIRED_NUMBER_OF_NETWORKS} SR-IOV networks"
    )

    return sriov_available_node_policies


@pytest.fixture(scope="class")
def sriov_nads(namespace, sriov_network_node_policy, sriov_namespace):
    nads_list = []
    for idx in range(REQUIRED_NUMBER_OF_NETWORKS):
        with network_nad(
            nad_type=SRIOV,
            nad_name=f"sriov-net-{idx + 1}",
            sriov_resource_name=sriov_network_node_policy[idx].instance.spec.resourceName,
            namespace=sriov_namespace,
            sriov_network_namespace=namespace.name,
            macspoofchk="off",
            teardown=False,
        ) as nad:
            nads_list.append(nad)
    yield nads_list
    [nad.clean_up() for nad in nads_list]


@pytest.fixture(scope="class")
def sap_hana_vm(
    request,
    unprivileged_client,
    namespace,
    sriov_nads,
    sap_hana_template_labels,
    sap_hana_data_volume_templates,
    sap_hana_node,
    workers_utility_pods,
):
    template_params = get_template_params_dict(sriov_nads=sriov_nads)
    vm_kwargs = {
        "name": SAP_HANA_VM_NAME,
        "namespace": namespace.name,
        "client": unprivileged_client,
        "labels": sap_hana_template_labels,
        "data_volume_template": sap_hana_data_volume_templates,
        "template_params": template_params,
    }

    # Allow connectivity on all interfaces
    cloud_init_data = prepare_cloud_init_user_data(section="bootcmd", data=["sysctl -w net.ipv4.conf.all.rp_filter=0"])
    if request.param.get("add_rhsm_secret"):
        rhsm_clout_init = generate_rhsm_cloud_init_data()
        cloud_init_data["userData"]["bootcmd"].extend(rhsm_clout_init["userData"]["bootcmd"])
        vm_kwargs["attached_rhsm_secret"] = generate_attached_rhsm_secret_dict()
    vm_kwargs["cloud_init_data"] = cloud_init_data

    if request.param.get("set_cpus"):
        numa_node_num_cpus = calculate_first_numa_num_cpus(utility_pods=workers_utility_pods, node=sap_hana_node)
        # Add an even number of CPUs
        cpu_cores = numa_node_num_cpus + (2 if numa_node_num_cpus % 2 == 0 else 1)
        vm_kwargs["cpu_cores"] = cpu_cores

        # A VM with more than 14 CPUs will not have connectivity if NetworkMultiqueue is enabled
        if cpu_cores > 14:
            vm_kwargs["network_multiqueue"] = False

    with SAPHANAVirtaulMachine(**vm_kwargs) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture(scope="class")
def sap_hana_node(schedulable_nodes):
    hana_nodes = [
        node
        for node in schedulable_nodes
        for label_name, label_value in node.labels.items()
        if WORKLOAD_NODE_LABEL_NAME in label_name and label_value == WORKLOAD_NODE_LABEL_VALUE
    ]
    if hana_nodes:
        return hana_nodes[0]


@pytest.fixture(scope="class")
def fail_if_not_hana_cluster(skip_if_no_cpumanager_workers, sap_hana_node):
    if not sap_hana_node:
        pytest.fail(f"No node is marked with sap label {WORKLOAD_NODE_LABEL_NAME} = {WORKLOAD_NODE_LABEL_VALUE}")


@pytest.fixture(scope="class")
def sap_hana_node_lscpu_configuration(workers_utility_pods, sap_hana_node):
    lscpu_output = get_node_lscpu(utility_pods=workers_utility_pods, node=sap_hana_node)
    return extract_lscpu_info(lscpu_output=lscpu_output)


@pytest.fixture()
def hana_node_invtsc_labels(sap_hana_node):
    node_invtsc_labels = {
        label_name: label_value for label_name, label_value in sap_hana_node.labels.items() if INVTSC in label_name
    }
    assert node_invtsc_labels, f"Node {sap_hana_node.name} does not have {INVTSC} labels."
    assert all([label_value == "true" for label_value in node_invtsc_labels.values()]), (
        f"Some {INVTSC} lables are disabled: {node_invtsc_labels}"
    )


@pytest.fixture()
def hana_node_cpu_tsc_frequency_labels(sap_hana_node):
    node_tsc_frequency_labels = get_node_labels_by_name_subset(node=sap_hana_node, label_name_subset=TSC_FREQUENCY)
    assert_node_label_exists(node=sap_hana_node, label_name=TSC_FREQUENCY)
    assert int(node_tsc_frequency_labels[f"{CPU_TIMER_LABEL_PREFIX}/{TSC_FREQUENCY}"]) > 0, (
        f"Wrong {TSC_FREQUENCY}, value: {node_tsc_frequency_labels}"
    )


@pytest.fixture()
def hana_node_nonstop_tsc_cpu_flag(sap_hana_node_lscpu_configuration, sap_hana_node):
    nonstop_tsc_flag = "nonstop_tsc"
    node_cpu_flags = sap_hana_node_lscpu_configuration["cpu_flags"]
    assert nonstop_tsc_flag in node_cpu_flags, (
        f"Node {sap_hana_node.name} does not have {nonstop_tsc_flag} flag; existing flags: {node_cpu_flags}"
    )


@pytest.fixture()
def hana_node_cpu_tsc_scalable_label(sap_hana_node):
    tsc_scalable = "tsc-scalable"
    node_tsc_scalable_label = get_node_labels_by_name_subset(node=sap_hana_node, label_name_subset=tsc_scalable)
    assert_node_label_exists(node=sap_hana_node, label_name=tsc_scalable)
    assert node_tsc_scalable_label[f"{CPU_TIMER_LABEL_PREFIX}/{tsc_scalable}"] == "true", (
        f"{tsc_scalable} is disabled on {sap_hana_node.name}"
    )


@pytest.fixture(scope="module")
def sap_hana_template_labels():
    return [
        f"{Template.Labels.OS}/rhel8.4",
        f"{Template.Labels.WORKLOAD}/saphana",
        f"{Template.Labels.FLAVOR}/{Template.Flavor.TINY}",
    ]


@pytest.fixture(scope="module")
def sap_hana_template(tmpdir_factory):
    template_name = "sap_hana_template"
    template_dir = tmpdir_factory.mktemp(template_name)
    with create_custom_template_from_url(
        url=f"{CNV_SUPPLEMENTAL_TEMPLATES_URL}/saphana/rhel8.saphana.yaml",
        template_name=f"{template_name}.yaml",
        template_dir=template_dir,
        namespace=NamespacesNames.OPENSHIFT,
    ) as template:
        yield template


@pytest.fixture(scope="class")
def vmi_domxml(sap_hana_vm):
    return sap_hana_vm.vmi.xml_dict["domain"]


@pytest.fixture(scope="class")
def guest_lscpu_configuration(sap_hana_vm):
    guest_lscpu_output = run_ssh_commands(host=sap_hana_vm.ssh_exec, commands=[LSCPU_CMD])[0]
    return extract_lscpu_info(lscpu_output=guest_lscpu_output)


@pytest.fixture()
def registered_hana_vm_rhsm(sap_hana_vm):
    return register_vm_to_rhsm(vm=sap_hana_vm)


@pytest.fixture()
def installed_vm_dump_metrics(registered_hana_vm_rhsm, sap_hana_vm):
    run_ssh_commands(
        host=sap_hana_vm.ssh_exec,
        commands=shlex.split("sudo dnf install -y vm-dump-metrics"),
    )


@pytest.fixture()
def vm_dump_metrics(sap_hana_vm):
    metrics = run_ssh_commands(host=sap_hana_vm.ssh_exec, commands=["sudo", "vm-dump-metrics"])
    assert metrics, "No metrics are extracted using vm_dump_metrics"
    return metrics


@pytest.fixture(scope="class")
def vm_virt_launcher_pod_instance(sap_hana_vm):
    return sap_hana_vm.vmi.virt_launcher_pod.instance


@pytest.fixture(scope="class")
def vm_cpu_list(sap_hana_vm):
    return get_vm_cpu_list(vm=sap_hana_vm)


@pytest.fixture()
def numa_node_dict(sap_hana_vm):
    return get_numa_node_cpu_dict(vm=sap_hana_vm)


@pytest.fixture()
def libvirt_disks(vmi_domxml):
    return [disk for disk in vmi_domxml["devices"]["disk"]]


@pytest.fixture()
def vm_interfaces_names(sap_hana_vm):
    return [interface["interfaceName"] for interface in sap_hana_vm.vmi.interfaces]


@pytest.fixture()
def vm_crio_id_path(workers_utility_pods, sap_hana_node, sap_hana_vm):
    output_file = "/tmp/systemd_cgls_output.txt"

    def _extract_crio_id():
        # Get crio item, located right before the VM entry
        # systemd_cgls output example:
        #   │ └─crio-889593b9d5d49ae95be2f8233647bd053dd89dc4b67a6e151f47c5caf35b03be.scope
        #   │   ├─954896 /usr/bin/virt-launcher --qemu-timeout 265s --name sap-hana-vm-...
        #   │   ├─955121 /usr/bin/virt-launcher --qemu-timeout 265s --name sap-hana-vm-...
        crio_systemd_cgls = (
            ExecCommandOnPod(utility_pods=workers_utility_pods, node=sap_hana_node)
            .exec(command=f"cat {output_file} | grep -B1 {sap_hana_vm.name[:10]}")
            .split("\n")
        )
        match_result = re.match(r".*(crio-.*)", crio_systemd_cgls[0])
        assert match_result, f"crio- not found in systemd-cgls output: {crio_systemd_cgls[0]}"
        return match_result.group(1).replace("conmon-", "")

    def _extract_kubepods_id(crio_id):
        # Get kubepods-pod, item parent of crio
        # systemd_cgls output example:
        #   ├─kubepods-pod464bcc52_1e91_411c_9190_34f510249bc1.slice
        #   │ ├─crio-conmon-889593b9d5d49ae95be2f8233647bd053dd89dc4b67a6e151f47c5caf35b03be.scope
        #   │ │ └─954852 /usr/bin/conmon -b /run/containers/storage/overlay-containers/...
        #   │ └─crio-889593b9d5d49ae95be2f8233647bd053dd89dc4b67a6e151f47c5caf35b03be.scope
        kubepods_systemd_cgls = (
            ExecCommandOnPod(utility_pods=workers_utility_pods, node=sap_hana_node)
            .exec(command=f"cat {output_file} | grep -B3 {crio_id}")
            .split("\n")
        )
        for entry in kubepods_systemd_cgls:
            kubepods_item = re.match(r".*(kubepods-pod.*)", entry)
            if kubepods_item:
                return kubepods_item.group(1)

    # Dump systemd-cgls for data extraction
    ExecCommandOnPod(utility_pods=workers_utility_pods, node=sap_hana_node).exec(
        command=f"systemd-cgls -l /kubepods.slice > {output_file}"
    )

    crio_id = _extract_crio_id()
    return f"/sys/fs/cgroup/cpuset/kubepods.slice/{_extract_kubepods_id(crio_id=crio_id)}/{crio_id}"


@pytest.fixture()
def crio_cpuset(workers_utility_pods, sap_hana_node, vm_crio_id_path):
    return (
        ExecCommandOnPod(utility_pods=workers_utility_pods, node=sap_hana_node)
        .exec(command=f"cat {vm_crio_id_path}/cpuset.cpus")
        .split(",")
    )


class TestSAPHANATemplate:
    @pytest.mark.polarion("CNV-7623")
    def test_sap_hana_template_validation_rules(self, sap_hana_template):
        assert sap_hana_template.instance.objects[0].metadata.annotations[
            f"{sap_hana_template.ApiGroup.VM_KUBEVIRT_IO}/validations"
        ], "HANA template does not have validation rules."

    @pytest.mark.polarion("CNV-7759")
    def test_sap_hana_template_machine_type(self, sap_hana_template, machine_type_from_kubevirt_config):
        sap_hana_template_machine_type = sap_hana_template.instance.objects[0].spec.template.spec.domain.machine.type
        assert sap_hana_template_machine_type == machine_type_from_kubevirt_config, (
            f"Hana template machine type '{sap_hana_template_machine_type or None}' does not match expected type "
            f"{machine_type_from_kubevirt_config}"
        )

    @pytest.mark.polarion("CNV-7852")
    def test_sap_hana_template_no_evict_strategy(self, sap_hana_template):
        sap_hana_template_evict_strategy = sap_hana_template.instance.objects[0].spec.template.spec.evictionStrategy
        assert not sap_hana_template_evict_strategy, (
            "HANA template should not have evictionStrategy, current value in template: "
            f"{sap_hana_template_evict_strategy}"
        )

    @pytest.mark.polarion("CNV-7758")
    def test_sap_hana_template_provider_support_annotations(self, sap_hana_template):
        template_failed_annotations = []
        template_annotations = sap_hana_template.instance.metadata.annotations
        template_api_group = sap_hana_template.ApiGroup.TEMPLATE_KUBEVIRT_IO
        if template_annotations[f"{template_api_group}/provider-support-level"] != "Experimental":
            template_failed_annotations.append("provider-support-level")
        if template_annotations[f"{template_api_group}/provider-url"] != "https://www.redhat.com":
            template_failed_annotations.append("provider-url")
        if template_annotations[f"{template_api_group}/provider"] != "Red Hat - Tech Preview":
            template_failed_annotations.append("provide")
        assert not template_failed_annotations, (
            f"HANA template failed annotations: {template_failed_annotations}, "
            f"template annotations: {template_annotations}"
        )


@pytest.mark.usefixtures(
    "rhsm_created_secret",
)
@pytest.mark.parametrize(
    "sap_hana_vm",
    [
        pytest.param(
            {"add_rhsm_secret": True},
        )
    ],
    indirect=True,
)
class TestSAPHANAVirtualMachine:
    @pytest.mark.dependency(name=SAP_HANA_VM_TEST_NAME)
    @pytest.mark.polarion("CNV-7622")
    def test_sap_hana_console(self, sap_hana_vm):
        wait_for_console(
            vm=sap_hana_vm,
        )

    @pytest.mark.dependency(depends=[SAP_HANA_VM_TEST_NAME])
    @pytest.mark.polarion("CNV-7760")
    def test_sap_hana_vm_cpu_configuration(
        self,
        sap_hana_vm,
        vmi_domxml,
        guest_lscpu_configuration,
        sap_hana_template,
        workers_utility_pods,
    ):
        verify_vm_cpu_topology(
            vm=sap_hana_vm,
            vmi_xml_dict=vmi_domxml,
            guest_cpu_config=guest_lscpu_configuration,
            template=sap_hana_template,
        )

    @pytest.mark.dependency(depends=[SAP_HANA_VM_TEST_NAME])
    @pytest.mark.polarion("CNV-7870")
    def test_sap_hana_vm_cpu_host_passthrough(
        self,
        sap_hana_vm,
        vmi_domxml,
        guest_lscpu_configuration,
        sap_hana_node_lscpu_configuration,
    ):
        assert_libvirt_cpu_host_passthrough(
            vm=sap_hana_vm,
            vmi_xml_dict=vmi_domxml,
        )
        assert_vm_cpu_matches_node_cpu(
            node_lscpu_configuration=sap_hana_node_lscpu_configuration,
            guest_cpu_config=guest_lscpu_configuration,
        )

    @pytest.mark.dependency(depends=[SAP_HANA_VM_TEST_NAME])
    @pytest.mark.polarion("CNV-7763")
    def test_sap_hana_vm_invtsc_feature(
        self,
        hana_node_invtsc_labels,
        hana_node_cpu_tsc_frequency_labels,
        hana_node_cpu_tsc_scalable_label,
        hana_node_nonstop_tsc_cpu_flag,
        vmi_domxml,
    ):
        invtsc_libvirt_name = vmi_domxml["cpu"]["feature"]["@name"]
        invtsc_libvirt_policy = vmi_domxml["cpu"]["feature"]["@policy"]
        expected_policy = "require"
        assert invtsc_libvirt_name == INVTSC and invtsc_libvirt_policy == expected_policy, (
            f"wrong {INVTSC} policy in libvirt: policy name: {invtsc_libvirt_name}, value: {invtsc_libvirt_policy}, "
            f"expected: {expected_policy}"
        )

    @pytest.mark.dependency(depends=[SAP_HANA_VM_TEST_NAME])
    @pytest.mark.polarion("CNV-7773")
    def test_sap_hana_vm_virt_launcher_qos(self, sap_hana_vm, vm_virt_launcher_pod_instance):
        guaranteed = "Guaranteed"
        LOGGER.info(f"Verify {sap_hana_vm.name} virt-launcher pod QoS is {guaranteed}")
        virt_launcher_pod_qos = vm_virt_launcher_pod_instance.status.qosClass
        assert virt_launcher_pod_qos == guaranteed, (
            f"Virt-launcher QoS is {virt_launcher_pod_qos}, expected: {guaranteed}"
        )

    @pytest.mark.dependency(depends=[SAP_HANA_VM_TEST_NAME])
    @pytest.mark.polarion("CNV-7761")
    def test_sap_hana_vm_isolate_emulator_thread(self, sap_hana_vm):
        vm_isolated_emulator_thread = sap_hana_vm.instance.spec.template.spec.domain.cpu.isolateEmulatorThread
        assert vm_isolated_emulator_thread, (
            f"VM isolateEmulatorThread is not enabled, value: {vm_isolated_emulator_thread}"
        )
        validate_iothreads_emulatorthread_on_same_pcpu(vm=sap_hana_vm)

    @pytest.mark.dependency(depends=[SAP_HANA_VM_TEST_NAME])
    @pytest.mark.polarion("CNV-7762")
    def test_sap_hana_vm_dedicated_cpu_placement(self, sap_hana_vm):
        vm_dedicate_cpu_placement = sap_hana_vm.instance.spec.template.spec.domain.cpu.dedicatedCpuPlacement
        assert vm_dedicate_cpu_placement, f"VM isolateEmulatorThread is not enabled, value: {vm_dedicate_cpu_placement}"
        validate_dedicated_emulatorthread(vm=sap_hana_vm)

    @pytest.mark.dependency(depends=[SAP_HANA_VM_TEST_NAME])
    @pytest.mark.polarion("CNV-7765")
    def test_sap_hana_vm_block_multiqueue(self, sap_hana_vm, vmi_domxml, libvirt_disks):
        vm_block_multiqueue = sap_hana_vm.instance.spec.template.spec.domain.devices.blockMultiQueue
        assert vm_block_multiqueue, f"VM blockMultiQueue is not enabled, value: {vm_block_multiqueue}"
        assert_vm_devices_queues(vm=sap_hana_vm, vmi_xml_dict=vmi_domxml, libvirt_disks=libvirt_disks)

    @pytest.mark.dependency(depends=[SAP_HANA_VM_TEST_NAME])
    @pytest.mark.polarion("CNV-7874")
    def test_sap_hana_vm_huge_pages(
        self,
        sap_hana_vm,
        sap_hana_template,
        vmi_domxml,
        workers_utility_pods,
        sap_hana_node,
    ):
        verify_libvirt_huge_pages_configuration(template=sap_hana_template, vmi_xml_dict=vmi_domxml)
        assert_node_huge_pages_size(
            utility_pods=workers_utility_pods,
            sap_hana_node=sap_hana_node,
            vm=sap_hana_vm,
        )

    @pytest.mark.dependency(depends=[SAP_HANA_VM_TEST_NAME])
    @pytest.mark.polarion("CNV-7771")
    def test_sap_hana_vm_io_thread_policy(self, sap_hana_vm):
        LOGGER.info(f"Verify {sap_hana_vm.name} VM ioThreadsPolicy is enabled.")
        vm_io_thread_policy = sap_hana_vm.instance.spec.template.spec.domain.ioThreadsPolicy
        assert vm_io_thread_policy == "auto", f"VM ioThreadsPolicy is not enabled; current value: {vm_io_thread_policy}"

    @pytest.mark.dependency(depends=[SAP_HANA_VM_TEST_NAME])
    @pytest.mark.polarion("CNV-7768")
    def test_sap_hana_vm_memory(self, sap_hana_vm, sap_hana_template, vmi_domxml):
        template_memory_param_subset_str = "MEMORY"
        template_memory_params = get_parameters_from_template(
            template=sap_hana_template,
            parameter_subset=template_memory_param_subset_str,
        )
        assert_vm_spec_memory_configuration(expected_memory_configuration=template_memory_params, vm=sap_hana_vm)
        verify_libvirt_memory_configuration(
            expected_memory=template_memory_params[template_memory_param_subset_str],
            vmi_xml_dict=vmi_domxml,
        )

    @pytest.mark.dependency(depends=[SAP_HANA_VM_TEST_NAME])
    @pytest.mark.polarion("CNV-7770")
    def test_sap_hana_vm_downwards_metrics(self, sap_hana_vm, installed_vm_dump_metrics, vm_dump_metrics, vmi_domxml):
        metrics_dict = xmltodict.parse(xml_input=vm_dump_metrics[0], process_namespaces=True)["metrics"]["metric"]
        assert_vm_memory_dump_metrics(metrics_dict=metrics_dict, vmi_xml_dict=vmi_domxml)
        assert_vm_cpu_dump_metrics(metrics_dict=metrics_dict, vmi_xml_dict=vmi_domxml)

    @pytest.mark.dependency(depends=[SAP_HANA_VM_TEST_NAME])
    @pytest.mark.polarion("CNV-7764")
    def test_sap_hana_vm_numa_topology(
        self,
        sap_hana_vm,
        vm_virt_launcher_pod_instance,
        workers_utility_pods,
        vm_cpu_list,
        numa_node_dict,
    ):
        LOGGER.info(f"Verify {sap_hana_vm.name} NUMA configuration")
        assert_virt_launcher_pod_cpu_manager_node_selector(virt_launcher_pod=vm_virt_launcher_pod_instance)
        assert_numa_cpu_allocation(vm_cpus=vm_cpu_list, numa_nodes=numa_node_dict)

        assert_cpus_and_sriov_on_same_node(vm=sap_hana_vm, utility_pods=workers_utility_pods)

    @pytest.mark.dependency(depends=[SAP_HANA_VM_TEST_NAME])
    @pytest.mark.polarion("CNV-7766")
    def test_sap_hana_vm_disks(self, sap_hana_vm, vmi_domxml, libvirt_disks):
        LOGGER.info(f"Verify {sap_hana_vm.name} disks configuration")
        assert_vm_disks_virtio_bus(libvirt_disks=libvirt_disks)
        assert_vm_downwardapi_disk(libvirt_disks=libvirt_disks)

    @pytest.mark.dependency(depends=[SAP_HANA_VM_TEST_NAME])
    @pytest.mark.polarion("CNV-7767")
    def test_sap_hana_vm_interfaces(self, sap_hana_vm, vm_interfaces_names):
        failed_pingable_interfaces = []
        for interface in vm_interfaces_names:
            LOGGER.info(f"Verify {sap_hana_vm.name} network connectivity via interface {interface}.")
            if not is_destination_pingable_from_vm(
                src_vm=sap_hana_vm,
                dst_ip=PUBLIC_DNS_SERVER_IP,
                count=10,
                interface=interface,
            ):
                failed_pingable_interfaces.append(interface)

        assert not failed_pingable_interfaces, (
            f"{sap_hana_vm.name} failed to ping interfaces {failed_pingable_interfaces}."
        )

    @pytest.mark.dependency(depends=[SAP_HANA_VM_TEST_NAME])
    @pytest.mark.polarion("CNV-7869")
    def test_vm_dedicated_cpus_on_node(self, sap_hana_vm, crio_cpuset, vm_cpu_list):
        verify_vm_reserved_cpus_on_node(vm_cpu_list=vm_cpu_list, crio_cpuset=crio_cpuset)


class TestSAPHANAVirtualMachineMultipleNUMANodes:
    @pytest.mark.parametrize(
        "sap_hana_vm",
        [
            pytest.param(
                {
                    "set_cpus": True,
                },
                marks=pytest.mark.polarion("CNV-8050"),
            )
        ],
        indirect=True,
    )
    def test_hana_vm_cpus_on_multiple_numa_nodes(self, sap_hana_vm, vm_cpu_list):
        expected_num_cores = sap_hana_vm.instance.spec.template.spec.domain.cpu.cores
        assert len(vm_cpu_list) == expected_num_cores, (
            f"VM number of CPUs {vm_cpu_list} is not as expected {expected_num_cores}"
        )

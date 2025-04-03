import pytest
from ocp_resources.virtual_machine_cluster_preference import (
    VirtualMachineClusterPreference,
)

from tests.infrastructure.instance_types.utils import assert_mismatch_vendor_label
from utilities.constants import VIRT_OPERATOR, Images
from utilities.virt import VirtualMachineForTests, running_vm

pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno]


UNIQUE_PREFERENCE_LIST = [
    "alpine",
    "ubuntu",
    "cirros",
    "fedora",
    "fedora.arm64",
    "fedora.s390x",
    "opensuse.leap",
    "opensuse.tumbleweed",
    "sles",
]
CENTOS_PREFERENCE_LIST = [
    "centos.stream9",
    "centos.stream10",
    "centos.stream9.desktop",
    "centos.stream10.desktop",
]
RHEL_PREFERENCE_LIST = [
    "rhel.7",
    "rhel.8",
    "rhel.9",
    "rhel.10",
    "rhel.9.realtime",
    "rhel.9.arm64",
    "rhel.9.s390x",
    "rhel.10.arm64",
    "rhel.7.desktop",
    "rhel.8.desktop",
    "rhel.9.desktop",
]
WINDOWS_PREFERENCE_LIST = [
    "windows.10",
    "windows.11",
    "windows.2k16",
    "windows.2k19",
    "windows.2k22",
    "windows.2k25",
    "windows.10.virtio",
    "windows.11.virtio",
    "windows.2k16.virtio",
    "windows.2k19.virtio",
    "windows.2k22.virtio",
    "windows.2k25.virtio",
]
NETWORK_PREFERENCE_LIST = [
    "centos.stream9.dpdk",
    "rhel.8.dpdk",
    "rhel.9.dpdk",
]


def start_vm_with_cluster_preference(client, preference_name, namespace_name):
    cluster_preference = VirtualMachineClusterPreference(name=preference_name)
    cluster_spec = cluster_preference.instance.spec
    cpu_guest = cluster_spec.requirements.cpu.guest
    spread_options = getattr(cluster_spec.cpu, "spreadOptions", None)

    sockets = cpu_guest
    cores = None
    threads = None

    # Default ratio is 2 if not specified
    if spread_options:
        cores = spread_options.get("ratio", 2)
        sockets = max(1, cpu_guest // cores)
        threads = 1

    with VirtualMachineForTests(
        client=client,
        name=f"rhel-vm-with-{preference_name}",
        namespace=namespace_name,
        # TODO: Add corresponding images to the VM based on preference
        image=Images.Rhel.RHEL9_REGISTRY_GUEST_IMG,
        memory_guest=cluster_spec.requirements.memory.guest,
        cpu_sockets=sockets,
        cpu_cores=cores,
        cpu_threads=threads,
        vm_preference=cluster_preference,
    ) as vm:
        running_vm(vm=vm, wait_for_interfaces=False, check_ssh_connectivity=False)


def run_general_vm_preferences(client, namespace, preferences):
    for preference_name in preferences:
        # TODO remove arm64 skip when openshift-virtualization-tests support arm64
        if all(suffix not in preference_name for suffix in ["virtio", "arm64"]):
            start_vm_with_cluster_preference(
                client=client,
                preference_name=preference_name,
                namespace_name=namespace.name,
            )


@pytest.fixture()
def vm_cluster_preferences_expected_list():
    return (
        UNIQUE_PREFERENCE_LIST
        + CENTOS_PREFERENCE_LIST
        + RHEL_PREFERENCE_LIST
        + WINDOWS_PREFERENCE_LIST
        + NETWORK_PREFERENCE_LIST
    )


@pytest.mark.polarion("CNV-9981")
def test_base_preferences_common_annotation(base_vm_cluster_preferences, vm_cluster_preferences_expected_list):
    assert set([preference.name for preference in base_vm_cluster_preferences]) == set(
        vm_cluster_preferences_expected_list
    ), "Not all base CNV cluster preferences exist"


@pytest.mark.gating
@pytest.mark.polarion("CNV-10798")
def test_common_preferences_vendor_labels(base_vm_cluster_preferences):
    assert_mismatch_vendor_label(resources_list=base_vm_cluster_preferences)


# all VMs use same image, we are testing the preferences so the image is irrelevant
@pytest.mark.tier3
class TestCommonVmPreference:
    @pytest.mark.polarion("CNV-9894")
    def test_common_vm_preference_windows(self, unprivileged_client, namespace):
        run_general_vm_preferences(client=unprivileged_client, namespace=namespace, preferences=WINDOWS_PREFERENCE_LIST)

    @pytest.mark.parametrize(
        "cluster_preferences",
        [
            pytest.param(
                RHEL_PREFERENCE_LIST,
                marks=pytest.mark.polarion("CNV-9895"),
            ),
            pytest.param(
                CENTOS_PREFERENCE_LIST,
                marks=pytest.mark.polarion("CNV-9896"),
            ),
            pytest.param(
                UNIQUE_PREFERENCE_LIST,
                marks=pytest.mark.polarion("CNV-9897"),
            ),
        ],
    )
    def test_common_vm_preference_linux(self, cluster_preferences, unprivileged_client, namespace):
        run_general_vm_preferences(client=unprivileged_client, namespace=namespace, preferences=cluster_preferences)

    @pytest.mark.special_infra
    @pytest.mark.polarion("CNV-10806")
    def test_common_vm_preference_dpdk(self, unprivileged_client, namespace):
        run_general_vm_preferences(client=unprivileged_client, namespace=namespace, preferences=NETWORK_PREFERENCE_LIST)


@pytest.mark.post_upgrade
@pytest.mark.polarion("CNV-11289")
def test_common_preference_owner(base_vm_cluster_preferences):
    failed_preferences = []
    for vm_cluster_preference in base_vm_cluster_preferences:
        if (
            vm_cluster_preference.labels[f"{vm_cluster_preference.ApiGroup.APP_KUBERNETES_IO}/managed-by"]
            != VIRT_OPERATOR
        ):
            failed_preferences.append(vm_cluster_preference.name)
    assert not failed_preferences, f"The following preferences do no have {VIRT_OPERATOR} owner: {failed_preferences}"

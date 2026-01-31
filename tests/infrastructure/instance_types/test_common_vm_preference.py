import pytest
from ocp_resources.virtual_machine_cluster_preference import (
    VirtualMachineClusterPreference,
)

from tests.infrastructure.instance_types.utils import assert_mismatch_vendor_label
from tests.infrastructure.instance_types.vm_preference_list import VM_PREFERENCES_LIST
from utilities.constants import VIRT_OPERATOR, Images
from utilities.virt import VirtualMachineForTests, running_vm

pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno]


def _extract_resources_from_cluster_preference_spec(cluster_preference_spec):
    memory_guest = (
        cluster_preference_spec.get("requirements", {}).get("memory", {}).get("guest")
        or Images.Rhel.DEFAULT_MEMORY_SIZE
    )
    spread_options = cluster_preference_spec.get("cpu", {}).get("spreadOptions", {})

    sockets = None
    cores = None
    threads = None

    if cpu_guest := cluster_preference_spec.get("requirements", {}).get("cpu", {}).get("guest"):
        cores = spread_options.get("ratio", 2) if spread_options else 1
        sockets = max(1, cpu_guest // cores)
        threads = 1

    return memory_guest, sockets, cores, threads


def start_vm_with_cluster_preference(client, preference_name, namespace_name):
    cluster_preference = VirtualMachineClusterPreference(client=client, name=preference_name)

    memory_guest, sockets, cores, threads = _extract_resources_from_cluster_preference_spec(
        cluster_preference_spec=cluster_preference.instance.spec
    )

    with VirtualMachineForTests(
        client=client,
        name=f"rhel-vm-with-{preference_name}",
        namespace=namespace_name,
        # TODO: Add corresponding images to the VM based on preference
        image=Images.Rhel.RHEL9_REGISTRY_GUEST_IMG,
        memory_guest=memory_guest,
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
    return [os for os_list in VM_PREFERENCES_LIST.values() for os in os_list]


@pytest.mark.polarion("CNV-9981")
def test_base_preferences_common_annotation(base_vm_cluster_preferences, vm_cluster_preferences_expected_list):
    assert set([preference.name for preference in base_vm_cluster_preferences]) == set(
        vm_cluster_preferences_expected_list
    ), "Not all base CNV cluster preferences exist"


@pytest.mark.gating
@pytest.mark.conformance
@pytest.mark.polarion("CNV-10798")
@pytest.mark.s390x
def test_common_preferences_vendor_labels(base_vm_cluster_preferences):
    assert_mismatch_vendor_label(resources_list=base_vm_cluster_preferences)


# all VMs use same image, we are testing the preferences so the image is irrelevant
@pytest.mark.tier3
class TestCommonVmPreference:
    @pytest.mark.polarion("CNV-9894")
    def test_common_vm_preference_windows(self, unprivileged_client, namespace):
        run_general_vm_preferences(
            client=unprivileged_client,
            namespace=namespace,
            # drop legacy preferences with pcihole
            preferences=[pref for pref in VM_PREFERENCES_LIST["windows"] if pref not in {"windows.2k3", "windows.xp"}],
        )

    @pytest.mark.parametrize(
        "cluster_preferences",
        [
            pytest.param(
                "rhel",
                marks=pytest.mark.polarion("CNV-9895"),
            ),
            pytest.param(
                "centos",
                marks=pytest.mark.polarion("CNV-9896"),
            ),
            pytest.param(
                "unique",
                marks=pytest.mark.polarion("CNV-9897"),
            ),
        ],
    )
    @pytest.mark.s390x
    def test_common_vm_preference_linux(self, cluster_preferences, unprivileged_client, namespace):
        run_general_vm_preferences(
            client=unprivileged_client, namespace=namespace, preferences=VM_PREFERENCES_LIST[cluster_preferences]
        )

    @pytest.mark.special_infra
    @pytest.mark.polarion("CNV-10806")
    def test_common_vm_preference_dpdk(self, unprivileged_client, namespace):
        run_general_vm_preferences(
            client=unprivileged_client, namespace=namespace, preferences=VM_PREFERENCES_LIST["network"]
        )


@pytest.mark.post_upgrade
@pytest.mark.polarion("CNV-11289")
@pytest.mark.s390x
def test_common_preference_owner(base_vm_cluster_preferences):
    failed_preferences = []
    for vm_cluster_preference in base_vm_cluster_preferences:
        if (
            vm_cluster_preference.labels[f"{vm_cluster_preference.ApiGroup.APP_KUBERNETES_IO}/managed-by"]
            != VIRT_OPERATOR
        ):
            failed_preferences.append(vm_cluster_preference.name)
    assert not failed_preferences, f"The following preferences do no have {VIRT_OPERATOR} owner: {failed_preferences}"

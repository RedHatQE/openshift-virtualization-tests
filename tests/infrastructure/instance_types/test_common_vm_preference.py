import logging

import pytest
from ocp_resources.virtual_machine_cluster_preference import (
    VirtualMachineClusterPreference,
)
from pytest_testconfig import config as py_config

from tests.infrastructure.instance_types.utils import (
    assert_mismatch_vendor_label,
    extract_resources_from_cluster_preference_spec,
)
from tests.infrastructure.instance_types.vm_preference_list import VM_PREFERENCES_LIST
from utilities.constants import Images
from utilities.constants.architecture import SUPPORTED_CPU_ARCHITECTURES
from utilities.constants.components import VIRT_OPERATOR
from utilities.constants.virt import VIRTIO
from utilities.virt import VirtualMachineForTests, running_vm

LOGGER = logging.getLogger(__name__)

pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno]


def start_vm_with_cluster_preference(client, preference_name, namespace_name):
    cluster_preference = VirtualMachineClusterPreference(client=client, name=preference_name)

    memory_guest, sockets, cores, threads = extract_resources_from_cluster_preference_spec(
        cluster_preference_spec=cluster_preference.instance.spec
    )

    with VirtualMachineForTests(
        client=client,
        name=f"rhel-vm-with-{preference_name}",
        namespace=namespace_name,
        # TODO: Add corresponding images to the VM based on preference
        image=Images.Fedora.FEDORA_CONTAINER_IMAGE,
        memory_guest=memory_guest,
        cpu_sockets=sockets,
        cpu_cores=cores,
        cpu_threads=threads,
        vm_preference=cluster_preference,
    ) as vm:
        running_vm(vm=vm, wait_for_interfaces=False, check_ssh_connectivity=False)


def run_general_vm_preferences(client, namespace, preferences):
    """Create, start and delete a VM for each preference applicable to the cluster architecture.

    Preferences containing 'virtio' or targeting a different CPU architecture are skipped.

    Args:
        client: Kubernetes client for resource operations.
        namespace: Namespace object where VMs are created.
        preferences: List of VirtualMachineClusterPreference names to validate.
    """
    cluster_arch = py_config["cpu_arch"]

    runnable_preferences = []
    skipped_preferences = []
    for preference_name in preferences:
        if VIRTIO in preference_name or any(
            suffix in preference_name for suffix in SUPPORTED_CPU_ARCHITECTURES - {cluster_arch}
        ):
            skipped_preferences.append(preference_name)
        else:
            runnable_preferences.append(preference_name)

    if skipped_preferences:
        LOGGER.info(f"Skipping preferences not applicable to cluster arch {cluster_arch}: {skipped_preferences}")

    for preference_name in runnable_preferences:
        start_vm_with_cluster_preference(
            client=client,
            preference_name=preference_name,
            namespace_name=namespace.name,
        )


@pytest.fixture()
def vm_cluster_preferences_expected_list():
    return [os for os_list in VM_PREFERENCES_LIST.values() for os in os_list]


def test_base_preferences_common_annotation(base_vm_cluster_preferences, vm_cluster_preferences_expected_list):
    """
    Jira: https://redhat.atlassian.net/browse/CNV-10833 # <skip-jira-utils-check>
    Polarion: CNV-9981
    """
    assert {preference.name for preference in base_vm_cluster_preferences} == set(
        vm_cluster_preferences_expected_list
    ), "Not all base CNV cluster preferences exist"


@pytest.mark.gating
@pytest.mark.conformance
@pytest.mark.s390x
def test_common_preferences_vendor_labels(base_vm_cluster_preferences):
    """
    Jira: https://redhat.atlassian.net/browse/CNV-21976 # <skip-jira-utils-check>
    Polarion: CNV-10798
    """
    assert_mismatch_vendor_label(resources_list=base_vm_cluster_preferences)


# all VMs use same image, we are testing the preferences so the image is irrelevant
@pytest.mark.tier3
class TestCommonVmPreference:
    def test_common_vm_preference_windows(self, unprivileged_client, namespace):
        """
        Jira: https://redhat.atlassian.net/browse/CNV-10833 # <skip-jira-utils-check>
        Polarion: CNV-9894
        """
        run_general_vm_preferences(
            client=unprivileged_client,
            namespace=namespace,
            # drop legacy preferences with pcihole
            preferences=[pref for pref in VM_PREFERENCES_LIST["windows"] if pref not in {"windows.2k3", "windows.xp"}],
        )

    @pytest.mark.parametrize(
        "cluster_preferences",
        [
            "rhel",
            "centos",
            "unique",
        ],
    )
    @pytest.mark.s390x
    def test_common_vm_preference_linux(self, cluster_preferences, unprivileged_client, namespace):
        """
        Jira: https://redhat.atlassian.net/browse/CNV-10833 # <skip-jira-utils-check>
        Polarion: CNV-9895
        Polarion: CNV-9896
        Polarion: CNV-9897
        """
        run_general_vm_preferences(
            client=unprivileged_client, namespace=namespace, preferences=VM_PREFERENCES_LIST[cluster_preferences]
        )

    @pytest.mark.special_infra
    def test_common_vm_preference_dpdk(self, unprivileged_client, namespace):
        """
        Jira: https://redhat.atlassian.net/browse/CNV-30013 # <skip-jira-utils-check>
        Polarion: CNV-10806
        """
        run_general_vm_preferences(
            client=unprivileged_client, namespace=namespace, preferences=VM_PREFERENCES_LIST["network"]
        )


@pytest.mark.post_upgrade
@pytest.mark.s390x
def test_common_preference_owner(base_vm_cluster_preferences):
    """
    Jira: https://redhat.atlassian.net/browse/CNV-26638 # <skip-jira-utils-check>
    Polarion: CNV-11289
    """
    failed_preferences = []
    for vm_cluster_preference in base_vm_cluster_preferences:
        if (
            vm_cluster_preference.labels[f"{vm_cluster_preference.ApiGroup.APP_KUBERNETES_IO}/managed-by"]
            != VIRT_OPERATOR
        ):
            failed_preferences.append(vm_cluster_preference.name)
    assert not failed_preferences, f"The following preferences do no have {VIRT_OPERATOR} owner: {failed_preferences}"

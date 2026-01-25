"""
Test networkInterfaceMultiqueue feature with cpu core/socket/thread combinations.
"""

import pytest
from ocp_resources.resource import ResourceEditor

from tests.os_params import (
    RHEL_LATEST,
    RHEL_LATEST_LABELS,
    RHEL_LATEST_OS,
    WINDOWS_2019,
    WINDOWS_2019_OS,
    WINDOWS_2019_TEMPLATE_LABELS,
)
from utilities.constants import TIMEOUT_2MIN, VIRTIO
from utilities.virt import restart_vm_wait_for_running_vm, vm_instance_from_template

RHEL_TESTS_CLASS_NAME = "TestLatestRHEL"
WINDOWS_TESTS_CLASS_NAME = "TestLatestWindows"

pytestmark = pytest.mark.post_upgrade


def update_cpu_spec(vm, network_multiqueue=True, cores=1, sockets=1, threads=1):
    ResourceEditor({
        vm: {
            "spec": {
                "template": {
                    "spec": {
                        "domain": {
                            "cpu": {
                                "cores": cores,
                                "sockets": sockets,
                                "threads": threads,
                                "maxSockets": sockets,
                            },
                            "devices": {"networkInterfaceMultiqueue": network_multiqueue},
                        }
                    }
                }
            }
        }
    }).update()


def validate_vm_cpu_spec(vm, cores=1, sockets=1, threads=1):
    cpu_spec = vm.instance.spec.template.spec.domain.cpu
    cpu_topology_xml = vm.privileged_vmi.xml_dict["domain"]["cpu"]["topology"]
    assert int(cpu_topology_xml["@cores"]) == cpu_spec.cores == cores
    assert int(cpu_topology_xml["@sockets"]) == cpu_spec.sockets == sockets
    assert int(cpu_topology_xml["@threads"]) == cpu_spec.threads == threads


def update_validate_cpu_in_vm(vm, network_multiqueue=True, cores=1, sockets=1, threads=1):
    update_cpu_spec(
        vm=vm,
        network_multiqueue=network_multiqueue,
        cores=cores,
        sockets=sockets,
        threads=threads,
    )
    restart_vm_wait_for_running_vm(vm=vm)
    validate_vm_cpu_spec(vm=vm, cores=cores, sockets=sockets, threads=threads)


@pytest.fixture(scope="class")
def network_interface_multiqueue_vm(
    request,
    unprivileged_client,
    namespace,
    golden_image_data_volume_template_for_test_scope_class,
):
    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_volume_template=golden_image_data_volume_template_for_test_scope_class,
    ) as multiqueue_vm:
        yield multiqueue_vm


@pytest.mark.parametrize(
    "golden_image_data_source_for_test_scope_class, network_interface_multiqueue_vm",
    [
        (
            {"os_dict": RHEL_LATEST},
            {"vm_name": RHEL_LATEST_OS, "template_labels": RHEL_LATEST_LABELS},
        )
    ],
    indirect=True,
)
@pytest.mark.arm64
@pytest.mark.sno
class TestLatestRHEL:
    """
    Test networkInterfaceMultiqueue on latest RHEL with different cpu core/socket/thread combinations.
    """

    @pytest.mark.dependency(name=f"{RHEL_TESTS_CLASS_NAME}::rhel_default_cpu_values")
    @pytest.mark.polarion("CNV-8891")
    @pytest.mark.s390x
    def test_default_cpu_values(
        self,
        network_interface_multiqueue_vm,
    ):
        network_interface_multiqueue_vm.ssh_exec.executor().is_connective(tcp_timeout=TIMEOUT_2MIN)

    @pytest.mark.dependency(depends=[f"{RHEL_TESTS_CLASS_NAME}::rhel_default_cpu_values"])
    @pytest.mark.polarion("CNV-8892")
    @pytest.mark.s390x
    def test_feature_disabled(self, network_interface_multiqueue_vm):
        update_validate_cpu_in_vm(vm=network_interface_multiqueue_vm, network_multiqueue=False)

    @pytest.mark.dependency(depends=[f"{RHEL_TESTS_CLASS_NAME}::rhel_default_cpu_values"])
    @pytest.mark.polarion("CNV-8893")
    @pytest.mark.s390x
    def test_four_cores(self, network_interface_multiqueue_vm):
        update_validate_cpu_in_vm(vm=network_interface_multiqueue_vm, cores=4)

    @pytest.mark.dependency(depends=[f"{RHEL_TESTS_CLASS_NAME}::rhel_default_cpu_values"])
    @pytest.mark.polarion("CNV-8894")
    @pytest.mark.s390x
    def test_four_sockets(self, network_interface_multiqueue_vm):
        update_validate_cpu_in_vm(vm=network_interface_multiqueue_vm, sockets=4)

    @pytest.mark.dependency(depends=[f"{RHEL_TESTS_CLASS_NAME}::rhel_default_cpu_values"])
    @pytest.mark.polarion("CNV-8895")
    def test_four_threads(self, network_interface_multiqueue_vm):
        update_validate_cpu_in_vm(vm=network_interface_multiqueue_vm, threads=4)

    @pytest.mark.dependency(depends=[f"{RHEL_TESTS_CLASS_NAME}::rhel_default_cpu_values"])
    @pytest.mark.polarion("CNV-8896")
    def test_two_cores_two_sockets_two_threads(self, network_interface_multiqueue_vm):
        update_validate_cpu_in_vm(vm=network_interface_multiqueue_vm, cores=4, sockets=2, threads=2)


@pytest.mark.parametrize(
    "golden_image_data_source_for_test_scope_class, network_interface_multiqueue_vm",
    [
        (
            {"os_dict": WINDOWS_2019},
            {
                "vm_name": WINDOWS_2019_OS,
                "template_labels": WINDOWS_2019_TEMPLATE_LABELS,
                "network_model": VIRTIO,
                "network_multiqueue": True,
            },
        )
    ],
    indirect=True,
)
@pytest.mark.special_infra
@pytest.mark.high_resource_vm
class TestLatestWindows:
    """
    Test networkInterfaceMultiqueue on latest Windows with different cpu core/socket/thread combinations.
    """

    @pytest.mark.dependency(name=f"{WINDOWS_TESTS_CLASS_NAME}::windows_default_cpu_values")
    @pytest.mark.polarion("CNV-8897")
    def test_default_cpu_values(self, network_interface_multiqueue_vm):
        network_interface_multiqueue_vm.ssh_exec.executor().is_connective(tcp_timeout=TIMEOUT_2MIN)

    @pytest.mark.dependency(depends=[f"{WINDOWS_TESTS_CLASS_NAME}::windows_default_cpu_values"])
    @pytest.mark.polarion("CNV-8898")
    def test_four_cores_two_sockets_two_threads(self, network_interface_multiqueue_vm):
        update_validate_cpu_in_vm(vm=network_interface_multiqueue_vm, cores=4, sockets=2, threads=2)

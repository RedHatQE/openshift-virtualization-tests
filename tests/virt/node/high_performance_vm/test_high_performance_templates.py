import logging
import os

import pytest
from ocp_resources.resource import ResourceEditor
from ocp_resources.template import Template
from pytest_testconfig import py_config

from tests.os_params import (
    RHEL_LATEST,
    RHEL_LATEST_OS,
)
from utilities.constants import Images
from utilities.virt import running_vm, vm_instance_from_template

pytestmark = [pytest.mark.special_infra, pytest.mark.cpu_manager]


LOGGER = logging.getLogger(__name__)
CPUTUNE = "cputune"
RHEL_TESTS_CLASS_NAME = "TestHighPerformanceTemplatesRHEL"
WINDOWS_TESTS_CLASS_NAME = "TestHighPerformanceTemplatesWindows"


def key_is_in_cputune(vm, key):
    LOGGER.info(f"Verify {key} is in <{CPUTUNE}> section of virsh dumpxml")
    return key in vm.privileged_vmi.xml_dict["domain"][CPUTUNE]


def check_vcpupin_count(vm):
    cpu_dict = vm.instance.spec.template.spec.domain.cpu
    expected_vcpupin_count = cpu_dict["cores"] * cpu_dict["threads"]
    vcpupin_count = len(vm.privileged_vmi.xml_dict["domain"][CPUTUNE]["vcpupin"])

    LOGGER.info(f"Verify that <vcpupin> count is as expected: ({expected_vcpupin_count})")
    return vcpupin_count == expected_vcpupin_count


def vm_has_io_thread_policy(vm, policy):
    LOGGER.info(f"Verify ioThreadsPolicy is {policy}")

    domain = vm.instance.spec.template.spec.domain
    if not hasattr(domain, "ioThreadsPolicy"):
        return False
    return domain.ioThreadsPolicy == policy


@pytest.fixture(scope="class")
def high_performance_vm(request, golden_image_data_source_scope_class, unprivileged_client, namespace):
    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_source=golden_image_data_source_scope_class,
    ) as vm:
        yield vm


@pytest.fixture(scope="class")
def cputune_is_in_dumpxml(high_performance_vm):
    LOGGER.info(f"Verify that {CPUTUNE} is in virsh dumpxml")
    if CPUTUNE not in high_performance_vm.privileged_vmi.xml_dict["domain"]:
        pytest.fail(f"{CPUTUNE} key not found in virsh xml dump of {high_performance_vm.name}")


@pytest.fixture()
def increased_high_performance_vm_core_count_by_one(high_performance_vm):
    high_performance_vm.stop(wait=True)

    new_core_count = high_performance_vm.instance.spec.template.spec.domain.cpu.cores + 1

    with ResourceEditor(
        patches={high_performance_vm: {"spec": {"template": {"spec": {"domain": {"cpu": {"cores": new_core_count}}}}}}}
    ):
        running_vm(
            vm=high_performance_vm,
        )
        yield


@pytest.mark.gating()
@pytest.mark.parametrize(
    "golden_image_data_volume_scope_class, high_performance_vm",
    [
        [
            {
                "dv_name": "rhel8-hp-vm-dv",
                "image": RHEL_LATEST["image_path"],
                "dv_size": RHEL_LATEST["dv_size"],
                "storage_class": py_config["default_storage_class"],
            },
            {
                "vm_name": "high-performance-rhel-vm",
                "template_labels": {
                    "os": RHEL_LATEST_OS,
                    "workload": Template.Workload.HIGHPERFORMANCE,
                    "flavor": Template.Flavor.SMALL,
                },
            },
        ],
    ],
    indirect=True,
)
@pytest.mark.usefixtures("high_performance_vm", "cputune_is_in_dumpxml")
class TestHighPerformanceTemplatesRHEL:
    @pytest.mark.dependency(name=f"{RHEL_TESTS_CLASS_NAME}::rhel_cpu_request")
    @pytest.mark.polarion("CNV-6756")
    def test_rhel_cpu_request(self, high_performance_vm):
        assert key_is_in_cputune(high_performance_vm, "vcpupin")

    @pytest.mark.dependency(name=f"{RHEL_TESTS_CLASS_NAME}::rhel_emulator_thread")
    @pytest.mark.polarion("CNV-6757")
    def test_rhel_emulator_thread(self, high_performance_vm):
        assert key_is_in_cputune(high_performance_vm, "emulatorpin")

    @pytest.mark.dependency(name=f"{RHEL_TESTS_CLASS_NAME}::rhel_iothread_policy")
    @pytest.mark.polarion("CNV-6822")
    def test_rhel_iothread_policy(self, high_performance_vm):
        assert vm_has_io_thread_policy(high_performance_vm, "shared")

    @pytest.mark.dependency(name=f"{RHEL_TESTS_CLASS_NAME}::rhel_iothread_pin")
    @pytest.mark.polarion("CNV-6810")
    def test_rhel_iothread_pin(self, high_performance_vm):
        assert key_is_in_cputune(high_performance_vm, "iothreadpin")

    @pytest.mark.dependency(
        depends=[
            f"{RHEL_TESTS_CLASS_NAME}::rhel_cpu_request",
            f"{RHEL_TESTS_CLASS_NAME}::rhel_emulator_thread",
            f"{RHEL_TESTS_CLASS_NAME}::rhel_iothread_policy",
            f"{RHEL_TESTS_CLASS_NAME}::rhel_iothread_pin",
        ]
    )
    @pytest.mark.polarion("CNV-6758")
    def test_rhel_change_cpu_core_count(self, high_performance_vm, increased_high_performance_vm_core_count_by_one):
        assert check_vcpupin_count(high_performance_vm)


@pytest.mark.parametrize(
    "golden_image_data_volume_scope_class, high_performance_vm",
    [
        [
            {
                "dv_name": "win-hp-vm-dv",
                "image": os.path.join(Images.Windows.HA_DIR, Images.Windows.WIN2k19_HA_IMG),
                "dv_size": Images.Windows.DEFAULT_DV_SIZE,
                "storage_class": py_config["default_storage_class"],
            },
            {
                "vm_name": "high-performance-win-vm",
                "template_labels": {
                    "os": "win2k19",
                    "workload": Template.Workload.HIGHPERFORMANCE,
                    "flavor": Template.Flavor.MEDIUM,
                },
            },
        ],
    ],
    indirect=True,
)
@pytest.mark.high_resource_vm
@pytest.mark.usefixtures("high_performance_vm", "cputune_is_in_dumpxml")
class TestHighPerformanceTemplatesWindows:
    @pytest.mark.dependency(name=f"{WINDOWS_TESTS_CLASS_NAME}::win_cpu_request")
    @pytest.mark.polarion("CNV-6771")
    def test_win_cpu_request(self, high_performance_vm):
        assert key_is_in_cputune(high_performance_vm, "vcpupin")

    @pytest.mark.dependency(name=f"{WINDOWS_TESTS_CLASS_NAME}::win_emulator_thread")
    @pytest.mark.polarion("CNV-6772")
    def test_win_emulator_thread(self, high_performance_vm):
        assert key_is_in_cputune(high_performance_vm, "emulatorpin")

    @pytest.mark.dependency(
        depends=[
            f"{WINDOWS_TESTS_CLASS_NAME}::win_cpu_request",
            f"{WINDOWS_TESTS_CLASS_NAME}::win_emulator_thread",
        ]
    )
    @pytest.mark.polarion("CNV-6773")
    def test_win_change_cpu_core_count(self, high_performance_vm, increased_high_performance_vm_core_count_by_one):
        assert check_vcpupin_count(high_performance_vm)

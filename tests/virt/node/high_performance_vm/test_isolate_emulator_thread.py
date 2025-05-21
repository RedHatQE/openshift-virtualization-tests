"""
Test isolateEmulatorThread feature.
"""

import logging

import pytest
from ocp_resources.template import Template
from pytest_testconfig import config as py_config

from tests.os_params import RHEL_LATEST, RHEL_LATEST_OS
from tests.utils import (
    validate_dedicated_emulatorthread,
)
from utilities.virt import migrate_vm_and_verify, vm_instance_from_template

LOGGER = logging.getLogger(__name__)


pytestmark = [pytest.mark.special_infra, pytest.mark.cpu_manager]


VM_DICT = {
    "vm_name": RHEL_LATEST_OS,
    "cpu_placement": True,
    "isolate_emulator_thread": True,
}

TEMPLATE_LABELS = {
    "os": RHEL_LATEST_OS,
    "workload": Template.Workload.SERVER,
}

ISOLATE_EMULATOR_THREAD = "TestIsolateEmulatorThread::isolate_emulator_thread"


@pytest.fixture(scope="class")
def isolated_emulatorthread_vm(
    request, unprivileged_client, namespace, golden_image_data_source_scope_class, cpu_for_migration
):
    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_source=golden_image_data_source_scope_class,
        vm_cpu_model=cpu_for_migration,
    ) as isolated_emulatorthread_vm:
        yield isolated_emulatorthread_vm


@pytest.mark.parametrize(
    ("golden_image_data_volume_scope_class", "isolated_emulatorthread_vm"),
    [
        pytest.param(
            {
                "dv_name": RHEL_LATEST_OS,
                "image": RHEL_LATEST["image_path"],
                "storage_class": py_config["default_storage_class"],
                "dv_size": RHEL_LATEST["dv_size"],
            },
            {
                **VM_DICT,
                "template_labels": {
                    **TEMPLATE_LABELS,
                    "flavor": Template.Flavor.MEDIUM,
                },
            },
        ),
    ],
    indirect=True,
)
class TestIsolateEmulatorThread:
    """
    Test Isolated Emulator Thread is used for QEMU Emulator.
    """

    @pytest.mark.dependency(name=ISOLATE_EMULATOR_THREAD)
    @pytest.mark.polarion("CNV-6744")
    def test_isolate_emulator_thread(
        self,
        isolated_emulatorthread_vm,
    ):
        """
        Test if a dedicated cpu is allocated for QEMU Emulator,
        when isolateEmulatorThread is True.
        """
        # With the Template Flavors being used,
        # As per Flavor ( threads(1) * cores(2) * socket(1))
        # Dedicated cpu will be consumed for CPU Operations.
        # One additional Dedicated cpu is allocated for QEMU Emulator.
        # nproc should still show the CPU count as 2 ( threads(1) * cores(2) * socket(1))
        # even though the VM is allocated overall 3 dedicated cpus.
        validate_dedicated_emulatorthread(vm=isolated_emulatorthread_vm)

    @pytest.mark.rwx_default_storage
    @pytest.mark.dependency(depends=[ISOLATE_EMULATOR_THREAD])
    @pytest.mark.polarion("CNV-10554")
    def test_vm_with_isolate_emulator_thread_live_migrates(self, isolated_emulatorthread_vm):
        migrate_vm_and_verify(vm=isolated_emulatorthread_vm)

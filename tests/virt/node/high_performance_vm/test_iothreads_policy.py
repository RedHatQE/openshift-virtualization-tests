"""
Test ioThreadsPolicy feature.
"""

import logging

import pytest
from ocp_resources.template import Template
from pytest_testconfig import config as py_config

from tests.os_params import RHEL_LATEST, RHEL_LATEST_OS
from tests.utils import (
    validate_iothreads_emulatorthread_on_same_pcpu,
)
from utilities.virt import vm_instance_from_template

LOGGER = logging.getLogger(__name__)


pytestmark = [pytest.mark.special_infra, pytest.mark.cpu_manager]


@pytest.fixture()
def iothreads_policy_vm(
    request,
    unprivileged_client,
    namespace,
    golden_image_data_source_scope_class,
):
    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_source=golden_image_data_source_scope_class,
    ) as iothreads_policy_vm:
        yield iothreads_policy_vm


@pytest.mark.gating
@pytest.mark.parametrize(
    "golden_image_data_volume_scope_class,",
    [
        pytest.param(
            {
                "dv_name": RHEL_LATEST_OS,
                "image": RHEL_LATEST["image_path"],
                "storage_class": py_config["default_storage_class"],
                "dv_size": RHEL_LATEST["dv_size"],
            },
        ),
    ],
    indirect=True,
)
class TestIsolateEmulatorThreadAndIOThreadsPolicy:
    """
    Test ioThreadsPolicy, dedicatedIOThread along with
    isolateEmulatorThread.
    """

    @pytest.mark.parametrize(
        "iothreads_policy_vm,",
        [
            pytest.param(
                {
                    "vm_name": RHEL_LATEST_OS,
                    "template_labels": {
                        "os": RHEL_LATEST_OS,
                        "workload": Template.Workload.SERVER,
                        "flavor": Template.Flavor.LARGE,
                    },
                    "cpu_placement": True,
                    "isolate_emulator_thread": True,
                    "iothreads_policy": "auto",
                    "dedicated_iothread": True,
                },
                marks=pytest.mark.polarion("CNV-6755"),
                id="test_latest_rhel_template_flavor_large",
            ),
        ],
        indirect=True,
    )
    def test_iothreads_policy(
        self,
        iothreads_policy_vm,
    ):
        """
        Test when ioThreadsPolicy is "auto"
        Ensure that KubeVirt will allocate ioThreads to the same physical cpu
        of the QEMU Emulator Thread.
        """
        validate_iothreads_emulatorthread_on_same_pcpu(vm=iothreads_policy_vm)

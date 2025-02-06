# Run strategies logic can be found under
# https://kubevirt.io/user-guide/#/creation/run-strategies?id=run-strategies

import logging
import re

import pytest
from kubernetes.client.rest import ApiException
from ocp_resources.pod import Pod
from ocp_resources.resource import ResourceEditor
from ocp_resources.virtual_machine import VirtualMachine
from ocp_resources.virtual_machine_instance import VirtualMachineInstance
from pytest_testconfig import py_config
from rrmngmnt import power_manager
from timeout_sampler import TimeoutSampler

from tests.os_params import RHEL_LATEST, RHEL_LATEST_OS
from utilities.constants import TIMEOUT_10MIN
from utilities.virt import migrate_vm_and_verify, running_vm

pytestmark = pytest.mark.post_upgrade


LOGGER = logging.getLogger(__name__)

MANUAL = VirtualMachine.RunStrategy.MANUAL
ALWAYS = VirtualMachine.RunStrategy.ALWAYS
HALTED = VirtualMachine.RunStrategy.HALTED
RERUNONFAILURE = VirtualMachine.RunStrategy.RERUNONFAILURE

RUN_STRATEGY_DICT = {
    MANUAL: {
        "start": {"status": True, "run_strategy": MANUAL},
        "restart": {"status": True, "run_strategy": MANUAL},
        "stop": {"status": None, "run_strategy": MANUAL},
    },
    ALWAYS: {
        "start": {
            "status": True,
            "run_strategy": ALWAYS,
            "expected_exceptions": [
                ".*Always does not support manual start requests.*",
                ".*VM is already running.*",
            ],
        },
        "restart": {"status": True, "run_strategy": ALWAYS},
        "stop": {"status": None, "run_strategy": HALTED},
    },
    HALTED: {
        "start": {"status": True, "run_strategy": ALWAYS},
        "restart": {"status": True, "run_strategy": ALWAYS},
        "stop": {"status": None, "run_strategy": HALTED},
    },
    RERUNONFAILURE: {
        "start": {
            "status": True,
            "run_strategy": RERUNONFAILURE,
            "expected_exceptions": [
                ".*RerunOnFailure does not support starting VM from failed state.*",
                ".*VM is already running.*",
            ],
        },
        "restart": {
            "status": True,
            "run_strategy": RERUNONFAILURE,
        },
        "stop": {
            "status": None,
            "run_strategy": RERUNONFAILURE,
            "expected_exception": "VM is not running",
        },
    },
}

# expected statuses for vmi and virt-launcher pod after shutdown from inside vm
RUN_STRATEGY_SHUTDOWN_STATUS = {
    MANUAL: {
        "vmi": VirtualMachineInstance.Status.SUCCEEDED,
        "launcher_pod": Pod.Status.SUCCEEDED,
    },
    RERUNONFAILURE: {
        "vmi": None,
        "launcher_pod": None,
    },
    ALWAYS: {
        "vmi": VirtualMachineInstance.Status.RUNNING,
        "launcher_pod": Pod.Status.RUNNING,
    },
}


@pytest.fixture()
def skip_run_strategy_halted(run_strategy_matrix__class__):
    if run_strategy_matrix__class__ == HALTED:
        pytest.skip("Skip test for VM with Halted runStrategy")


def updated_vm_run_strategy(run_strategy, vm_for_test):
    if vm_for_test.instance.spec.runStrategy != run_strategy:
        LOGGER.info(f"Update VM with runStrategy {run_strategy}")

        if vm_for_test.vmi.exists and vm_for_test.vmi.status == VirtualMachineInstance.Status.RUNNING:
            vm_for_test.stop(wait=True)

        ResourceEditor(patches={vm_for_test: {"spec": {"runStrategy": run_strategy}}}).update()
    return run_strategy


@pytest.fixture(scope="class")
def matrix_updated_vm_run_strategy(run_strategy_matrix__class__, lifecycle_vm):
    # Update the VM run strategy from run_strategy_matrix__class__
    return updated_vm_run_strategy(run_strategy=run_strategy_matrix__class__, vm_for_test=lifecycle_vm)


@pytest.fixture()
def request_updated_vm_run_strategy(request, lifecycle_vm):
    # Update the VM run strategy from request.param
    return updated_vm_run_strategy(run_strategy=request.param["run_strategy"], vm_for_test=lifecycle_vm)


@pytest.fixture()
def start_vm_if_not_running(lifecycle_vm):
    running_vm(vm=lifecycle_vm)


def run_vm_action(vm, vm_action, expected_exceptions=None):
    LOGGER.info(f"{vm_action} VM")

    def _vm_run_action():
        if expected_exceptions:
            # when runStrategy changes cause a VM to start and then we immediately
            # send the start instruction from here there is a race condition which may
            # cause expected exceptions not to be raised.
            try:
                getattr(vm, vm_action)(wait=True, timeout=TIMEOUT_10MIN)
            except ApiException as e:
                if re.search(pattern=rf"{'|'.join(expected_exceptions)}", string=str(e)):
                    return True
                raise e
        else:
            getattr(vm, vm_action)(wait=True, timeout=TIMEOUT_10MIN)
            return True

    for sample in TimeoutSampler(
        wait_timeout=TIMEOUT_10MIN,
        sleep=2,
        func=_vm_run_action,
    ):
        if sample:
            break


def verify_vm_ready_status(vm, ready_status=True):
    LOGGER.info(f"Verify VM ready status: {ready_status}")
    vm.wait_for_ready_status(status=ready_status, timeout=TIMEOUT_10MIN)
    if ready_status:
        running_vm(vm=vm)


def verify_vm_run_strategy(vm, run_strategy):
    LOGGER.info(f"Verify VM runStrategy: {run_strategy}")
    assert vm.instance.spec.runStrategy == run_strategy


def verify_vm_action(vm, vm_action, run_strategy):
    run_strategy_policy = RUN_STRATEGY_DICT[run_strategy][vm_action]
    run_vm_action(
        vm=vm,
        vm_action=vm_action,
        expected_exceptions=run_strategy_policy.get("expected_exceptions"),
    )
    verify_vm_ready_status(vm=vm, ready_status=run_strategy_policy["status"])
    verify_vm_run_strategy(vm=vm, run_strategy=run_strategy_policy["run_strategy"])


def pause_unpause_vmi_and_verify_status(vm):
    vm.privileged_vmi.pause(wait=True)
    assert vm.printable_status == vm.Status.PAUSED, f"VM is not paused, status: {vm.printable_status}"
    vm.privileged_vmi.unpause(wait=True)
    verify_vm_ready_status(vm=vm)


def migrate_validate_run_strategy_vm(vm, run_strategy):
    LOGGER.info(f"The VM migration with runStrategy {run_strategy}")
    verify_vm_ready_status(vm=vm)
    migrate_vm_and_verify(vm=vm)
    verify_vm_ready_status(vm=vm)
    verify_vm_run_strategy(vm=vm, run_strategy=run_strategy)


def shutdown_vm_guest_os(vm):
    LOGGER.info(f"Powering off {vm.name}")
    host = vm.ssh_exec
    host.sudo = True
    host.add_power_manager(pm_type=power_manager.SSH_TYPE)
    host.power_manager.poweroff()


@pytest.mark.parametrize(
    "golden_image_data_volume_scope_module",
    [
        {
            "dv_name": RHEL_LATEST_OS,
            "image": RHEL_LATEST["image_path"],
            "dv_size": RHEL_LATEST["dv_size"],
            "storage_class": py_config["default_storage_class"],
        },
    ],
    indirect=True,
)
@pytest.mark.gating
class TestRunStrategyBaseActions:
    @pytest.mark.parametrize(
        "vm_action",
        [
            pytest.param("start", marks=pytest.mark.polarion("CNV-4685")),
            pytest.param("restart", marks=pytest.mark.polarion("CNV-4686")),
            pytest.param("stop", marks=pytest.mark.polarion("CNV-4687")),
        ],
    )
    def test_run_strategy_policy(
        self,
        lifecycle_vm,
        matrix_updated_vm_run_strategy,
        vm_action,
    ):
        LOGGER.info(f"Verify VM with run strategy {matrix_updated_vm_run_strategy} and VM action {vm_action}")
        verify_vm_action(
            vm=lifecycle_vm,
            vm_action=vm_action,
            run_strategy=matrix_updated_vm_run_strategy,
        )


@pytest.mark.parametrize(
    "golden_image_data_volume_scope_module",
    [
        {
            "dv_name": RHEL_LATEST_OS,
            "image": RHEL_LATEST["image_path"],
            "dv_size": RHEL_LATEST["dv_size"],
            "storage_class": py_config["default_storage_class"],
        },
    ],
    indirect=True,
)
class TestRunStrategyAdvancedActions:
    @pytest.mark.polarion("CNV-5054")
    def test_run_strategy_shutdown(
        self,
        lifecycle_vm,
        skip_run_strategy_halted,
        matrix_updated_vm_run_strategy,
        start_vm_if_not_running,
    ):
        vmi = lifecycle_vm.vmi
        launcher_pod = vmi.virt_launcher_pod
        run_strategy = matrix_updated_vm_run_strategy
        status_dict = RUN_STRATEGY_SHUTDOWN_STATUS[run_strategy]

        shutdown_vm_guest_os(vm=lifecycle_vm)

        # runStrategy "Always" and "RerunOnFailure" first terminates the pod, then re-raises it
        if run_strategy in (ALWAYS, RERUNONFAILURE):
            launcher_pod.wait_deleted()

        if run_strategy == RERUNONFAILURE:
            # RerunOnFailure deletes VMI
            vmi.wait_deleted()
        else:
            # wait for vmi and launcher pod status by matrix
            vmi.wait_for_status(status=status_dict["vmi"])
            vmi.virt_launcher_pod.wait_for_status(status=status_dict["launcher_pod"])

    @pytest.mark.parametrize(
        "request_updated_vm_run_strategy",
        [
            pytest.param(
                {"run_strategy": MANUAL},
                marks=pytest.mark.polarion("CNV-4688"),
                id="Manual",
            ),
            pytest.param(
                {"run_strategy": ALWAYS},
                marks=pytest.mark.polarion("CNV-4689"),
                id="Always",
            ),
        ],
        indirect=True,
    )
    def test_run_strategy_pause_unpause_vmi(
        self, lifecycle_vm, request_updated_vm_run_strategy, start_vm_if_not_running
    ):
        LOGGER.info(f"Verify VMI pause/un-pause with runStrategy: {request_updated_vm_run_strategy}")
        pause_unpause_vmi_and_verify_status(vm=lifecycle_vm)

    @pytest.mark.parametrize(
        "request_updated_vm_run_strategy",
        [
            pytest.param(
                {"run_strategy": MANUAL},
                marks=pytest.mark.polarion("CNV-5893"),
                id="Manual",
            ),
            pytest.param(
                {"run_strategy": ALWAYS},
                marks=pytest.mark.polarion("CNV-4690"),
                id="Always",
            ),
        ],
        indirect=True,
    )
    def test_run_strategy_migrate_vm(
        self,
        skip_if_no_common_cpu,
        skip_access_mode_rwo_scope_function,
        lifecycle_vm,
        request_updated_vm_run_strategy,
        start_vm_if_not_running,
    ):
        migrate_validate_run_strategy_vm(vm=lifecycle_vm, run_strategy=request_updated_vm_run_strategy)

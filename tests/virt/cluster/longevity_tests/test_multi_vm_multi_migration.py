import pytest
from pytest_testconfig import config as py_config

from tests.virt.cluster.longevity_tests.constants import (
    LINUX_DV_PARAMS,
    LINUX_OS_PREFIX,
    LINUX_VM_PARAMS,
    WINDOWS_DV_PARAMS,
    WINDOWS_OS_PREFIX,
    WINDOWS_VM_PARAMS,
    WSL2_DV_PARAMS,
    WSL2_VM_PARAMS,
)
from tests.virt.cluster.longevity_tests.utils import run_migration_loop

pytestmark = [
    pytest.mark.usefixtures("skip_if_workers_vms", "skip_when_one_node", "skip_if_no_common_modern_cpu"),
    pytest.mark.longevity,
]


@pytest.mark.parametrize(
    "multi_dv, multi_vms",
    [
        pytest.param(
            {"dv_params": LINUX_DV_PARAMS},
            {"vm_params": LINUX_VM_PARAMS},
            marks=pytest.mark.polarion("CNV-8310"),
        )
    ],
    indirect=True,
)
def test_migration_storm_linux_vms(linux_vms_with_pids):
    run_migration_loop(
        iterations=int(py_config["linux_iterations"]),
        vms_with_pids=linux_vms_with_pids,
        os_type=LINUX_OS_PREFIX,
    )


@pytest.mark.parametrize(
    "multi_dv, multi_vms",
    [
        pytest.param(
            {"dv_params": WINDOWS_DV_PARAMS},
            {"vm_params": WINDOWS_VM_PARAMS},
            marks=pytest.mark.polarion("CNV-8311"),
        )
    ],
    indirect=True,
)
def test_migration_storm_windows_vms(windows_vms_with_pids):
    run_migration_loop(
        iterations=int(py_config["windows_iterations"]),
        vms_with_pids=windows_vms_with_pids,
        os_type=WINDOWS_OS_PREFIX,
    )


@pytest.mark.parametrize(
    "multi_dv, multi_vms",
    [
        pytest.param(
            {"dv_params": WSL2_DV_PARAMS},
            {"vm_params": WSL2_VM_PARAMS},
            marks=pytest.mark.polarion("CNV-9692"),
        )
    ],
    indirect=True,
)
def test_migration_storm_wsl2_vms(wsl2_vms_with_pids):
    run_migration_loop(
        iterations=int(py_config["windows_iterations"]),
        vms_with_pids=wsl2_vms_with_pids,
        os_type=WINDOWS_OS_PREFIX,
        wsl2_guest=True,
    )

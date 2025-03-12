import pytest

from tests.virt.cluster.longevity_tests.constants import WSL2_DV_PARAMS, WSL2_VM_PARAMS
from tests.virt.cluster.longevity_tests.utils import run_windows_upgrade_storm

pytestmark = [pytest.mark.usefixtures("skip_test_if_no_ocs_sc"), pytest.mark.longevity, pytest.mark.special_infra]


@pytest.mark.parametrize(
    "multi_dv, multi_vms",
    [
        pytest.param(
            {"dv_params": [WSL2_DV_PARAMS[0]]},
            {"vm_params": [WSL2_VM_PARAMS[0]]},
            marks=pytest.mark.polarion("CNV-10152"),
        )
    ],
    indirect=True,
)
def test_win_upgrade_storm_wsl2_vms(wsl2_vms_with_pids):
    run_windows_upgrade_storm(vms_with_pids=wsl2_vms_with_pids)

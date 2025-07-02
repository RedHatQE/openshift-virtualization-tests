import pytest

from tests.install_upgrade_operators.constants import WORKLOAD_UPDATE_STRATEGY_KEY_NAME, WORKLOADUPDATEMETHODS
from tests.install_upgrade_operators.launcher_updates.constants import (
    DEFAULT_WORKLOAD_UPDATE_STRATEGY,
    MOD_CUST_DEFAULT_BATCH_EVICTION_INTERVAL,
    MOD_CUST_DEFAULT_BATCH_EVICTION_SIZE,
    MOD_CUST_DEFAULT_WORKLOAD_UPDATE_METHOD,
)
from tests.install_upgrade_operators.utils import wait_for_spec_change
from utilities.hco import get_hco_spec
from utilities.virt import get_hyperconverged_kubevirt

pytestmark = [pytest.mark.sno, pytest.mark.arm64]


class TestLauncherUpdateResetFields:
    @pytest.mark.parametrize(
        "updated_hco_cr, expected",
        [
            pytest.param(
                {
                    "patch": {"spec": {WORKLOAD_UPDATE_STRATEGY_KEY_NAME: None}},
                },
                DEFAULT_WORKLOAD_UPDATE_STRATEGY,
                marks=(pytest.mark.polarion("CNV-6928"),),
            ),
            pytest.param(
                {
                    "patch": {"spec": {WORKLOAD_UPDATE_STRATEGY_KEY_NAME: {"batchEvictionInterval": None}}},
                },
                MOD_CUST_DEFAULT_BATCH_EVICTION_INTERVAL,
                marks=pytest.mark.polarion("CNV-6929"),
                id="test_hyperconverged_reset_workload_update_strategy_batch_eviction_size",
            ),
            pytest.param(
                {
                    "patch": {"spec": {WORKLOAD_UPDATE_STRATEGY_KEY_NAME: {"batchEvictionSize": None}}},
                },
                MOD_CUST_DEFAULT_BATCH_EVICTION_SIZE,
                marks=pytest.mark.polarion("CNV-6930"),
                id="test_hyperconverged_reset_workload_update_strategy_workload_update_methods",
            ),
            pytest.param(
                {
                    "patch": {"spec": {WORKLOAD_UPDATE_STRATEGY_KEY_NAME: {WORKLOADUPDATEMETHODS: None}}},
                },
                MOD_CUST_DEFAULT_WORKLOAD_UPDATE_METHOD,
                marks=pytest.mark.polarion("CNV-6931"),
            ),
        ],
        indirect=["updated_hco_cr"],
    )
    @pytest.mark.s390x
    def test_hyperconverged_reset_custom_workload_update_strategy(
        self,
        updated_workload_strategy_custom_values,
        admin_client,
        hco_namespace,
        updated_hco_cr,
        expected,
    ):
        """Validate ability to reset, hyperconverged's spec.workloadUpdateStrategy from custom values"""
        wait_for_spec_change(
            expected=expected,
            get_spec_func=lambda: get_hco_spec(admin_client=admin_client, hco_namespace=hco_namespace),
            base_path=[WORKLOAD_UPDATE_STRATEGY_KEY_NAME],
        )
        wait_for_spec_change(
            expected=expected,
            get_spec_func=lambda: get_hyperconverged_kubevirt(admin_client=admin_client, hco_namespace=hco_namespace)
            .instance.to_dict()
            .get("spec"),
            base_path=[WORKLOAD_UPDATE_STRATEGY_KEY_NAME],
        )

import pytest

from tests.install_upgrade_operators.constants import WORKLOAD_UPDATE_STRATEGY_KEY_NAME, WORKLOADUPDATEMETHODS
from tests.install_upgrade_operators.launcher_updates.constants import (
    CUSTOM_BATCH_EVICTION_INTERVAL,
    CUSTOM_BATCH_EVICTION_INTERVAL_INT,
    CUSTOM_BATCH_EVICTION_SIZE,
    CUSTOM_BATCH_EVICTION_SIZE_INT,
    CUSTOM_WORKLOAD_UPDATE_METHODS,
    CUSTOM_WORKLOAD_UPDATE_STRATEGY,
    MOD_DEFAULT_BATCH_EVICTION_INTERVAL,
    MOD_DEFAULT_BATCH_EVICTION_INTERVAL_INT,
    MOD_DEFAULT_BATCH_EVICTION_INTERVAL_ZERO,
    MOD_DEFAULT_BATCH_EVICTION_SIZE,
    MOD_DEFAULT_BATCH_EVICTION_SIZE_INT,
    MOD_DEFAULT_BATCH_EVICTION_SIZE_ZERO,
    MOD_DEFAULT_WORKLOAD_UPDATE_METHOD,
    MOD_DEFAULT_WORKLOAD_UPDATE_METHOD_EMPTY,
)
from tests.install_upgrade_operators.utils import wait_for_spec_change
from utilities.hco import get_hco_spec
from utilities.virt import get_hyperconverged_kubevirt

pytestmark = [pytest.mark.sno, pytest.mark.arm64]


class TestLauncherUpdateAll:
    @pytest.mark.parametrize(
        "resource_name, expected",
        [
            pytest.param(
                "hyperconverged",
                CUSTOM_WORKLOAD_UPDATE_STRATEGY,
                marks=pytest.mark.polarion("CNV-6926"),
                id="test_hyperconverged_modify_custom_workload_update_strategy_all",
            ),
            pytest.param(
                "kubevirt",
                CUSTOM_WORKLOAD_UPDATE_STRATEGY,
                marks=pytest.mark.polarion("CNV-6927"),
                id="test_kubevirt_modify_custom_workload_update_strategy",
            ),
        ],
    )
    @pytest.mark.s390x
    def test_modify_custom_workload_update_strategy_all(
        self,
        admin_client,
        hco_namespace,
        updated_workload_strategy_custom_values,
        resource_name,
        expected,
    ):
        """Validate ability to update, hyperconverged's spec.workloadUpdateStrategy to custom values"""
        if resource_name == "hyperconverged":
            wait_for_spec_change(
                expected=expected,
                get_spec_func=lambda: get_hco_spec(admin_client=admin_client, hco_namespace=hco_namespace),
                base_path=[WORKLOAD_UPDATE_STRATEGY_KEY_NAME],
            )
        elif resource_name == "kubevirt":
            wait_for_spec_change(
                expected=expected,
                get_spec_func=lambda: get_hyperconverged_kubevirt(
                    admin_client=admin_client, hco_namespace=hco_namespace
                )
                .instance.to_dict()
                .get("spec"),
                base_path=[WORKLOAD_UPDATE_STRATEGY_KEY_NAME],
            )
        else:
            raise AssertionError(f"Unexpected resource name: {resource_name}")


class TestCustomWorkLoadStrategy:
    @pytest.mark.parametrize(
        "updated_hco_cr, expected",
        [
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            WORKLOAD_UPDATE_STRATEGY_KEY_NAME: {"batchEvictionInterval": CUSTOM_BATCH_EVICTION_INTERVAL}
                        }
                    },
                },
                MOD_DEFAULT_BATCH_EVICTION_INTERVAL,
                marks=pytest.mark.polarion("CNV-6932"),
                id="test_hyperconverged_modify_custom_workloadUpdateStrategy_batchEvictionInterval",
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {WORKLOAD_UPDATE_STRATEGY_KEY_NAME: {"batchEvictionSize": CUSTOM_BATCH_EVICTION_SIZE}}
                    },
                },
                MOD_DEFAULT_BATCH_EVICTION_SIZE,
                marks=pytest.mark.polarion("CNV-6933"),
                id="test_hyperconverged_modify_custom_workloadUpdateStrategy_batchEvictionSize",
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            WORKLOAD_UPDATE_STRATEGY_KEY_NAME: {"workloadUpdateMethods": CUSTOM_WORKLOAD_UPDATE_METHODS}
                        }
                    },
                },
                MOD_DEFAULT_WORKLOAD_UPDATE_METHOD,
                marks=pytest.mark.polarion("CNV-6934"),
                id="test_hyperconverged_modify_custom_workloadUpdateStrategy_workloadUpdateMethods",
            ),
            pytest.param(
                {
                    "patch": {"spec": {WORKLOAD_UPDATE_STRATEGY_KEY_NAME: {"workloadUpdateMethods": []}}},
                },
                MOD_DEFAULT_WORKLOAD_UPDATE_METHOD_EMPTY,
                marks=pytest.mark.polarion("CNV-6935"),
                id="test_hyperconverged_modify_workloadUpdateStrategy_workloadUpdateMethods_empty",
            ),
            pytest.param(
                {
                    "patch": {"spec": {WORKLOAD_UPDATE_STRATEGY_KEY_NAME: {"batchEvictionInterval": "0s"}}},
                },
                MOD_DEFAULT_BATCH_EVICTION_INTERVAL_ZERO,
                marks=pytest.mark.polarion("CNV-6936"),
                id="test_hyperconverged_modify_workloadUpdateStrategy_batchEvictionInterval_zero",
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            WORKLOAD_UPDATE_STRATEGY_KEY_NAME: {
                                "batchEvictionInterval": CUSTOM_BATCH_EVICTION_INTERVAL_INT
                            }
                        }
                    },
                },
                MOD_DEFAULT_BATCH_EVICTION_INTERVAL_INT,
                marks=pytest.mark.polarion("CNV-6937"),
                id="Test_hyperconverged_modify_workloadUpdateStrategy_batchEvictionInterval_large_value",
            ),
            pytest.param(
                {
                    "patch": {"spec": {WORKLOAD_UPDATE_STRATEGY_KEY_NAME: {"batchEvictionSize": 0}}},
                },
                MOD_DEFAULT_BATCH_EVICTION_SIZE_ZERO,
                marks=pytest.mark.polarion("CNV-6938"),
                id="Test_hyperconverged_modify_workloadUpdateStrategy_batchEvictionSize_zero",
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            WORKLOAD_UPDATE_STRATEGY_KEY_NAME: {"batchEvictionSize": CUSTOM_BATCH_EVICTION_SIZE_INT}
                        }
                    },
                },
                MOD_DEFAULT_BATCH_EVICTION_SIZE_INT,
                marks=pytest.mark.polarion("CNV-6939"),
                id="test_hyperconverged_modify_workloadUpdateStrategy_batchEvictionSize_large_value",
            ),
        ],
        indirect=["updated_hco_cr"],
    )
    @pytest.mark.s390x
    def test_hyperconverged_modify_custom_workload_update_strategy(
        self, admin_client, hco_namespace, updated_hco_cr, expected
    ):
        """Validate ability to update, hyperconverged's spec.workloadUpdateStrategy to custom values"""
        wait_for_spec_change(
            expected=expected,
            get_spec_func=lambda: get_hco_spec(admin_client=admin_client, hco_namespace=hco_namespace),
            base_path=[WORKLOAD_UPDATE_STRATEGY_KEY_NAME],
        )
        if expected == MOD_DEFAULT_WORKLOAD_UPDATE_METHOD_EMPTY:
            del expected[WORKLOADUPDATEMETHODS]
        wait_for_spec_change(
            expected=expected,
            get_spec_func=lambda: get_hyperconverged_kubevirt(admin_client=admin_client, hco_namespace=hco_namespace)
            .instance.to_dict()
            .get("spec"),
            base_path=[WORKLOAD_UPDATE_STRATEGY_KEY_NAME],
        )

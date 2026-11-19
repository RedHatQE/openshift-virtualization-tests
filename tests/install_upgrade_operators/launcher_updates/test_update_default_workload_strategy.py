import pytest

from tests.install_upgrade_operators.constants import WORKLOAD_UPDATE_STRATEGY_KEY_NAME, WORKLOADUPDATEMETHODS
from tests.install_upgrade_operators.launcher_updates.constants import (
    DEFAULT_BATCH_EVICTION_INTERVAL,
    DEFAULT_BATCH_EVICTION_SIZE,
    DEFAULT_WORKLOAD_UPDATE_METHODS,
    DEFAULT_WORKLOAD_UPDATE_STRATEGY,
    HCO_WORKLOAD_UPDATE_STRATEGY_BASE_PATH,
    MOD_CUST_DEFAULT_BATCH_EVICTION_INTERVAL,
    MOD_CUST_DEFAULT_BATCH_EVICTION_SIZE,
    MOD_CUST_DEFAULT_WORKLOAD_UPDATE_METHOD,
)
from tests.install_upgrade_operators.utils import wait_for_spec_change
from utilities.hco import get_hco_spec
from utilities.virt import get_hyperconverged_kubevirt

pytestmark = [pytest.mark.sno, pytest.mark.arm64, pytest.mark.s390x]


class TestLauncherUpdateModifyDefault:
    @pytest.mark.parametrize(
        "updated_hco_cr, expected",
        [
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "virtualization": {
                                WORKLOAD_UPDATE_STRATEGY_KEY_NAME: {
                                    "batchEvictionInterval": DEFAULT_BATCH_EVICTION_INTERVAL
                                }
                            }
                        }
                    },
                },
                MOD_CUST_DEFAULT_BATCH_EVICTION_INTERVAL,
                id="test_hyperconverged_modify_default_batchEvictionInterval",
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "virtualization": {
                                WORKLOAD_UPDATE_STRATEGY_KEY_NAME: {"batchEvictionSize": DEFAULT_BATCH_EVICTION_SIZE}
                            }
                        }
                    },
                },
                MOD_CUST_DEFAULT_BATCH_EVICTION_SIZE,
                id="Test_hyperconverged_modify_default_batchEvictionSize",
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "virtualization": {
                                WORKLOAD_UPDATE_STRATEGY_KEY_NAME: {
                                    WORKLOADUPDATEMETHODS: DEFAULT_WORKLOAD_UPDATE_METHODS
                                }
                            }
                        }
                    },
                },
                MOD_CUST_DEFAULT_WORKLOAD_UPDATE_METHOD,
                id="test_hyperconverged_modify_default_workloadUpdateMethods",
            ),
        ],
        indirect=["updated_hco_cr"],
    )
    def test_hyperconverged_modify_custom_workload_update_strategy(
        self,
        updated_workload_strategy_custom_values,
        admin_client,
        hco_namespace,
        updated_hco_cr,
        expected,
    ):
        """
        Jira: https://redhat.atlassian.net/browse/CNV-8762 # <skip-jira-utils-check>
        Polarion: CNV-6942
        Polarion: CNV-6943
        Polarion: CNV-6944

        Validate ability to update, hyperconverged's spec.workloadUpdateStrategy to custom values
        """
        wait_for_spec_change(
            expected=expected,
            get_spec_func=lambda: get_hco_spec(admin_client=admin_client, hco_namespace=hco_namespace),
            base_path=HCO_WORKLOAD_UPDATE_STRATEGY_BASE_PATH,
        )
        wait_for_spec_change(
            expected=expected,
            get_spec_func=lambda: (
                get_hyperconverged_kubevirt(admin_client=admin_client, hco_namespace=hco_namespace)
                .instance.to_dict()
                .get("spec")
            ),
            base_path=[WORKLOAD_UPDATE_STRATEGY_KEY_NAME],
        )

    @pytest.mark.parametrize(
        "updated_hco_cr, resource_name, expected",
        [
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "virtualization": {
                                WORKLOAD_UPDATE_STRATEGY_KEY_NAME: DEFAULT_WORKLOAD_UPDATE_STRATEGY,
                            }
                        }
                    },
                },
                "hyperconverged",
                DEFAULT_WORKLOAD_UPDATE_STRATEGY,
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "virtualization": {
                                WORKLOAD_UPDATE_STRATEGY_KEY_NAME: DEFAULT_WORKLOAD_UPDATE_STRATEGY,
                            }
                        }
                    },
                },
                "kubevirt",
                DEFAULT_WORKLOAD_UPDATE_STRATEGY,
            ),
        ],
        indirect=["updated_hco_cr"],
    )
    def test_hyperconverged_modify_all_workload_update_strategy(
        self,
        updated_workload_strategy_custom_values,
        admin_client,
        hco_namespace,
        updated_hco_cr,
        resource_name,
        expected,
    ):
        """
        Jira: https://redhat.atlassian.net/browse/CNV-8762 # <skip-jira-utils-check>
        Polarion: CNV-6940
        Polarion: CNV-6941

        Validate ability to reset, hyperconverged's spec.workloadUpdateStrategy from custom values
        """
        if resource_name == "hyperconverged":
            wait_for_spec_change(
                expected=expected,
                get_spec_func=lambda: get_hco_spec(admin_client=admin_client, hco_namespace=hco_namespace),
                base_path=HCO_WORKLOAD_UPDATE_STRATEGY_BASE_PATH,
            )
        elif resource_name == "kubevirt":
            wait_for_spec_change(
                expected=expected,
                get_spec_func=lambda: (
                    get_hyperconverged_kubevirt(admin_client=admin_client, hco_namespace=hco_namespace)
                    .instance.to_dict()
                    .get("spec")
                ),
                base_path=[WORKLOAD_UPDATE_STRATEGY_KEY_NAME],
            )
        else:
            raise AssertionError(f"Unexpected resource name: {resource_name}")

import pytest

from tests.install_upgrade_operators.constants import WORKLOAD_UPDATE_STRATEGY_KEY_NAME, WORKLOADUPDATEMETHODS
from tests.install_upgrade_operators.launcher_updates.constants import (
    CUSTOM_WORKLOAD_UPDATE_STRATEGY,
)
from tests.install_upgrade_operators.utils import wait_for_spec_change
from utilities.hco import get_hco_spec
from utilities.virt import get_hyperconverged_kubevirt

pytestmark = [pytest.mark.sno, pytest.mark.arm64]
KUBEVIRT_NEGATIVE_STRATEGY = {
    "batchEvictionInterval": "2m",
    "batchEvictionSize": 30,
    WORKLOADUPDATEMETHODS: ["Evict"],
}


class TestLauncherUpdateNegative:
    @pytest.mark.parametrize(
        "updated_kubevirt_cr,",
        [
            pytest.param(
                {
                    "patch": {"spec": {WORKLOAD_UPDATE_STRATEGY_KEY_NAME: KUBEVIRT_NEGATIVE_STRATEGY}},
                },
                marks=pytest.mark.polarion("CNV-6945"),
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            WORKLOAD_UPDATE_STRATEGY_KEY_NAME: {
                                "batchEvictionInterval": KUBEVIRT_NEGATIVE_STRATEGY["batchEvictionInterval"]
                            }
                        }
                    },
                },
                marks=pytest.mark.polarion("CNV-6946"),
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            WORKLOAD_UPDATE_STRATEGY_KEY_NAME: {
                                "batchEvictionSize": KUBEVIRT_NEGATIVE_STRATEGY["batchEvictionSize"]
                            }
                        }
                    },
                },
                marks=pytest.mark.polarion("CNV-6947"),
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            WORKLOAD_UPDATE_STRATEGY_KEY_NAME: {
                                WORKLOADUPDATEMETHODS: KUBEVIRT_NEGATIVE_STRATEGY[WORKLOADUPDATEMETHODS]
                            }
                        }
                    },
                },
                marks=pytest.mark.polarion("CNV-6948"),
            ),
        ],
        indirect=True,
    )
    @pytest.mark.s390x
    def test_hyperconverged_reset_custom_workload_update_strategy(
        self,
        updated_workload_strategy_custom_values,
        admin_client,
        hco_namespace,
        updated_kubevirt_cr,
    ):
        """Negative tests to validate, workload update strategy fields of kubevirt gets reconciled"""
        wait_for_spec_change(
            expected=CUSTOM_WORKLOAD_UPDATE_STRATEGY,
            get_spec_func=lambda: get_hco_spec(admin_client=admin_client, hco_namespace=hco_namespace),
            base_path=[WORKLOAD_UPDATE_STRATEGY_KEY_NAME],
        )
        wait_for_spec_change(
            expected=CUSTOM_WORKLOAD_UPDATE_STRATEGY,
            get_spec_func=lambda: get_hyperconverged_kubevirt(
                admin_client=admin_client, hco_namespace=hco_namespace
            ).instance.to_dict()["spec"],
            base_path=[WORKLOAD_UPDATE_STRATEGY_KEY_NAME],
        )

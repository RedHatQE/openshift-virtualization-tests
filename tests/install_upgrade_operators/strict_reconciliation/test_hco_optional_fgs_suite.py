import logging

import pytest

from tests.install_upgrade_operators.strict_reconciliation.utils import (
    validate_featuregates_not_in_cdi_cr,
    wait_for_fg_update,
)
from utilities.constants.hco import FEATURE_GATES
from utilities.hco import get_hco_feature_gates, wait_for_hco_conditions
from utilities.virt import (
    get_kubevirt_hyperconverged_spec,
    wait_for_kubevirt_conditions,
)

pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno, pytest.mark.arm64, pytest.mark.s390x]

LOGGER = logging.getLogger(__name__)


class TestNegativeFeatureGates:
    @pytest.mark.parametrize(
        ("hco_with_non_default_feature_gates",),
        [
            pytest.param(
                {
                    "fgs": ["fakeGate", "Sidecar"],
                },
                marks=(pytest.mark.polarion("CNV-6273")),
                id="invalid_featuregates_fake_kept_on_hco_not_propagated",
            ),
            pytest.param(
                {
                    "fgs": ["LiveMigration"],
                },
                marks=(pytest.mark.polarion("CNV-6274")),
                id="invalid_featuregates_livemigration_kept_on_hco_not_propagated",
            ),
            pytest.param(
                {
                    "fgs": ["Sidecar"],
                },
                marks=(pytest.mark.polarion("CNV-6276")),
                id="invalid_featuregates_sidecar_kept_on_hco_not_propagated",
            ),
            pytest.param(
                {
                    "fgs": ["HonorWaitForFirstConsumer"],
                },
                marks=(pytest.mark.polarion("CNV-6278")),
                id="invalid_cdi_featuregate_kept_on_hco_not_propagated",
            ),
        ],
        indirect=["hco_with_non_default_feature_gates"],
    )
    def test_invalid_featuregates_in_hco_cr(
        self,
        admin_client,
        hco_namespace,
        kubevirt_feature_gates_scope_module,
        hyperconverged_resource_scope_function,
        hco_with_non_default_feature_gates,
    ):
        updated_hco_names = {
            entry["name"] for entry in get_hco_feature_gates(hco=hyperconverged_resource_scope_function)
        }
        missing_hco_gates = [
            gate_name for gate_name in hco_with_non_default_feature_gates if gate_name not in updated_hco_names
        ]
        assert not missing_hco_gates, (
            f"HCO dropped unknown feature gates {missing_hco_gates} from spec.featureGates; "
            f"v1 keeps user-supplied names. Current list: {updated_hco_names}"
        )

        kv_current_fg = get_kubevirt_hyperconverged_spec(admin_client=admin_client, hco_namespace=hco_namespace)[
            "configuration"
        ]["developerConfiguration"][FEATURE_GATES]
        assert kubevirt_feature_gates_scope_module == kv_current_fg, (
            f"Kubevirt featuregates: {kubevirt_feature_gates_scope_module} got updated with invalid values:"
            f"{kv_current_fg}"
        )

    @pytest.mark.parametrize(
        ("updated_kv_with_feature_gates"),
        [
            pytest.param(
                ["fakeGate", "Sidecar"],
                marks=(pytest.mark.polarion("CNV-6272")),
                id="kubevirt_cr_reconciles_on_modifcation_fakegate_sidecar",
            ),
            pytest.param(
                ["Sidecar"],
                marks=(pytest.mark.polarion("CNV-6275")),
                id="kubevirt_cr_reconciles_on_modifcation_sidecar",
            ),
        ],
        indirect=["updated_kv_with_feature_gates"],
    )
    def test_optional_featuregates_removed_from_kubevirt_cr(
        self,
        admin_client,
        hco_namespace,
        updated_kv_with_feature_gates,
        kubevirt_feature_gates_scope_module,
    ):
        wait_for_kubevirt_conditions(
            admin_client=admin_client,
            hco_namespace=hco_namespace,
        )
        wait_for_hco_conditions(admin_client=admin_client, hco_namespace=hco_namespace)
        assert (
            kubevirt_feature_gates_scope_module
            == get_kubevirt_hyperconverged_spec(admin_client=admin_client, hco_namespace=hco_namespace)[
                "configuration"
            ]["developerConfiguration"][FEATURE_GATES]
        )


class TestHCOOptionalFeatureGatesSuite:
    @pytest.mark.polarion("CNV-6277")
    @pytest.mark.parametrize(
        "updated_cdi_with_feature_gates",
        [["fakeGate"]],
        indirect=["updated_cdi_with_feature_gates"],
    )
    def test_optional_featuregates_fake_removed_from_cdi_cr(
        self,
        updated_cdi_with_feature_gates,
        admin_client,
        hco_namespace,
    ):
        wait_for_fg_update(
            admin_client=admin_client,
            hco_namespace=hco_namespace,
            expected_fg=["fakeGate"],
            validate_func=validate_featuregates_not_in_cdi_cr,
        )

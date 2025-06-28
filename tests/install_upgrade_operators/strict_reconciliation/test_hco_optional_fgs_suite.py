import logging

import pytest

from tests.install_upgrade_operators.strict_reconciliation.utils import (
    validate_featuregates_not_in_cdi_cr,
    wait_for_fg_update,
)
from utilities.constants import FEATURE_GATES
from utilities.hco import get_hco_spec, wait_for_hco_conditions
from utilities.virt import (
    get_kubevirt_hyperconverged_spec,
    wait_for_kubevirt_conditions,
)

pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno, pytest.mark.arm64]

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
                id="invalid_featuregates_fake_removed_from_hco_cr",
            ),
            pytest.param(
                {
                    "fgs": ["LiveMigration"],
                },
                marks=(pytest.mark.polarion("CNV-6274")),
                id="invalid_featuregates_livemigration_is_removed_from_hco_cr",
            ),
            pytest.param(
                {
                    "fgs": ["Sidecar"],
                },
                marks=(pytest.mark.polarion("CNV-6276")),
                id="invalid_featuregates_sidecar_removed_from_hco_cr",
            ),
            pytest.param(
                {
                    "fgs": ["HonorWaitForFirstConsumer"],
                },
                marks=(pytest.mark.polarion("CNV-6278")),
                id="invalid_cdi_featuregate_removed_from_hco_cr",
            ),
        ],
        indirect=["hco_with_non_default_feature_gates"],
    )
    @pytest.mark.s390x
    def test_invalid_featuregates_in_hco_cr(
        self,
        admin_client,
        hco_namespace,
        kubevirt_feature_gates_scope_module,
        hco_spec_scope_module,
        hco_with_non_default_feature_gates,
    ):
        default_hco_fg = hco_spec_scope_module[FEATURE_GATES]
        updated_hco_fg = get_hco_spec(admin_client=admin_client, hco_namespace=hco_namespace)[FEATURE_GATES]
        assert updated_hco_fg == default_hco_fg, (
            f"HCO featuregates: {default_hco_fg} got updated with invalid featuregates {updated_hco_fg}"
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
    @pytest.mark.s390x
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
    @pytest.mark.s390x
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

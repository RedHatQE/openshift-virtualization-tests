import pytest

from tests.install_upgrade_operators.strict_reconciliation.constants import (
    ALLOW_AUTO_CONVERGE,
    ALLOW_POST_COPY,
    KUBEVIRT_CR_CONFIGURATION_KEY,
    KUBEVIRT_CR_MIGRATIONS_KEY,
    LIVE_MIGRATION_CONFIG_KEY,
)

pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno, pytest.mark.gating, pytest.mark.arm64]
EXPECTED_VALUE = True
SPEC_STR = "spec"
PATCH_STR = "patch"


class TestLiveMigrationConfigUpdate:
    @pytest.mark.parametrize(
        ("updated_hco_cr", "expected"),
        [
            pytest.param(
                {
                    PATCH_STR: {SPEC_STR: {LIVE_MIGRATION_CONFIG_KEY: {ALLOW_AUTO_CONVERGE: EXPECTED_VALUE}}},
                },
                ALLOW_AUTO_CONVERGE,
                marks=pytest.mark.polarion("CNV-9674"),
                id="test_allow_auto_converge",
            ),
            pytest.param(
                {
                    PATCH_STR: {SPEC_STR: {LIVE_MIGRATION_CONFIG_KEY: {ALLOW_POST_COPY: EXPECTED_VALUE}}},
                },
                ALLOW_POST_COPY,
                marks=pytest.mark.polarion("CNV-9675"),
                id="test_allow_post_copy",
            ),
        ],
        indirect=["updated_hco_cr"],
    )
    @pytest.mark.s390x
    def test_modify_hco_cr(
        self,
        updated_hco_cr,
        expected,
        hco_spec,
        kubevirt_hyperconverged_spec_scope_function,
    ):
        hco_value = hco_spec[LIVE_MIGRATION_CONFIG_KEY].get(expected)
        kubevirt_value = kubevirt_hyperconverged_spec_scope_function[KUBEVIRT_CR_CONFIGURATION_KEY][
            KUBEVIRT_CR_MIGRATIONS_KEY
        ].get(expected)

        assert hco_value == kubevirt_value == EXPECTED_VALUE, (
            f"Current HCO.{SPEC_STR}.{LIVE_MIGRATION_CONFIG_KEY}.{expected} value: "
            f"{hco_value}, current Kubevirt.{SPEC_STR}.{KUBEVIRT_CR_CONFIGURATION_KEY}.{KUBEVIRT_CR_MIGRATIONS_KEY}."
            f"{expected} value:  {kubevirt_value}, "
            f"expected: {EXPECTED_VALUE}, "
        )

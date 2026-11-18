import pytest

from tests.install_upgrade_operators.strict_reconciliation.constants import (
    ALLOW_AUTO_CONVERGE,
    ALLOW_POST_COPY,
    ALLOW_WORKLOAD_DISRUPTION,
    KUBEVIRT_CR_CONFIGURATION_KEY,
    KUBEVIRT_CR_MIGRATIONS_KEY,
    LIVE_MIGRATION_CONFIG_KEY,
)

pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno, pytest.mark.gating, pytest.mark.arm64, pytest.mark.s390x]
EXPECTED_VALUE = True
SPEC_STR = "spec"
PATCH_STR = "patch"


class TestLiveMigrationConfigUpdate:
    @pytest.mark.parametrize(
        ("updated_hco_cr", "expected"),
        [
            pytest.param(
                {
                    PATCH_STR: {
                        SPEC_STR: {"virtualization": {LIVE_MIGRATION_CONFIG_KEY: {ALLOW_AUTO_CONVERGE: EXPECTED_VALUE}}}
                    },
                },
                ALLOW_AUTO_CONVERGE,
                id="test_allow_auto_converge",
            ),
            pytest.param(
                {
                    PATCH_STR: {
                        SPEC_STR: {"virtualization": {LIVE_MIGRATION_CONFIG_KEY: {ALLOW_POST_COPY: EXPECTED_VALUE}}}
                    },
                },
                ALLOW_POST_COPY,
                id="test_allow_post_copy",
            ),
            pytest.param(
                {
                    PATCH_STR: {
                        SPEC_STR: {
                            "virtualization": {LIVE_MIGRATION_CONFIG_KEY: {ALLOW_WORKLOAD_DISRUPTION: EXPECTED_VALUE}}
                        }
                    },
                },
                ALLOW_WORKLOAD_DISRUPTION,
                id="test_allow_workload_disruption",
            ),
        ],
        indirect=["updated_hco_cr"],
    )
    def test_modify_hco_cr(
        self,
        updated_hco_cr,
        expected,
        hco_spec,
        kubevirt_hyperconverged_spec_scope_function,
    ):
        """
        Jira: https://redhat.atlassian.net/browse/CNV-8296 # <skip-jira-utils-check>
        Jira: https://redhat.atlassian.net/browse/CNV-54933 # <skip-jira-utils-check>
        Polarion: CNV-9674
        Polarion: CNV-9675
        Polarion: CNV-16551
        """
        hco_value = hco_spec["virtualization"][LIVE_MIGRATION_CONFIG_KEY].get(expected)
        kubevirt_value = kubevirt_hyperconverged_spec_scope_function[KUBEVIRT_CR_CONFIGURATION_KEY][
            KUBEVIRT_CR_MIGRATIONS_KEY
        ].get(expected)

        assert hco_value == kubevirt_value == EXPECTED_VALUE, (
            f"Current HCO.{SPEC_STR}.virtualization.{LIVE_MIGRATION_CONFIG_KEY}.{expected} value: "
            f"{hco_value}, current Kubevirt.{SPEC_STR}.{KUBEVIRT_CR_CONFIGURATION_KEY}.{KUBEVIRT_CR_MIGRATIONS_KEY}."
            f"{expected} value:  {kubevirt_value}, "
            f"expected: {EXPECTED_VALUE}, "
        )

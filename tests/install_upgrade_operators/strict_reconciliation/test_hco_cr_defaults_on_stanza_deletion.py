import logging

import pytest
from benedict import benedict
from ocp_resources.cdi import CDI
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.network_addons_config import NetworkAddonsConfig

from tests.install_upgrade_operators.constants import (
    HCO_CR_CERT_CONFIG_CA_KEY,
    HCO_CR_CERT_CONFIG_DURATION_KEY,
    HCO_CR_CERT_CONFIG_KEY,
    HCO_CR_CERT_CONFIG_RENEW_BEFORE_KEY,
    HCO_CR_CERT_CONFIG_SERVER_KEY,
)
from tests.install_upgrade_operators.strict_reconciliation.constants import (
    CERTC_CUSTOM_18H,
    CERTC_CUSTOM_36H,
    CERTC_CUSTOM_96H,
    COMPLETION_TIMEOUT_PER_GIB_KEY,
    EXPCT_CERTC_CUSTOM_CA_DUR,
    EXPCT_CERTC_CUSTOM_CA_RB,
    EXPCT_CERTC_CUSTOM_SERVER_DUR,
    EXPCT_CERTC_CUSTOM_SERVER_RB,
    EXPCT_CERTC_DEFAULTS,
    EXPCT_LM_CUSTOM_C,
    EXPCT_LM_CUSTOM_PM,
    EXPCT_LM_CUSTOM_PO,
    EXPCT_LM_CUSTOM_PT,
    EXPCT_LM_DEFAULTS,
    LIVE_MIGRATION_CONFIG_KEY,
    LM_COMPLETIONTIMEOUTPERGIB_CUSTOM,
    LM_PARALLELMIGRATIONSPERCLUSTER_CUSTOM,
    LM_PARALLELOUTBOUNDMIGRATIONSPERNODE_CUSTOM,
    LM_PROGRESSTIMEOUT_CUSTOM,
    PARALLEL_MIGRATIONS_PER_CLUSTER_KEY,
    PARALLEL_OUTBOUND_MIGRATIONS_PER_NODE_KEY,
    PROGRESS_TIMEOUT_KEY,
)
from utilities.hco import wait_for_hco_conditions

pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno, pytest.mark.arm64]

LOGGER = logging.getLogger(__name__)


class TestCRDefaultsOnStanzaDeletion:
    @pytest.mark.parametrize(
        "deleted_stanza_on_hco_cr, expected",
        [
            pytest.param(
                {
                    "rpatch": {
                        "spec": {
                            HCO_CR_CERT_CONFIG_KEY: {HCO_CR_CERT_CONFIG_CA_KEY: {HCO_CR_CERT_CONFIG_DURATION_KEY: None}}
                        }
                    },
                },
                EXPCT_CERTC_DEFAULTS,
                id="defaults_cr_ca_duration_none",
                marks=(pytest.mark.polarion("CNV-6377")),
            ),
            pytest.param(
                {
                    "rpatch": {
                        "spec": {
                            HCO_CR_CERT_CONFIG_KEY: {
                                HCO_CR_CERT_CONFIG_CA_KEY: {HCO_CR_CERT_CONFIG_RENEW_BEFORE_KEY: None}
                            }
                        }
                    },
                },
                EXPCT_CERTC_DEFAULTS,
                id="defaults_cr_ca_renewbefore_none",
                marks=(pytest.mark.polarion("CNV-6378")),
            ),
            pytest.param(
                {
                    "rpatch": {"spec": {HCO_CR_CERT_CONFIG_KEY: {HCO_CR_CERT_CONFIG_CA_KEY: {}}}},
                },
                EXPCT_CERTC_DEFAULTS,
                id="defaults_cr_ca_empty",
                marks=(pytest.mark.polarion("CNV-6379")),
            ),
            pytest.param(
                {
                    "rpatch": {"spec": {HCO_CR_CERT_CONFIG_KEY: {HCO_CR_CERT_CONFIG_CA_KEY: None}}},
                },
                EXPCT_CERTC_DEFAULTS,
                id="defaults_cr_ca_none",
                marks=(pytest.mark.polarion("CNV-6380")),
            ),
            pytest.param(
                {
                    "rpatch": {
                        "spec": {
                            HCO_CR_CERT_CONFIG_KEY: {
                                HCO_CR_CERT_CONFIG_SERVER_KEY: {HCO_CR_CERT_CONFIG_DURATION_KEY: None}
                            }
                        }
                    },
                },
                EXPCT_CERTC_DEFAULTS,
                id="defaults_cr_server_duration_none",
                marks=(pytest.mark.polarion("CNV-6381")),
            ),
            pytest.param(
                {
                    "rpatch": {
                        "spec": {
                            HCO_CR_CERT_CONFIG_KEY: {
                                HCO_CR_CERT_CONFIG_SERVER_KEY: {HCO_CR_CERT_CONFIG_RENEW_BEFORE_KEY: None}
                            }
                        }
                    },
                },
                EXPCT_CERTC_DEFAULTS,
                id="defaults_cr_server_renewbefore_none",
                marks=(pytest.mark.polarion("CNV-6382")),
            ),
            pytest.param(
                {
                    "rpatch": {"spec": {HCO_CR_CERT_CONFIG_KEY: {HCO_CR_CERT_CONFIG_SERVER_KEY: {}}}},
                },
                EXPCT_CERTC_DEFAULTS,
                id="defaults_cr_server_empty",
                marks=(pytest.mark.polarion("CNV-6383")),
            ),
            pytest.param(
                {
                    "rpatch": {"spec": {HCO_CR_CERT_CONFIG_KEY: {HCO_CR_CERT_CONFIG_SERVER_KEY: None}}},
                },
                EXPCT_CERTC_DEFAULTS,
                id="defaults_cr_server_none",
                marks=(pytest.mark.polarion("CNV-6384")),
            ),
            pytest.param(
                {
                    "rpatch": {"spec": {HCO_CR_CERT_CONFIG_KEY: {}}},
                },
                EXPCT_CERTC_DEFAULTS,
                id="defaults_cr_empty",
                marks=(pytest.mark.polarion("CNV-6385")),
            ),
            pytest.param(
                {
                    "rpatch": {"spec": {HCO_CR_CERT_CONFIG_KEY: None}},
                },
                EXPCT_CERTC_DEFAULTS,
                id="defaults_cr_none",
                marks=(pytest.mark.polarion("CNV-6386")),
            ),
            pytest.param(
                {
                    "rpatch": {"spec": {}},
                },
                EXPCT_CERTC_DEFAULTS,
                id="defaults_cr_spec_empty",
                marks=(pytest.mark.polarion("CNV-6387")),
            ),
            pytest.param(
                {
                    "rpatch": {"spec": None},
                },
                EXPCT_CERTC_DEFAULTS,
                id="defaults_cr_spec_none",
                marks=(pytest.mark.polarion("CNV-6388")),
            ),
            pytest.param(
                {
                    "rpatch": {},
                },
                EXPCT_CERTC_DEFAULTS,
                id="defaults_cr_empty",
                marks=(pytest.mark.polarion("CNV-6389")),
            ),
            pytest.param(
                {
                    "rpatch": {
                        "spec": {
                            HCO_CR_CERT_CONFIG_KEY: {
                                HCO_CR_CERT_CONFIG_CA_KEY: {HCO_CR_CERT_CONFIG_DURATION_KEY: CERTC_CUSTOM_96H}
                            }
                        }
                    },
                    "list_resource_reconcile": [NetworkAddonsConfig, CDI],
                },
                EXPCT_CERTC_CUSTOM_CA_DUR,
                id="defaults_cr_custom_ca_dur",
                marks=(pytest.mark.polarion("CNV-6390")),
            ),
            pytest.param(
                {
                    "rpatch": {
                        "spec": {
                            HCO_CR_CERT_CONFIG_KEY: {
                                HCO_CR_CERT_CONFIG_CA_KEY: {HCO_CR_CERT_CONFIG_RENEW_BEFORE_KEY: CERTC_CUSTOM_36H}
                            }
                        }
                    },
                    "list_resource_reconcile": [NetworkAddonsConfig, CDI],
                },
                EXPCT_CERTC_CUSTOM_CA_RB,
                id="defaults_cr_custom_ca_rb",
                marks=(pytest.mark.polarion("CNV-6391")),
            ),
            pytest.param(
                {
                    "rpatch": {
                        "spec": {
                            HCO_CR_CERT_CONFIG_KEY: {
                                HCO_CR_CERT_CONFIG_SERVER_KEY: {HCO_CR_CERT_CONFIG_DURATION_KEY: CERTC_CUSTOM_36H}
                            }
                        }
                    },
                    "list_resource_reconcile": [NetworkAddonsConfig, CDI],
                },
                EXPCT_CERTC_CUSTOM_SERVER_DUR,
                id="defaults_cr_custom_server_dur",
                marks=(pytest.mark.polarion("CNV-6392")),
            ),
            pytest.param(
                {
                    "rpatch": {
                        "spec": {
                            HCO_CR_CERT_CONFIG_KEY: {
                                HCO_CR_CERT_CONFIG_SERVER_KEY: {HCO_CR_CERT_CONFIG_RENEW_BEFORE_KEY: CERTC_CUSTOM_18H}
                            }
                        }
                    },
                    "list_resource_reconcile": [NetworkAddonsConfig, CDI],
                },
                EXPCT_CERTC_CUSTOM_SERVER_RB,
                id="defaults_cr_custom_server_rb",
                marks=(pytest.mark.polarion("CNV-6393")),
            ),
        ],
        indirect=["deleted_stanza_on_hco_cr"],
    )
    @pytest.mark.s390x
    def test_certconfig_defaults_on_stanza_delete(
        self,
        deleted_stanza_on_hco_cr,
        hyperconverged_resource_scope_function,
        expected,
    ):
        assert (
            hyperconverged_resource_scope_function.instance.to_dict().get("spec").get(HCO_CR_CERT_CONFIG_KEY)
            == expected
        )

    @pytest.mark.parametrize(
        "deleted_stanza_on_hco_cr, expected",
        [
            pytest.param(
                {
                    "rpatch": {"spec": {"featureGates": None}},
                },
                {"featureGates": None},
                id="defaults_fg_none",
                marks=(pytest.mark.polarion("CNV-6397")),
            ),
            pytest.param(
                {
                    "rpatch": {"spec": None},
                },
                {"spec": None},
                id="defaults_fg_spec_none",
                marks=(pytest.mark.polarion("CNV-6399")),
            ),
        ],
        indirect=["deleted_stanza_on_hco_cr"],
    )
    @pytest.mark.s390x
    def test_featuregates_defaults_on_stanza_delete(
        self,
        admin_client,
        hco_namespace,
        hco_spec_scope_module,
        deleted_stanza_on_hco_cr,
        hyperconverged_resource_scope_function,
        expected,
    ):
        wait_for_hco_conditions(
            admin_client=admin_client,
            hco_namespace=hco_namespace,
            consecutive_checks_count=6,
        )
        for key, value in expected.items():
            current_spec = benedict(hyperconverged_resource_scope_function.instance.to_dict()["spec"])
            current_value = current_spec if key == "spec" else current_spec.get(key)
            if value is not None:
                assert current_value == value, f"Expected value of hco.{key}: {value}, actual: {current_value}"
            else:
                default_value = benedict(hco_spec_scope_module)
                default_value = default_value if key == "spec" else default_value.get(key)
                assert current_value == default_value, (
                    f"Default value for hco.{key}: {default_value} does not match actual value: {current_value}"
                )

    @pytest.mark.parametrize(
        "deleted_stanza_on_hco_cr, expected",
        [
            pytest.param(
                {
                    "rpatch": {"spec": {LIVE_MIGRATION_CONFIG_KEY: {PARALLEL_MIGRATIONS_PER_CLUSTER_KEY: None}}},
                },
                EXPCT_LM_DEFAULTS,
                id="defaults_lm_pm_none",
                marks=(pytest.mark.polarion("CNV-6403")),
            ),
            pytest.param(
                {
                    "rpatch": {"spec": {LIVE_MIGRATION_CONFIG_KEY: {PARALLEL_OUTBOUND_MIGRATIONS_PER_NODE_KEY: None}}},
                },
                EXPCT_LM_DEFAULTS,
                id="defaults_lm_po_none",
                marks=(pytest.mark.polarion("CNV-6404")),
            ),
            pytest.param(
                {
                    "rpatch": {"spec": {LIVE_MIGRATION_CONFIG_KEY: {COMPLETION_TIMEOUT_PER_GIB_KEY: None}}},
                },
                EXPCT_LM_DEFAULTS,
                id="defaults_lm_c_none",
                marks=(pytest.mark.polarion("CNV-6406")),
            ),
            pytest.param(
                {
                    "rpatch": {"spec": {LIVE_MIGRATION_CONFIG_KEY: {PROGRESS_TIMEOUT_KEY: None}}},
                },
                EXPCT_LM_DEFAULTS,
                id="defaults_lm_pt_none",
                marks=(pytest.mark.polarion("CNV-6407")),
            ),
            pytest.param(
                {
                    "rpatch": {"spec": {LIVE_MIGRATION_CONFIG_KEY: {}}},
                },
                EXPCT_LM_DEFAULTS,
                id="defaults_lm_empty",
                marks=(pytest.mark.polarion("CNV-6408")),
            ),
            pytest.param(
                {
                    "rpatch": {"spec": {LIVE_MIGRATION_CONFIG_KEY: None}},
                },
                EXPCT_LM_DEFAULTS,
                id="defaults_lm_none",
                marks=(pytest.mark.polarion("CNV-6409")),
            ),
            pytest.param(
                {
                    "rpatch": {"spec": {}},
                },
                EXPCT_LM_DEFAULTS,
                id="defaults_lm_spec_empty",
                marks=(pytest.mark.polarion("CNV-6410")),
            ),
            pytest.param(
                {
                    "rpatch": {"spec": None},
                },
                EXPCT_LM_DEFAULTS,
                id="defaults_lm_spec_none",
                marks=(pytest.mark.polarion("CNV-6411")),
            ),
            pytest.param(
                {
                    "rpatch": {},
                },
                EXPCT_LM_DEFAULTS,
                id="defaults_lm_cr_empty",
                marks=(pytest.mark.polarion("CNV-6412")),
            ),
            pytest.param(
                {
                    "rpatch": {
                        "spec": {
                            LIVE_MIGRATION_CONFIG_KEY: {
                                PARALLEL_MIGRATIONS_PER_CLUSTER_KEY: LM_PARALLELMIGRATIONSPERCLUSTER_CUSTOM
                            }
                        },
                    },
                    "list_resource_reconcile": [KubeVirt],
                },
                EXPCT_LM_CUSTOM_PM,
                id="defaults_lm_custom_pm",
                marks=(pytest.mark.polarion("CNV-6413")),
            ),
            pytest.param(
                {
                    "rpatch": {
                        "spec": {
                            LIVE_MIGRATION_CONFIG_KEY: {
                                PARALLEL_OUTBOUND_MIGRATIONS_PER_NODE_KEY: LM_PARALLELOUTBOUNDMIGRATIONSPERNODE_CUSTOM
                            }
                        }
                    },
                    "list_resource_reconcile": [KubeVirt],
                },
                EXPCT_LM_CUSTOM_PO,
                id="defaults_lm_custom_po",
                marks=(pytest.mark.polarion("CNV-6414")),
            ),
            pytest.param(
                {
                    "rpatch": {
                        "spec": {
                            LIVE_MIGRATION_CONFIG_KEY: {
                                COMPLETION_TIMEOUT_PER_GIB_KEY: LM_COMPLETIONTIMEOUTPERGIB_CUSTOM
                            }
                        }
                    },
                    "list_resource_reconcile": [KubeVirt],
                },
                EXPCT_LM_CUSTOM_C,
                id="defaults_lm_custom_c",
                marks=(pytest.mark.polarion("CNV-6416")),
            ),
            pytest.param(
                {
                    "rpatch": {"spec": {LIVE_MIGRATION_CONFIG_KEY: {PROGRESS_TIMEOUT_KEY: LM_PROGRESSTIMEOUT_CUSTOM}}},
                    "list_resource_reconcile": [KubeVirt],
                },
                EXPCT_LM_CUSTOM_PT,
                id="defaults_lm_custom_pt",
                marks=(pytest.mark.polarion("CNV-6417")),
            ),
        ],
        indirect=["deleted_stanza_on_hco_cr"],
    )
    @pytest.mark.s390x
    def test_livemigrationconfig_defaults_on_stanza_delete(
        self,
        deleted_stanza_on_hco_cr,
        hyperconverged_resource_scope_function,
        expected,
    ):
        assert (
            hyperconverged_resource_scope_function.instance.to_dict().get("spec").get(LIVE_MIGRATION_CONFIG_KEY)
            == expected
        )

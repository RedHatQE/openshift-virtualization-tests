import logging

import pytest

from tests.install_upgrade_operators.constants import (
    HCO_CR_CERT_CONFIG_CA_KEY,
    HCO_CR_CERT_CONFIG_DURATION_KEY,
    HCO_CR_CERT_CONFIG_KEY,
    HCO_CR_CERT_CONFIG_RENEW_BEFORE_KEY,
    HCO_CR_CERT_CONFIG_SERVER_KEY,
)
from tests.install_upgrade_operators.strict_reconciliation.constants import (
    CDI_CR_CERT_CONFIG_KEY,
    CERTC_DEFAULT_12H,
    CERTC_DEFAULT_24H,
    CERTC_DEFAULT_48H,
    CNAO_CERT_CONFIG_DEFAULT,
    CNAO_CR_CERT_CONFIG_KEY,
    CNAO_MOD_DEFAULT_CA_DUR_EXPECTED,
    CNAO_MOD_DEFAULT_CA_RB_EXPECTED,
    CNAO_MOD_DEFAULT_SER_DUR_EXPECTED,
    CNAO_MOD_DEFAULT_SER_RB_EXPECTED,
    COMPLETION_TIMEOUT_PER_GIB_KEY,
    EXPCT_CERTC_DEFAULTS,
    EXPCT_LM_DEFAULTS,
    HCO_MOD_DEFAULT_CA_DUR,
    HCO_MOD_DEFAULT_CA_RB,
    HCO_MOD_DEFAULT_SER_DUR,
    HCO_MOD_DEFAULT_SER_RB,
    KUBEVIRT_CR_CERT_CONFIG_KEY,
    KUBEVIRT_CR_CONFIGURATION_KEY,
    KUBEVIRT_CR_MIGRATIONS_KEY,
    KUBEVIRT_DEFAULT,
    KV_MOD_DEFAULT_CA_DUR,
    KV_MOD_DEFAULT_CA_RB,
    KV_MOD_DEFAULT_SER_DUR,
    KV_MOD_DEFAULT_SER_RB,
    LIVE_MIGRATION_CONFIG_KEY,
    LM_COMPLETIONTIMEOUTPERGIB_DEFAULT,
    LM_CUST_DEFAULT_C,
    LM_CUST_DEFAULT_PM,
    LM_CUST_DEFAULT_PO,
    LM_CUST_DEFAULT_PT,
    LM_PARALLELMIGRATIONSPERCLUSTER_DEFAULT,
    LM_PO_DEFAULT,
    LM_PROGRESSTIMEOUT_DEFAULT,
    PARALLEL_MIGRATIONS_PER_CLUSTER_KEY,
    PROGRESS_TIMEOUT_KEY,
)
from tests.install_upgrade_operators.utils import (
    get_network_addon_config,
    wait_for_spec_change,
)
from utilities.hco import get_hco_spec
from utilities.storage import get_hyperconverged_cdi
from utilities.virt import get_hyperconverged_kubevirt

pytestmark = [pytest.mark.sno, pytest.mark.post_upgrade, pytest.mark.arm64]
LOGGER = logging.getLogger(__name__)


class TestOperatorsModify:
    @pytest.mark.parametrize(
        ("updated_hco_cr", "expected"),
        [
            pytest.param(
                {
                    "patch": {"spec": {HCO_CR_CERT_CONFIG_KEY: EXPCT_CERTC_DEFAULTS}},
                },
                {
                    "hco_spec": {
                        "expected": EXPCT_CERTC_DEFAULTS,
                        "base_path": [HCO_CR_CERT_CONFIG_KEY],
                    },
                    "kubevirt_spec": {
                        "expected": KUBEVIRT_DEFAULT,
                        "base_path": [KUBEVIRT_CR_CERT_CONFIG_KEY],
                    },
                    "cdi_spec": EXPCT_CERTC_DEFAULTS,
                    "cnao_spec": CNAO_CERT_CONFIG_DEFAULT,
                },
                marks=pytest.mark.polarion("CNV-6698"),
                id="modify_defaults_certconfig",
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            HCO_CR_CERT_CONFIG_KEY: {
                                HCO_CR_CERT_CONFIG_CA_KEY: {
                                    HCO_CR_CERT_CONFIG_DURATION_KEY: CERTC_DEFAULT_48H,
                                },
                            }
                        }
                    },
                },
                {
                    "hco_spec": {
                        "expected": HCO_MOD_DEFAULT_CA_DUR,
                        "base_path": [HCO_CR_CERT_CONFIG_KEY],
                    },
                    "kubevirt_spec": {
                        "expected": KV_MOD_DEFAULT_CA_DUR,
                        "base_path": [KUBEVIRT_CR_CERT_CONFIG_KEY],
                    },
                    "cdi_spec": HCO_MOD_DEFAULT_CA_DUR,
                    "cnao_spec": CNAO_MOD_DEFAULT_CA_DUR_EXPECTED,
                },
                marks=pytest.mark.polarion("CNV-6699"),
                id="Test_Modify_HCO_CR_CertConfig_ca_duration",
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            HCO_CR_CERT_CONFIG_KEY: {
                                HCO_CR_CERT_CONFIG_CA_KEY: {
                                    HCO_CR_CERT_CONFIG_RENEW_BEFORE_KEY: CERTC_DEFAULT_24H,
                                },
                            }
                        }
                    },
                },
                {
                    "hco_spec": {
                        "expected": HCO_MOD_DEFAULT_CA_RB,
                        "base_path": HCO_CR_CERT_CONFIG_KEY,
                    },
                    "kubevirt_spec": {
                        "expected": KV_MOD_DEFAULT_CA_RB,
                        "base_path": KUBEVIRT_CR_CERT_CONFIG_KEY,
                    },
                    "cdi_spec": HCO_MOD_DEFAULT_CA_RB,
                    "cnao_spec": CNAO_MOD_DEFAULT_CA_RB_EXPECTED,
                },
                marks=pytest.mark.polarion("CNV-6700"),
                id="Test_Modify_HCO_CR_CertConfig_ca_renewBefore",
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            HCO_CR_CERT_CONFIG_KEY: {
                                HCO_CR_CERT_CONFIG_SERVER_KEY: {
                                    HCO_CR_CERT_CONFIG_DURATION_KEY: CERTC_DEFAULT_24H,
                                },
                            }
                        }
                    },
                },
                {
                    "hco_spec": {
                        "expected": HCO_MOD_DEFAULT_SER_DUR,
                        "base_path": HCO_CR_CERT_CONFIG_KEY,
                    },
                    "kubevirt_spec": {
                        "expected": KV_MOD_DEFAULT_SER_DUR,
                        "base_path": KUBEVIRT_CR_CERT_CONFIG_KEY,
                    },
                    "cdi_spec": HCO_MOD_DEFAULT_SER_DUR,
                    "cnao_spec": CNAO_MOD_DEFAULT_SER_DUR_EXPECTED,
                },
                marks=pytest.mark.polarion("CNV-6701"),
                id="Test_Modify_HCO_CR_CertConfig_server_duration",
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            HCO_CR_CERT_CONFIG_KEY: {
                                HCO_CR_CERT_CONFIG_SERVER_KEY: {
                                    HCO_CR_CERT_CONFIG_RENEW_BEFORE_KEY: CERTC_DEFAULT_12H,
                                },
                            }
                        }
                    },
                },
                {
                    "hco_spec": {
                        "expected": HCO_MOD_DEFAULT_SER_RB,
                        "base_path": HCO_CR_CERT_CONFIG_KEY,
                    },
                    "kubevirt_spec": {
                        "expected": KV_MOD_DEFAULT_SER_RB,
                        "base_path": KUBEVIRT_CR_CERT_CONFIG_KEY,
                    },
                    "cdi_spec": HCO_MOD_DEFAULT_SER_RB,
                    "cnao_spec": CNAO_MOD_DEFAULT_SER_RB_EXPECTED,
                },
                marks=pytest.mark.polarion("CNV-6702"),
                id="Test_Modify_HCO_CR_CertConfig_server_renewBefore",
            ),
            pytest.param(
                {"patch": {"spec": {LIVE_MIGRATION_CONFIG_KEY: EXPCT_LM_DEFAULTS}}},
                {
                    "hco_spec": {
                        "expected": EXPCT_LM_DEFAULTS,
                        "base_path": LIVE_MIGRATION_CONFIG_KEY,
                    },
                    "kubevirt_spec": {
                        "expected": EXPCT_LM_DEFAULTS,
                        "base_path": [
                            KUBEVIRT_CR_CONFIGURATION_KEY,
                            KUBEVIRT_CR_MIGRATIONS_KEY,
                        ],
                    },
                    "cdi_spec": None,
                    "cnao_spec": None,
                },
                marks=pytest.mark.polarion("CNV-6703"),
                id="Test_Modify_HCO_CR_liveMigrationConfig",
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            LIVE_MIGRATION_CONFIG_KEY: {
                                COMPLETION_TIMEOUT_PER_GIB_KEY: LM_COMPLETIONTIMEOUTPERGIB_DEFAULT,
                            }
                        }
                    }
                },
                {
                    "hco_spec": {
                        "expected": LM_CUST_DEFAULT_C,
                        "base_path": LIVE_MIGRATION_CONFIG_KEY,
                    },
                    "kubevirt_spec": {
                        "expected": LM_CUST_DEFAULT_C,
                        "base_path": [
                            KUBEVIRT_CR_CONFIGURATION_KEY,
                            KUBEVIRT_CR_MIGRATIONS_KEY,
                        ],
                    },
                    "cdi_spec": None,
                    "cnao_spec": None,
                },
                marks=pytest.mark.polarion("CNV-6705"),
                id="Test_Modify_HCO_CR_liveMigrationConfig_completionTimeoutPerGiB",
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            LIVE_MIGRATION_CONFIG_KEY: {
                                PARALLEL_MIGRATIONS_PER_CLUSTER_KEY: LM_PARALLELMIGRATIONSPERCLUSTER_DEFAULT,
                            }
                        }
                    }
                },
                {
                    "hco_spec": {
                        "expected": LM_CUST_DEFAULT_PM,
                        "base_path": LIVE_MIGRATION_CONFIG_KEY,
                    },
                    "kubevirt_spec": {
                        "expected": LM_CUST_DEFAULT_PM,
                        "base_path": [
                            KUBEVIRT_CR_CONFIGURATION_KEY,
                            KUBEVIRT_CR_MIGRATIONS_KEY,
                        ],
                    },
                    "cdi_spec": None,
                    "cnao_spec": None,
                },
                marks=pytest.mark.polarion("CNV-6706"),
                id="Test_Modify_HCO_CR_liveMigrationConfig_parallelMigrationsPerCluster",
            ),
            pytest.param(
                {"patch": {"spec": {LIVE_MIGRATION_CONFIG_KEY: LM_PO_DEFAULT}}},
                {
                    "hco_spec": {
                        "expected": LM_CUST_DEFAULT_PO,
                        "base_path": LIVE_MIGRATION_CONFIG_KEY,
                    },
                    "kubevirt_spec": {
                        "expected": LM_CUST_DEFAULT_PO,
                        "base_path": [
                            KUBEVIRT_CR_CONFIGURATION_KEY,
                            KUBEVIRT_CR_MIGRATIONS_KEY,
                        ],
                    },
                    "cdi_spec": None,
                    "cnao_spec": None,
                },
                marks=pytest.mark.polarion("CNV-6707"),
                id="Test_Modify_HCO_CR_liveMigrationConfig_parallelOutboundMigrationsPerNode",
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            LIVE_MIGRATION_CONFIG_KEY: {
                                PROGRESS_TIMEOUT_KEY: LM_PROGRESSTIMEOUT_DEFAULT,
                            }
                        }
                    }
                },
                {
                    "hco_spec": {
                        "expected": LM_CUST_DEFAULT_PT,
                        "base_path": LIVE_MIGRATION_CONFIG_KEY,
                    },
                    "kubevirt_spec": {
                        "expected": LM_CUST_DEFAULT_PT,
                        "base_path": [
                            KUBEVIRT_CR_CONFIGURATION_KEY,
                            KUBEVIRT_CR_MIGRATIONS_KEY,
                        ],
                    },
                    "cdi_spec": None,
                    "cnao_spec": None,
                },
                marks=pytest.mark.polarion("CNV-6708"),
                id="Test_Modify_HCO_CR_liveMigrationConfig_progressTimeout",
            ),
        ],
        indirect=["updated_hco_cr"],
    )
    @pytest.mark.s390x
    def test_modify_hco_cr(
        self,
        hco_cr_custom_values,
        admin_client,
        hco_namespace,
        updated_hco_cr,
        expected,
    ):
        """
        Tests validates that on modifying single or multiple spec fields of HCO CR with default values,
        appropriate values are found in associated spec fields for networkaddonsconfig, cdi, kubevirt and
        hyperconverged kinds
        """
        if expected["hco_spec"]:
            wait_for_spec_change(
                expected=expected["hco_spec"]["expected"],
                get_spec_func=lambda: get_hco_spec(admin_client=admin_client, hco_namespace=hco_namespace),
                base_path=expected["hco_spec"]["base_path"],
            )
        if expected["kubevirt_spec"]:
            wait_for_spec_change(
                expected=expected["kubevirt_spec"]["expected"],
                get_spec_func=lambda: get_hyperconverged_kubevirt(
                    admin_client=admin_client, hco_namespace=hco_namespace
                )
                .instance.to_dict()
                .get("spec"),
                base_path=expected["kubevirt_spec"]["base_path"],
            )
        if expected["cdi_spec"]:
            wait_for_spec_change(
                expected=expected["cdi_spec"],
                get_spec_func=lambda: get_hyperconverged_cdi(admin_client=admin_client).instance.to_dict().get("spec"),
                base_path=[CDI_CR_CERT_CONFIG_KEY],
            )
        if expected["cnao_spec"]:
            wait_for_spec_change(
                expected=expected["cnao_spec"],
                get_spec_func=lambda: get_network_addon_config(admin_client=admin_client)
                .instance.to_dict()
                .get("spec"),
                base_path=[CNAO_CR_CERT_CONFIG_KEY],
            )

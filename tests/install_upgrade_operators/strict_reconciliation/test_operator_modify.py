import pytest

from tests.install_upgrade_operators.constants import (
    HCO_CR_CERT_CONFIG_CA_KEY,
    HCO_CR_CERT_CONFIG_DURATION_KEY,
    HCO_CR_CERT_CONFIG_KEY,
    HCO_CR_CERT_CONFIG_RENEW_BEFORE_KEY,
    HCO_CR_CERT_CONFIG_SERVER_KEY,
)
from tests.install_upgrade_operators.strict_reconciliation.constants import (
    CNAO_CR_CERT_CONFIG_CA_DURATION_KEY,
    CNAO_CR_CERT_CONFIG_KEY_CA_RENEW_BEFORE_KEY,
    CNAO_CR_CERT_CONFIG_KEY_SERVER_RENEW_BEFORE_KEY,
    CNAO_CR_CERT_CONFIG_SERVER_DURATION_KEY,
    COMPLETION_TIMEOUT_PER_GIB_KEY,
    COMPLETION_TIMEOUT_PER_GIB_VALUE,
    KUBEVIRT_CR_CERT_CONFIG_SELF_SIGNED_KEY,
    PARALLEL_MIGRATIONS_PER_CLUSTER_KEY,
    PARALLEL_MIGRATIONS_PER_CLUSTER_VALUE,
    PARALLEL_OUTBOUND_MIGRATIONS_PER_NODE_KEY,
    PARALLEL_OUTBOUND_MIGRATIONS_PN_VALUE,
    PROGRESS_TIMEOUT_KEY,
    PROGRESS_TIMEOUT_VALUE,
)
from tests.install_upgrade_operators.strict_reconciliation.utils import verify_specs

pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno, pytest.mark.arm64]


class TestOperatorsModify:
    @pytest.mark.parametrize(
        "updated_cdi_cr",
        [
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            HCO_CR_CERT_CONFIG_KEY: {
                                HCO_CR_CERT_CONFIG_CA_KEY: {
                                    HCO_CR_CERT_CONFIG_DURATION_KEY: "9h",
                                    HCO_CR_CERT_CONFIG_RENEW_BEFORE_KEY: "2h",
                                },
                                HCO_CR_CERT_CONFIG_SERVER_KEY: {
                                    HCO_CR_CERT_CONFIG_DURATION_KEY: "3h",
                                    HCO_CR_CERT_CONFIG_RENEW_BEFORE_KEY: "1h",
                                },
                            }
                        }
                    }
                },
                marks=pytest.mark.polarion("CNV-6312"),
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            HCO_CR_CERT_CONFIG_KEY: {
                                HCO_CR_CERT_CONFIG_CA_KEY: {
                                    HCO_CR_CERT_CONFIG_DURATION_KEY: "99h",
                                }
                            }
                        }
                    }
                },
                marks=pytest.mark.polarion("CNV-6315"),
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            HCO_CR_CERT_CONFIG_KEY: {
                                HCO_CR_CERT_CONFIG_CA_KEY: {
                                    HCO_CR_CERT_CONFIG_RENEW_BEFORE_KEY: "2h",
                                },
                            }
                        }
                    }
                },
                marks=pytest.mark.polarion("CNV-6318"),
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            HCO_CR_CERT_CONFIG_KEY: {
                                HCO_CR_CERT_CONFIG_SERVER_KEY: {
                                    HCO_CR_CERT_CONFIG_DURATION_KEY: "33h",
                                },
                            }
                        }
                    }
                },
                marks=pytest.mark.polarion("CNV-6321"),
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            HCO_CR_CERT_CONFIG_KEY: {
                                HCO_CR_CERT_CONFIG_SERVER_KEY: {
                                    HCO_CR_CERT_CONFIG_RENEW_BEFORE_KEY: "1h",
                                },
                            }
                        }
                    }
                },
                marks=pytest.mark.polarion("CNV-6324"),
            ),
        ],
        indirect=True,
    )
    @pytest.mark.s390x
    def test_modify_cdi_cr(
        self,
        admin_client,
        hco_namespace,
        hco_spec,
        kubevirt_hyperconverged_spec_scope_function,
        cdi_spec,
        cnao_spec,
        updated_cdi_cr,
    ):
        assert verify_specs(
            admin_client,
            hco_namespace,
            hco_spec,
            kubevirt_hyperconverged_spec_scope_function,
            cdi_spec,
            cnao_spec,
        )

    @pytest.mark.parametrize(
        "updated_kubevirt_cr",
        [
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "certificateRotateStrategy": {
                                KUBEVIRT_CR_CERT_CONFIG_SELF_SIGNED_KEY: {
                                    HCO_CR_CERT_CONFIG_CA_KEY: {
                                        HCO_CR_CERT_CONFIG_DURATION_KEY: "9h",
                                        HCO_CR_CERT_CONFIG_RENEW_BEFORE_KEY: "2h",
                                    },
                                    HCO_CR_CERT_CONFIG_SERVER_KEY: {
                                        HCO_CR_CERT_CONFIG_DURATION_KEY: "3h",
                                        HCO_CR_CERT_CONFIG_RENEW_BEFORE_KEY: "1h",
                                    },
                                }
                            }
                        }
                    }
                },
                marks=pytest.mark.polarion("CNV-6313"),
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "certificateRotateStrategy": {
                                KUBEVIRT_CR_CERT_CONFIG_SELF_SIGNED_KEY: {
                                    HCO_CR_CERT_CONFIG_CA_KEY: {
                                        HCO_CR_CERT_CONFIG_DURATION_KEY: "99h",
                                    }
                                }
                            }
                        }
                    }
                },
                marks=pytest.mark.polarion("CNV-6316"),
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "certificateRotateStrategy": {
                                KUBEVIRT_CR_CERT_CONFIG_SELF_SIGNED_KEY: {
                                    HCO_CR_CERT_CONFIG_CA_KEY: {
                                        HCO_CR_CERT_CONFIG_RENEW_BEFORE_KEY: "2h",
                                    },
                                }
                            }
                        }
                    }
                },
                marks=pytest.mark.polarion("CNV-6319"),
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "certificateRotateStrategy": {
                                KUBEVIRT_CR_CERT_CONFIG_SELF_SIGNED_KEY: {
                                    HCO_CR_CERT_CONFIG_SERVER_KEY: {
                                        HCO_CR_CERT_CONFIG_DURATION_KEY: "33h",
                                    },
                                }
                            }
                        }
                    }
                },
                marks=pytest.mark.polarion("CNV-6322"),
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "certificateRotateStrategy": {
                                KUBEVIRT_CR_CERT_CONFIG_SELF_SIGNED_KEY: {
                                    HCO_CR_CERT_CONFIG_SERVER_KEY: {
                                        HCO_CR_CERT_CONFIG_RENEW_BEFORE_KEY: "1h",
                                    },
                                }
                            }
                        }
                    }
                },
                marks=pytest.mark.polarion("CNV-6325"),
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "configuration": {
                                "migrations": {
                                    COMPLETION_TIMEOUT_PER_GIB_KEY: COMPLETION_TIMEOUT_PER_GIB_VALUE,
                                    PARALLEL_MIGRATIONS_PER_CLUSTER_KEY: PARALLEL_MIGRATIONS_PER_CLUSTER_VALUE,
                                    PARALLEL_OUTBOUND_MIGRATIONS_PER_NODE_KEY: PARALLEL_OUTBOUND_MIGRATIONS_PN_VALUE,
                                    PROGRESS_TIMEOUT_KEY: PROGRESS_TIMEOUT_VALUE,
                                }
                            }
                        }
                    }
                },
                marks=pytest.mark.polarion("CNV-6328"),
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "configuration": {
                                "migrations": {
                                    COMPLETION_TIMEOUT_PER_GIB_KEY: COMPLETION_TIMEOUT_PER_GIB_VALUE,
                                }
                            }
                        }
                    }
                },
                marks=pytest.mark.polarion("CNV-6334"),
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "configuration": {
                                "migrations": {
                                    PARALLEL_MIGRATIONS_PER_CLUSTER_KEY: PARALLEL_MIGRATIONS_PER_CLUSTER_VALUE,
                                }
                            }
                        }
                    }
                },
                marks=pytest.mark.polarion("CNV-6337"),
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "configuration": {
                                "migrations": {
                                    PARALLEL_OUTBOUND_MIGRATIONS_PER_NODE_KEY: PARALLEL_OUTBOUND_MIGRATIONS_PN_VALUE,
                                }
                            }
                        }
                    }
                },
                marks=pytest.mark.polarion("CNV-6340"),
            ),
            pytest.param(
                {"patch": {"spec": {"configuration": {"migrations": {PROGRESS_TIMEOUT_KEY: PROGRESS_TIMEOUT_VALUE}}}}},
                marks=pytest.mark.polarion("CNV-6343"),
            ),
        ],
        indirect=True,
    )
    @pytest.mark.s390x
    def test_modify_kubevirt_cr(
        self,
        admin_client,
        hco_namespace,
        hco_spec,
        kubevirt_hyperconverged_spec_scope_function,
        cdi_spec,
        cnao_spec,
        updated_kubevirt_cr,
    ):
        assert verify_specs(
            admin_client,
            hco_namespace,
            hco_spec,
            kubevirt_hyperconverged_spec_scope_function,
            cdi_spec,
            cnao_spec,
        )

    @pytest.mark.parametrize(
        "updated_cnao_cr",
        [
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "selfSignConfiguration": {
                                CNAO_CR_CERT_CONFIG_KEY_CA_RENEW_BEFORE_KEY: "2h",
                                CNAO_CR_CERT_CONFIG_CA_DURATION_KEY: "9h",
                                CNAO_CR_CERT_CONFIG_KEY_SERVER_RENEW_BEFORE_KEY: "2h",
                                CNAO_CR_CERT_CONFIG_SERVER_DURATION_KEY: "3h",
                            }
                        }
                    }
                },
                marks=pytest.mark.polarion("CNV-6314"),
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "selfSignConfiguration": {
                                CNAO_CR_CERT_CONFIG_CA_DURATION_KEY: "99h",
                            }
                        }
                    }
                },
                marks=pytest.mark.polarion("CNV-6317"),
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "selfSignConfiguration": {
                                CNAO_CR_CERT_CONFIG_KEY_CA_RENEW_BEFORE_KEY: "2h",
                            }
                        }
                    }
                },
                marks=pytest.mark.polarion("CNV-6320"),
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "selfSignConfiguration": {
                                CNAO_CR_CERT_CONFIG_SERVER_DURATION_KEY: "33h",
                            }
                        }
                    }
                },
                marks=pytest.mark.polarion("CNV-6323"),
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "selfSignConfiguration": {
                                CNAO_CR_CERT_CONFIG_KEY_SERVER_RENEW_BEFORE_KEY: "1h",
                            }
                        }
                    }
                },
                marks=pytest.mark.polarion("CNV-6326"),
            ),
        ],
        indirect=True,
    )
    @pytest.mark.s390x
    def test_modify_cnao_cr(
        self,
        admin_client,
        hco_namespace,
        hco_spec,
        kubevirt_hyperconverged_spec_scope_function,
        cdi_spec,
        cnao_spec,
        updated_cnao_cr,
    ):
        assert verify_specs(
            admin_client,
            hco_namespace,
            hco_spec,
            kubevirt_hyperconverged_spec_scope_function,
            cdi_spec,
            cnao_spec,
        )

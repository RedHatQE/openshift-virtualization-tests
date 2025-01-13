import logging

import pytest
from ocp_resources.cdi import CDI
from ocp_resources.network_addons_config import NetworkAddonsConfig
from ocp_resources.secret import Secret
from ocp_resources.ssp import SSP

from tests.install_upgrade_operators.cert_renewal.constants import (
    SSP_OPERATOR_SERVICE_CERT,
    VIRT_TEMPLATE_VALIDATOR_CERTS,
)
from tests.install_upgrade_operators.cert_renewal.utils import (
    SECRETS,
    get_certificates_validity_period_and_checkend_result,
)
from tests.install_upgrade_operators.constants import (
    HCO_CR_CERT_CONFIG_CA_KEY,
    HCO_CR_CERT_CONFIG_KEY,
    HCO_CR_CERT_CONFIG_SERVER_KEY,
)
from utilities.constants import TIMEOUT_1MIN, TIMEOUT_11MIN
from utilities.hco import ResourceEditorValidateHCOReconcile, wait_for_hco_conditions
from utilities.infra import is_jira_open

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="class")
def hyperconverged_resource_certconfig_change(
    request, admin_client, hco_namespace, hyperconverged_resource_scope_class
):
    """
    Update HCO CR with certconfig
    """
    target_certconfig_stanza = {
        HCO_CR_CERT_CONFIG_CA_KEY: {**request.param},
        HCO_CR_CERT_CONFIG_SERVER_KEY: {**request.param},
    }
    LOGGER.info("Modifying certconfig in HCO CR")
    with ResourceEditorValidateHCOReconcile(
        patches={hyperconverged_resource_scope_class: {"spec": {HCO_CR_CERT_CONFIG_KEY: target_certconfig_stanza}}},
        list_resource_reconcile=[CDI, NetworkAddonsConfig, SSP],
        wait_for_reconcile_post_update=True,
    ):
        yield


@pytest.fixture()
def initial_certificates_dates(admin_client, hco_namespace, tmpdir, secrets_with_non_closed_bugs):
    LOGGER.info("Delete secrets so that the cert-manager will create new ones with the updated certConfig")
    for secret in SECRETS:
        Secret(name=secret, namespace=hco_namespace.name).delete(wait=True)

    for secret in SECRETS:
        Secret(name=secret, namespace=hco_namespace.name).wait(timeout=TIMEOUT_1MIN)

    wait_for_hco_conditions(
        admin_client=admin_client,
        hco_namespace=hco_namespace,
        list_dependent_crs_to_check=[SSP],
    )

    LOGGER.info("Retrieve the certificates dates")
    return get_certificates_validity_period_and_checkend_result(
        hco_namespace_name=hco_namespace.name,
        tmpdir=tmpdir,
        secrets_to_skip=secrets_with_non_closed_bugs,
        seconds=TIMEOUT_11MIN,
    )


@pytest.fixture(scope="module")
def secrets_with_non_closed_bugs():
    jira_component_name_dict = {
        "CNV-15131": SSP_OPERATOR_SERVICE_CERT,
        "CNV-14625": VIRT_TEMPLATE_VALIDATOR_CERTS,
    }
    return tuple(
        component_name
        for bug_id, component_name in jira_component_name_dict.items()
        if is_jira_open(
            jira_id=bug_id,
        )
    )

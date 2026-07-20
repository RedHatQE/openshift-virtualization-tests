import logging

import pytest

from tests.install_upgrade_operators.product_install.constants import (
    HCO_NOT_INSTALLED_ALERT,
)
from tests.install_upgrade_operators.product_install.utils import (
    validate_hpp_installation,
)
from utilities.constants import (
    KUBEVIRT_HCO_HYPERCONVERGED_CR_EXISTS,
    PENDING_STR,
    TIMEOUT_10MIN,
)
from utilities.hco import wait_for_hco_conditions
from utilities.infra import wait_for_pods_running
from utilities.monitoring import (
    validate_alerts,
    wait_for_firing_alert_clean_up,
    wait_for_gauge_metrics_value,
)
from utilities.storage import (
    verify_boot_sources_reimported,
)

CNV_INSTALLATION_TEST = "test_cnv_installation"
CNV_ALERT_CLEANUP_TEST = "test_cnv_installation_alert_cleanup"
LOGGER = logging.getLogger(__name__)

pytestmark = [pytest.mark.install, pytest.mark.s390x]


@pytest.mark.polarion("CNV-10072")
@pytest.mark.order(before=CNV_INSTALLATION_TEST)
def test_cnv_installation_without_hco_cr_alert(
    prometheus,
    cnv_version_to_install_info,
    installed_openshift_virtualization,
    alert_dictionary_hco_not_installed,
):
    validate_alerts(
        prometheus=prometheus,
        alert_dict=alert_dictionary_hco_not_installed,
        state=PENDING_STR,
        timeout=TIMEOUT_10MIN,
    )


@pytest.mark.polarion("CNV-10437")
@pytest.mark.order(before=CNV_INSTALLATION_TEST)
def test_cnv_installation_without_hco_cr_metrics(
    prometheus,
):
    wait_for_gauge_metrics_value(
        prometheus=prometheus,
        query=KUBEVIRT_HCO_HYPERCONVERGED_CR_EXISTS,
        expected_value="0",
    )


@pytest.mark.polarion("CNV-9311")
@pytest.mark.dependency(name=CNV_INSTALLATION_TEST)
def test_cnv_installation(admin_client, cnv_version_to_install_info, created_cnv_namespace, created_hco_cr):
    wait_for_hco_conditions(admin_client=admin_client, hco_namespace=created_cnv_namespace)
    current_hco_version = created_hco_cr.instance.status.versions[0]["version"]
    version_to_install = cnv_version_to_install_info["version"]
    assert version_to_install == current_hco_version, (
        f"Expected hco version: {version_to_install}. Actual version: {current_hco_version}"
    )
    wait_for_pods_running(admin_client=admin_client, namespace=created_cnv_namespace)


@pytest.mark.polarion("CNV-10074")
@pytest.mark.order(after=CNV_INSTALLATION_TEST)
@pytest.mark.dependency(name=CNV_ALERT_CLEANUP_TEST)
def test_cnv_installation_alert_cleanup(prometheus):
    wait_for_firing_alert_clean_up(prometheus=prometheus, alert_name=HCO_NOT_INSTALLED_ALERT)


@pytest.mark.polarion("CNV-12453")
@pytest.mark.order(after=CNV_INSTALLATION_TEST)
# Dependency: CNV must be installed before storage class configuration can be verified
@pytest.mark.dependency(depends=[CNV_INSTALLATION_TEST])
@pytest.mark.usefixtures("updated_default_storage_class_from_config")
def test_default_storage_class_set(admin_client, golden_images_namespace):
    assert verify_boot_sources_reimported(
        admin_client=admin_client, namespace=golden_images_namespace.name, consecutive_checks_count=3
    ), "Failed to re-import boot sources"


@pytest.mark.polarion("CNV-10528")
def test_install_hpp(admin_client, schedulable_nodes, installed_hpp, created_cnv_namespace):
    validate_hpp_installation(
        admin_client=admin_client,
        schedulable_nodes=schedulable_nodes,
        cnv_namespace=created_cnv_namespace,
    )

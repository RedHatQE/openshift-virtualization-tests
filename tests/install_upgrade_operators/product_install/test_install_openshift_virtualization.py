import logging

import pytest

from tests.install_upgrade_operators.product_install.constants import (
    CLUSTER_RESOURCE_ALLOWLIST,
    HCO_NOT_INSTALLED_ALERT,
    IGNORE_KIND,
    IGNORE_NAMESPACE,
    NAMESPACED_IGNORE_KINDS,
    NAMESPACED_RESOURCE_ALLOWLIST,
)
from tests.install_upgrade_operators.product_install.utils import (
    validate_hpp_installation,
)
from utilities.constants import (
    KUBEVIRT_HCO_HYPERCONVERGED_CR_EXISTS,
    PENDING_STR,
    TIMEOUT_10MIN,
)
from utilities.exceptions import ResourceMismatch
from utilities.hco import wait_for_hco_conditions
from utilities.infra import wait_for_pods_running
from utilities.monitoring import (
    validate_alerts,
    wait_for_firing_alert_clean_up,
    wait_for_gauge_metrics_value,
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
    before_installation_all_resources,
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


@pytest.mark.polarion("CNV-10076")
@pytest.mark.order(after=CNV_ALERT_CLEANUP_TEST)
@pytest.mark.dependency(
    name="test_cnv_resources_installed_cluster_scoped",
    depends=[CNV_INSTALLATION_TEST],
)
def test_cnv_resources_installed_cluster_scoped(
    before_installation_all_resources,
    after_installation_all_resources,
):
    mismatch_cluster_scoped = []
    for kind in after_installation_all_resources["cluster-scoped"]:
        if kind in IGNORE_KIND:
            continue

        diff_values = [
            value
            for value in list(
                set(after_installation_all_resources["cluster-scoped"][kind])
                - (set(before_installation_all_resources["cluster-scoped"].get(kind, [])))
            )
            if "kubevirt.io" not in value
        ]
        allowlisted_values = CLUSTER_RESOURCE_ALLOWLIST.get(kind, [])
        if allowlisted_values and diff_values:
            LOGGER.info(f"Expected allowlisted values for kind: {kind}: {allowlisted_values}")
            LOGGER.warning(
                f"Current difference in resources between before and after installation of cnv: {diff_values}"
            )
            diff_values = [value for value in diff_values if not value.startswith(tuple(allowlisted_values))]
            if diff_values:
                LOGGER.warning(f"After removing allowlisted resources, the diff is: {diff_values}")
                mismatch_cluster_scoped.append({kind: diff_values})
    if mismatch_cluster_scoped:
        LOGGER.error(f"Mismatched cluster resources: {mismatch_cluster_scoped}")
        raise ResourceMismatch(f"Unexpected cluster resources found post cnv installation: {mismatch_cluster_scoped}")


@pytest.mark.order(after=CNV_ALERT_CLEANUP_TEST)
@pytest.mark.dependency(
    depends=[CNV_INSTALLATION_TEST],
)
@pytest.mark.polarion("CNV-10075")
def test_cnv_resources_installed_namespace_scoped(
    before_installation_all_resources,
    after_installation_all_resources,
):
    namespaced_resource_before = before_installation_all_resources["namespaced"]
    namespaced_resource_after = after_installation_all_resources["namespaced"]
    mismatch_namespaced = {}
    for namespace in namespaced_resource_after:
        if namespace in IGNORE_NAMESPACE:
            continue
        LOGGER.info(f"Checking resources in {namespace}")
        mismatch_namespaced[namespace] = {}
        allowlisted_kinds = NAMESPACED_RESOURCE_ALLOWLIST.get(namespace, [])

        for kind in after_installation_all_resources["namespaced"][namespace]:
            if kind in NAMESPACED_IGNORE_KINDS:
                continue
            allowlisted_values = []
            if allowlisted_kinds:
                LOGGER.info(f"Currently allowlisted resources: {allowlisted_kinds}")
                allowlisted_values = allowlisted_kinds.get(kind, [])
            diff_value_ns = [
                value
                for value in list(
                    set(namespaced_resource_after[namespace].get(kind, []))
                    - (set(namespaced_resource_before.get(namespace, {}).get(kind, [])))
                )
                if "kubevirt.io" not in value
            ]

            if allowlisted_values and diff_value_ns:
                LOGGER.warning(
                    f"For namespace: {namespace}, kind: {kind} difference in before and after installation "
                    f"resource(s): {diff_value_ns}"
                )
                diff_value_ns = [value for value in diff_value_ns if not value.startswith(tuple(allowlisted_values))]
            if diff_value_ns:
                LOGGER.warning(f"After removing allowlisted elements from the difference, mismatch is: {diff_value_ns}")
                mismatch_namespaced[namespace][kind] = diff_value_ns
    mismatch_namespaced = {key: value for key, value in mismatch_namespaced.items() if value}
    if mismatch_namespaced:
        LOGGER.error(f"Mismatched namespaced resources: {mismatch_namespaced}")
        raise ResourceMismatch(f"Unexpected namespaced resources found post cnv installation: {mismatch_namespaced}")


@pytest.mark.polarion("CNV-10528")
def test_install_hpp(admin_client, schedulable_nodes, installed_hpp, created_cnv_namespace):
    validate_hpp_installation(
        admin_client=admin_client,
        schedulable_nodes=schedulable_nodes,
        cnv_namespace=created_cnv_namespace,
    )

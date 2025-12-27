import logging
import os
import re

import pytest
from ocp_resources.cluster_version import ClusterVersion
from ocp_resources.resource import ResourceEditor
from ocp_utilities.monitoring import Prometheus
from packaging.version import Version
from pytest_testconfig import py_config

from tests.install_upgrade_operators.constants import WORKLOAD_UPDATE_STRATEGY_KEY_NAME, WORKLOADUPDATEMETHODS
from tests.install_upgrade_operators.product_upgrade.utils import (
    approve_cnv_upgrade_install_plan,
    extract_ocp_version_from_ocp_image,
    get_alerts_fired_during_upgrade,
    get_all_cnv_alerts,
    get_iib_images_of_cnv_versions,
    get_nodes_labels,
    get_nodes_taints,
    get_shortest_upgrade_path,
    perform_cnv_upgrade,
    run_ocp_upgrade_command,
    set_workload_update_methods_hco,
    update_mcp_paused_spec,
    verify_upgrade_ocp,
    wait_for_hco_csv_creation,
    wait_for_hco_upgrade,
    wait_for_odf_update,
    wait_for_pods_replacement_by_type,
)
from tests.install_upgrade_operators.utils import wait_for_operator_condition
from utilities.constants import EUS, HCO_CATALOG_SOURCE, HOTFIX_STR, TIMEOUT_10MIN, NamespacesNames
from utilities.data_collector import (
    get_data_collector_base_directory,
)
from utilities.infra import (
    generate_openshift_pull_secret_file,
    get_csv_by_name,
    get_prometheus_k8s_token,
    get_related_images_name_and_version,
    get_subscription,
)
from utilities.operator import (
    apply_icsp_idms,
    get_generated_icsp_idms,
    get_machine_config_pool_by_name,
    get_machine_config_pools_conditions,
    update_image_in_catalog_source,
    update_subscription_source,
    wait_for_mcp_update_completion,
)
from utilities.pytest_utils import exit_pytest_execution
from utilities.virt import get_oc_image_info

LOGGER = logging.getLogger(__name__)
POD_STR_NOT_MANAGED_BY_HCO = "hostpath-"
EUS_ERROR_CODE = 98


@pytest.fixture(scope="session")
def cnv_image_name(cnv_image_url):
    # Image name format example osbs: registry-proxy.engineering.redhat.com/rh-osbs/iib:45131
    match = re.match(".*/(.*):", cnv_image_url)
    assert match, (
        f"Can not find CNV image name from: {cnv_image_url} "
        f"(example: registry-proxy.engineering.redhat.com/rh-osbs/iib:45131 should find 'iib')"
    )
    return match.group(1)


@pytest.fixture(scope="session")
def nodes_taints_before_upgrade(nodes):
    return get_nodes_taints(nodes=nodes)


@pytest.fixture(scope="session")
def cnv_upgrade(pytestconfig):
    return pytestconfig.option.upgrade == "cnv"


@pytest.fixture(scope="session")
def nodes_labels_before_upgrade(nodes, cnv_upgrade):
    return get_nodes_labels(nodes=nodes, cnv_upgrade=cnv_upgrade)


@pytest.fixture()
def updated_image_content_source_policy(
    admin_client,
    nodes,
    tmpdir_factory,
    active_machine_config_pools,
    machine_config_pools_conditions,
    cnv_image_url,
    cnv_image_name,
    cnv_source,
    cnv_target_version,
    cnv_registry_source,
    pull_secret_directory,
    generated_pulled_secret,
    is_disconnected_cluster,
    is_idms_cluster,
):
    """
    Creates a new ImageContentSourcePolicy file with a given CNV image and applies it to the cluster.
    """
    if is_disconnected_cluster:
        LOGGER.warning("Skip applying ICSP/IDMS in a disconnected setup.")
        return

    if cnv_source == HOTFIX_STR:
        LOGGER.info("ICSP updates skipped as upgrading using production source/upgrade to hotfix")
        return
    file_path = get_generated_icsp_idms(
        image_url=cnv_image_url,
        registry_source=cnv_registry_source["source_map"],
        generated_pulled_secret=generated_pulled_secret,
        pull_secret_directory=pull_secret_directory,
        is_idms_cluster=is_idms_cluster,
    )
    apply_icsp_idms(
        file_paths=[file_path],
        machine_config_pools=active_machine_config_pools,
        mcp_conditions=machine_config_pools_conditions,
        nodes=nodes,
        is_idms_file=is_idms_cluster,
        delete_file=True,
    )


@pytest.fixture()
def updated_custom_hco_catalog_source_image(
    admin_client,
    cnv_image_url,
    is_disconnected_cluster,
):
    image_url = cnv_image_url
    if is_disconnected_cluster:
        image_info = get_oc_image_info(image=image_url, pull_secret=generate_openshift_pull_secret_file())
        assert image_info, f"For cnv image {image_url}, image information not found"
        image_url = f"{cnv_image_url.split('iib:')[0]}iib@{image_info['digest']}"
    LOGGER.info(f"Deployment is not from production; updating HCO catalog source image to {image_url}.")
    update_image_in_catalog_source(
        dyn_client=admin_client,
        image=image_url,
        catalog_source_name=HCO_CATALOG_SOURCE,
        cr_name=py_config["hco_cr_name"],
    )


@pytest.fixture()
def updated_cnv_subscription_source(cnv_subscription_scope_session, cnv_registry_source):
    LOGGER.info("Update subscription source.")
    update_subscription_source(
        subscription=cnv_subscription_scope_session,
        subscription_source=cnv_registry_source["cnv_subscription_source"],
        subscription_channel=py_config["cnv_subscription_channel"],
    )


@pytest.fixture()
def approved_cnv_upgrade_install_plan(admin_client, hco_namespace, hco_target_csv_name, is_production_source):
    approve_cnv_upgrade_install_plan(
        dyn_client=admin_client,
        hco_namespace=hco_namespace.name,
        hco_target_csv_name=hco_target_csv_name,
        is_production_source=is_production_source,
    )


@pytest.fixture()
def created_target_hco_csv(admin_client, hco_namespace, hco_target_csv_name):
    return wait_for_hco_csv_creation(
        admin_client=admin_client, hco_namespace=hco_namespace.name, hco_target_csv_name=hco_target_csv_name
    )


@pytest.fixture()
def related_images_from_target_csv(created_target_hco_csv):
    LOGGER.info(f"Get all related images names and versions from target CSV {created_target_hco_csv.name}")
    return get_related_images_name_and_version(csv=created_target_hco_csv)


@pytest.fixture()
def target_operator_pods_images(created_target_hco_csv):
    # Operator pods are taken from csv deployment as their names under relatedImages do not exact-match
    # the pods' prefixes
    return {
        deploy.name: deploy.spec.template.spec.containers[0].image
        for deploy in created_target_hco_csv.instance.spec.install.spec.deployments
    }


@pytest.fixture()
def target_images_for_pods_not_managed_by_hco(related_images_from_target_csv):
    LOGGER.info("Get hpp target images names and versions.")
    return [image for image in related_images_from_target_csv.values() if POD_STR_NOT_MANAGED_BY_HCO in image]


@pytest.fixture()
def started_cnv_upgrade(admin_client, hco_namespace, hco_target_csv_name):
    wait_for_operator_condition(
        dyn_client=admin_client,
        hco_namespace=hco_namespace.name,
        name=hco_target_csv_name,
        upgradable=False,
    )


@pytest.fixture()
def upgraded_cnv(
    admin_client,
    hco_namespace,
    cnv_target_version,
    hco_target_csv_name,
    created_target_hco_csv,
    target_operator_pods_images,
    target_images_for_pods_not_managed_by_hco,
):
    LOGGER.info(f"Wait for csv: {created_target_hco_csv.name} to be in SUCCEEDED state.")
    created_target_hco_csv.wait_for_status(
        status=created_target_hco_csv.Status.SUCCEEDED,
        timeout=TIMEOUT_10MIN,
        stop_status="fakestatus",  # to bypass intermittent FAILED status that is not permanent.
    )
    LOGGER.info(f"Wait for operator condition {hco_target_csv_name} to reach upgradable: True")
    wait_for_operator_condition(
        dyn_client=admin_client,
        hco_namespace=hco_namespace.name,
        name=hco_target_csv_name,
        upgradable=True,
    )

    LOGGER.info("Wait for all openshift-virtualization operator pod replacement:")
    wait_for_pods_replacement_by_type(
        dyn_client=admin_client,
        hco_namespace=hco_namespace.name,
        pod_list=target_operator_pods_images.keys(),
        related_images=target_operator_pods_images.values(),
    )
    LOGGER.info("Wait for non-hco managed pods to be replaced:")
    wait_for_pods_replacement_by_type(
        dyn_client=admin_client,
        hco_namespace=hco_namespace.name,
        pod_list=[POD_STR_NOT_MANAGED_BY_HCO],
        related_images=target_images_for_pods_not_managed_by_hco,
    )
    wait_for_hco_upgrade(
        dyn_client=admin_client,
        hco_namespace=hco_namespace,
        cnv_target_version=cnv_target_version,
    )


@pytest.fixture(scope="session")
def ocp_image_url(pytestconfig):
    return pytestconfig.option.ocp_image


@pytest.fixture(scope="session")
def cluster_version(admin_client):
    cluster_version = ClusterVersion(name="version")
    if cluster_version.exists:
        return cluster_version


@pytest.fixture()
def updated_ocp_upgrade_channel(extracted_ocp_version_from_image_url, cluster_version):
    expected_cluster_version = Version(version=extracted_ocp_version_from_image_url.split("-")[0])
    expected_channel = f"stable-{expected_cluster_version.major}.{expected_cluster_version.minor}"
    if cluster_version.instance.spec.channel != expected_channel:
        LOGGER.info(f"Updating cluster version channel to {expected_channel}")
        ResourceEditor({cluster_version: {"spec": {"channel": expected_channel}}}).update()


@pytest.fixture()
def triggered_ocp_upgrade(ocp_image_url, is_disconnected_cluster):
    image_url = ocp_image_url
    if is_disconnected_cluster:
        image_info = get_oc_image_info(image=ocp_image_url, pull_secret=generate_openshift_pull_secret_file())
        assert image_info, f"For ocp image {ocp_image_url}, image information not found"
        image_url = f"quay.io/openshift-release-dev/ocp-release@{image_info['digest']}"
    LOGGER.info(f"Executing OCP upgrade command to image {ocp_image_url}")
    run_ocp_upgrade_command(ocp_image_url=image_url)


@pytest.fixture(scope="session")
def extracted_ocp_version_from_image_url(ocp_image_url):
    return extract_ocp_version_from_ocp_image(ocp_image_url=ocp_image_url)


@pytest.fixture(scope="session")
def alert_dir():
    return os.path.join(get_data_collector_base_directory(), "alert_information")


@pytest.fixture()
def prometheus_scope_function():
    return Prometheus(verify_ssl=False, bearer_token=get_prometheus_k8s_token())


@pytest.fixture(scope="session")
def fired_alerts_before_upgrade(pytestconfig, prometheus, alert_dir):
    return get_all_cnv_alerts(
        prometheus=prometheus,
        file_name=f"before_{pytestconfig.option.upgrade}_upgrade_alerts.json",
        base_directory=alert_dir,
    )


@pytest.fixture()
def fired_alerts_during_upgrade(fired_alerts_before_upgrade, alert_dir, prometheus_scope_function):
    return get_alerts_fired_during_upgrade(
        prometheus=prometheus_scope_function,
        before_upgrade_alerts=fired_alerts_before_upgrade,
        base_directory=alert_dir,
    )


@pytest.fixture(scope="session")
def eus_cnv_upgrade_path(admin_client, eus_target_cnv_version):
    if eus_target_cnv_version is None:
        exit_pytest_execution(
            log_message="EUS upgrade can not be performed from non-eus version",
            return_code=EUS_ERROR_CODE,
            filename="eus_upgrade_failure.txt",
            admin_client=admin_client,
        )
    # Get the shortest path to the target (EUS) version
    upgrade_path_to_target_version = get_shortest_upgrade_path(target_version=eus_target_cnv_version)
    # Get the shortest path to the intermediate (non-EUS) version
    upgrade_path_to_intermediate_version = get_shortest_upgrade_path(
        target_version=upgrade_path_to_target_version["startVersion"]
    )
    # Return a dictionary with the versions and images for the EUS-to-EUS upgrade
    upgrade_path = {
        "non-eus": get_iib_images_of_cnv_versions(versions=upgrade_path_to_intermediate_version["versions"]),
        EUS: get_iib_images_of_cnv_versions(versions=upgrade_path_to_target_version["versions"], errata_status="false"),
    }
    LOGGER.info(f"Upgrade path for EUS-to-EUS upgrade: {upgrade_path}")
    return upgrade_path


@pytest.fixture(scope="session")
def default_workload_update_strategy(hyperconverged_resource_scope_session):
    return hyperconverged_resource_scope_session.instance.to_dict()["spec"][WORKLOAD_UPDATE_STRATEGY_KEY_NAME]


@pytest.fixture()
def eus_paused_worker_mcp(
    workers,
    worker_machine_config_pools,
    worker_machine_config_pools_conditions,
    eus_applied_all_icsp,
):
    LOGGER.info("Pausing worker MCP updates before starting EUS upgrade.")
    update_mcp_paused_spec(mcp=worker_machine_config_pools)


@pytest.fixture()
def eus_unpaused_worker_mcp(
    workers,
    worker_machine_config_pools,
    worker_machine_config_pools_conditions,
):
    LOGGER.info("Un-pause worker mcp and wait for worker mcp to complete update.")
    update_mcp_paused_spec(mcp=worker_machine_config_pools, paused=False)

    wait_for_mcp_update_completion(
        machine_config_pools_list=worker_machine_config_pools,
        initial_mcp_conditions=worker_machine_config_pools_conditions,
        nodes=workers,
    )


@pytest.fixture()
def eus_paused_workload_update(
    hyperconverged_resource_scope_module,
    default_workload_update_strategy,
):
    LOGGER.info("Pause workload updates in HCO")
    set_workload_update_methods_hco(
        hyperconverged_resource=hyperconverged_resource_scope_module,
        workload_update_method=[],
    )


@pytest.fixture()
def eus_unpaused_workload_update(
    hyperconverged_resource_scope_module,
    default_workload_update_strategy,
):
    LOGGER.info(f"Reset hco.spec.{WORKLOAD_UPDATE_STRATEGY_KEY_NAME}.")
    set_workload_update_methods_hco(
        hyperconverged_resource=hyperconverged_resource_scope_module,
        workload_update_method=default_workload_update_strategy[WORKLOADUPDATEMETHODS],
    )


@pytest.fixture(scope="module")
def created_eus_icsps(
    pull_secret_directory,
    generated_pulled_secret,
    cnv_registry_source,
    eus_cnv_upgrade_path,
    is_idms_cluster,
):
    icsp_files = []
    for entry in eus_cnv_upgrade_path:
        for version in eus_cnv_upgrade_path[entry]:
            icsp_file = get_generated_icsp_idms(
                image_url=eus_cnv_upgrade_path[entry][version],
                registry_source=cnv_registry_source["source_map"],
                generated_pulled_secret=generated_pulled_secret,
                pull_secret_directory=pull_secret_directory,
                is_idms_cluster=is_idms_cluster,
                cnv_version=version,
            )
            icsp_files.append(icsp_file)
    LOGGER.info(f"EUS ICSP Files created: {icsp_files}")
    return icsp_files


@pytest.fixture(scope="module")
def eus_applied_all_icsp(
    nodes,
    generated_pulled_secret,
    machine_config_pools,
    machine_config_pools_conditions_scope_module,
    created_eus_icsps,
    is_idms_cluster,
):
    apply_icsp_idms(
        file_paths=created_eus_icsps,
        machine_config_pools=machine_config_pools,
        mcp_conditions=machine_config_pools_conditions_scope_module,
        nodes=nodes,
        is_idms_file=is_idms_cluster,
    )


@pytest.fixture(scope="session")
def active_machine_config_pools(machine_config_pools):
    return [
        machine_config_pool
        for machine_config_pool in machine_config_pools
        if machine_config_pool.instance.status.machineCount > 0
    ]


@pytest.fixture()
def machine_config_pools_conditions(active_machine_config_pools):
    return get_machine_config_pools_conditions(machine_config_pools=active_machine_config_pools)


@pytest.fixture(scope="session")
def master_machine_config_pools():
    return [get_machine_config_pool_by_name(mcp_name="master")]


@pytest.fixture(scope="session")
def worker_machine_config_pools():
    return [get_machine_config_pool_by_name(mcp_name="worker")]


@pytest.fixture(scope="module")
def worker_machine_config_pools_conditions(worker_machine_config_pools):
    return get_machine_config_pools_conditions(machine_config_pools=worker_machine_config_pools)


@pytest.fixture(scope="session")
def eus_ocp_image_urls(pytestconfig):
    return pytestconfig.option.eus_ocp_images.split(",")


@pytest.fixture(scope="session")
def ocp_version_eus_to_non_eus_from_image_url(eus_ocp_image_urls):
    return extract_ocp_version_from_ocp_image(ocp_image_url=eus_ocp_image_urls[0])


@pytest.fixture(scope="session")
def ocp_version_non_eus_to_eus_from_image_url(eus_ocp_image_urls):
    return extract_ocp_version_from_ocp_image(ocp_image_url=eus_ocp_image_urls[1])


@pytest.fixture()
def triggered_source_eus_to_non_eus_ocp_upgrade(eus_ocp_image_urls):
    run_ocp_upgrade_command(ocp_image_url=eus_ocp_image_urls[0])


@pytest.fixture()
def triggered_non_eus_to_target_eus_ocp_upgrade(eus_ocp_image_urls):
    run_ocp_upgrade_command(ocp_image_url=eus_ocp_image_urls[1])


@pytest.fixture()
def source_eus_to_non_eus_ocp_upgraded(
    admin_client,
    masters,
    master_machine_config_pools,
    ocp_version_eus_to_non_eus_from_image_url,
    triggered_source_eus_to_non_eus_ocp_upgrade,
):
    verify_upgrade_ocp(
        admin_client=admin_client,
        machine_config_pools_list=master_machine_config_pools,
        target_ocp_version=ocp_version_eus_to_non_eus_from_image_url,
        initial_mcp_conditions=get_machine_config_pools_conditions(machine_config_pools=master_machine_config_pools),
        nodes=masters,
    )


@pytest.fixture()
def non_eus_to_target_eus_ocp_upgraded(
    admin_client,
    masters,
    master_machine_config_pools,
    ocp_version_non_eus_to_eus_from_image_url,
    triggered_non_eus_to_target_eus_ocp_upgrade,
):
    verify_upgrade_ocp(
        admin_client=admin_client,
        machine_config_pools_list=master_machine_config_pools,
        target_ocp_version=ocp_version_non_eus_to_eus_from_image_url,
        initial_mcp_conditions=get_machine_config_pools_conditions(machine_config_pools=master_machine_config_pools),
        nodes=masters,
    )


@pytest.fixture()
def source_eus_to_non_eus_cnv_upgraded(
    admin_client,
    hco_namespace,
    eus_cnv_upgrade_path,
    hyperconverged_resource_scope_function,
    updated_cnv_subscription_source,
):
    for version, cnv_image in sorted(eus_cnv_upgrade_path["non-eus"].items()):
        LOGGER.info(f"Cnv upgrade to version {version} using image: {cnv_image}")
        perform_cnv_upgrade(
            admin_client=admin_client,
            cnv_image_url=cnv_image,
            cr_name=hyperconverged_resource_scope_function.name,
            hco_namespace=hco_namespace,
            cnv_target_version=version.lstrip("v"),
        )
    LOGGER.info("Successfully performed cnv upgrades from source EUS to non-EUS version.")


@pytest.fixture()
def non_eus_to_target_eus_cnv_upgraded(
    admin_client,
    hco_namespace,
    eus_cnv_upgrade_path,
    hyperconverged_resource_scope_function,
    updated_cnv_subscription_source,
):
    version, cnv_image = next(iter(eus_cnv_upgrade_path[EUS].items()))
    LOGGER.info(f"Cnv upgrade to version {version} using image: {cnv_image}")
    perform_cnv_upgrade(
        admin_client=admin_client,
        cnv_image_url=cnv_image,
        cr_name=hyperconverged_resource_scope_function.name,
        hco_namespace=hco_namespace,
        cnv_target_version=version.lstrip("v"),
    )


@pytest.fixture()
def eus_created_target_hco_csv(admin_client, hco_namespace, eus_hco_target_csv_name):
    return get_csv_by_name(
        csv_name=eus_hco_target_csv_name,
        admin_client=admin_client,
        namespace=hco_namespace.name,
    )


@pytest.fixture()
def odf_version(openshift_current_version):
    ocp_version = Version(version=openshift_current_version.split("-")[0])
    return f"{ocp_version.major}.{ocp_version.minor + 1}"


@pytest.fixture()
def odf_subscription(admin_client):
    return get_subscription(
        admin_client=admin_client,
        namespace=NamespacesNames.OPENSHIFT_STORAGE,
        subscription_name="ocs-subscription",
    )


@pytest.fixture()
def updated_odf_subscription_source(odf_subscription, odf_version):
    LOGGER.info(f"Update subscription {odf_subscription.name} source channel: {odf_version}")
    ResourceEditor(
        patches={
            odf_subscription: {
                "spec": {
                    "channel": f"stable-{odf_version}",
                }
            }
        }
    ).update()


@pytest.fixture()
def upgraded_odf(
    odf_version,
    updated_odf_subscription_source,
):
    wait_for_odf_update(target_version=odf_version)

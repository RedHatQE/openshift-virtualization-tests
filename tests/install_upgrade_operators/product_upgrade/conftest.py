import logging
import os
import re

import packaging.version
import pytest
from ocp_resources.cluster_version import ClusterVersion
from ocp_resources.machine_config_pool import MachineConfigPool
from ocp_resources.resource import ResourceEditor
from ocp_utilities.monitoring import Prometheus
from pyhelper_utils.shell import run_command
from pytest_testconfig import py_config
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.install_upgrade_operators.product_upgrade.utils import (
    approve_cnv_upgrade_install_plan,
    get_alerts_fired_during_upgrade,
    get_all_cnv_alerts,
    get_nodes_labels,
    get_nodes_taints,
    wait_for_hco_upgrade,
    wait_for_pods_replacement_by_type,
)
from tests.install_upgrade_operators.utils import wait_for_operator_condition
from utilities.constants import HCO_CATALOG_SOURCE, HOTFIX_STR, TIMEOUT_10MIN
from utilities.data_collector import (
    get_data_collector_base_directory,
)
from utilities.infra import (
    generate_openshift_pull_secret_file,
    get_csv_by_name,
    get_prometheus_k8s_token,
    get_related_images_name_and_version,
)
from utilities.operator import (
    create_icsp_idms_command,
    create_icsp_idms_from_file,
    delete_existing_icsp_idms,
    generate_icsp_idms_file,
    update_image_in_catalog_source,
    update_subscription_source,
    wait_for_mcp_update_completion,
)
from utilities.virt import get_oc_image_info

LOGGER = logging.getLogger(__name__)
POD_STR_NOT_MANAGED_BY_HCO = "hostpath-"


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
    machine_config_pools,
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
    source_url = cnv_registry_source["source_map"]
    cnv_mirror_cmd = create_icsp_idms_command(
        image=cnv_image_url,
        source_url=source_url,
        folder_name=pull_secret_directory,
        pull_secret=generated_pulled_secret,
    )
    file_path = generate_icsp_idms_file(
        folder_name=pull_secret_directory,
        command=cnv_mirror_cmd,
        cnv_version=cnv_target_version,
        is_idms_file=is_idms_cluster,
    )

    LOGGER.info("pausing MCP updates while modifying ICSP/IDMS")
    with ResourceEditor(
        patches={mcp: {"spec": {"paused": True}} for mcp in MachineConfigPool.get(dyn_client=admin_client)}
    ):
        # Due to the amount of annotations in ICSP/IDMS yaml, `oc apply` may fail. Existing ICSP/IDMS is deleted.
        LOGGER.info("Deleting existing ICSP/IDMS.")
        delete_existing_icsp_idms(name="iib", is_idms_file=is_idms_cluster)
        LOGGER.info("Creating new ICSP/IDMS.")
        create_icsp_idms_from_file(file_path=file_path)

    LOGGER.info("Wait for MCP update after ICSP/IDMS modification.")
    wait_for_mcp_update_completion(
        machine_config_pools_list=machine_config_pools,
        initial_mcp_conditions=machine_config_pools_conditions,
        nodes=nodes,
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
    )


@pytest.fixture()
def approved_cnv_upgrade_install_plan(admin_client, hco_namespace, hco_target_version, is_production_source):
    approve_cnv_upgrade_install_plan(
        dyn_client=admin_client,
        hco_namespace=hco_namespace.name,
        hco_target_version=hco_target_version,
        is_production_source=is_production_source,
    )


@pytest.fixture()
def created_target_hco_csv(admin_client, hco_namespace, hco_target_version):
    LOGGER.info(f"Wait for new CSV {hco_target_version} to be created")
    csv_sampler = TimeoutSampler(
        wait_timeout=TIMEOUT_10MIN,
        sleep=1,
        func=get_csv_by_name,
        admin_client=admin_client,
        namespace=hco_namespace.name,
        csv_name=hco_target_version,
    )
    try:
        for csv in csv_sampler:
            if csv:
                return csv
    except TimeoutExpiredError:
        LOGGER.error(f"timeout waiting for target cluster service version: {hco_target_version}")
        raise


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
def started_cnv_upgrade(admin_client, hco_namespace, hco_target_version):
    wait_for_operator_condition(
        dyn_client=admin_client,
        hco_namespace=hco_namespace.name,
        name=hco_target_version,
        upgradable=False,
    )


@pytest.fixture()
def upgraded_cnv(
    admin_client,
    hco_namespace,
    cnv_target_version,
    hco_target_version,
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
    LOGGER.info(f"Wait for operator condition {hco_target_version} to reach upgradable: True")
    wait_for_operator_condition(
        dyn_client=admin_client,
        hco_namespace=hco_namespace.name,
        name=hco_target_version,
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
    expected_cluster_version = packaging.version.parse(version=extracted_ocp_version_from_image_url.split("-")[0])
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
    rc, out, err = run_command(
        command=[
            "oc",
            "adm",
            "upgrade",
            "--force=true",
            "--allow-explicit-upgrade",
            "--allow-upgrade-with-warnings",
            "--to-image",
            image_url,
        ],
        verify_stderr=False,
        check=False,
    )
    assert rc, f"OCP upgrade command failed. out: {out}. err: {err}"


@pytest.fixture(scope="session")
def extracted_ocp_version_from_image_url(ocp_image_url):
    """
    Extract the OCP version from the OCP URL input.

    Expected inputs / output examples:
        quay.io/openshift-release-dev/ocp-release:4.10.9-x86_64 -> 4.10.9
        quay.io/openshift-release-dev/ocp-release:4.10.0-rc.6-x86_64 -> 4.10.0-rc.6
        registry.ci.openshift.org/ocp/release:4.11.0-0.nightly-2022-04-01-172551 -> 4.11.0-0.nightly-2022-04-01-172551
        registry.ci.openshift.org/ocp/release:4.11.0-0.ci-2022-04-06-165430 -> 4.11.0-0.ci-2022-04-06-165430
    """
    ocp_version_match = re.search(r"release:(.*?)(?:-x86_64$|$)", ocp_image_url)
    ocp_version = ocp_version_match.group(1) if ocp_version_match else None
    assert ocp_version, f"Cannot extract OCP version. OCP image url: {ocp_image_url} is invalid"
    LOGGER.info(f"OCP version {ocp_version} extracted from ocp image: {ocp_version}")
    return ocp_version


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

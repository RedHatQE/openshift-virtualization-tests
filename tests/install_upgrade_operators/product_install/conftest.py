import logging
import os

import bitmath
import pytest
from ocp_resources.cluster_service_version import ClusterServiceVersion
from ocp_resources.hostpath_provisioner import HostPathProvisioner
from ocp_resources.hyperconverged import HyperConverged
from ocp_resources.installplan import InstallPlan
from ocp_resources.persistent_volume import PersistentVolume
from ocp_resources.resource import get_client
from pytest_testconfig import py_config

from tests.install_upgrade_operators.product_install.constants import (
    HCO_NOT_INSTALLED_ALERT,
    OPENSHIFT_VIRTUALIZATION,
)
from tests.install_upgrade_operators.product_install.utils import get_all_resources
from utilities.constants import (
    BREW_REGISTERY_SOURCE,
    CRITICAL_STR,
    HCO_CATALOG_SOURCE,
    HCO_SUBSCRIPTION,
    ICSP_FILE,
    IDMS_FILE,
    INFO_STR,
    PENDING_STR,
    PRODUCTION_CATALOG_SOURCE,
    TIMEOUT_5MIN,
    TIMEOUT_10MIN,
    StorageClassNames,
)
from utilities.data_collector import (
    get_data_collector_base_directory,
)
from utilities.infra import (
    create_ns,
    get_cluster_platform,
    get_cnv_info_by_iib,
    get_csv_by_name,
    get_latest_stable_released_z_stream_info,
)
from utilities.operator import (
    create_catalog_source,
    create_icsp_idms_from_file,
    create_operator,
    create_operator_group,
    create_subscription,
    generate_icsp_idms_file,
    get_hco_csv_name_by_version,
    get_install_plan_from_subscription,
    get_mcp_updating_transition_times,
    wait_for_catalogsource_ready,
    wait_for_mcp_update_end,
    wait_for_mcp_update_start,
)
from utilities.storage import (
    HppCsiStorageClass,
    HPPWithStoragePool,
    create_hpp_storage_class,
)

INSTALLATION_VERSION_MISMATCH = "98"
LOCAL_BLOCK_HPP = "local-block-hpp"
LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def installation_data_dir():
    return os.path.join(get_data_collector_base_directory(), "resource_information")


@pytest.fixture(scope="session")
def before_installation_all_resources(installation_data_dir):
    return get_all_resources(file_name="before_installation", base_directory=installation_data_dir)


@pytest.fixture(scope="module")
def after_installation_all_resources(installation_data_dir):
    return get_all_resources(file_name="after_installation", base_directory=installation_data_dir)


@pytest.fixture(scope="module")
def hyperconverged_directory(tmpdir_factory, is_production_source):
    if is_production_source:
        yield
    else:
        yield tmpdir_factory.mktemp(f"{OPENSHIFT_VIRTUALIZATION}-folder")


@pytest.fixture(scope="module")
def generated_hyperconverged_icsp_idms(
    is_production_source,
    is_idms_cluster,
    hyperconverged_directory,
    generated_pulled_secret,
    cnv_image_url,
):
    if is_production_source:
        LOGGER.info("This is installation from production source, icsp update is not needed.")
        return
    folder_name = f"{hyperconverged_directory}/{OPENSHIFT_VIRTUALIZATION}-manifest"
    LOGGER.info(f"Create CNV ICSP/IDMS file {ICSP_FILE}/{IDMS_FILE} in {hyperconverged_directory}")
    mirror_cmd = (
        f"oc adm catalog mirror {cnv_image_url} {BREW_REGISTERY_SOURCE} --manifests-only"
        f" --to-manifests {folder_name} --registry-config={generated_pulled_secret}"
    )

    return generate_icsp_idms_file(folder_name=folder_name, command=mirror_cmd, is_idms_file=is_idms_cluster)


@pytest.fixture(scope="module")
def updated_icsp_hyperconverged(
    is_production_source,
    generated_hyperconverged_icsp_idms,
    machine_config_pools,
    machine_config_pools_conditions_scope_module,
):
    initial_updating_transition_times = get_mcp_updating_transition_times(
        mcp_conditions=machine_config_pools_conditions_scope_module
    )
    if is_production_source:
        LOGGER.info("This is installation from production source, icsp/idms update is not needed.")
        return
    create_icsp_idms_from_file(file_path=generated_hyperconverged_icsp_idms)
    LOGGER.info("Wait for MCP update after ICSP/IDMS modification.")
    wait_for_mcp_update_start(
        machine_config_pools_list=machine_config_pools,
        initial_transition_times=initial_updating_transition_times,
    )
    wait_for_mcp_update_end(machine_config_pools_list=machine_config_pools)


@pytest.fixture(scope="module")
def hyperconverged_catalog_source(admin_client, is_production_source, cnv_image_url):
    if is_production_source:
        LOGGER.info("No creation or update to catalogsource is needed for installation from production source.")
        return
    LOGGER.info(f"Creating catalog source {HCO_CATALOG_SOURCE}")
    catalog_source = create_catalog_source(
        catalog_name=HCO_CATALOG_SOURCE,
        image=cnv_image_url,
    )
    wait_for_catalogsource_ready(
        admin_client=admin_client,
        catalog_name=HCO_CATALOG_SOURCE,
    )
    return catalog_source


@pytest.fixture(scope="module")
def created_cnv_namespace(admin_client):
    cnv_namespace_name = py_config["hco_namespace"]
    yield from create_ns(
        admin_client=admin_client,
        name=cnv_namespace_name,
        teardown=False,
        labels={
            "pod-security.kubernetes.io/enforce": "privileged",
            "security.openshift.io/scc.podSecurityLabelSync": "false",
        },
    )


@pytest.fixture(scope="module")
def created_cnv_operator_group(created_cnv_namespace):
    cnv_namespace_name = created_cnv_namespace.name
    return create_operator_group(
        namespace_name=cnv_namespace_name,
        operator_group_name="openshift-cnv-group",
        target_namespaces=[cnv_namespace_name],
    )


@pytest.fixture(scope="module")
def installed_cnv_subscription(
    is_production_source,
    hyperconverged_catalog_source,
    created_cnv_namespace,
    cnv_version_to_install_info,
):
    return create_subscription(
        subscription_name=HCO_SUBSCRIPTION,
        package_name=py_config["hco_cr_name"],
        namespace_name=created_cnv_namespace.name,
        catalogsource_name=PRODUCTION_CATALOG_SOURCE if is_production_source else hyperconverged_catalog_source.name,
        channel_name=cnv_version_to_install_info["channel"],
    )


@pytest.fixture(scope="module")
def updated_subscription_with_install_plan(installed_cnv_subscription):
    return get_install_plan_from_subscription(subscription=installed_cnv_subscription)


@pytest.fixture(scope="module")
def cnv_install_plan_installed(
    admin_client,
    created_cnv_namespace,
    updated_subscription_with_install_plan,
    cnv_version_to_install_info,
):
    install_plan = InstallPlan(
        client=admin_client,
        name=updated_subscription_with_install_plan,
        namespace=created_cnv_namespace.name,
    )
    install_plan.wait_for_status(status=install_plan.Status.COMPLETE, timeout=TIMEOUT_5MIN)
    csv = get_csv_by_name(
        csv_name=get_hco_csv_name_by_version(cnv_target_version=cnv_version_to_install_info["version"]),
        admin_client=admin_client,
        namespace=created_cnv_namespace.name,
    )
    csv.wait_for_status(status=ClusterServiceVersion.Status.SUCCEEDED, timeout=TIMEOUT_10MIN)


@pytest.fixture(scope="module")
def installed_openshift_virtualization(
    admin_client,
    disabled_default_sources_in_operatorhub_scope_module,
    updated_icsp_hyperconverged,
    hyperconverged_catalog_source,
    created_cnv_namespace,
    created_cnv_operator_group,
    installed_cnv_subscription,
    cnv_install_plan_installed,
):
    LOGGER.info("Installed Openshift Virtualization, without creating HCO CR.")
    yield


@pytest.fixture(scope="module")
def created_hco_cr(created_cnv_namespace, installed_openshift_virtualization):
    return create_operator(
        operator_class=HyperConverged,
        operator_name=py_config["hco_cr_name"],
        namespace_name=created_cnv_namespace.name,
    )


@pytest.fixture(scope="module")
def alert_dictionary_hco_not_installed():
    return {
        "alert_name": HCO_NOT_INSTALLED_ALERT,
        "labels": {
            "severity": INFO_STR,
            "operator_health_impact": CRITICAL_STR,
        },
        "state": PENDING_STR,
    }


@pytest.fixture(scope="module")
def cluster_backend_storage(admin_client):
    backend_storage = None
    cluster_platform = get_cluster_platform(admin_client=admin_client)
    if cluster_platform == "Azure":
        backend_storage = "managed-csi"
    elif cluster_platform == "AWS":
        backend_storage = "gp3-csi"
    elif cluster_platform == "OpenStack":
        backend_storage = LOCAL_BLOCK_HPP
    else:
        backend_storage = StorageClassNames.CEPH_RBD_VIRTUALIZATION
    return backend_storage


@pytest.fixture(scope="module")
def hpp_volume_size(cluster_backend_storage):
    hpp_volume_size = "70Gi"
    if cluster_backend_storage == LOCAL_BLOCK_HPP:
        persistent_volumes = PersistentVolume.get(
            dyn_client=get_client(),
            label_selector=f"storage.openshift.com/local-volume-owner-name={cluster_backend_storage}",
        )
        for persistent_volume in persistent_volumes:
            persistent_volume_size = persistent_volume.instance.spec.capacity.storage
            if bitmath.parse_string_unsafe(persistent_volume_size) < bitmath.parse_string_unsafe(hpp_volume_size):
                hpp_volume_size = persistent_volume_size
    return hpp_volume_size


@pytest.fixture(scope="module")
def installed_hpp(cluster_backend_storage, hpp_volume_size):
    LOGGER.info(f"Creating HPP CR using backend storage: {cluster_backend_storage} and storage size: {hpp_volume_size}")
    hpp_cr = HPPWithStoragePool(
        name=HostPathProvisioner.Name.HOSTPATH_PROVISIONER,
        backend_storage_class_name=cluster_backend_storage,
        volume_size=hpp_volume_size,
    )
    hpp_cr.deploy(wait=True)
    create_hpp_storage_class(
        storage_class_name=HppCsiStorageClass.Name.HOSTPATH_CSI_BASIC,
    )
    create_hpp_storage_class(
        storage_class_name=HppCsiStorageClass.Name.HOSTPATH_CSI_PVC_BLOCK,
    )


@pytest.fixture(scope="session")
def cnv_version_to_install_info(is_production_source, ocp_current_version, cnv_image_url):
    if is_production_source:
        latest_z_stream = get_latest_stable_released_z_stream_info(
            minor_version=f"v{ocp_current_version.major}.{ocp_current_version.minor}"
        )
        LOGGER.info(
            f"Using production catalog source for: {ocp_current_version},"
            f" CNV latest stable released version info: {latest_z_stream}"
        )
    else:
        latest_z_stream = get_cnv_info_by_iib(iib=cnv_image_url.split(":")[-1])
        LOGGER.info(f"Using iib image {cnv_image_url}: CNV version info associated: {latest_z_stream}")
    if not latest_z_stream:
        pytest.exit(reason="CNV version can't be determined for this run", returncode=INSTALLATION_VERSION_MISMATCH)
    return latest_z_stream

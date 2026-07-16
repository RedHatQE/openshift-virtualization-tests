import logging

import pytest
from ocp_resources.catalog_source import CatalogSource
from ocp_resources.cluster_service_version import ClusterServiceVersion
from ocp_resources.network_addons_config import NetworkAddonsConfig
from ocp_resources.pod import Pod
from packaging.version import parse
from pytest_testconfig import config as py_config

import utilities.hco
from utilities.constants.hco import FEATURE_GATES
from utilities.infra import (
    get_clusterversion,
    get_hyperconverged_resource,
    scale_deployment_replicas,
)
from utilities.virt import get_hyperconverged_kubevirt, get_kubevirt_hyperconverged_spec

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def installing_cnv(pytestconfig):
    return pytestconfig.option.install


@pytest.fixture(scope="session")
def hco_namespace(admin_client, installing_cnv):
    if not installing_cnv:
        return utilities.hco.get_hco_namespace(admin_client=admin_client, namespace=py_config["hco_namespace"])


@pytest.fixture()
def hyperconverged_resource_scope_function(admin_client, hco_namespace):
    return get_hyperconverged_resource(client=admin_client, hco_ns_name=hco_namespace.name)


@pytest.fixture(scope="class")
def hyperconverged_resource_scope_class(admin_client, hco_namespace):
    return get_hyperconverged_resource(client=admin_client, hco_ns_name=hco_namespace.name)


@pytest.fixture(scope="module")
def hyperconverged_resource_scope_module(admin_client, hco_namespace, installing_cnv):
    if not installing_cnv:
        return get_hyperconverged_resource(client=admin_client, hco_ns_name=hco_namespace.name)


@pytest.fixture(scope="package")
def hyperconverged_resource_scope_package(admin_client, hco_namespace, installing_cnv):
    if not installing_cnv:
        return get_hyperconverged_resource(client=admin_client, hco_ns_name=hco_namespace.name)


@pytest.fixture(scope="session")
def hyperconverged_resource_scope_session(admin_client, hco_namespace, installing_cnv):
    if not installing_cnv:
        return get_hyperconverged_resource(client=admin_client, hco_ns_name=hco_namespace.name)


@pytest.fixture()
def kubevirt_hyperconverged_spec_scope_function(admin_client, hco_namespace, installing_cnv):
    if not installing_cnv:
        return get_kubevirt_hyperconverged_spec(admin_client=admin_client, hco_namespace=hco_namespace)


@pytest.fixture(scope="module")
def kubevirt_hyperconverged_spec_scope_module(admin_client, hco_namespace):
    return get_kubevirt_hyperconverged_spec(admin_client=admin_client, hco_namespace=hco_namespace)


@pytest.fixture()
def kubevirt_config(kubevirt_hyperconverged_spec_scope_function):
    return kubevirt_hyperconverged_spec_scope_function["configuration"]


@pytest.fixture(scope="module")
def kubevirt_config_scope_module(kubevirt_hyperconverged_spec_scope_module):
    return kubevirt_hyperconverged_spec_scope_module["configuration"]


@pytest.fixture()
def kubevirt_feature_gates(kubevirt_config):
    return kubevirt_config["developerConfiguration"][FEATURE_GATES]


@pytest.fixture(scope="module")
def kubevirt_feature_gates_scope_module(kubevirt_config_scope_module):
    return kubevirt_config_scope_module["developerConfiguration"][FEATURE_GATES]


@pytest.fixture(scope="session")
def network_addons_config_scope_session(admin_client):
    nac = list(NetworkAddonsConfig.get(client=admin_client))
    assert nac, "There should be one NetworkAddonsConfig CR."
    return nac[0]


@pytest.fixture(scope="class")
def hyperconverged_with_node_placement(request, admin_client, hco_namespace, hyperconverged_resource_scope_class):
    """
    Update HCO CR with infrastructure and workloads spec.
    """
    infra_placement = request.param["infra"]
    workloads_placement = request.param["workloads"]

    LOGGER.info("Fetching HCO to save its initial node placement configuration ")
    initial_infra = hyperconverged_resource_scope_class.instance.to_dict()["spec"].get("infra", {})
    initial_workloads = hyperconverged_resource_scope_class.instance.to_dict()["spec"].get("workloads", {})
    yield utilities.hco.apply_np_changes(
        admin_client=admin_client,
        hco=hyperconverged_resource_scope_class,
        hco_namespace=hco_namespace,
        infra_placement=infra_placement,
        workloads_placement=workloads_placement,
    )
    LOGGER.info("Revert to initial HCO node placement configuration ")
    utilities.hco.apply_np_changes(
        admin_client=admin_client,
        hco=hyperconverged_resource_scope_class,
        hco_namespace=hco_namespace,
        infra_placement=initial_infra,
        workloads_placement=initial_workloads,
    )


@pytest.fixture(scope="module")
def cnv_pods(admin_client, hco_namespace):
    yield list(Pod.get(client=admin_client, namespace=hco_namespace.name))


@pytest.fixture()
def hco_spec(hyperconverged_resource_scope_function):
    return hyperconverged_resource_scope_function.instance.to_dict()["spec"]


@pytest.fixture(scope="session")
def ocs_current_version(ocs_storage_class, admin_client):
    if ocs_storage_class:
        for csv in ClusterServiceVersion.get(
            client=admin_client,
            namespace="openshift-storage",
            label_selector=f"{ClusterServiceVersion.ApiGroup.OPERATORS_COREOS_COM}/ocs-operator.openshift-storage",
        ):
            return csv.instance.spec.version


@pytest.fixture(scope="session")
def openshift_current_version(admin_client):
    return get_clusterversion(client=admin_client).instance.status.history[0].version


@pytest.fixture(scope="session")
def ocp_current_version(openshift_current_version):
    return parse(version=openshift_current_version.split("-")[0])


@pytest.fixture(scope="session")
def hco_image(
    admin_client,
    installing_cnv,
    cnv_subscription_scope_session,
):
    if installing_cnv:
        return "CNV not yet installed."
    source_name = cnv_subscription_scope_session.instance.spec.source
    for cs in CatalogSource.get(
        client=admin_client,
        name=source_name,
        namespace=py_config["marketplace_namespace"],
    ):
        return cs.instance.spec.image


@pytest.fixture(scope="session")
def kubevirt_resource_scope_session(admin_client, installing_cnv, hco_namespace):
    if not installing_cnv:
        return get_hyperconverged_kubevirt(admin_client=admin_client, hco_namespace=hco_namespace)


@pytest.fixture(scope="package")
def must_gather_image_url(csv_scope_session):
    LOGGER.info(f"Csv name is : {csv_scope_session.name}")
    must_gather_image = [
        image["image"] for image in csv_scope_session.instance.spec.relatedImages if "must-gather" in image["name"]
    ]
    assert must_gather_image, (
        f"Csv: {csv_scope_session.name}, "
        f"related images: {csv_scope_session.instance.spec.relatedImages} "
        "does not have must gather image."
    )

    return must_gather_image[0]


@pytest.fixture()
def scaled_deployment(request, hco_namespace):
    with scale_deployment_replicas(
        deployment_name=request.param["deployment_name"],
        replica_count=request.param["replicas"],
        namespace=hco_namespace.name,
    ):
        yield


@pytest.fixture(scope="module")
def hco_status_related_objects(hyperconverged_resource_scope_module):
    """
    Gets HCO.status.relatedObjects list
    """
    return hyperconverged_resource_scope_module.instance.status.relatedObjects


@pytest.fixture(scope="module")
def machine_type_from_kubevirt_config(kubevirt_config_scope_module, nodes_cpu_architecture):
    """Extract machine type default from kubevirt CR."""
    return kubevirt_config_scope_module["architectureConfiguration"][nodes_cpu_architecture]["machineType"]


@pytest.fixture(scope="module")
def smbios_from_kubevirt_config(kubevirt_config_scope_module):
    """Extract SMBIOS default from kubevirt CR."""
    return kubevirt_config_scope_module["smbios"]

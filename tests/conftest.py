"""
Pytest conftest file for CNV tests
"""

import copy
import ipaddress
import logging
import os
import os.path
import re
import shlex
import shutil
import subprocess
import tempfile
from collections import defaultdict
from signal import SIGINT, SIGTERM, getsignal, signal
from subprocess import check_output

import bcrypt
import paramiko
import pytest
import requests
import yaml
from bs4 import BeautifulSoup
from kubernetes.dynamic.exceptions import ResourceNotFoundError
from ocp_resources.application_aware_resource_quota import ApplicationAwareResourceQuota
from ocp_resources.catalog_source import CatalogSource
from ocp_resources.cdi import CDI
from ocp_resources.cdi_config import CDIConfig
from ocp_resources.cluster_role import ClusterRole
from ocp_resources.cluster_service_version import ClusterServiceVersion
from ocp_resources.config_map import ConfigMap
from ocp_resources.daemonset import DaemonSet
from ocp_resources.data_source import DataSource
from ocp_resources.datavolume import DataVolume
from ocp_resources.deployment import Deployment
from ocp_resources.hostpath_provisioner import HostPathProvisioner
from ocp_resources.infrastructure import Infrastructure
from ocp_resources.installplan import InstallPlan
from ocp_resources.machine import Machine
from ocp_resources.migration_policy import MigrationPolicy
from ocp_resources.mutating_webhook_config import MutatingWebhookConfiguration
from ocp_resources.namespace import Namespace
from ocp_resources.network_addons_config import NetworkAddonsConfig
from ocp_resources.network_config_openshift_io import Network
from ocp_resources.node import Node
from ocp_resources.node_network_state import NodeNetworkState
from ocp_resources.oauth import OAuth
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_resources.pod import Pod
from ocp_resources.resource import Resource, ResourceEditor, get_client
from ocp_resources.role_binding import RoleBinding
from ocp_resources.secret import Secret
from ocp_resources.service_account import ServiceAccount
from ocp_resources.sriov_network_node_state import SriovNetworkNodeState
from ocp_resources.storage_class import StorageClass
from ocp_resources.virtual_machine_cluster_instancetype import (
    VirtualMachineClusterInstancetype,
)
from ocp_resources.virtual_machine_cluster_preference import (
    VirtualMachineClusterPreference,
)
from ocp_resources.virtual_machine_instance_migration import (
    VirtualMachineInstanceMigration,
)
from ocp_resources.virtual_machine_instancetype import VirtualMachineInstancetype
from ocp_resources.virtual_machine_preference import VirtualMachinePreference
from ocp_utilities.monitoring import Prometheus
from packaging.version import Version, parse
from pytest_testconfig import config as py_config
from timeout_sampler import TimeoutSampler

import utilities.hco
from tests.utils import download_and_extract_tar, update_cluster_cpu_model
from utilities.bitwarden import get_cnv_tests_secret_by_name
from utilities.constants import (
    AAQ_NAMESPACE_LABEL,
    AMD,
    ARM_64,
    ARQ_QUOTA_HARD_SPEC,
    AUDIT_LOGS_PATH,
    CDI_KUBEVIRT_HYPERCONVERGED,
    CLUSTER,
    CNV_TEST_SERVICE_ACCOUNT,
    CNV_VM_SSH_KEY_PATH,
    DEFAULT_HCO_CONDITIONS,
    ES_NONE,
    EXPECTED_CLUSTER_INSTANCE_TYPE_LABELS,
    FEATURE_GATES,
    HCO_SUBSCRIPTION,
    HOTFIX_STR,
    INSTANCE_TYPE_STR,
    INTEL,
    KMP_ENABLED_LABEL,
    KMP_VM_ASSIGNMENT_LABEL,
    KUBECONFIG,
    KUBEMACPOOL_MAC_CONTROLLER_MANAGER,
    KUBEMACPOOL_MAC_RANGE_CONFIG,
    LINUX_BRIDGE,
    MIGRATION_POLICY_VM_LABEL,
    NODE_ROLE_KUBERNETES_IO,
    NODE_TYPE_WORKER_LABEL,
    OC_ADM_LOGS_COMMAND,
    OS_FLAVOR_RHEL,
    OVS_BRIDGE,
    POD_SECURITY_NAMESPACE_LABELS,
    PREFERENCE_STR,
    RHEL9_PREFERENCE,
    RHEL9_STR,
    RHEL_WITH_INSTANCETYPE_AND_PREFERENCE,
    RHSM_SECRET_NAME,
    SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME,
    TIMEOUT_3MIN,
    TIMEOUT_4MIN,
    TIMEOUT_5MIN,
    U1_SMALL,
    UNPRIVILEGED_PASSWORD,
    UNPRIVILEGED_USER,
    UTILITY,
    VIRTCTL_CLI_DOWNLOADS,
    VIRTIO,
    WORKER_NODE_LABEL_KEY,
    WORKERS_TYPE,
    Images,
    NamespacesNames,
    StorageClassNames,
    UpgradeStreams,
)
from utilities.exceptions import MissingEnvironmentVariableError
from utilities.infra import (
    ClusterHosts,
    ExecCommandOnPod,
    add_scc_to_service_account,
    base64_encode_str,
    cluster_sanity,
    create_ns,
    download_file_from_cluster,
    exit_pytest_execution,
    find_common_cpu_model_for_live_migration,
    generate_namespace_name,
    generate_openshift_pull_secret_file,
    get_artifactory_header,
    get_cluster_platform,
    get_clusterversion,
    get_common_cpu_from_nodes,
    get_daemonset_yaml_file_with_image_hash,
    get_deployment_by_name,
    get_host_model_cpu,
    get_http_image_url,
    get_hyperconverged_resource,
    get_infrastructure,
    get_node_selector_dict,
    get_nodes_cpu_architecture,
    get_nodes_cpu_model,
    get_nodes_with_label,
    get_pods,
    get_subscription,
    get_utility_pods_from_nodes,
    label_nodes,
    label_project,
    login_with_user_password,
    name_prefix,
    run_virtctl_command,
    scale_deployment_replicas,
    wait_for_pods_deletion,
)
from utilities.network import (
    EthernetNetworkConfigurationPolicy,
    MacPool,
    SriovIfaceNotFound,
    cloud_init,
    create_sriov_node_policy,
    enable_hyperconverged_ovs_annotations,
    get_cluster_cni_type,
    network_device,
    network_nad,
    wait_for_node_marked_by_bridge,
    wait_for_ovs_daemonset_resource,
    wait_for_ovs_status,
)
from utilities.operator import (
    cluster_with_icsp,
    disable_default_sources_in_operatorhub,
    get_hco_csv_name_by_version,
    get_machine_config_pool_by_name,
)
from utilities.ssp import get_data_import_crons, get_ssp_resource
from utilities.storage import (
    create_or_update_data_source,
    data_volume,
    get_default_storage_class,
    get_storage_class_with_specified_volume_mode,
    get_test_artifact_server_url,
    is_snapshot_supported_by_sc,
    remove_default_storage_classes,
    sc_is_hpp_with_immediate_volume_binding,
    update_default_sc,
    verify_boot_sources_reimported,
)
from utilities.virt import (
    VirtualMachineForCloning,
    VirtualMachineForTests,
    create_vm_cloning_job,
    fedora_vm_body,
    get_all_virt_pods_with_running_status,
    get_base_templates_list,
    get_hyperconverged_kubevirt,
    get_hyperconverged_ovs_annotations,
    get_kubevirt_hyperconverged_spec,
    kubernetes_taint_exists,
    running_vm,
    start_and_fetch_processid_on_linux_vm,
    target_vm_from_cloning_job,
    vm_instance_from_template,
    wait_for_kv_stabilize,
    wait_for_windows_vm,
)

LOGGER = logging.getLogger(__name__)
HTTP_SECRET_NAME = "htpass-secret-for-cnv-tests"
HTPASSWD_PROVIDER_DICT = {
    "name": "htpasswd_provider",
    "mappingMethod": "claim",
    "type": "HTPasswd",
    "htpasswd": {"fileData": {"name": HTTP_SECRET_NAME}},
}
ACCESS_TOKEN = {
    "accessTokenMaxAgeSeconds": 604800,
    "accessTokenInactivityTimeout": None,
}
CNV_NOT_INSTALLED = "CNV not yet installed."
EUS_ERROR_CODE = 98
RWX_FS_STORAGE_CLASS_NAMES_LIST = [
    StorageClassNames.CEPHFS,
    StorageClassNames.TRIDENT_CSI_FSX,
    StorageClassNames.PORTWORX_CSI_DB_SHARED,
]


@pytest.fixture(scope="session")
def junitxml_polarion(record_testsuite_property):
    """
    Add polarion needed attributes to junit xml

    export as os environment:
    POLARION_CUSTOM_PLANNEDIN
    POLARION_TESTRUN_ID
    POLARION_TIER
    """
    record_testsuite_property("polarion-custom-isautomated", "True")
    record_testsuite_property("polarion-testrun-status-id", "inprogress")
    record_testsuite_property("polarion-custom-plannedin", os.getenv("POLARION_CUSTOM_PLANNEDIN"))
    record_testsuite_property("polarion-user-id", "cnvqe")
    record_testsuite_property("polarion-project-id", "CNV")
    record_testsuite_property("polarion-response-myproduct", "cnv-test-run")
    record_testsuite_property("polarion-testrun-id", os.getenv("POLARION_TESTRUN_ID"))
    record_testsuite_property("polarion-custom-env_tier", os.getenv("POLARION_TIER"))
    record_testsuite_property("polarion-custom-env_os", os.getenv("POLARION_OS"))


@pytest.fixture(scope="session")
def kubeconfig_export_path():
    return os.environ.get(KUBECONFIG)


@pytest.fixture(scope="session")
def exported_kubeconfig(unprivileged_secret, kubeconfig_export_path):
    if not unprivileged_secret:
        yield

    else:
        kube_config_path = os.path.join(os.path.expanduser("~"), ".kube/config")

        if os.path.isfile(kube_config_path) and kubeconfig_export_path:
            LOGGER.warning(
                f"Both {KUBECONFIG} {kubeconfig_export_path} and {kube_config_path} exist. "
                f"{kubeconfig_export_path} is used as kubeconfig source for this run."
            )

        orig_kubeconfig_file_path = kubeconfig_export_path or kube_config_path

        tests_kubeconfig_dir_path = tempfile.mkdtemp(suffix="-cnv-tests-kubeconfig")
        LOGGER.info(f"Setting {KUBECONFIG} dir for this run to point to: {tests_kubeconfig_dir_path}")

        kubeconfig_file_dest_path = os.path.join(tests_kubeconfig_dir_path, KUBECONFIG.lower())

        LOGGER.info(f"Copy {KUBECONFIG} to {kubeconfig_file_dest_path}")
        shutil.copyfile(src=orig_kubeconfig_file_path, dst=kubeconfig_file_dest_path)

        LOGGER.info(f"Set: {KUBECONFIG}={kubeconfig_file_dest_path}")
        os.environ[KUBECONFIG] = kubeconfig_file_dest_path

        yield kubeconfig_file_dest_path

        LOGGER.info(f"Remove: {kubeconfig_file_dest_path}")
        shutil.rmtree(tests_kubeconfig_dir_path, ignore_errors=True)

        if kubeconfig_export_path:
            LOGGER.info(f"Set: {KUBECONFIG}={kubeconfig_export_path}")
            os.environ[KUBECONFIG] = kubeconfig_export_path

        else:
            del os.environ[KUBECONFIG]


@pytest.fixture(scope="session")
def admin_client():
    """
    Get DynamicClient
    """
    return get_client()


@pytest.fixture(scope="session")
def unprivileged_secret(admin_client, skip_unprivileged_client):
    if skip_unprivileged_client:
        yield

    else:
        password = UNPRIVILEGED_PASSWORD.encode()
        enc_password = bcrypt.hashpw(password, bcrypt.gensalt(5, prefix=b"2a")).decode()
        crypto_credentials = f"{UNPRIVILEGED_USER}:{enc_password}"
        with Secret(
            name=HTTP_SECRET_NAME,
            namespace=NamespacesNames.OPENSHIFT_CONFIG,
            htpasswd=base64_encode_str(text=crypto_credentials),
        ) as secret:
            yield secret

        #  Wait for oauth-openshift deployment to update after removing htpass-secret
        _wait_for_oauth_openshift_deployment()


def _wait_for_oauth_openshift_deployment():
    dp = get_deployment_by_name(
        deployment_name="oauth-openshift",
        namespace_name="openshift-authentication",
    )

    _log = f"Wait for {dp.name} -> Type: Progressing -> Reason:"

    def _wait_sampler(_reason):
        sampler = TimeoutSampler(
            wait_timeout=TIMEOUT_4MIN,
            sleep=1,
            func=lambda: dp.instance.status.conditions,
        )
        for sample in sampler:
            for _spl in sample:
                if _spl.type == "Progressing" and _spl.reason == _reason:
                    return

    for reason in ("ReplicaSetUpdated", "NewReplicaSetAvailable"):
        LOGGER.info(f"{_log} {reason}")
        _wait_sampler(_reason=reason)


@pytest.fixture(scope="session")
def skip_unprivileged_client():
    # To disable unprivileged_client pass --tc=no_unprivileged_client:True to pytest commandline.
    return py_config.get("no_unprivileged_client")


@pytest.fixture(scope="session")
def identity_provider_config(skip_unprivileged_client, admin_client):
    if skip_unprivileged_client:
        return

    return OAuth(client=admin_client, name=CLUSTER)


@pytest.fixture(scope="session")
def identity_provider_with_htpasswd(skip_unprivileged_client, admin_client, identity_provider_config):
    if skip_unprivileged_client:
        yield
    else:
        identity_provider_config_editor = ResourceEditor(
            patches={
                identity_provider_config: {
                    "metadata": {"name": identity_provider_config.name},
                    "spec": {
                        "identityProviders": [HTPASSWD_PROVIDER_DICT],
                        "tokenConfig": ACCESS_TOKEN,
                    },
                }
            }
        )
        identity_provider_config_editor.update(backup_resources=True)
        _wait_for_oauth_openshift_deployment()
        yield
        identity_provider_config_editor.restore()


@pytest.fixture(scope="session")
def unprivileged_client(
    skip_unprivileged_client,
    admin_client,
    unprivileged_secret,
    identity_provider_with_htpasswd,
    exported_kubeconfig,
):
    """
    Provides none privilege API client
    """
    if skip_unprivileged_client:
        yield

    else:
        current_user = check_output("oc whoami", shell=True).decode().strip()  # Get the current admin account
        if login_with_user_password(
            api_address=admin_client.configuration.host,
            user=UNPRIVILEGED_USER,
            password=UNPRIVILEGED_PASSWORD,
        ):  # Login to an unprivileged account
            with open(exported_kubeconfig) as fd:
                kubeconfig_content = yaml.safe_load(fd)
            unprivileged_context = kubeconfig_content["current-context"]

            # Get back to an admin account
            login_with_user_password(
                api_address=admin_client.configuration.host,
                user=current_user.strip(),
            )
            yield get_client(config_file=exported_kubeconfig, context=unprivileged_context)

        else:
            yield admin_client


@pytest.fixture(scope="session")
def nodes(admin_client):
    yield list(Node.get(dyn_client=admin_client))


@pytest.fixture(scope="session")
def schedulable_nodes(nodes):
    """Get nodes marked as schedulable by kubevirt"""
    schedulable_label = "kubevirt.io/schedulable"
    yield [
        node
        for node in nodes
        if schedulable_label in node.labels.keys()
        and node.labels[schedulable_label] == "true"
        and not node.instance.spec.unschedulable
        and not kubernetes_taint_exists(node)
        and node.kubelet_ready
    ]


@pytest.fixture(scope="session")
def workers(nodes):
    return get_nodes_with_label(nodes=nodes, label=WORKER_NODE_LABEL_KEY)


@pytest.fixture(scope="session")
def control_plane_nodes(nodes):
    return get_nodes_with_label(nodes=nodes, label=f"{NODE_ROLE_KUBERNETES_IO}/control-plane")


@pytest.fixture(scope="session")
def cnv_tests_utilities_namespace(admin_client, installing_cnv):
    if installing_cnv:
        yield
    else:
        name = "cnv-tests-utilities"
        if Namespace(client=admin_client, name=name).exists:
            exit_pytest_execution(
                message=f"{name} namespace already exists."
                f"\nAfter verifying no one else is performing tests against the cluster, run:"
                f"\n'oc delete namespace {name}'",
                return_code=100,
            )

        else:
            yield from create_ns(
                admin_client=admin_client,
                labels=POD_SECURITY_NAMESPACE_LABELS,
                name=name,
            )


@pytest.fixture(scope="session")
def cnv_tests_utilities_service_account(cnv_tests_utilities_namespace, installing_cnv):
    if installing_cnv:
        yield
    else:
        with ServiceAccount(
            name=CNV_TEST_SERVICE_ACCOUNT,
            namespace=cnv_tests_utilities_namespace.name,
        ) as service_account:
            add_scc_to_service_account(
                namespace=cnv_tests_utilities_namespace.name,
                scc_name="privileged",
                sa_name=service_account.name,
            )
            yield service_account


@pytest.fixture(scope="session")
def utility_daemonset(
    admin_client,
    installing_cnv,
    generated_pulled_secret,
    cnv_tests_utilities_namespace,
    cnv_tests_utilities_service_account,
):
    """
    Deploy utility daemonset into the cnv-tests-utilities namespace.

    This daemonset deploys a pod on every node with hostNetwork and the main usage is to run commands on the hosts.
    For example to create linux bridge and other components related to the host configuration.
    """
    if installing_cnv:
        yield
    else:
        modified_ds_yaml_file = get_daemonset_yaml_file_with_image_hash(
            generated_pulled_secret=generated_pulled_secret,
            service_account=cnv_tests_utilities_service_account,
        )
        with DaemonSet(yaml_file=modified_ds_yaml_file) as ds:
            ds.wait_until_deployed()
            yield ds


@pytest.fixture(scope="session")
def pull_secret_directory(tmpdir_factory):
    yield tmpdir_factory.mktemp("pullsecret-folder")


@pytest.fixture(scope="session")
def generated_pulled_secret(
    is_production_source,
    installing_cnv,
    admin_client,
):
    if is_production_source and installing_cnv:
        return
    return generate_openshift_pull_secret_file()


@pytest.fixture(scope="session")
def workers_utility_pods(admin_client, workers, utility_daemonset, installing_cnv):
    """
    Get utility pods from worker nodes.
    When the tests start we deploy a pod on every worker node in the cluster using a daemonset.
    These pods have a label of cnv-test=utility and they are privileged pods with hostnetwork=true
    """
    if installing_cnv:
        return
    return get_utility_pods_from_nodes(
        nodes=workers,
        admin_client=admin_client,
        label_selector="cnv-test=utility",
    )


@pytest.fixture(scope="session")
def control_plane_utility_pods(admin_client, installing_cnv, control_plane_nodes, utility_daemonset):
    """
    Get utility pods from control plane nodes.
    When the tests start we deploy a pod on every control plane node in the cluster using a daemonset.
    These pods have a label of cnv-test=utility and they are privileged pods with hostnetwork=true
    """
    if installing_cnv:
        return
    return get_utility_pods_from_nodes(
        nodes=control_plane_nodes,
        admin_client=admin_client,
        label_selector="cnv-test=utility",
    )


@pytest.fixture(scope="session")
def node_physical_nics(workers_utility_pods):
    interfaces = {}
    for pod in workers_utility_pods:
        node = pod.instance.spec.nodeName
        output = pod.execute(
            command=shlex.split("bash -c \"nmcli dev s | grep -v unmanaged | grep ethernet | awk '{print $1}'\"")
        ).split("\n")
        interfaces[node] = list(filter(None, output))  # Filter out empty lines

    LOGGER.info(f"Nodes physical NICs: {interfaces}")
    return interfaces


@pytest.fixture(scope="session")
def nodes_active_nics(
    workers,
    workers_utility_pods,
    node_physical_nics,
):
    # TODO: Reduce cognitive complexity
    def _bridge_ports(node_interface):
        ports = set()
        if node_interface["type"] in (OVS_BRIDGE, LINUX_BRIDGE) and node_interface["bridge"].get("port"):
            for bridge_port in node_interface["bridge"]["port"]:
                ports.add(bridge_port["name"])
        elif node_interface["type"] == "bond" and node_interface["link-aggregation"].get("port"):
            for bridge_port in node_interface["link-aggregation"]["port"]:
                ports.add(bridge_port)
        return ports

    """
    Get nodes active NICs.
    First NIC is management NIC
    """
    nodes_nics = {}
    for node in workers:
        nodes_nics[node.name] = {"available": [], "occupied": []}
        nns = NodeNetworkState(name=node.name)

        for node_iface in nns.interfaces:
            iface_name = node_iface["name"]
            #  Exclude SR-IOV (VFs) interfaces.
            if re.findall(r"v\d+$", iface_name):
                continue

            # If the interface is a bridge with physical ports, then these ports should be labeled as occupied.
            for bridge_port in _bridge_ports(node_interface=node_iface):
                if (
                    bridge_port in node_physical_nics[node.name]
                    and bridge_port not in nodes_nics[node.name]["occupied"]
                ):
                    node_iface_type = node_iface["type"]
                    LOGGER.warning(
                        f"{node.name}:{bridge_port} is a port of {iface_name} {node_iface_type} - adding it "
                        f"to the node's occupied interfaces list."
                    )
                    nodes_nics[node.name]["occupied"].append(bridge_port)
                    if bridge_port in nodes_nics[node.name]["available"]:
                        nodes_nics[node.name]["available"].remove(bridge_port)

            if iface_name in nodes_nics[node.name]["occupied"]:
                continue

            if iface_name not in node_physical_nics[node.name]:
                continue

            physically_connected = (
                ExecCommandOnPod(utility_pods=workers_utility_pods, node=node)
                .exec(command=f"nmcli -g WIRED-PROPERTIES.CARRIER device show {iface_name}")
                .lower()
            )
            if physically_connected != "on":
                LOGGER.warning(f"{node.name} {iface_name} link is down")
                continue

            if node_iface["ipv4"].get("address"):
                nodes_nics[node.name]["occupied"].append(iface_name)
            else:
                nodes_nics[node.name]["available"].append(iface_name)

    LOGGER.info(f"Nodes active NICs: {nodes_nics}")
    return nodes_nics


@pytest.fixture(scope="session")
def nodes_available_nics(nodes_active_nics):
    return {node: nodes_active_nics[node]["available"] for node in nodes_active_nics.keys()}


@pytest.fixture(scope="module")
def namespace(request, admin_client, unprivileged_client):
    """
    To create namespace using admin client, pass {"use_unprivileged_client": False} to request.param
    (default for "use_unprivileged_client" is True)
    """
    use_unprivileged_client = getattr(request, "param", {}).get("use_unprivileged_client", True)
    teardown = getattr(request, "param", {}).get("teardown", True)
    unprivileged_client = unprivileged_client if use_unprivileged_client else None
    yield from create_ns(
        unprivileged_client=unprivileged_client,
        admin_client=admin_client,
        name=generate_namespace_name(file_path=request.fspath.strpath.split(f"{os.path.dirname(__file__)}/")[1]),
        teardown=teardown,
    )


@pytest.fixture(scope="session")
def leftovers_cleanup(admin_client, cnv_tests_utilities_namespace, identity_provider_config):
    LOGGER.info("Checking for leftover resources")
    secret = Secret(
        client=admin_client,
        name=HTTP_SECRET_NAME,
        namespace=NamespacesNames.OPENSHIFT_CONFIG,
    )
    ds = None
    if cnv_tests_utilities_namespace:
        ds = DaemonSet(
            client=admin_client,
            name=UTILITY,
            namespace=cnv_tests_utilities_namespace.name,
        )
    #  Delete Secret and DaemonSet created by us.
    for resource_ in (secret, ds):
        if resource_ and resource_.exists:
            resource_.delete(wait=True)

    #  Remove leftovers from OAuth
    if not identity_provider_config:
        # When running CI (k8s) OAuth is not exists on the cluster.
        LOGGER.warning("OAuth does not exist on the cluster")
        return

    identity_providers_spec = identity_provider_config.instance.to_dict()["spec"]
    identity_providers_token = identity_providers_spec.get("tokenConfig")
    identity_providers = identity_providers_spec.get("identityProviders", [])

    if ACCESS_TOKEN == identity_providers_token:
        identity_providers_spec["tokenConfig"] = None

    if HTPASSWD_PROVIDER_DICT in identity_providers:
        identity_providers.pop(identity_providers.index(HTPASSWD_PROVIDER_DICT))
        identity_providers_spec["identityProviders"] = identity_providers or None

    r_editor = ResourceEditor(
        patches={
            identity_provider_config: {
                "metadata": {"name": identity_provider_config.name},
                "spec": identity_providers_spec,
            }
        }
    )
    r_editor.update()


@pytest.fixture(scope="session")
def workers_type(workers_utility_pods, installing_cnv):
    if installing_cnv:
        return
    physical = ClusterHosts.Type.PHYSICAL
    virtual = ClusterHosts.Type.VIRTUAL
    for pod in workers_utility_pods:
        pod_exec = ExecCommandOnPod(utility_pods=workers_utility_pods, node=pod.node)
        out = pod_exec.exec(command="systemd-detect-virt", ignore_rc=True)
        if out == "none":
            LOGGER.info(f"Cluster workers are: {physical}")
            os.environ[WORKERS_TYPE] = physical
            return physical

    LOGGER.info(f"Cluster workers are: {virtual}")
    os.environ[WORKERS_TYPE] = virtual
    return virtual


@pytest.fixture(scope="session")
def is_psi_cluster():
    return Infrastructure(name="cluster").instance.status.platform == "OpenStack"


@pytest.fixture()
def data_volume_multi_storage_scope_function(
    request,
    namespace,
    storage_class_matrix__function__,
    schedulable_nodes,
):
    yield from data_volume(
        request=request,
        namespace=namespace,
        storage_class_matrix=storage_class_matrix__function__,
        schedulable_nodes=schedulable_nodes,
    )


@pytest.fixture(scope="module")
def data_volume_multi_storage_scope_module(
    request,
    namespace,
    storage_class_matrix__module__,
    schedulable_nodes,
):
    yield from data_volume(
        request=request,
        namespace=namespace,
        storage_class_matrix=storage_class_matrix__module__,
        schedulable_nodes=schedulable_nodes,
    )


@pytest.fixture(scope="class")
def golden_image_data_volume_multi_storage_scope_class(
    admin_client,
    request,
    golden_images_namespace,
    storage_class_matrix__class__,
    schedulable_nodes,
):
    yield from data_volume(
        request=request,
        namespace=golden_images_namespace,
        storage_class_matrix=storage_class_matrix__class__,
        schedulable_nodes=schedulable_nodes,
        check_dv_exists=True,
        admin_client=admin_client,
    )


@pytest.fixture(scope="class")
def golden_image_data_source_multi_storage_scope_class(
    admin_client, golden_image_data_volume_multi_storage_scope_class
):
    yield from create_or_update_data_source(
        admin_client=admin_client, dv=golden_image_data_volume_multi_storage_scope_class
    )


@pytest.fixture()
def golden_image_data_volume_multi_storage_scope_function(
    admin_client,
    request,
    golden_images_namespace,
    storage_class_matrix__function__,
    schedulable_nodes,
):
    yield from data_volume(
        request=request,
        namespace=golden_images_namespace,
        storage_class_matrix=storage_class_matrix__function__,
        schedulable_nodes=schedulable_nodes,
        check_dv_exists=True,
        admin_client=admin_client,
    )


@pytest.fixture()
def golden_image_data_source_multi_storage_scope_function(
    admin_client, golden_image_data_volume_multi_storage_scope_function
):
    yield from create_or_update_data_source(
        admin_client=admin_client,
        dv=golden_image_data_volume_multi_storage_scope_function,
    )


@pytest.fixture()
def data_volume_scope_function(request, namespace, schedulable_nodes):
    yield from data_volume(
        request=request,
        namespace=namespace,
        storage_class=request.param["storage_class"],
        schedulable_nodes=schedulable_nodes,
    )


@pytest.fixture(scope="class")
def data_volume_scope_class(request, namespace, schedulable_nodes):
    yield from data_volume(
        request=request,
        namespace=namespace,
        storage_class=request.param["storage_class"],
        schedulable_nodes=schedulable_nodes,
    )


@pytest.fixture(scope="class")
def golden_image_data_volume_scope_class(request, admin_client, golden_images_namespace, schedulable_nodes):
    yield from data_volume(
        request=request,
        namespace=golden_images_namespace,
        storage_class=request.param["storage_class"],
        schedulable_nodes=schedulable_nodes,
        check_dv_exists=True,
        admin_client=admin_client,
    )


@pytest.fixture(scope="class")
def golden_image_data_source_scope_class(admin_client, golden_image_data_volume_scope_class):
    yield from create_or_update_data_source(admin_client=admin_client, dv=golden_image_data_volume_scope_class)


@pytest.fixture(scope="module")
def golden_image_data_volume_scope_module(request, admin_client, golden_images_namespace, schedulable_nodes):
    yield from data_volume(
        request=request,
        namespace=golden_images_namespace,
        storage_class=request.param["storage_class"],
        schedulable_nodes=schedulable_nodes,
        check_dv_exists=True,
        admin_client=admin_client,
    )


@pytest.fixture()
def golden_image_data_volume_scope_function(request, admin_client, golden_images_namespace, schedulable_nodes):
    yield from data_volume(
        request=request,
        namespace=golden_images_namespace,
        storage_class=request.param["storage_class"],
        storage_class_matrix=request.param.get("storage_class_matrix"),
        schedulable_nodes=schedulable_nodes,
        check_dv_exists=True,
        admin_client=admin_client,
    )


@pytest.fixture()
def golden_image_data_source_scope_function(admin_client, golden_image_data_volume_scope_function):
    yield from create_or_update_data_source(admin_client=admin_client, dv=golden_image_data_volume_scope_function)


@pytest.fixture(scope="module")
def rhel9_data_source_scope_module(golden_images_namespace):
    return DataSource(
        client=golden_images_namespace.client,
        name=RHEL9_STR,
        namespace=golden_images_namespace.name,
        ensure_exists=True,
    )


"""
VM creation from template
"""


@pytest.fixture()
def vm_instance_from_template_multi_storage_scope_function(
    request,
    unprivileged_client,
    namespace,
    data_volume_multi_storage_scope_function,
    cpu_for_migration,
):
    """Calls vm_instance_from_template contextmanager

    Creates a VM from template and starts it (if requested).
    """

    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        existing_data_volume=data_volume_multi_storage_scope_function,
        vm_cpu_model=(cpu_for_migration if request.param.get("set_vm_common_cpu") else None),
    ) as vm:
        yield vm


@pytest.fixture()
def golden_image_vm_instance_from_template_multi_storage_scope_function(
    request,
    unprivileged_client,
    namespace,
    golden_image_data_source_multi_storage_scope_function,
    cpu_for_migration,
):
    """Calls vm_instance_from_template contextmanager

    Creates a VM from template and starts it (if requested).
    """

    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_source=golden_image_data_source_multi_storage_scope_function,
        vm_cpu_model=(cpu_for_migration if request.param.get("set_vm_common_cpu") else None),
    ) as vm:
        yield vm


@pytest.fixture(scope="class")
def golden_image_vm_instance_from_template_multi_storage_scope_class(
    request,
    unprivileged_client,
    namespace,
    golden_image_data_source_multi_storage_scope_class,
    cpu_for_migration,
):
    """Calls vm_instance_from_template contextmanager

    Creates a VM from template and starts it (if requested).
    """

    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_source=golden_image_data_source_multi_storage_scope_class,
        vm_cpu_model=(cpu_for_migration if request.param.get("set_vm_common_cpu") else None),
    ) as vm:
        yield vm


"""
Windows-specific fixtures
"""


@pytest.fixture()
def started_windows_vm(
    request,
    vm_instance_from_template_multi_storage_scope_function,
):
    wait_for_windows_vm(
        vm=vm_instance_from_template_multi_storage_scope_function,
        version=request.param["os_version"],
    )


@pytest.fixture(scope="session")
def worker_nodes_ipv4_false_secondary_nics(nodes_available_nics, schedulable_nodes):
    """
    Function removes ipv4 from secondary nics.
    """
    for worker_node in schedulable_nodes:
        worker_nics = nodes_available_nics[worker_node.name]
        with EthernetNetworkConfigurationPolicy(
            name=f"disable-ipv4-{name_prefix(worker_node.name)}",
            node_selector=get_node_selector_dict(node_selector=worker_node.hostname),
            interfaces_name=worker_nics,
        ):
            LOGGER.info(
                f"selected worker node - {worker_node.name} under NNCP selected NIC information - {worker_nics} "
            )


@pytest.fixture(scope="session")
def csv_scope_session(admin_client, hco_namespace, installing_cnv):
    if not installing_cnv:
        return utilities.hco.get_installed_hco_csv(admin_client=admin_client, hco_namespace=hco_namespace)


@pytest.fixture(scope="session")
def cnv_current_version(installing_cnv, csv_scope_session):
    if installing_cnv:
        return CNV_NOT_INSTALLED
    if csv_scope_session:
        return csv_scope_session.instance.spec.version


@pytest.fixture(scope="session")
def hco_namespace(admin_client, installing_cnv):
    if not installing_cnv:
        return utilities.hco.get_hco_namespace(admin_client=admin_client, namespace=py_config["hco_namespace"])


@pytest.fixture(scope="session")
def worker_node1(schedulable_nodes):
    # Get first worker nodes out of schedulable_nodes list
    return schedulable_nodes[0]


@pytest.fixture(scope="session")
def worker_node2(schedulable_nodes):
    # Get second worker nodes out of schedulable_nodes list
    return schedulable_nodes[1]


@pytest.fixture(scope="session")
def worker_node3(schedulable_nodes):
    # Get third worker nodes out of schedulable_nodes list
    return schedulable_nodes[2]


@pytest.fixture(scope="session")
def sriov_namespace():
    return Namespace(name=py_config["sriov_namespace"])


@pytest.fixture(scope="session")
def sriov_nodes_states(admin_client, sriov_namespace, sriov_workers):
    sriov_nns_list = [
        SriovNetworkNodeState(client=admin_client, namespace=sriov_namespace.name, name=worker.name)
        for worker in sriov_workers
    ]
    return sriov_nns_list


@pytest.fixture(scope="session")
def sriov_workers(schedulable_nodes):
    sriov_worker_label = "feature.node.kubernetes.io/network-sriov.capable"
    yield [node for node in schedulable_nodes if node.labels.get(sriov_worker_label) == "true"]


@pytest.fixture(scope="session")
def vlan_base_iface(worker_node1, nodes_available_nics):
    # Select the last NIC from the list as a way to ensure that the selected NIC
    # is not already used (e.g. as a bond's port).
    return nodes_available_nics[worker_node1.name][-1]


@pytest.fixture(scope="session")
def sriov_ifaces(sriov_nodes_states, workers_utility_pods):
    node = sriov_nodes_states[0]
    state_up = Resource.Interface.State.UP
    ifaces_list = [
        iface
        for iface in node.instance.status.interfaces
        if (
            iface.totalvfs
            and ExecCommandOnPod(utility_pods=workers_utility_pods, node=node).interface_status(interface=iface.name)
            == state_up
        )
    ]

    if not ifaces_list:
        raise SriovIfaceNotFound(
            f"no sriov interface with '{state_up}' status was found, "
            f"please make sure at least one sriov interface is {state_up}"
        )

    return ifaces_list


@pytest.fixture(scope="session")
def sriov_node_policy(sriov_unused_ifaces, sriov_nodes_states, workers_utility_pods, sriov_namespace):
    yield from create_sriov_node_policy(
        nncp_name="test-sriov-policy",
        namespace=sriov_namespace.name,
        sriov_iface=sriov_unused_ifaces[0],
        sriov_nodes_states=sriov_nodes_states,
        sriov_resource_name="sriov_net",
    )


@pytest.fixture(scope="session")
def mac_pool(hco_namespace):
    return MacPool(
        kmp_range=ConfigMap(namespace=hco_namespace.name, name=KUBEMACPOOL_MAC_RANGE_CONFIG).instance["data"]
    )


def _skip_access_mode_rwo(storage_class_matrix):
    if storage_class_matrix[[*storage_class_matrix][0]]["access_mode"] == PersistentVolumeClaim.AccessMode.RWO:
        pytest.skip(reason="Skipping when access_mode is RWO; possible reason: cannot migrate VMI with non-shared PVCs")


@pytest.fixture()
def skip_access_mode_rwo_scope_function(storage_class_matrix__function__):
    _skip_access_mode_rwo(storage_class_matrix=storage_class_matrix__function__)


@pytest.fixture(scope="class")
def skip_access_mode_rwo_scope_class(storage_class_matrix__class__):
    _skip_access_mode_rwo(storage_class_matrix=storage_class_matrix__class__)


@pytest.fixture(scope="module")
def skip_access_mode_rwo_scope_module(storage_class_matrix__module__):
    _skip_access_mode_rwo(storage_class_matrix=storage_class_matrix__module__)


@pytest.fixture(scope="session")
def nodes_cpu_vendor(schedulable_nodes):
    if schedulable_nodes[0].labels.get(f"cpu-vendor.node.kubevirt.io/{AMD}"):
        return AMD
    elif schedulable_nodes[0].labels.get(f"cpu-vendor.node.kubevirt.io/{INTEL}"):
        return INTEL
    else:
        return None


@pytest.fixture(scope="session")
def nodes_cpu_architecture(nodes):
    return get_nodes_cpu_architecture(nodes=nodes)


@pytest.fixture(scope="session")
def cluster_node_cpus(schedulable_nodes):
    # Get cpu model information from the nodes
    return get_nodes_cpu_model(nodes=schedulable_nodes)


@pytest.fixture(scope="session")
def cluster_common_node_cpu(cluster_node_cpus):
    return get_common_cpu_from_nodes(cluster_cpus=set.intersection(*cluster_node_cpus.get("common").values()))


@pytest.fixture(scope="session")
def cluster_common_modern_node_cpu(cluster_node_cpus):
    return get_common_cpu_from_nodes(cluster_cpus=set.intersection(*cluster_node_cpus.get("modern").values()))


@pytest.fixture(scope="session")
def host_cpu_model(schedulable_nodes, nodes_cpu_architecture):
    # get the host-model-cpu labels from the nodes
    return None if nodes_cpu_architecture == ARM_64 else get_host_model_cpu(nodes=schedulable_nodes)


@pytest.fixture(scope="session")
def cpu_for_migration(cluster_common_node_cpu, host_cpu_model, nodes_cpu_architecture):
    """
    Get a CPU model that is common for all nodes
    """
    return (
        None
        if nodes_cpu_architecture == ARM_64
        else find_common_cpu_model_for_live_migration(
            cluster_cpu=cluster_common_node_cpu, host_cpu_model=host_cpu_model
        )
    )


@pytest.fixture(scope="session")
def modern_cpu_for_migration(cluster_common_modern_node_cpu, host_cpu_model, nodes_cpu_architecture):
    """
    Get a modern CPU model that is common for all nodes
    """
    return (
        None
        if nodes_cpu_architecture == ARM_64
        else find_common_cpu_model_for_live_migration(
            cluster_cpu=cluster_common_modern_node_cpu, host_cpu_model=host_cpu_model
        )
    )


@pytest.fixture(scope="module")
def skip_if_no_common_cpu(cluster_common_node_cpu, nodes_cpu_architecture):
    if not cluster_common_node_cpu and nodes_cpu_architecture != ARM_64:
        pytest.skip("This is a heterogeneous cluster")


@pytest.fixture(scope="module")
def skip_if_no_common_modern_cpu(cluster_common_modern_node_cpu):
    if not cluster_common_modern_node_cpu and nodes_cpu_architecture != ARM_64:
        pytest.skip("This is a heterogeneous cluster")


@pytest.fixture(scope="session")
def golden_images_namespace(
    admin_client,
):
    for ns in Namespace.get(
        name=py_config["golden_images_namespace"],
        dyn_client=admin_client,
    ):
        return ns


@pytest.fixture(scope="session")
def golden_images_cluster_role_edit(
    admin_client,
):
    for cluster_role in ClusterRole.get(
        name="os-images.kubevirt.io:edit",
        dyn_client=admin_client,
    ):
        return cluster_role


@pytest.fixture()
def golden_images_edit_rolebinding(
    golden_images_namespace,
    golden_images_cluster_role_edit,
):
    with RoleBinding(
        name="role-bind-create-dv",
        namespace=golden_images_namespace.name,
        subjects_kind="User",
        subjects_name="unprivileged-user",
        subjects_namespace=golden_images_namespace.name,
        role_ref_kind=golden_images_cluster_role_edit.kind,
        role_ref_name=golden_images_cluster_role_edit.name,
    ) as role_binding:
        yield role_binding


@pytest.fixture(scope="session")
def hosts_common_available_ports(nodes_available_nics):
    """
    Get list of common ports from nodes_available_nics.

    nodes_available_nics like
    [['ens3', 'ens4', 'ens6', 'ens5'],
    ['ens3', 'ens8', 'ens6', 'ens7'],
    ['ens3', 'ens8', 'ens6', 'ens7']]

    will return ['ens3', 'ens6']
    """
    nics_list = list(set.intersection(*[set(_list) for _list in nodes_available_nics.values()]))
    nics_list.sort()
    LOGGER.info(f"Hosts common available NICs: {nics_list}")
    return nics_list


@pytest.fixture(scope="session")
def default_sc(admin_client):
    """
    Get default Storage Class defined
    """
    try:
        yield get_default_storage_class()
    except ValueError:
        yield


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


@pytest.fixture(scope="class")
def ovs_daemonset(admin_client, hco_namespace):
    return wait_for_ovs_daemonset_resource(admin_client=admin_client, hco_namespace=hco_namespace)


@pytest.fixture()
def hyperconverged_ovs_annotations_fetched(hyperconverged_resource_scope_function):
    return get_hyperconverged_ovs_annotations(hyperconverged=hyperconverged_resource_scope_function)


@pytest.fixture(scope="session")
def network_addons_config_scope_session(admin_client):
    nac = list(NetworkAddonsConfig.get(dyn_client=admin_client))
    assert nac, "There should be one NetworkAddonsConfig CR."
    return nac[0]


@pytest.fixture(scope="session")
def ocs_storage_class(cluster_storage_classes):
    """
    Get the OCS storage class if configured
    """
    for sc in cluster_storage_classes:
        if sc.name == StorageClassNames.CEPH_RBD_VIRTUALIZATION:
            return sc


@pytest.fixture(scope="session")
def skip_test_if_no_ocs_sc(ocs_storage_class):
    """
    Skip test if no OCS storage class available
    """
    if not ocs_storage_class:
        pytest.skip("Skipping test, OCS storage class is not deployed")


@pytest.fixture(scope="session")
def hyperconverged_ovs_annotations_enabled_scope_session(
    admin_client,
    hco_namespace,
    hyperconverged_resource_scope_session,
    network_addons_config_scope_session,
):
    yield from enable_hyperconverged_ovs_annotations(
        admin_client=admin_client,
        hco_namespace=hco_namespace,
        hyperconverged_resource=hyperconverged_resource_scope_session,
        network_addons_config=network_addons_config_scope_session,
    )

    # Make sure all ovs pods are deleted:
    wait_for_ovs_status(network_addons_config=network_addons_config_scope_session, status=False)
    wait_for_pods_deletion(
        pods=get_pods(
            dyn_client=admin_client,
            namespace=hco_namespace,
            label="app=ovs-cni",
        )
    )


@pytest.fixture(scope="session")
def cluster_storage_classes(admin_client):
    return list(StorageClass.get(dyn_client=admin_client))


@pytest.fixture(scope="session")
def cluster_storage_classes_names(cluster_storage_classes):
    return [sc.name for sc in cluster_storage_classes]


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
def hostpath_provisioner_scope_module():
    yield HostPathProvisioner(name=HostPathProvisioner.Name.HOSTPATH_PROVISIONER)


@pytest.fixture(scope="session")
def hostpath_provisioner_scope_session():
    yield HostPathProvisioner(name=HostPathProvisioner.Name.HOSTPATH_PROVISIONER)


@pytest.fixture(scope="module")
def cnv_pods(admin_client, hco_namespace):
    yield list(Pod.get(dyn_client=admin_client, namespace=hco_namespace.name))


@pytest.fixture(scope="session")
def cluster_sanity_scope_session(
    request,
    nodes,
    cluster_storage_classes_names,
    admin_client,
    hco_namespace,
    junitxml_plugin,
    hyperconverged_resource_scope_session,
    installing_cnv,
):
    """
    Performs various cluster level checks, e.g.: storage class validation, node state, as well as all cnv pod
    check to ensure all are in 'Running' state, to determine current state of cluster
    """
    if not installing_cnv:
        cluster_sanity(
            request=request,
            admin_client=admin_client,
            cluster_storage_classes_names=cluster_storage_classes_names,
            nodes=nodes,
            hco_namespace=hco_namespace,
            junitxml_property=junitxml_plugin,
            hco_status_conditions=hyperconverged_resource_scope_session.instance.status.conditions,
            expected_hco_status=DEFAULT_HCO_CONDITIONS,
        )


@pytest.fixture(scope="module")
def cluster_sanity_scope_module(
    request,
    nodes,
    cluster_storage_classes_names,
    admin_client,
    hco_namespace,
    junitxml_plugin,
    hyperconverged_resource_scope_session,
    installing_cnv,
):
    """
    Performs various cluster level checks, e.g.: storage class validation, node state, as well as all cnv pod
    check to ensure all are in 'Running' state, to determine current state of cluster
    """
    if not installing_cnv:
        cluster_sanity(
            request=request,
            admin_client=admin_client,
            cluster_storage_classes_names=cluster_storage_classes_names,
            nodes=nodes,
            hco_namespace=hco_namespace,
            junitxml_property=junitxml_plugin,
            hco_status_conditions=hyperconverged_resource_scope_session.instance.status.conditions,
            expected_hco_status=DEFAULT_HCO_CONDITIONS,
        )


@pytest.fixture(scope="session")
def kmp_vm_label(admin_client):
    kmp_webhook_config = MutatingWebhookConfiguration(client=admin_client, name="kubemacpool-mutator")

    for webhook in kmp_webhook_config.instance.to_dict()["webhooks"]:
        if webhook["name"] == KMP_VM_ASSIGNMENT_LABEL:
            return {
                ldict["key"]: ldict["values"][0]
                for ldict in webhook["namespaceSelector"]["matchExpressions"]
                if ldict["key"] == KMP_VM_ASSIGNMENT_LABEL
            }

    raise ResourceNotFoundError(f"Webhook {KMP_VM_ASSIGNMENT_LABEL} was not found")


@pytest.fixture(scope="class")
def kmp_enabled_ns(admin_client, kmp_vm_label):
    # Enabling label "allocate" (or any other non-configured label) - Allocates.
    kmp_vm_label[KMP_VM_ASSIGNMENT_LABEL] = KMP_ENABLED_LABEL
    yield from create_ns(admin_client=admin_client, name="kmp-enabled", labels=kmp_vm_label)


@pytest.fixture(scope="session")
def cdi(hco_namespace):
    cdi = CDI(name=CDI_KUBEVIRT_HYPERCONVERGED)
    assert cdi.instance is not None
    yield cdi


@pytest.fixture(scope="session")
def cdi_config():
    cdi_config = CDIConfig(name="config")
    assert cdi_config.instance is not None
    return cdi_config


@pytest.fixture(scope="session")
def prometheus():
    return Prometheus(
        verify_ssl=False,
        bearer_token=utilities.infra.get_prometheus_k8s_token(duration="86400s"),
    )


@pytest.fixture()
def cdi_spec(cdi):
    return cdi.instance.to_dict()["spec"]


@pytest.fixture()
def hco_spec(hyperconverged_resource_scope_function):
    return hyperconverged_resource_scope_function.instance.to_dict()["spec"]


@pytest.fixture(scope="module")
def is_post_cnv_upgrade_cluster(admin_client, hco_namespace):
    return (
        len(
            list(
                InstallPlan.get(
                    dyn_client=admin_client,
                    namespace=hco_namespace.name,
                )
            )
        )
        > 1
    )


@pytest.fixture(scope="session")
def cluster_info(
    admin_client,
    installing_cnv,
    openshift_current_version,
    cnv_current_version,
    hco_image,
    ocs_current_version,
    kubevirt_resource_scope_session,
    ipv6_supported_cluster,
    ipv4_supported_cluster,
    workers_type,
    nodes_cpu_architecture,
):
    title = "\nCluster info:\n"
    virtctl_client_version, virtctl_server_version = None, None
    if not installing_cnv:
        virtctl_client_version, virtctl_server_version = (
            run_virtctl_command(command=["version"])[1].strip().splitlines()
        )

    LOGGER.info(
        f"{title}"
        f"\tOpenshift version: {openshift_current_version}\n"
        f"\tCNV version: {cnv_current_version}\n"
        f"\tHCO image: {hco_image}\n"
        f"\tOCS version: {ocs_current_version}\n"
        f"\tCNI type: {get_cluster_cni_type(admin_client=admin_client)}\n"
        f"\tWorkers type: {workers_type}\n"
        f"\tCluster CPU Architecture: {nodes_cpu_architecture}\n"
        f"\tIPv4 cluster: {ipv4_supported_cluster}\n"
        f"\tIPv6 cluster: {ipv6_supported_cluster}\n"
        f"\tVirtctl version: \n\t{virtctl_client_version}\n\t{virtctl_server_version}\n"
    )


@pytest.fixture(scope="session")
def ocs_current_version(ocs_storage_class, admin_client):
    if ocs_storage_class:
        for csv in ClusterServiceVersion.get(
            dyn_client=admin_client,
            namespace="openshift-storage",
            label_selector=f"{ClusterServiceVersion.ApiGroup.OPERATORS_COREOS_COM}/ocs-operator.openshift-storage",
        ):
            return csv.instance.spec.version


@pytest.fixture(scope="session")
def openshift_current_version(admin_client):
    return get_clusterversion(dyn_client=admin_client).instance.status.history[0].version


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
        return CNV_NOT_INSTALLED
    source_name = cnv_subscription_scope_session.instance.spec.source
    for cs in CatalogSource.get(
        dyn_client=admin_client,
        name=source_name,
        namespace=py_config["marketplace_namespace"],
    ):
        return cs.instance.spec.image


@pytest.fixture(scope="session")
def cnv_subscription_scope_session(
    admin_client,
    installing_cnv,
    hco_namespace,
):
    if not installing_cnv:
        return get_subscription(
            admin_client=admin_client,
            namespace=hco_namespace.name,
            subscription_name=py_config["hco_subscription"] or HCO_SUBSCRIPTION,
        )


@pytest.fixture(scope="session")
def kubevirt_resource_scope_session(admin_client, installing_cnv, hco_namespace):
    if not installing_cnv:
        return get_hyperconverged_kubevirt(admin_client=admin_client, hco_namespace=hco_namespace)


@pytest.fixture(scope="session")
def junitxml_plugin(request, record_testsuite_property):
    return record_testsuite_property if request.config.pluginmanager.has_plugin("junitxml") else None


@pytest.fixture(scope="module")
def base_templates(admin_client):
    return get_base_templates_list(client=admin_client)


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


@pytest.fixture
def term_handler_scope_function():
    orig = signal(SIGTERM, getsignal(SIGINT))
    yield
    signal(SIGTERM, orig)


@pytest.fixture(scope="class")
def term_handler_scope_class():
    orig = signal(SIGTERM, getsignal(SIGINT))
    yield
    signal(SIGTERM, orig)


@pytest.fixture(scope="module")
def term_handler_scope_module():
    orig = signal(SIGTERM, getsignal(SIGINT))
    yield
    signal(SIGTERM, orig)


@pytest.fixture(scope="session")
def term_handler_scope_session():
    orig = signal(SIGTERM, getsignal(SIGINT))
    yield
    signal(SIGTERM, orig)


@pytest.fixture(scope="session")
def upgrade_bridge_on_all_nodes(
    label_schedulable_nodes,
    hosts_common_available_ports,
):
    with network_device(
        interface_type=LINUX_BRIDGE,
        nncp_name="upgrade-bridge",
        interface_name="br1upgrade",
        node_selector_labels=NODE_TYPE_WORKER_LABEL,
        ports=[hosts_common_available_ports[0]],
    ) as br:
        yield br


@pytest.fixture(scope="session")
def bridge_on_one_node(worker_node1):
    with network_device(
        interface_type=LINUX_BRIDGE,
        nncp_name="upgrade-br-marker",
        interface_name="upg-br-mark",
        node_selector=get_node_selector_dict(node_selector=worker_node1.name),
    ) as br:
        yield br


@pytest.fixture(scope="session")
def upgrade_bridge_marker_nad(bridge_on_one_node, kmp_enabled_namespace, worker_node1):
    with network_nad(
        nad_type=LINUX_BRIDGE,
        nad_name=bridge_on_one_node.bridge_name,
        interface_name=bridge_on_one_node.bridge_name,
        namespace=kmp_enabled_namespace,
    ) as nad:
        wait_for_node_marked_by_bridge(bridge_nad=nad, node=worker_node1)
        yield nad


@pytest.fixture(scope="session")
def running_vm_upgrade_a(
    unprivileged_client,
    upgrade_bridge_marker_nad,
    kmp_enabled_namespace,
    upgrade_br1test_nad,
):
    name = "vm-upgrade-a"
    with VirtualMachineForTests(
        name=name,
        namespace=kmp_enabled_namespace.name,
        networks={upgrade_bridge_marker_nad.name: upgrade_bridge_marker_nad.name},
        interfaces=[upgrade_bridge_marker_nad.name],
        client=unprivileged_client,
        cloud_init_data=cloud_init(ip_address="10.200.100.1"),
        body=fedora_vm_body(name=name),
        eviction_strategy=ES_NONE,
    ) as vm:
        running_vm(vm=vm, wait_for_cloud_init=True)
        yield vm


@pytest.fixture(scope="session")
def running_vm_upgrade_b(
    unprivileged_client,
    upgrade_bridge_marker_nad,
    kmp_enabled_namespace,
    upgrade_br1test_nad,
):
    name = "vm-upgrade-b"
    with VirtualMachineForTests(
        name=name,
        namespace=kmp_enabled_namespace.name,
        networks={upgrade_bridge_marker_nad.name: upgrade_bridge_marker_nad.name},
        interfaces=[upgrade_bridge_marker_nad.name],
        client=unprivileged_client,
        cloud_init_data=cloud_init(ip_address="10.200.100.2"),
        body=fedora_vm_body(name=name),
        eviction_strategy=ES_NONE,
    ) as vm:
        running_vm(vm=vm, wait_for_cloud_init=True)
        yield vm


@pytest.fixture(scope="session")
def upgrade_br1test_nad(upgrade_namespace_scope_session, upgrade_bridge_on_all_nodes):
    with network_nad(
        nad_type=LINUX_BRIDGE,
        nad_name=upgrade_bridge_on_all_nodes.bridge_name,
        interface_name=upgrade_bridge_on_all_nodes.bridge_name,
        namespace=upgrade_namespace_scope_session,
    ) as nad:
        yield nad


@pytest.fixture(scope="session")
def cnv_upgrade_stream(admin_client, pytestconfig, cnv_current_version, cnv_target_version):
    """
    Verify if the upgrade can be performed by comparing the current and target versions.

    Args:
        admin_client: The admin client instance.
        pytestconfig: The pytest configuration object.
        cnv_current_version: The current CNV version.
        cnv_target_version: The target CNV version.
    """
    upgrade_stream = determine_upgrade_stream(
        current_version=cnv_current_version,
        target_version=cnv_target_version,
    )

    LOGGER.info(
        f"CNV upgrade:\n"
        f"Current version: {cnv_current_version},\n"
        f"Target version: {cnv_target_version},\n"
        f"Upgrade stream: {upgrade_stream},\n"
    )
    return upgrade_stream


def determine_upgrade_stream(current_version, target_version):
    current_cnv_version = parse(version=current_version.split("-")[0])
    target_cnv_version = parse(version=target_version.split("-")[0])

    if current_cnv_version.major < target_cnv_version.major:
        return UpgradeStreams.X_STREAM
    elif current_cnv_version.minor < target_cnv_version.minor:
        return UpgradeStreams.Y_STREAM
    elif current_cnv_version.micro < target_cnv_version.micro:
        return UpgradeStreams.Z_STREAM
    elif HOTFIX_STR in current_version:
        # if we reach here, this is an upgrade out of hotfix to next z-stream
        return UpgradeStreams.Z_STREAM
    else:
        if target_cnv_version <= current_cnv_version:
            # Upgrade only if a newer CNV version is requested
            raise ValueError(
                f"Cannot upgrade to older/identical versions,"
                f"current: {cnv_current_version} target: {target_cnv_version}"
            )
        raise ValueError(
            f"Unknown upgrade stream. Current cnv version: {current_cnv_version}, "
            f"target cnv version: {target_cnv_version}."
        )


@pytest.fixture(scope="session")
def upgrade_namespace_scope_session(admin_client, unprivileged_client):
    yield from create_ns(
        unprivileged_client=unprivileged_client,
        admin_client=admin_client,
        name="test-upgrade-namespace",
    )


@pytest.fixture(scope="session")
def kmp_enabled_namespace(kmp_vm_label, unprivileged_client, admin_client):
    # Enabling label "allocate" (or any other non-configured label) - Allocates.
    kmp_vm_label[KMP_VM_ASSIGNMENT_LABEL] = KMP_ENABLED_LABEL
    yield from create_ns(
        name="kmp-enabled-for-upgrade",
        labels=kmp_vm_label,
        unprivileged_client=unprivileged_client,
        admin_client=admin_client,
    )


@pytest.fixture(scope="session")
def rhel_latest_os_params():
    """This fixture is needed as during collection pytest_testconfig is empty.
    os_params or any globals using py_config in conftest cannot be used.
    """
    if latest_rhel_dict := py_config.get("latest_rhel_os_dict"):
        return {
            "rhel_image_path": f"{get_test_artifact_server_url()}{latest_rhel_dict['image_path']}",
            "rhel_dv_size": latest_rhel_dict["dv_size"],
            "rhel_template_labels": latest_rhel_dict["template_labels"],
        }

    raise ValueError("Failed to get latest RHEL OS parameters")


@pytest.fixture(scope="session")
def hco_target_csv_name(cnv_target_version):
    return get_hco_csv_name_by_version(cnv_target_version=cnv_target_version) if cnv_target_version else None


@pytest.fixture(scope="session")
def eus_hco_target_csv_name(eus_target_cnv_version):
    return get_hco_csv_name_by_version(cnv_target_version=eus_target_cnv_version)


@pytest.fixture(scope="session")
def cnv_target_version(pytestconfig):
    return pytestconfig.option.cnv_version


@pytest.fixture(scope="session")
def eus_target_cnv_version(pytestconfig, cnv_current_version):
    cnv_current_version = Version(version=cnv_current_version)
    minor = cnv_current_version.minor
    # EUS-to-EUS upgrades are only viable between even-numbered minor versions, exit if non-eus version
    if minor % 2:
        exit_pytest_execution(
            message=f"EUS upgrade can not be performed from non-eus version: {cnv_current_version}",
            return_code=EUS_ERROR_CODE,
        )
    return pytestconfig.option.eus_cnv_target_version or f"{cnv_current_version.major}.{minor + 2}.0"


@pytest.fixture()
def ssp_resource_scope_function(admin_client, hco_namespace):
    return get_ssp_resource(admin_client=admin_client, namespace=hco_namespace)


@pytest.fixture(scope="session")
def cluster_service_network(admin_client):
    return Network(client=admin_client, name="cluster").instance.status.serviceNetwork


@pytest.fixture(scope="session")
def ipv4_supported_cluster(cluster_service_network):
    if cluster_service_network:
        return any([ipaddress.ip_network(ip).version == 4 for ip in cluster_service_network])


@pytest.fixture(scope="session")
def ipv6_supported_cluster(cluster_service_network):
    if cluster_service_network:
        return any([ipaddress.ip_network(ip).version == 6 for ip in cluster_service_network])


@pytest.fixture()
def disabled_common_boot_image_import_hco_spec_scope_function(
    admin_client,
    hyperconverged_resource_scope_function,
    golden_images_namespace,
    golden_images_data_import_crons_scope_function,
):
    yield from utilities.hco.disable_common_boot_image_import_hco_spec(
        admin_client=admin_client,
        hco_resource=hyperconverged_resource_scope_function,
        golden_images_namespace=golden_images_namespace,
        golden_images_data_import_crons=golden_images_data_import_crons_scope_function,
    )


@pytest.fixture()
def golden_images_data_import_crons_scope_function(admin_client, golden_images_namespace):
    return get_data_import_crons(admin_client=admin_client, namespace=golden_images_namespace)


@pytest.fixture(scope="session")
def sno_cluster(admin_client):
    return get_infrastructure(admin_client=admin_client).instance.status.infrastructureTopology == "SingleReplica"


@pytest.fixture(scope="session")
def label_schedulable_nodes(schedulable_nodes):
    yield from label_nodes(nodes=schedulable_nodes, labels=NODE_TYPE_WORKER_LABEL)


@pytest.fixture(scope="class")
def disabled_common_boot_image_import_hco_spec_scope_class(
    admin_client,
    hyperconverged_resource_scope_class,
    golden_images_namespace,
    golden_images_data_import_crons_scope_class,
):
    yield from utilities.hco.disable_common_boot_image_import_hco_spec(
        admin_client=admin_client,
        hco_resource=hyperconverged_resource_scope_class,
        golden_images_namespace=golden_images_namespace,
        golden_images_data_import_crons=golden_images_data_import_crons_scope_class,
    )


@pytest.fixture(scope="class")
def golden_images_data_import_crons_scope_class(admin_client, golden_images_namespace):
    return get_data_import_crons(admin_client=admin_client, namespace=golden_images_namespace)


@pytest.fixture(scope="session")
def compact_cluster(nodes, workers, control_plane_nodes):
    return len(nodes) == len(workers) == len(control_plane_nodes) == 3


@pytest.fixture()
def virt_pods_with_running_status(admin_client, hco_namespace):
    return get_all_virt_pods_with_running_status(dyn_client=admin_client, hco_namespace=hco_namespace)


@pytest.fixture(scope="session")
def bin_directory(tmpdir_factory):
    return tmpdir_factory.mktemp("bin")


@pytest.fixture(scope="session")
def os_path_environment():
    return os.environ["PATH"]


@pytest.fixture(scope="session")
def virtctl_binary(installing_cnv, os_path_environment, bin_directory):
    if installing_cnv:
        return
    installed_virtctl = os.environ.get("CNV_TESTS_VIRTCTL_BIN")
    if installed_virtctl:
        LOGGER.warning(f"Using previously installed: {installed_virtctl}")
        return
    return download_file_from_cluster(get_console_spec_links_name=VIRTCTL_CLI_DOWNLOADS, dest_dir=bin_directory)


@pytest.fixture(scope="session")
def oc_binary(os_path_environment, bin_directory):
    installed_oc = os.environ.get("CNV_TESTS_OC_BIN")
    if installed_oc:
        LOGGER.warning(f"Using previously installed: {installed_oc}")
        return
    return download_file_from_cluster(get_console_spec_links_name="oc-cli-downloads", dest_dir=bin_directory)


@pytest.fixture(scope="session")
def bin_directory_to_os_path(os_path_environment, bin_directory, virtctl_binary, oc_binary):
    LOGGER.info(f"Adding {bin_directory} to $PATH")
    os.environ["PATH"] = f"{bin_directory}:{os_path_environment}"


@pytest.fixture(scope="session")
def artifactory_setup(pytestconfig):
    LOGGER.info("Checking for artifactory credentials:")
    if pytestconfig.option.skip_artifactory_check:
        LOGGER.warning("Explicitly skipping artifactory setup check due to use of --skip-artifactory-check")
        return
    if not (os.environ.get("ARTIFACTORY_TOKEN") and os.environ.get("ARTIFACTORY_USER")):
        raise MissingEnvironmentVariableError("Please set ARTIFACTORY_USER and ARTIFACTORY_TOKEN environment variables")


@pytest.fixture(autouse=True)
@pytest.mark.early(order=0)
def autouse_fixtures(
    leftovers_cleanup,  # Must be called first to avoid delete created resources.
    artifactory_setup,
    bin_directory_to_os_path,
    cluster_info,
    term_handler_scope_function,
    term_handler_scope_class,
    term_handler_scope_module,
    term_handler_scope_session,
    junitxml_polarion,
    admin_client,
    cluster_sanity_scope_session,
    cluster_sanity_scope_module,
    generated_ssh_key_for_vm_access,
):
    """call all autouse fixtures"""


@pytest.fixture(scope="session")
def ssh_key_tmpdir_scope_session(tmpdir_factory):
    yield tmpdir_factory.mktemp("vm-ssh-key-folder")


@pytest.fixture(scope="session")
def generated_ssh_key_for_vm_access(ssh_key_tmpdir_scope_session):
    key_generated = paramiko.RSAKey.generate(bits=2048)
    vm_ssh_key_file = os.path.join(ssh_key_tmpdir_scope_session, "vm_ssh_key.key")
    os.environ[CNV_VM_SSH_KEY_PATH] = vm_ssh_key_file
    key_generated.write_private_key_file(filename=vm_ssh_key_file)
    yield
    if os.path.isfile(vm_ssh_key_file):
        os.unlink(vm_ssh_key_file)
    del os.environ[CNV_VM_SSH_KEY_PATH]


@pytest.fixture(scope="session")
def rhel9_http_image_url():
    return get_http_image_url(image_directory=Images.Rhel.DIR, image_name=Images.Rhel.RHEL9_4_IMG)


@pytest.fixture(scope="session")
def storage_class_for_snapshot(admin_client):
    available_storage_classes = py_config["storage_class_matrix"]
    sc_for_snapshot = None
    sc_names = []
    for sc in available_storage_classes:
        sc_name = [*sc][0]
        if is_snapshot_supported_by_sc(sc_name=sc_name, client=admin_client):
            sc_for_snapshot = sc_name
            LOGGER.info(f"Storage class for snapshot: {sc_for_snapshot}")
            break
        sc_names.append(sc_name)
    if not sc_for_snapshot:
        LOGGER.warning(f"No Storage class among {sc_names} supports snapshots")
    yield sc_for_snapshot


@pytest.fixture(scope="session")
def skip_if_no_storage_class_for_snapshot(storage_class_for_snapshot):
    if not storage_class_for_snapshot:
        sc_names = [[*sc][0] for sc in py_config["storage_class_matrix"]]
        pytest.skip(f"There's no Storage Class among {sc_names} that supports snapshots, skipping the test")


@pytest.fixture()
def audit_logs():
    """Get audit logs names"""
    output = subprocess.getoutput(
        f"{OC_ADM_LOGS_COMMAND} --role=control-plane {AUDIT_LOGS_PATH} | grep audit"
    ).splitlines()
    nodes_logs = defaultdict(list)
    for line in output:
        try:
            node, log = line.split()
            nodes_logs[node].append(log)
        # When failing to get node log, for example "error trying to reach service: ... : connect: connection refused"
        except ValueError:
            LOGGER.error(f"Fail to get log: {line}")

    return nodes_logs


@pytest.fixture(scope="session")
def installing_cnv(pytestconfig):
    return pytestconfig.option.install


@pytest.fixture(scope="session")
def is_production_source(cnv_source):
    return cnv_source == "production"


@pytest.fixture(scope="session")
def cnv_source(pytestconfig):
    return pytestconfig.option.cnv_source or "osbs"


@pytest.fixture(scope="session")
def fips_enabled_cluster(workers_utility_pods):
    """
    Check if FIPS is enabled on cluster
    """
    for pod in workers_utility_pods:
        # command output: 0 == fips disabled
        #                 1 == fips enabled
        cluster_fips_status = pod.execute(["bash", "-c", "cat /proc/sys/crypto/fips_enabled"]).strip()
        if int(cluster_fips_status) == 1:
            return True
    return False


@pytest.fixture(scope="class")
def instance_type_for_test_scope_class(namespace, common_instance_type_param_dict):
    instance_type_param_dict = copy.deepcopy(common_instance_type_param_dict)
    instance_type_param_dict["namespace"] = namespace.name
    return VirtualMachineInstancetype(**instance_type_param_dict)


@pytest.fixture(scope="class")
def common_instance_type_param_dict(request):
    common_instance_dict = {
        "name": request.param["name"],
        "cpu": {"guest": request.param.get("preferred_cpu_topology_value", 1)},
        "memory": {"guest": request.param["memory_requests"]},
    }
    if request.param.get("dedicated_cpu_placement"):
        common_instance_dict["cpu"]["dedicated_cpu_placement"] = request.param["dedicated_cpu_placement"]
    if request.param.get("cpu_model"):
        common_instance_dict["cpu"]["model"] = request.param["cpu_model"]
    if request.param.get("cpu_isolate_emulator_thread") is not None:
        common_instance_dict["cpu"]["isolateEmulatorThread"] = request.param["cpu_isolate_emulator_thread"]
    if request.param.get("cpu_numa"):
        common_instance_dict["cpu"]["numa"] = request.param["cpu_numa"]
    if request.param.get("cpu_realtime"):
        common_instance_dict["cpu"]["realtime"] = request.param["cpu_realtime"]
    if request.param.get("cpu_max_sockets"):
        common_instance_dict["cpu"]["maxSockets"] = request.param["cpu_max_sockets"]
    if request.param.get("gpus_list"):
        common_instance_dict["gpus"] = request.param["gpus_list"]
    if request.param.get("host_devices_list"):
        common_instance_dict["host_devices"] = request.param["host_devices_list"]
    if request.param.get("io_thread_policy"):
        common_instance_dict["io_threads_policy"] = request.param["io_thread_policy"]
    if request.param.get("memory_huge_pages"):
        common_instance_dict["memory"]["hugepages"] = request.param["memory_huge_pages"]
    if request.param.get("memory_max_guest"):
        common_instance_dict["memory"]["maxGuest"] = request.param["memory_max_guest"]
    return common_instance_dict


@pytest.fixture(scope="class")
def vm_preference_for_test(namespace, common_vm_preference_param_dict):
    vm_preference_param_dict = copy.deepcopy(common_vm_preference_param_dict)
    vm_preference_param_dict["namespace"] = namespace.name
    return VirtualMachinePreference(**vm_preference_param_dict)


@pytest.fixture(scope="class")
def common_vm_preference_param_dict(request):
    common_preference_dict = {
        "name": request.param["name"],
        "client": request.param.get("client"),
        "teardown": request.param.get("teardown", True),
        "yaml_file": request.param.get("yaml_file"),
    }
    if request.param.get("clock_timezone") or request.param.get("clock_utc_seconds_offset"):
        common_preference_dict["clock"] = {
            "preferredClockOffset": {
                "timezone": request.param.get("clock_timezone"),
                "utc": {"offsetSeconds": request.param.get("clock_utc_seconds_offset")},
            }
        }
    if request.param.get("clock_preferred_timer"):
        common_preference_dict.setdefault("clock", {})["preferredTimer"] = request.param["clock_preferred_timer"]

    if request.param.get("cpu_topology"):
        common_preference_dict["cpu"] = {"preferredCPUTopology": request.param["cpu_topology"]}
    if request.param.get("devices"):
        common_preference_dict["devices"] = request.param["devices"]
    if request.param.get("features"):
        common_preference_dict["features"] = request.param["features"]
    if request.param.get("firmware"):
        common_preference_dict["firmware"] = request.param["firmware"]
    if request.param.get("machine_type"):
        common_preference_dict["machine"] = {"preferredMachineType": request.param["machine_type"]}
    if request.param.get("storage_class"):
        common_preference_dict["volumes"] = {"preferredStorageClassName": request.param["storage_class"]}
    if request.param.get("cpu_spread_option"):
        common_preference_dict.setdefault("cpu", {}).update({"spreadOption": request.param.get("cpu_spread_option")})
    return common_preference_dict


@pytest.fixture(scope="module")
def disabled_default_sources_in_operatorhub_scope_module(admin_client, installing_cnv):
    if installing_cnv:
        yield
    else:
        with disable_default_sources_in_operatorhub(admin_client=admin_client):
            yield


@pytest.fixture(scope="module")
def kmp_deployment(hco_namespace):
    return Deployment(namespace=hco_namespace.name, name=KUBEMACPOOL_MAC_CONTROLLER_MANAGER)


@pytest.fixture(scope="class")
def running_metric_vm(namespace, unprivileged_client):
    name = "running-metrics-vm"
    with VirtualMachineForTests(
        name=name,
        namespace=namespace.name,
        body=fedora_vm_body(name=name),
        client=unprivileged_client,
        network_model=VIRTIO,
    ) as vm:
        running_vm(vm=vm, wait_for_cloud_init=True)
        yield vm


@pytest.fixture()
def vm_from_template_with_existing_dv(
    request,
    unprivileged_client,
    namespace,
    data_volume_scope_function,
):
    """create VM from template using an existing DV (and not a golden image)"""
    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        existing_data_volume=data_volume_scope_function,
    ) as vm:
        yield vm


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


@pytest.fixture(scope="class")
def rhel_vm_with_instance_type_and_preference(
    namespace,
    unprivileged_client,
    instance_type_for_test_scope_class,
    vm_preference_for_test,
):
    with (
        instance_type_for_test_scope_class as vm_instance_type,
        vm_preference_for_test as vm_preference,
    ):
        with VirtualMachineForTests(
            client=unprivileged_client,
            name="rhel-vm-with-instance-type",
            namespace=namespace.name,
            image=Images.Rhel.RHEL9_REGISTRY_GUEST_IMG,
            vm_instance_type=vm_instance_type,
            vm_preference=vm_preference,
        ) as vm:
            yield vm


@pytest.fixture(scope="class")
def vm_from_template_scope_class(
    request,
    unprivileged_client,
    namespace,
    golden_image_data_source_scope_class,
):
    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_source=golden_image_data_source_scope_class,
    ) as vm:
        yield vm


@pytest.fixture(scope="session")
def is_disconnected_cluster():
    # To enable disconnected_cluster pass --tc=disconnected_cluster:True to pytest commandline.
    return py_config.get("disconnected_cluster")


@pytest.fixture()
def migration_policy_with_bandwidth():
    with MigrationPolicy(
        name="migration-policy",
        bandwidth_per_migration="128Ki",
        vmi_selector=MIGRATION_POLICY_VM_LABEL,
    ) as mp:
        yield mp


@pytest.fixture(scope="class")
def migration_policy_with_bandwidth_scope_class():
    with MigrationPolicy(
        name="migration-policy",
        bandwidth_per_migration="128Ki",
        vmi_selector=MIGRATION_POLICY_VM_LABEL,
    ) as mp:
        yield mp


@pytest.fixture(scope="session")
def gpu_nodes(nodes):
    return get_nodes_with_label(nodes=nodes, label="nvidia.com/gpu.present")


@pytest.fixture(scope="session")
def worker_machine1(worker_node1):
    machine = Machine(
        name=worker_node1.machine_name,
        namespace=py_config["machine_api_namespace"],
    )
    if machine.exists:
        return machine
    raise ResourceNotFoundError(f"Machine object for {worker_node1.name} doesn't exists")


@pytest.fixture(scope="session")
def is_idms_cluster():
    return not cluster_with_icsp()


@pytest.fixture(scope="session")
def available_storage_classes_names():
    return [[*sc][0] for sc in py_config["storage_class_matrix"]]


@pytest.fixture(scope="session")
def storage_class_with_filesystem_volume_mode(available_storage_classes_names):
    yield get_storage_class_with_specified_volume_mode(
        volume_mode=DataVolume.VolumeMode.FILE, sc_names=available_storage_classes_names
    )


@pytest.fixture(scope="module")
def skip_test_if_no_block_sc(storage_class_with_block_volume_mode):
    if not storage_class_with_block_volume_mode:
        pytest.skip("Skip the test: no Storage class with Block volume mode")


@pytest.fixture(scope="session")
def storage_class_with_block_volume_mode(available_storage_classes_names):
    yield get_storage_class_with_specified_volume_mode(
        volume_mode=DataVolume.VolumeMode.BLOCK,
        sc_names=available_storage_classes_names,
    )


@pytest.fixture(scope="class")
def vm_for_test(request, namespace, unprivileged_client):
    vm_name = request.param
    with VirtualMachineForTests(
        client=unprivileged_client,
        name=vm_name,
        body=fedora_vm_body(name=vm_name),
        namespace=namespace.name,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture(scope="class")
def rhel_vm_with_instancetype_and_preference_for_cloning(namespace, unprivileged_client):
    with VirtualMachineForCloning(
        name=RHEL_WITH_INSTANCETYPE_AND_PREFERENCE,
        image=Images.Rhel.RHEL9_REGISTRY_GUEST_IMG,
        namespace=namespace.name,
        client=unprivileged_client,
        vm_instance_type=VirtualMachineClusterInstancetype(name=U1_SMALL),
        vm_preference=VirtualMachineClusterPreference(name=RHEL9_PREFERENCE),
        os_flavor=OS_FLAVOR_RHEL,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture(scope="class")
def migrated_vm_multiple_times(request, vm_for_migration_test):
    vmim = []
    for migration_index in range(request.param):
        migration_obj = VirtualMachineInstanceMigration(
            name=f"{vm_for_migration_test.name}-{migration_index}",
            namespace=vm_for_migration_test.namespace,
            vmi_name=vm_for_migration_test.vmi.name,
            teardown=False,
        )
        migration_obj.deploy(wait=True)
        migration_obj.wait_for_status(status=migration_obj.Status.SUCCEEDED, timeout=TIMEOUT_3MIN)
        vmim.append(migration_obj)
        LOGGER.info(f"Migration #{migration_index + 1} done")
    yield
    for mig_obj in vmim:
        mig_obj.clean_up()


@pytest.fixture()
def removed_default_storage_classes(cluster_storage_classes):
    with remove_default_storage_classes(cluster_storage_classes=cluster_storage_classes):
        yield


@pytest.fixture(scope="session")
def csv_related_images_scope_session(csv_scope_session):
    return csv_scope_session.instance.spec.relatedImages


@pytest.fixture()
def hyperconverged_status_templates_scope_function(
    hyperconverged_resource_scope_function,
):
    return hyperconverged_resource_scope_function.instance.to_dict()["status"][SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME]


@pytest.fixture(scope="module")
def hyperconverged_status_templates_scope_module(
    hyperconverged_resource_scope_module,
):
    return hyperconverged_resource_scope_module.instance.to_dict()["status"][SSP_CR_COMMON_TEMPLATES_LIST_KEY_NAME]


@pytest.fixture(scope="class")
def hyperconverged_status_templates_scope_class(
    hyperconverged_resource_scope_class,
):
    return hyperconverged_resource_scope_class.instance.status.dataImportCronTemplates


@pytest.fixture()
def cloning_job_scope_function(request, namespace):
    with create_vm_cloning_job(
        name=f"clone-job-{request.param['source_name']}",
        namespace=namespace.name,
        source_name=request.param["source_name"],
        label_filters=request.param.get("label_filters"),
        annotation_filters=request.param.get("annotation_filters"),
    ) as vmc:
        yield vmc


@pytest.fixture()
def target_vm_scope_function(cloning_job_scope_function):
    with target_vm_from_cloning_job(cloning_job=cloning_job_scope_function) as target_vm:
        yield target_vm


@pytest.fixture(scope="module")
def snapshot_storage_class_name_scope_module(
    storage_class_matrix_snapshot_matrix__module__,
):
    return [*storage_class_matrix_snapshot_matrix__module__][0]


@pytest.fixture(scope="class")
def rhel_vm_with_cluster_instance_type_and_preference(namespace, unprivileged_client):
    with VirtualMachineForTests(
        name="rhel-vm-with-clustertype-resources",
        image=Images.Rhel.RHEL9_REGISTRY_GUEST_IMG,
        namespace=namespace.name,
        client=unprivileged_client,
        vm_instance_type=VirtualMachineClusterInstancetype(
            name=EXPECTED_CLUSTER_INSTANCE_TYPE_LABELS[INSTANCE_TYPE_STR]
        ),
        vm_preference=VirtualMachineClusterPreference(name=EXPECTED_CLUSTER_INSTANCE_TYPE_LABELS[PREFERENCE_STR]),
        os_flavor=OS_FLAVOR_RHEL,
    ) as vm:
        running_vm(
            vm=vm,
            wait_for_interfaces=False,
            ssh_timeout=TIMEOUT_5MIN,
            wait_for_cloud_init=True,
        )
        yield vm


@pytest.fixture(scope="session")
def upgrade_skip_default_sc_setup(pytestconfig):
    return pytestconfig.option.upgrade_skip_default_sc_setup


@pytest.fixture(scope="session")
def updated_default_storage_class_ocs_virt(
    admin_client,
    upgrade_skip_default_sc_setup,
    cluster_storage_classes,
    available_storage_classes_names,
    ocs_storage_class,
    golden_images_namespace,
):
    # set ocs-virt as default storage class if it isn't
    if (
        not upgrade_skip_default_sc_setup
        and ocs_storage_class
        and ocs_storage_class.name in available_storage_classes_names
        and ocs_storage_class.instance.metadata.get("annotations", {}).get(
            StorageClass.Annotations.IS_DEFAULT_VIRT_CLASS
        )
        == "false"
    ):
        boot_source_imported_successfully = False
        with remove_default_storage_classes(cluster_storage_classes=cluster_storage_classes):
            with update_default_sc(default=True, storage_class=ocs_storage_class):
                boot_source_imported_successfully = verify_boot_sources_reimported(
                    admin_client=admin_client,
                    namespace=golden_images_namespace.name,
                )
                if boot_source_imported_successfully:
                    yield

        # on teardown, wait for the original sources to re-create
        verify_boot_sources_reimported(
            admin_client=admin_client,
            namespace=golden_images_namespace.name,
        )
        if not boot_source_imported_successfully:
            exit_pytest_execution(message=f"Failed to set {ocs_storage_class.name} as default storage class")
    else:
        yield


@pytest.fixture(scope="session")
def dvs_for_upgrade(
    admin_client,
    worker_node1,
    rhel_latest_os_params,
    updated_default_storage_class_ocs_virt,
):
    golden_images_namespace_name = py_config["golden_images_namespace"]
    dvs_list = []
    artifactory_secret = utilities.infra.get_artifactory_secret(namespace=golden_images_namespace_name)
    artifactory_config_map = utilities.infra.get_artifactory_config_map(namespace=golden_images_namespace_name)

    for sc in py_config["storage_class_matrix"]:
        storage_class = [*sc][0]
        dv = DataVolume(
            client=admin_client,
            name=f"dv-for-product-upgrade-{storage_class}",
            namespace=golden_images_namespace_name,
            source="http",
            storage_class=storage_class,
            secret=artifactory_secret,
            cert_configmap=artifactory_config_map.name,
            url=rhel_latest_os_params["rhel_image_path"],
            size=rhel_latest_os_params["rhel_dv_size"],
            bind_immediate_annotation=True,
            hostpath_node=(worker_node1.name if sc_is_hpp_with_immediate_volume_binding(sc=storage_class) else None),
            api_name="storage",
        )
        dv.create()
        dvs_list.append(dv)
    for dv in dvs_list:
        dv.wait_for_dv_success()

    yield dvs_list

    for dv in dvs_list:
        dv.clean_up()
    utilities.infra.cleanup_artifactory_secret_and_config_map(
        artifactory_secret=artifactory_secret,
        artifactory_config_map=artifactory_config_map,
    )


@pytest.fixture(scope="class")
def vm_for_migration_test(request, namespace, unprivileged_client, cpu_for_migration):
    vm_name = request.param
    with VirtualMachineForTests(
        client=unprivileged_client,
        name=vm_name,
        body=fedora_vm_body(name=vm_name),
        cpu_model=cpu_for_migration,
        namespace=namespace.name,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture(scope="class")
def ssp_resource_scope_class(admin_client, hco_namespace):
    return get_ssp_resource(admin_client=admin_client, namespace=hco_namespace)


@pytest.fixture(scope="session")
def skip_test_if_no_odf_cephfs_sc(cluster_storage_classes_names):
    """
    Skip test if no odf cephfs storage class available
    """
    if StorageClassNames.CEPHFS not in cluster_storage_classes_names:
        pytest.skip(
            f"Skipping test, {StorageClassNames.CEPHFS} storage class is not deployed,"
            f"deployed storage classes: {cluster_storage_classes_names}"
        )


@pytest.fixture(scope="session")
def sriov_unused_ifaces(sriov_ifaces):
    """
    This fixture returns SRIOV interfaces which are not used. If an interface has
    some VFs in use but still have available VFs, it will be seen as used and will
    not be included in the returned list.
    """
    available_ifaces_list = [interface for interface in sriov_ifaces if not interface.numVfs]
    return available_ifaces_list


@pytest.fixture(scope="session")
def kube_system_namespace():
    kube_system_ns = Namespace(name="kube-system")
    if kube_system_ns.exists:
        return kube_system_ns
    raise ResourceNotFoundError(f"{kube_system_ns.name} namespace not found")


@pytest.fixture(scope="session")
def is_aws_cluster(admin_client):
    return get_cluster_platform(admin_client=admin_client) == Infrastructure.Type.AWS


@pytest.fixture(scope="session")
def skip_on_aws_cluster(is_aws_cluster):
    if is_aws_cluster:
        pytest.skip("This test is skipped on an AWS cluster")


@pytest.fixture()
def cluster_cpu_model_scope_function(
    admin_client,
    hco_namespace,
    hyperconverged_resource_scope_function,
    cluster_common_node_cpu,
):
    with update_cluster_cpu_model(
        admin_client=admin_client,
        hco_namespace=hco_namespace,
        hco_resource=hyperconverged_resource_scope_function,
        cpu_model=cluster_common_node_cpu,
    ):
        yield
    wait_for_kv_stabilize(admin_client=admin_client, hco_namespace=hco_namespace)


@pytest.fixture(scope="module")
def cluster_cpu_model_scope_module(
    admin_client,
    hco_namespace,
    hyperconverged_resource_scope_module,
    cluster_common_node_cpu,
):
    with update_cluster_cpu_model(
        admin_client=admin_client,
        hco_namespace=hco_namespace,
        hco_resource=hyperconverged_resource_scope_module,
        cpu_model=cluster_common_node_cpu,
    ):
        yield
    wait_for_kv_stabilize(admin_client=admin_client, hco_namespace=hco_namespace)


@pytest.fixture(scope="class")
def cluster_cpu_model_scope_class(
    admin_client,
    hco_namespace,
    hyperconverged_resource_scope_class,
    cluster_common_node_cpu,
):
    with update_cluster_cpu_model(
        admin_client=admin_client,
        hco_namespace=hco_namespace,
        hco_resource=hyperconverged_resource_scope_class,
        cpu_model=cluster_common_node_cpu,
    ):
        yield
    wait_for_kv_stabilize(admin_client=admin_client, hco_namespace=hco_namespace)


@pytest.fixture(scope="class")
def cluster_modern_cpu_model_scope_class(
    admin_client,
    hco_namespace,
    hyperconverged_resource_scope_class,
    cluster_common_modern_node_cpu,
):
    with update_cluster_cpu_model(
        admin_client=admin_client,
        hco_namespace=hco_namespace,
        hco_resource=hyperconverged_resource_scope_class,
        cpu_model=cluster_common_modern_node_cpu,
    ):
        yield
    wait_for_kv_stabilize(admin_client=admin_client, hco_namespace=hco_namespace)


@pytest.fixture(scope="module")
def machine_type_from_kubevirt_config(kubevirt_config_scope_module, nodes_cpu_architecture):
    """Extract machine type default from kubevirt CR."""
    return kubevirt_config_scope_module["architectureConfiguration"][nodes_cpu_architecture]["machineType"]


@pytest.fixture(scope="module")
def skip_if_no_cpumanager_workers(schedulable_nodes):
    if not any([node.labels.cpumanager == "true" for node in schedulable_nodes]):
        pytest.skip("Test should run on cluster with CPU Manager")


@pytest.fixture(scope="module")
def latest_osinfo_db_file_name(osinfo_repo):
    sorted_osinfo_repo = f"{osinfo_repo}/?C=M;O=A"
    soup_page = BeautifulSoup(
        markup=requests.get(sorted_osinfo_repo, headers=get_artifactory_header(), verify=False).text,
        features="html.parser",
    )
    full_link = soup_page.findAll(name="a", attrs={"href": re.compile(r"osinfo-db-[0-9]*.tar.xz")})

    assert full_link, "No osinfo-db file was found."

    return full_link[-1].get("href")


@pytest.fixture(scope="module")
def osinfo_repo():
    return f"{py_config['servers']['https_server']}/cnv-tests/osinfo-db/"


@pytest.fixture(scope="module")
def downloaded_latest_libosinfo_db(tmpdir_factory, latest_osinfo_db_file_name, osinfo_repo):
    """Obtain the osinfo path."""
    osinfo_path = tmpdir_factory.mktemp("osinfodb")
    download_and_extract_tar(
        tarfile_url=f"{osinfo_repo}{latest_osinfo_db_file_name}",
        dest_path=osinfo_path,
    )
    osinfo_db_file_name_no_suffix = latest_osinfo_db_file_name.partition(".")[0]
    yield os.path.join(osinfo_path, osinfo_db_file_name_no_suffix)


@pytest.fixture(scope="session")
def rwx_fs_available_storage_classes_names(cluster_storage_classes_names):
    return [
        storage_class
        for storage_class in cluster_storage_classes_names
        if storage_class in RWX_FS_STORAGE_CLASS_NAMES_LIST
    ]


@pytest.fixture(scope="session")
def rhsm_credentials_from_bitwarden():
    return get_cnv_tests_secret_by_name(secret_name="RHSM_CREDENTIALS")


@pytest.fixture(scope="module")
def rhsm_created_secret(rhsm_credentials_from_bitwarden, namespace):
    with Secret(
        name=RHSM_SECRET_NAME,
        namespace=namespace.name,
        data_dict={
            "username": base64_encode_str(text=rhsm_credentials_from_bitwarden["user"]),
            "password": base64_encode_str(text=rhsm_credentials_from_bitwarden["password"]),
        },
    ) as secret:
        yield secret


@pytest.fixture(scope="session")
def machine_config_pools():
    return [
        get_machine_config_pool_by_name(mcp_name="master"),
        get_machine_config_pool_by_name(mcp_name="worker"),
    ]


@pytest.fixture(scope="session")
def nmstate_namespace(admin_client, nmstate_required):
    if nmstate_required:
        return Namespace(client=admin_client, name="openshift-nmstate", ensure_exists=True)

    return None


@pytest.fixture()
def ipv6_single_stack_cluster(ipv4_supported_cluster, ipv6_supported_cluster):
    return ipv6_supported_cluster and not ipv4_supported_cluster


@pytest.fixture(scope="class")
def ping_process_in_rhel_os():
    def _start_ping(vm):
        return start_and_fetch_processid_on_linux_vm(
            vm=vm,
            process_name="ping",
            args="localhost",
        )

    return _start_ping


@pytest.fixture(scope="module")
def smbios_from_kubevirt_config(kubevirt_config_scope_module):
    """Extract SMBIOS default from kubevirt CR."""
    return kubevirt_config_scope_module["smbios"]


@pytest.fixture(scope="session")
def nmstate_required(admin_client):
    return get_cluster_platform(admin_client=admin_client) in ("BareMetal", "OpenStack")


@pytest.fixture(scope="session")
def conformance_tests(request):
    return (
        (marker_args := request.config.getoption("-m"))
        and "conformance" in marker_args
        and "not conformance" not in marker_args
    )


@pytest.fixture(scope="module")
def updated_namespace_with_aaq_label(admin_client, namespace):
    label_project(name=namespace.name, label=AAQ_NAMESPACE_LABEL, admin_client=admin_client)


@pytest.fixture(scope="class")
def application_aware_resource_quota(admin_client, namespace):
    with ApplicationAwareResourceQuota(
        client=admin_client,
        name="application-aware-resource-quota-for-aaq-test",
        namespace=namespace.name,
        hard=ARQ_QUOTA_HARD_SPEC,
    ) as arq:
        yield arq

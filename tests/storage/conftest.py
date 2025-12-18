# -*- coding: utf-8 -*-

"""
Pytest conftest file for CNV CDI tests
"""

import base64
import logging
import os
import ssl

import pytest
from kubernetes.dynamic.exceptions import ResourceNotFoundError
from ocp_resources.cdi import CDI
from ocp_resources.config_map import ConfigMap
from ocp_resources.csi_driver import CSIDriver
from ocp_resources.data_source import DataSource
from ocp_resources.deployment import Deployment
from ocp_resources.exceptions import ExecOnPodError
from ocp_resources.resource import ResourceEditor
from ocp_resources.route import Route
from ocp_resources.secret import Secret
from ocp_resources.storage_class import StorageClass
from ocp_resources.virtual_machine_cluster_instancetype import (
    VirtualMachineClusterInstancetype,
)
from ocp_resources.virtual_machine_cluster_preference import (
    VirtualMachineClusterPreference,
)
from ocp_resources.virtual_machine_snapshot import VirtualMachineSnapshot
from pytest_testconfig import config as py_config
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.storage.constants import (
    CIRROS_QCOW2_IMG,
    HPP_STORAGE_CLASSES,
    HTTPS_CONFIG_MAP_NAME,
    INTERNAL_HTTP_CONFIGMAP_NAME,
)
from tests.storage.utils import (
    HttpService,
    check_snapshot_indication,
    get_hpp_daemonset,
    hpp_cr_suffix,
    is_hpp_cr_legacy,
)
from tests.utils import create_cirros_vm
from utilities.constants import (
    CDI_OPERATOR,
    CDI_UPLOADPROXY,
    CNV_TEST_SERVICE_ACCOUNT,
    CNV_TESTS_CONTAINER,
    OS_FLAVOR_RHEL,
    RHEL10_PREFERENCE,
    SECURITY_CONTEXT,
    TIMEOUT_1MIN,
    TIMEOUT_5SEC,
    U1_SMALL,
    Images,
)
from utilities.hco import (
    ResourceEditorValidateHCOReconcile,
    hco_cr_jsonpatch_annotations_dict,
)
from utilities.infra import (
    INTERNAL_HTTP_SERVER_ADDRESS,
    ExecCommandOnPod,
    get_artifactory_config_map,
    get_artifactory_secret,
)
from utilities.storage import data_volume_template_with_source_ref_dict, get_downloaded_artifact, write_file_via_ssh
from utilities.virt import VirtualMachineForTests, running_vm

LOGGER = logging.getLogger(__name__)
LOCAL_PATH = f"/tmp/{Images.Cdi.QCOW2_IMG}"
ROUTER_CERT_NAME = "router.crt"
INTERNAL_HTTP_SELECTOR = {"matchLabels": {"name": "internal-http"}}
INTERNAL_HTTP_TEMPLATE = {
    "metadata": {
        "labels": {
            "name": "internal-http",
            "cdi.kubevirt.io/testing": "",
        }
    },
    "spec": {
        "terminationGracePeriodSeconds": 0,
        "containers": [
            {
                "name": "http",
                "image": "quay.io/openshift-cnv/qe-cnv-tests-internal-http:v1.1.0",
                "imagePullPolicy": "Always",
                "command": ["/usr/sbin/nginx"],
                "readinessProbe": {
                    "httpGet": {"path": "/", "port": 80},
                    "initialDelaySeconds": 20,
                    "periodSeconds": 20,
                },
                SECURITY_CONTEXT: {"privileged": True},
                "livenessProbe": {
                    "httpGet": {"path": "/", "port": 80},
                    "initialDelaySeconds": 20,
                    "periodSeconds": 20,
                },
            }
        ],
        "serviceAccount": CNV_TEST_SERVICE_ACCOUNT,
        "serviceAccountName": CNV_TEST_SERVICE_ACCOUNT,
    },
}


@pytest.fixture()
def hpp_resources(request, admin_client):
    rcs_object = request.param
    LOGGER.info(f"Get all resources with kind: {rcs_object.kind}")
    resource_list = list(rcs_object.get(dyn_client=admin_client))
    return [rcs for rcs in resource_list if rcs.name.startswith("hostpath-")]


@pytest.fixture(scope="module")
def internal_http_configmap(namespace, internal_http_service, workers_utility_pods, worker_node1):
    svc_ip = internal_http_service.instance.to_dict()["spec"]["clusterIP"]

    def _fetch_cert():
        try:
            return ExecCommandOnPod(utility_pods=workers_utility_pods, node=worker_node1).exec(
                command=(
                    f"openssl s_client -showcerts -connect {svc_ip}:443 </dev/null 2>/dev/null | "
                    "sed -n '/-----BEGIN/,/-----END/p'"
                )
            )
        except ExecOnPodError:
            return None

    try:
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_1MIN,
            sleep=TIMEOUT_5SEC,
            func=_fetch_cert,
        ):
            if sample:
                with ConfigMap(
                    name=INTERNAL_HTTP_CONFIGMAP_NAME,
                    namespace=namespace.name,
                    data={"tlsregistry.crt": sample},
                ) as configmap:
                    yield configmap
                break

    except TimeoutExpiredError:
        LOGGER.error(f"Timeout while fetching cert from {svc_ip}")
        raise


@pytest.fixture(scope="module")
def internal_http_secret(namespace):
    with Secret(
        name="internal-http-secret",
        namespace=namespace.name,
        accesskeyid="YWRtaW4=",
        secretkey="cGFzc3dvcmQ=",
    ) as secret:
        yield secret


@pytest.fixture(scope="session")
def internal_http_deployment(cnv_tests_utilities_namespace):
    """
    Deploy internal HTTP server Deployment into the cnv_tests_utilities_namespace namespace.
    This Deployment deploys a pod that runs an HTTP server
    """
    with Deployment(
        name="internal-http",
        namespace=cnv_tests_utilities_namespace.name,
        selector=INTERNAL_HTTP_SELECTOR,
        template=INTERNAL_HTTP_TEMPLATE,
        replicas=1,
    ) as dep:
        dep.wait_for_replicas()
        yield dep


@pytest.fixture(scope="session")
def internal_http_service(cnv_tests_utilities_namespace, internal_http_deployment):
    with HttpService(name=internal_http_deployment.name, namespace=cnv_tests_utilities_namespace.name) as svc:
        yield svc


@pytest.fixture(scope="session")
def images_internal_http_server(internal_http_deployment, internal_http_service):
    return {
        "http": f"http://{INTERNAL_HTTP_SERVER_ADDRESS}/",
        "https": f"https://{INTERNAL_HTTP_SERVER_ADDRESS}/",
        "http_auth": f"http://{INTERNAL_HTTP_SERVER_ADDRESS}:81/",
    }


@pytest.fixture()
def upload_proxy_route(admin_client):
    routes = Route.get(dyn_client=admin_client)
    upload_route = None
    for route in routes:
        if route.exposed_service == CDI_UPLOADPROXY:
            upload_route = route
    assert upload_route is not None
    yield upload_route


@pytest.fixture(scope="session")
def skip_test_if_no_hpp_sc(cluster_storage_classes):
    existing_hpp_sc = [sc.name for sc in cluster_storage_classes if sc.name in HPP_STORAGE_CLASSES]
    if not existing_hpp_sc:
        pytest.skip(f"This test runs only on one of the hpp storage classes: {HPP_STORAGE_CLASSES}")


@pytest.fixture()
def uploadproxy_route_deleted(hco_namespace):
    """
    Delete uploadproxy route from kubevirt-hyperconverged namespace.

    This scales down cdi-operator replicas to 0 so that the route is not auto-created by the cdi-operator pod.
    Once the cdi-operator is terminated, route is deleted to perform the test.
    """
    ns = hco_namespace.name
    deployment = Deployment(name=CDI_OPERATOR, namespace=ns)
    try:
        deployment.scale_replicas(replica_count=0)
        deployment.wait_for_replicas(deployed=False)
        Route(name=CDI_UPLOADPROXY, namespace=ns).delete(wait=True)
        yield
    finally:
        deployment.scale_replicas(replica_count=1)
        deployment.wait_for_replicas()
        Route(name=CDI_UPLOADPROXY, namespace=ns).wait()


@pytest.fixture()
def cdi_config_upload_proxy_overridden(
    hco_namespace,
    hyperconverged_resource_scope_function,
    cdi_config,
    new_route_created,
):
    with ResourceEditorValidateHCOReconcile(
        patches={
            hyperconverged_resource_scope_function: hco_cr_jsonpatch_annotations_dict(
                component="cdi",
                path="uploadProxyURLOverride",
                value=new_route_created.host,
            )
        },
        list_resource_reconcile=[CDI],
    ):
        cdi_config.wait_until_upload_url_changed(uploadproxy_url=new_route_created.host)
        yield


@pytest.fixture()
def new_route_created(hco_namespace):
    existing_route = Route(name=CDI_UPLOADPROXY, namespace=hco_namespace.name)
    route = Route(
        name="newuploadroute-cdi",
        namespace=hco_namespace.name,
        destination_ca_cert=existing_route.ca_cert,
        service=CDI_UPLOADPROXY,
    )
    route.create(wait=True)
    yield route
    route.delete(wait=True)


@pytest.fixture(scope="session")
def https_server_certificate():
    yield ssl.get_server_certificate(addr=(py_config["server_url"], 443))


@pytest.fixture()
def https_config_map(request, namespace, https_server_certificate):
    data = {"ca.pem": request.param["data"]} if hasattr(request, "param") else {"ca.pem": https_server_certificate}
    with ConfigMap(
        name=HTTPS_CONFIG_MAP_NAME,
        namespace=namespace.name,
        data=data,
    ) as configmap:
        yield configmap


@pytest.fixture()
def download_image():
    get_downloaded_artifact(remote_name=f"{Images.Cdi.DIR}/{Images.Cdi.QCOW2_IMG}", local_name=LOCAL_PATH)


def _skip_block_volumemode(storage_class_matrix):
    storage_class = [*storage_class_matrix][0]
    if storage_class_matrix[storage_class]["volume_mode"] == "Block":
        pytest.skip("Test is not supported on Block volume mode")


@pytest.fixture(scope="module")
def skip_block_volumemode_scope_module(storage_class_matrix__module__):
    _skip_block_volumemode(storage_class_matrix=storage_class_matrix__module__)


@pytest.fixture()
def default_fs_overhead(cdi_config):
    return float(cdi_config.instance.status.filesystemOverhead["global"])


@pytest.fixture()
def unset_predefined_scratch_sc(hyperconverged_resource_scope_module, cdi_config):
    if cdi_config.instance.spec.scratchSpaceStorageClass:
        empty_scratch_space_spec = {"spec": {"scratchSpaceStorageClass": ""}}
        with ResourceEditorValidateHCOReconcile(
            patches={hyperconverged_resource_scope_module: empty_scratch_space_spec},
            list_resource_reconcile=[CDI],
        ):
            LOGGER.info(f"wait for {empty_scratch_space_spec} in CDIConfig")
            for sample in TimeoutSampler(
                wait_timeout=20,
                sleep=1,
                func=lambda: not cdi_config.instance.spec.scratchSpaceStorageClass,
            ):
                if sample:
                    break
            yield
    else:
        yield


@pytest.fixture()
def default_sc_as_fallback_for_scratch(unset_predefined_scratch_sc, admin_client, cdi_config, default_sc):
    # Based on py_config["default_storage_class"], update default SC, if needed
    if default_sc:
        yield default_sc
    else:
        for sc in StorageClass.get(dyn_client=admin_client, name=py_config["default_storage_class"]):
            assert sc, f"The cluster does not include {py_config['default_storage_class']} storage class"
            with ResourceEditor(
                patches={
                    sc: {
                        "metadata": {
                            "annotations": {StorageClass.Annotations.IS_DEFAULT_CLASS: "true"},
                            "name": sc.name,
                        }
                    }
                }
            ):
                yield sc


@pytest.fixture()
def router_cert_secret(admin_client):
    router_secret = "router-certs-default"
    for secret in Secret.get(
        dyn_client=admin_client,
        name=router_secret,
        namespace="openshift-ingress",
    ):
        return secret
    raise ResourceNotFoundError(f"secret: {router_secret} not found")


@pytest.fixture()
def temp_router_cert(tmpdir, router_cert_secret):
    router_cert_path = f"{tmpdir}/{ROUTER_CERT_NAME}"
    with open(router_cert_path, "w") as the_file:
        the_file.write((base64.standard_b64decode(router_cert_secret.instance.data["tls.crt"])).decode("utf-8"))
    yield router_cert_path


@pytest.fixture()
def xfail_if_running_from_container():
    if os.environ.get(CNV_TESTS_CONTAINER):
        pytest.xfail("Skipping the test because it's running from the container")


@pytest.fixture()
def enabled_ca(xfail_if_running_from_container, temp_router_cert):
    update_ca_trust_command = "sudo update-ca-trust"
    ca_path = "/etc/pki/ca-trust/source/anchors/"
    # copy to the trusted secure list and update
    os.popen(f"sudo cp {temp_router_cert} {ca_path}")
    os.popen(update_ca_trust_command)
    yield
    os.popen(f"sudo rm {ca_path}{ROUTER_CERT_NAME}")
    os.popen(update_ca_trust_command)


@pytest.fixture(scope="module")
def is_hpp_cr_legacy_scope_module(hostpath_provisioner_scope_module):
    return is_hpp_cr_legacy(hostpath_provisioner=hostpath_provisioner_scope_module)


@pytest.fixture(scope="session")
def is_hpp_cr_legacy_scope_session(hostpath_provisioner_scope_session):
    return is_hpp_cr_legacy(hostpath_provisioner=hostpath_provisioner_scope_session)


@pytest.fixture(scope="module")
def hpp_cr_suffix_scope_module(is_hpp_cr_legacy_scope_module):
    return hpp_cr_suffix(is_hpp_cr_legacy=is_hpp_cr_legacy_scope_module)


@pytest.fixture(scope="session")
def hpp_cr_suffix_scope_session(is_hpp_cr_legacy_scope_session):
    return hpp_cr_suffix(is_hpp_cr_legacy=is_hpp_cr_legacy_scope_session)


@pytest.fixture(scope="session")
def hpp_daemonset_scope_session(hco_namespace, hpp_cr_suffix_scope_session):
    yield get_hpp_daemonset(hco_namespace=hco_namespace, hpp_cr_suffix=hpp_cr_suffix_scope_session)


@pytest.fixture(scope="module")
def hpp_daemonset_scope_module(hco_namespace, hpp_cr_suffix_scope_module):
    yield get_hpp_daemonset(hco_namespace=hco_namespace, hpp_cr_suffix=hpp_cr_suffix_scope_module)


@pytest.fixture()
def rhel_vm_name(request):
    return request.param["vm_name"]


@pytest.fixture(scope="session")
def available_hpp_storage_class(skip_test_if_no_hpp_sc, cluster_storage_classes):
    """
    Get an HPP storage class if there is any in the cluster
    """
    for storage_class in cluster_storage_classes:
        if storage_class.name in HPP_STORAGE_CLASSES:
            return storage_class


@pytest.fixture(scope="module")
def artifactory_secret_scope_module(namespace):
    artifactory_secret = get_artifactory_secret(namespace=namespace.name)
    yield artifactory_secret
    if artifactory_secret:
        artifactory_secret.clean_up()


@pytest.fixture(scope="module")
def artifactory_config_map_scope_module(namespace):
    artifactory_config_map = get_artifactory_config_map(namespace=namespace.name)
    yield artifactory_config_map
    if artifactory_config_map:
        artifactory_config_map.clean_up()


@pytest.fixture()
def rhel_vm_for_snapshot(
    admin_client,
    namespace,
    rhel_vm_name,
    rhel10_data_source_scope_session,
    snapshot_storage_class_name_scope_module,
):
    """Create a RHEL VM with using DataSource that supports snapshots"""
    with VirtualMachineForTests(
        name=rhel_vm_name,
        namespace=namespace.name,
        client=admin_client,
        os_flavor=OS_FLAVOR_RHEL,
        vm_instance_type=VirtualMachineClusterInstancetype(client=admin_client, name=U1_SMALL),
        vm_preference=VirtualMachineClusterPreference(client=admin_client, name=RHEL10_PREFERENCE),
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=rhel10_data_source_scope_session,
            storage_class=snapshot_storage_class_name_scope_module,
        ),
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture()
def snapshot_with_content(
    request,
    namespace,
    admin_client,
    rhel_vm_for_snapshot,
):
    """
    Creates a requested number of snapshots with content
    The default behavior of the fixture is creating an offline
    snapshot unless {online_vm = True} declared in the test
    """
    vm_snapshots = []
    is_online_test = request.param.get("online_vm", False)
    for idx in range(request.param["number_of_snapshots"]):
        index = idx + 1
        before_snap_index = f"before-snap-{index}"
        running_vm(vm=rhel_vm_for_snapshot)
        write_file_via_ssh(vm=rhel_vm_for_snapshot, filename=f"{before_snap_index}.txt", content=before_snap_index)
        if not is_online_test:
            rhel_vm_for_snapshot.stop(wait=True)
        with VirtualMachineSnapshot(
            name=f"snapshot-{rhel_vm_for_snapshot.name}-number-{index}",
            namespace=rhel_vm_for_snapshot.namespace,
            vm_name=rhel_vm_for_snapshot.name,
            client=admin_client,
            teardown=False,
        ) as vm_snapshot:
            vm_snapshots.append(vm_snapshot)
            vm_snapshot.wait_snapshot_done()
            after_snap_index = f"after-snap-{index}"
            running_vm(vm=rhel_vm_for_snapshot)
            write_file_via_ssh(vm=rhel_vm_for_snapshot, filename=f"{after_snap_index}.txt", content=after_snap_index)
            if not is_online_test:
                rhel_vm_for_snapshot.stop(wait=True)
    check_snapshot_indication(snapshot=vm_snapshot, is_online=is_online_test)
    yield vm_snapshots

    for vm_snapshot in vm_snapshots:
        vm_snapshot.clean_up()


@pytest.fixture(scope="module")
def downloaded_cirros_image_full_path(tmpdir_factory):
    return tmpdir_factory.mktemp("wffc_upload").join(Images.Cirros.QCOW2_IMG)


@pytest.fixture(scope="module")
def downloaded_cirros_image_scope_class(downloaded_cirros_image_full_path):
    get_downloaded_artifact(
        remote_name=CIRROS_QCOW2_IMG,
        local_name=downloaded_cirros_image_full_path,
    )


@pytest.fixture()
def multi_storage_cirros_vm(request, namespace, unprivileged_client, storage_class_name_scope_function):
    with create_cirros_vm(
        storage_class=storage_class_name_scope_function,
        namespace=namespace.name,
        client=unprivileged_client,
        dv_name=f"{request.param['dv_name']}-{storage_class_name_scope_function}",
        vm_name=request.param["vm_name"],
        annotations=request.param.get("annotations"),
    ) as vm:
        yield vm


@pytest.fixture()
def data_volume_template_metadata(multi_storage_cirros_vm):
    return multi_storage_cirros_vm.data_volume_template["metadata"]


@pytest.fixture()
def storage_class_name_scope_function(storage_class_matrix__function__):
    return [*storage_class_matrix__function__][0]


@pytest.fixture(scope="module")
def storage_class_name_scope_module(storage_class_matrix__module__):
    return [*storage_class_matrix__module__][0]


@pytest.fixture(scope="module")
def storage_class_name_immediate_binding_scope_module(storage_class_matrix_immediate_matrix__module__):
    return [*storage_class_matrix_immediate_matrix__module__][0]


@pytest.fixture(scope="session")
def cluster_csi_drivers_names():
    yield [csi_driver.name for csi_driver in list(CSIDriver.get())]


@pytest.fixture(scope="module")
def rhel10_data_source_scope_module(golden_images_namespace):
    return DataSource(
        namespace=golden_images_namespace.name,
        name="rhel10",
        client=golden_images_namespace.client,
        ensure_exists=True,
    )

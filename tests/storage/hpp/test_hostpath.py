# -*- coding: utf-8 -*-

"""
Hostpath Provisioner test suite
"""

import logging
from multiprocessing.pool import ThreadPool

import pytest
from ocp_resources.cluster_role import ClusterRole
from ocp_resources.cluster_role_binding import ClusterRoleBinding
from ocp_resources.custom_resource_definition import CustomResourceDefinition
from ocp_resources.datavolume import DataVolume
from ocp_resources.deployment import Deployment
from ocp_resources.hostpath_provisioner import HostPathProvisioner
from ocp_resources.persistent_volume import PersistentVolume
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_resources.pod import Pod
from ocp_resources.prometheus_rule import PrometheusRule
from ocp_resources.resource import Resource
from ocp_resources.role import Role
from ocp_resources.role_binding import RoleBinding
from ocp_resources.security_context_constraints import SecurityContextConstraints
from ocp_resources.service import Service
from ocp_resources.service_account import ServiceAccount
from ocp_resources.service_monitor import ServiceMonitor
from ocp_resources.storage_class import StorageClass
from ocp_resources.template import Template
from pytest_testconfig import config as py_config
from timeout_sampler import TimeoutSampler

import tests.storage.utils as storage_utils
from tests.os_params import RHEL_LATEST
from tests.storage.constants import HPP_STORAGE_CLASSES
from utilities.constants import (
    CDI_UPLOAD,
    CDI_UPLOAD_TMP_PVC,
    HOSTPATH_PROVISIONER_OPERATOR,
    HPP_POOL,
    TIMEOUT_1MIN,
    TIMEOUT_2MIN,
    TIMEOUT_3MIN,
    TIMEOUT_5MIN,
    TIMEOUT_10MIN,
    TIMEOUT_20SEC,
    TIMEOUT_30SEC,
    Images,
)
from utilities.infra import get_http_image_url, get_pod_by_name_prefix
from utilities.storage import (
    PodWithPVC,
    check_disk_count_in_vm,
    check_upload_virtctl_result,
    create_dv,
    get_containers_for_pods_with_pvc,
    get_downloaded_artifact,
    get_test_artifact_server_url,
    sc_volume_binding_mode_is_wffc,
    virtctl_upload_dv,
)
from utilities.virt import VirtualMachineForTestsFromTemplate, running_vm

LOGGER = logging.getLogger(__name__)

HOSTPATH_PROVISIONER_ADMIN = "hostpath-provisioner-admin"
VOLUME_BINDING_MODE = "volumeBindingMode"

pytestmark = pytest.mark.usefixtures("skip_test_if_no_hpp_sc")


def skipped_hco_resources():
    hpp_operator_service = f"{HOSTPATH_PROVISIONER_OPERATOR}-service"
    return {
        "ServiceAccount": [HOSTPATH_PROVISIONER_OPERATOR],
        "Role": [f"{hpp_operator_service}-cert"],
        "Service": [hpp_operator_service],
        "RoleBinding": [
            f"{hpp_operator_service}-auth-reader",
            f"{hpp_operator_service}-cert",
        ],
        "ClusterRoleBinding": [f"{hpp_operator_service}-system:auth-delegator"],
    }


def verify_hpp_app_label(hpp_resources, cnv_version):
    hco_resources_to_skip = skipped_hco_resources()
    for resource in hpp_resources:
        if resource.name in hco_resources_to_skip.get(resource.kind, []):
            LOGGER.info(
                f"Test skipped: {resource.kind}:{resource.name}, "
                "labels determined by HCO and do not contain the required labels"
            )
            continue
        else:
            assert resource.labels[f"{Resource.ApiGroup.APP_KUBERNETES_IO}/component"] == "storage", (
                f"Missing label {Resource.ApiGroup.APP_KUBERNETES_IO}/component for {resource.name}"
            )
            assert resource.labels[f"{Resource.ApiGroup.APP_KUBERNETES_IO}/part-of"] == "hyperconverged-cluster", (
                f"Missing label {Resource.ApiGroup.APP_KUBERNETES_IO}/part-of for {resource.name}"
            )
            assert resource.labels[f"{Resource.ApiGroup.APP_KUBERNETES_IO}/version"] == cnv_version, (
                f"Missing label {Resource.ApiGroup.APP_KUBERNETES_IO}/version for {resource.name}"
            )
            if resource.name.startswith(HOSTPATH_PROVISIONER_OPERATOR):
                assert resource.labels[f"{resource.ApiGroup.APP_KUBERNETES_IO}/managed-by"] == "olm", (
                    f"Missing label {Resource.ApiGroup.APP_KUBERNETES_IO}/managed-by for {resource.name}"
                )
            else:
                assert (
                    resource.labels[f"{resource.ApiGroup.APP_KUBERNETES_IO}/managed-by"]
                    == HOSTPATH_PROVISIONER_OPERATOR
                ), f"Missing label {Resource.ApiGroup.APP_KUBERNETES_IO}/managed-by for {resource.name}"


@pytest.fixture(scope="module")
def skip_when_hpp_no_immediate(storage_class_matrix_hpp_matrix__module__):
    storage_class = [*storage_class_matrix_hpp_matrix__module__][0]
    volume_binding_mode = StorageClass(name=storage_class).instance[VOLUME_BINDING_MODE]
    if volume_binding_mode != StorageClass.VolumeBindingMode.Immediate:
        pytest.skip(
            f"Test only runs when volumeBindingMode is Immediate, but '{storage_class}' has '{volume_binding_mode}'"
        )


@pytest.fixture(scope="module")
def hpp_operator_deployment(hco_namespace):
    hpp_operator_deployment = Deployment(name=HOSTPATH_PROVISIONER_OPERATOR, namespace=hco_namespace.name)
    assert hpp_operator_deployment.exists
    return hpp_operator_deployment


@pytest.fixture(scope="module")
def skip_when_cdiconfig_scratch_no_hpp(cdi_config):
    if cdi_config.scratch_space_storage_class_from_status not in HPP_STORAGE_CLASSES:
        pytest.skip("scratchSpaceStorageClass of cdiconfig is not HPP")


@pytest.fixture(scope="module")
def hpp_prometheus_resources(hco_namespace):
    rbac_name = "hostpath-provisioner-monitoring"
    yield [
        PrometheusRule(name="prometheus-hpp-rules", namespace=hco_namespace.name),
        ServiceMonitor(name="service-monitor-hpp", namespace=hco_namespace.name),
        Service(name="hpp-prometheus-metrics", namespace=hco_namespace.name),
        Role(name=rbac_name, namespace=hco_namespace.name),
        RoleBinding(name=rbac_name, namespace=hco_namespace.name),
    ]


@pytest.fixture(scope="module")
def hpp_clusterrole_version_suffix(is_hpp_cr_legacy_scope_module):
    return "" if is_hpp_cr_legacy_scope_module else "-admin-csi"


@pytest.fixture(scope="module")
def hpp_serviceaccount(hco_namespace, hpp_cr_suffix_scope_module):
    yield ServiceAccount(
        name=f"{HOSTPATH_PROVISIONER_ADMIN}{hpp_cr_suffix_scope_module}",
        namespace=hco_namespace.name,
    )


@pytest.fixture(scope="module")
def hpp_scc(hpp_cr_suffix_scope_module):
    yield SecurityContextConstraints(
        name=f"{HostPathProvisioner.Name.HOSTPATH_PROVISIONER}{hpp_cr_suffix_scope_module}"
    )


@pytest.fixture(scope="module")
def hpp_clusterrole(hpp_clusterrole_version_suffix):
    yield ClusterRole(name=f"{HostPathProvisioner.Name.HOSTPATH_PROVISIONER}{hpp_clusterrole_version_suffix}")


@pytest.fixture(scope="module")
def hpp_clusterrolebinding(hpp_clusterrole_version_suffix):
    yield ClusterRoleBinding(name=f"{HostPathProvisioner.Name.HOSTPATH_PROVISIONER}{hpp_clusterrole_version_suffix}")


@pytest.fixture(scope="module")
def hpp_operator_pod(admin_client, hco_namespace):
    yield get_pod_by_name_prefix(
        dyn_client=admin_client,
        pod_prefix=HOSTPATH_PROVISIONER_OPERATOR,
        namespace=hco_namespace.name,
    )


@pytest.fixture()
def dv_kwargs(request, namespace, worker_node1, storage_class_matrix_hpp_matrix__module__):
    return {
        "dv_name": request.param.get("name"),
        "namespace": namespace.name,
        "url": request.param.get(
            "url",
            f"{get_test_artifact_server_url()}{py_config['latest_fedora_os_dict']['image_path']}",
        ),
        "size": request.param.get("size", Images.Fedora.DEFAULT_DV_SIZE),
        "storage_class": [*storage_class_matrix_hpp_matrix__module__][0],
        "hostpath_node": worker_node1.name,
    }


@pytest.fixture(scope="module")
def hpp_pool_deployments_scope_module(admin_client, hco_namespace):
    return [
        dp
        for dp in Deployment.get(dyn_client=admin_client, namespace=hco_namespace.name)
        if dp.name.startswith(HPP_POOL)
    ]


def verify_image_location_via_dv_pod_with_pvc(dv, worker_node_name):
    dv.wait_for_dv_success()
    with PodWithPVC(
        namespace=dv.namespace,
        name=f"{dv.name}-pod",
        pvc_name=dv.pvc.name,
        containers=get_containers_for_pods_with_pvc(volume_mode=dv.volume_mode, pvc_name=dv.pvc.name),
    ) as pod:
        pod.wait_for_status(status="Running")
        LOGGER.debug("Check pod location...")
        assert pod.instance["spec"]["nodeName"] == worker_node_name
        LOGGER.debug("Check image location...")
        storage_utils.assert_disk_img(pod=pod)


def assert_provision_on_node_annotation(pvc, node_name, type_):
    provision_on_node = "kubevirt.io/provisionOnNode"
    assert pvc.instance.metadata.annotations.get(provision_on_node) == node_name
    f"No '{provision_on_node}' annotation found on {type_} PVC / node names differ"


def assert_selected_node_annotation(pvc_node_name, pod_node_name, type_="source"):
    assert pvc_node_name == pod_node_name, (
        f"No 'volume.kubernetes.io/selected-node' annotation found on {type_} PVC / node names differ"
    )


def _get_pod_and_scratch_pvc(dyn_client, namespace, pod_prefix, pvc_suffix):
    pvcs = list(PersistentVolumeClaim.get(dyn_client=dyn_client, namespace=namespace))
    matched_pvcs = [pvc for pvc in pvcs if pvc.name.endswith(pvc_suffix)]
    matched_pod = get_pod_by_name_prefix(dyn_client=dyn_client, pod_prefix=pod_prefix, namespace=namespace)
    return {
        "pod": matched_pod,
        "pvc": matched_pvcs[0] if matched_pvcs else None,
    }


def get_pod_and_scratch_pvc_nodes(dyn_client, namespace):
    """
    Returns scratch pvc and pod nodes using sampling.
    This is essential in order to get hold of the resources before they are finished and not accessible.

    Args:
        namespace: namespace to search in
        dyn_client: open connection to remote cluster
    """
    LOGGER.info("Waiting for cdi-upload worker pod and scratch pvc")
    sampler = TimeoutSampler(
        wait_timeout=TIMEOUT_30SEC,
        sleep=5,
        func=_get_pod_and_scratch_pvc,
        dyn_client=dyn_client,
        namespace=namespace,
        pod_prefix=CDI_UPLOAD,
        pvc_suffix="scratch",
    )
    for sample in sampler:
        pod = sample.get("pod")
        pvc = sample.get("pvc")
        if pod and pvc:
            pod_node = pod.instance.spec.nodeName
            pvc_node = pvc.selected_node
            if pod_node and pvc_node:
                LOGGER.info(f"Found {CDI_UPLOAD} worker pod and scratch pvc")
                return {
                    "pod_node": pod_node,
                    "scratch_pvc_node": pvc_node,
                }


@pytest.mark.sno
@pytest.mark.polarion("CNV-2817")
@pytest.mark.parametrize(
    "dv_kwargs",
    [
        pytest.param(
            {
                "name": "cnv-2817",
            },
        ),
    ],
    indirect=True,
)
@pytest.mark.s390x
def test_hostpath_pod_reference_pvc(
    namespace,
    dv_kwargs,
    storage_class_matrix_hpp_matrix__module__,
):
    """
    Check that after disk image is written to the PVC which has been provisioned on the specified node,
    Pod can use this image.
    """
    if sc_volume_binding_mode_is_wffc(sc=[*storage_class_matrix_hpp_matrix__module__][0]):
        dv_kwargs.pop("hostpath_node")
    with create_dv(**dv_kwargs) as dv:
        verify_image_location_via_dv_pod_with_pvc(dv=dv, worker_node_name=dv.pvc.selected_node or dv.hostpath_node)


@pytest.mark.sno
@pytest.mark.polarion("CNV-3354")
@pytest.mark.s390x
def test_hpp_not_specify_node_immediate(
    skip_when_hpp_no_immediate,
    namespace,
    storage_class_matrix_hpp_matrix__module__,
):
    """
    Negative case
    Check that PVC should remain Pending when hostpath node was not specified
    and the volumeBindingMode of hostpath-provisioner StorageClass is 'Immediate'
    """
    with create_dv(
        source="http",
        dv_name="cnv-3354",
        namespace=namespace.name,
        url=f"{get_test_artifact_server_url()}{Images.Windows.WIN2k16_UEFI_IMG}",
        content_type=DataVolume.ContentType.KUBEVIRT,
        size="35Gi",
        storage_class=[*storage_class_matrix_hpp_matrix__module__][0],
    ) as dv:
        dv.wait_for_status(
            status=dv.Status.PENDING,
            timeout=TIMEOUT_2MIN,
            stop_status=dv.Status.SUCCEEDED,
        )


@pytest.mark.sno
@pytest.mark.polarion("CNV-3228")
@pytest.mark.s390x
def test_hpp_specify_node_immediate(
    skip_when_hpp_no_immediate,
    namespace,
    worker_node1,
    storage_class_matrix_hpp_matrix__module__,
):
    """
    Check that the PVC will bound PV and DataVolume status becomes Succeeded once importer Pod finished importing
    when PVC is annotated to a specified node and the volumeBindingMode of hostpath-provisioner StorageClass is
    'Immediate'
    """
    with create_dv(
        source="http",
        dv_name="cnv-3228",
        namespace=namespace.name,
        url=f"{get_test_artifact_server_url()}{RHEL_LATEST['image_path']}",
        content_type=DataVolume.ContentType.KUBEVIRT,
        size="35Gi",
        storage_class=[*storage_class_matrix_hpp_matrix__module__][0],
        hostpath_node=worker_node1.name,
    ) as dv:
        dv.wait_for_dv_success(timeout=TIMEOUT_10MIN)


@pytest.mark.sno
@pytest.mark.polarion("CNV-3227")
@pytest.mark.s390x
def test_hpp_pvc_without_specify_node_waitforfirstconsumer(
    skip_when_hpp_no_waitforfirstconsumer,
    namespace,
    storage_class_matrix_hpp_matrix__module__,
):
    """
    Check that in the condition of the volumeBindingMode of hostpath-provisioner StorageClass is 'WaitForFirstConsumer',
    if you do not specify the node on the PVC, it will remain Pending.
    The PV will be created only and PVC get bound when the first Pod using this PVC is scheduled.
    """
    with PersistentVolumeClaim(
        name="cnv-3227",
        namespace=namespace.name,
        accessmodes=PersistentVolumeClaim.AccessMode.RWO,
        size="1Gi",
        storage_class=[*storage_class_matrix_hpp_matrix__module__][0],
    ) as pvc:
        pvc.wait_for_status(
            status=pvc.Status.PENDING,
            timeout=TIMEOUT_1MIN,
            stop_status=pvc.Status.BOUND,
        )
        with PodWithPVC(
            namespace=pvc.namespace,
            name=f"{pvc.name}-pod",
            pvc_name=pvc.name,
            containers=get_containers_for_pods_with_pvc(volume_mode=pvc.volume_mode, pvc_name=pvc.name),
        ) as pod:
            pod.wait_for_status(status=pod.Status.RUNNING, timeout=TIMEOUT_3MIN)
            pvc.wait_for_status(status=pvc.Status.BOUND, timeout=TIMEOUT_1MIN)
            assert pod.instance.spec.nodeName == pvc.selected_node


@pytest.mark.sno
@pytest.mark.polarion("CNV-3280")
@pytest.mark.s390x
def test_hpp_pvc_specify_node_immediate(
    skip_when_hpp_no_immediate,
    namespace,
    worker_node1,
    storage_class_matrix_hpp_matrix__module__,
):
    """
    Check that kubevirt.io/provisionOnNode annotation works in Immediate mode.
    The annotation causes an immediate bind on the specified node.
    """
    with PersistentVolumeClaim(
        name="cnv-3280",
        namespace=namespace.name,
        accessmodes=PersistentVolumeClaim.AccessMode.RWO,
        size="1Gi",
        storage_class=[*storage_class_matrix_hpp_matrix__module__][0],
        hostpath_node=worker_node1.name,
    ) as pvc:
        assert_provision_on_node_annotation(pvc=pvc, node_name=worker_node1.name, type_="regular")
        with PodWithPVC(
            namespace=pvc.namespace,
            name=f"{pvc.name}-pod",
            pvc_name=pvc.name,
            containers=get_containers_for_pods_with_pvc(volume_mode=pvc.volume_mode, pvc_name=pvc.name),
        ) as pod:
            pod.wait_for_status(status=Pod.Status.RUNNING, timeout=TIMEOUT_3MIN)
            assert pod.instance.spec.nodeName == worker_node1.name


@pytest.mark.sno
@pytest.mark.polarion("CNV-2771")
@pytest.mark.s390x
def test_hpp_upload_virtctl(
    skip_when_hpp_no_waitforfirstconsumer,
    skip_when_cdiconfig_scratch_no_hpp,
    admin_client,
    namespace,
    tmpdir,
    storage_class_matrix_hpp_matrix__module__,
):
    """
    Check that upload disk image via virtctl tool works
    """
    latest_fedora_image = py_config["latest_fedora_os_dict"]["image_name"]
    local_name = f"{tmpdir}/{latest_fedora_image}"
    remote_name = f"{Images.Fedora.DIR}/{latest_fedora_image}"
    get_downloaded_artifact(remote_name=remote_name, local_name=local_name)
    pvc_name = "cnv-2771"

    # Get pod and scratch pvc nodes, before they are inaccessible
    thread_pool = ThreadPool(processes=1)
    async_result = thread_pool.apply_async(
        func=get_pod_and_scratch_pvc_nodes,
        kwds={"dyn_client": admin_client, "namespace": namespace.name},
    )
    # Start virtctl upload process, meanwhile, resources are sampled
    with virtctl_upload_dv(
        namespace=namespace.name,
        name=pvc_name,
        size=Images.Fedora.DEFAULT_DV_SIZE,
        storage_class=[*storage_class_matrix_hpp_matrix__module__][0],
        image_path=local_name,
        insecure=True,
    ) as virtctl_upload:
        check_upload_virtctl_result(result=virtctl_upload)
        return_val = async_result.get()  # get return value from side thread
        pvc = PersistentVolumeClaim(name=pvc_name, namespace=namespace.name)
        assert pvc.bound()
        pv = PersistentVolume(name=pvc.instance.spec.volumeName)
        pv_node = (
            pv.instance.spec.nodeAffinity.required.nodeSelectorTerms[0].get("matchExpressions")[0].get("values")[0]
        )
        assert pv_node == return_val.get("pod_node") == return_val.get("scratch_pvc_node"), "Node names differ"


@pytest.mark.sno
@pytest.mark.polarion("CNV-2769")
@pytest.mark.s390x
def test_hostpath_upload_dv_with_token(
    skip_when_cdiconfig_scratch_no_hpp,
    skip_when_hpp_no_waitforfirstconsumer,
    namespace,
    tmpdir,
    storage_class_matrix_hpp_matrix__module__,
):
    dv_name = "cnv-2769"
    local_name = f"{tmpdir}/{Images.Cirros.QCOW2_IMG}"
    remote_name = f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}"
    get_downloaded_artifact(
        remote_name=remote_name,
        local_name=local_name,
    )
    with create_dv(
        source="upload",
        dv_name=dv_name,
        namespace=namespace.name,
        size="1Gi",
        storage_class=[*storage_class_matrix_hpp_matrix__module__][0],
    ) as dv:
        dv.wait_for_status(status=DataVolume.Status.UPLOAD_READY, timeout=TIMEOUT_3MIN)
        storage_utils.upload_token_request(storage_ns_name=dv.namespace, pvc_name=dv.pvc.name, data=local_name)
        dv.wait_for_dv_success()
        verify_image_location_via_dv_pod_with_pvc(dv=dv, worker_node_name=dv.pvc.selected_node)


@pytest.mark.sno
@pytest.mark.parametrize(
    "data_volume_multi_hpp_storage",
    [
        pytest.param(
            {
                "dv_name": "cnv-3516-source-dv",
                "image": py_config.get("latest_fedora_os_dict", {}).get("image_path"),
                "dv_size": Images.Fedora.DEFAULT_DV_SIZE,
            },
            marks=pytest.mark.polarion("CNV-3516"),
        ),
    ],
    indirect=True,
)
@pytest.mark.s390x
def test_hostpath_clone_dv_without_annotation_wffc(
    skip_when_hpp_no_waitforfirstconsumer,
    admin_client,
    namespace,
    data_volume_multi_hpp_storage,
):
    """
    Check that in case of WaitForFirstConsumer binding mode, without annotating the source/target DV to a node,
    CDI clone function works well. The PVCs will have an annotation 'volume.kubernetes.io/selected-node' containing
    the node name where the pod is scheduled on.
    """
    storage_class = data_volume_multi_hpp_storage.storage_class
    with create_dv(
        source="pvc",
        dv_name=f"cnv-3516-target-dv-{storage_class}",
        namespace=namespace.name,
        source_namespace=data_volume_multi_hpp_storage.namespace,
        source_pvc=data_volume_multi_hpp_storage.pvc.name,
        size=data_volume_multi_hpp_storage.size,
        storage_class=storage_class,
    ) as target_dv:
        upload_target_pod = None
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_20SEC,
            sleep=1,
            func=get_pod_by_name_prefix,
            dyn_client=admin_client,
            namespace=namespace.name,
            pod_prefix=CDI_UPLOAD_TMP_PVC,
        ):
            if sample:
                upload_target_pod = sample
                break

        upload_target_pod.wait_for_status(status=Pod.Status.RUNNING, timeout=TIMEOUT_3MIN)
        assert_selected_node_annotation(
            pvc_node_name=target_dv.pvc.selected_node,
            pod_node_name=upload_target_pod.instance.spec.nodeName,
            type_="target",
        )
        target_dv.wait_for_dv_success(timeout=TIMEOUT_5MIN)
        with VirtualMachineForTestsFromTemplate(
            name="fedora-vm",
            namespace=namespace.name,
            client=admin_client,
            labels=Template.generate_template_labels(**py_config["latest_fedora_os_dict"]["template_labels"]),
            existing_data_volume=target_dv,
        ) as vm:
            running_vm(vm=vm)


@pytest.mark.polarion("CNV-2770")
@pytest.mark.s390x
def test_hostpath_clone_dv_with_annotation(
    skip_when_hpp_no_immediate,
    namespace,
    worker_node1,
    storage_class_matrix_hpp_matrix__module__,
):
    """
    Check that on Immediate binding mode,
    if the source/target DV is annotated to a specified node, CDI clone function works well.
    The PVCs will have an annotation 'kubevirt.io/provisionOnNode: <specified_node_name>'
    and bound immediately.
    """
    storage_class = [*storage_class_matrix_hpp_matrix__module__][0]
    with create_dv(
        source="http",
        dv_name="cnv-2770-source-dv",
        namespace=namespace.name,
        content_type=DataVolume.ContentType.KUBEVIRT,
        url=get_http_image_url(image_directory=Images.Cirros.DIR, image_name=Images.Cirros.QCOW2_IMG),
        size=Images.Cirros.DEFAULT_DV_SIZE,
        storage_class=storage_class,
        hostpath_node=worker_node1.name,
    ) as source_dv:
        source_dv.wait_for_dv_success(timeout=TIMEOUT_5MIN)
        assert_provision_on_node_annotation(pvc=source_dv.pvc, node_name=worker_node1.name, type_="import")
        with create_dv(
            source="pvc",
            dv_name="cnv-2770-target-dv",
            namespace=namespace.name,
            size=source_dv.size,
            storage_class=storage_class,
            hostpath_node=worker_node1.name,
            source_namespace=source_dv.namespace,
            source_pvc=source_dv.pvc.name,
        ) as target_dv:
            target_dv.wait_for_dv_success(timeout=TIMEOUT_10MIN)
            assert_provision_on_node_annotation(pvc=target_dv.pvc, node_name=worker_node1.name, type_="target")
            with storage_utils.create_vm_from_dv(dv=target_dv) as vm:
                check_disk_count_in_vm(vm=vm)


@pytest.mark.sno
@pytest.mark.polarion("CNV-8928")
@pytest.mark.s390x
def test_hpp_cr(hostpath_provisioner_scope_module):
    assert hostpath_provisioner_scope_module.exists
    hostpath_provisioner_scope_module.wait_for_condition(
        condition=hostpath_provisioner_scope_module.Condition.AVAILABLE,
        status=hostpath_provisioner_scope_module.Condition.Status.TRUE,
        timeout=TIMEOUT_1MIN,
    )


@pytest.mark.sno
@pytest.mark.polarion("CNV-7969")
@pytest.mark.s390x
def test_hpp_prometheus_resources(hpp_prometheus_resources):
    non_existing_resources = []
    for rsc in hpp_prometheus_resources:
        if not rsc.exists:
            non_existing_resources.append(rsc)
    assert not non_existing_resources, f"Non existing prometheus resources - {non_existing_resources}"


@pytest.mark.sno
@pytest.mark.polarion("CNV-3279")
@pytest.mark.s390x
def test_hpp_serviceaccount(
    hpp_serviceaccount,
    hpp_daemonset_scope_module,
    hpp_pool_deployments_scope_module,
):
    assert hpp_serviceaccount.exists, "HPP serviceAccount doesn't exist"
    hpp_serviceaccount_name = hpp_serviceaccount.instance.metadata.name
    hpp_daemonset_serviceaccount = hpp_daemonset_scope_module.instance.spec.template.spec.serviceAccount
    assert hpp_daemonset_serviceaccount == hpp_serviceaccount_name, (
        f"HPP daemonset's serviceAccount name '{hpp_daemonset_serviceaccount}' "
        f"is not matching with HPP's serviceAccount name '{hpp_serviceaccount_name}'"
    )

    # HPP pool deployments are only present when HPP CR has PVC template
    if hpp_pool_deployments_scope_module:
        for dp in hpp_pool_deployments_scope_module:
            dp_serviceaccount = dp.instance.spec.template.spec.serviceAccount
            assert dp_serviceaccount == hpp_serviceaccount_name, (
                f"HPP pool deployment's serviceAccount name '{dp_serviceaccount}' "
                f"is not matching with HPP's serviceAccount name '{hpp_serviceaccount_name}'"
            )


@pytest.mark.sno
@pytest.mark.polarion("CNV-8901")
@pytest.mark.s390x
def test_hpp_scc(hpp_scc, hpp_cr_suffix_scope_module):
    assert hpp_scc.exists
    assert (
        hpp_scc.instance.users[0]
        == f"system:serviceaccount:openshift-cnv:{HOSTPATH_PROVISIONER_ADMIN}{hpp_cr_suffix_scope_module}"
    ), f"No '{HOSTPATH_PROVISIONER_ADMIN}{hpp_cr_suffix_scope_module}' SA attached to 'hostpath-provisioner' SCC"


@pytest.mark.sno
@pytest.mark.polarion("CNV-8902")
@pytest.mark.s390x
def test_hpp_clusterrole_and_clusterrolebinding(
    hpp_clusterrole,
    hpp_clusterrolebinding,
    hpp_clusterrole_version_suffix,
    hpp_cr_suffix_scope_module,
):
    assert hpp_clusterrole.exists
    assert (
        hpp_clusterrole.instance["metadata"]["name"]
        == f"{HostPathProvisioner.Name.HOSTPATH_PROVISIONER}{hpp_clusterrole_version_suffix}"
    )

    assert hpp_clusterrolebinding.exists
    assert (
        hpp_clusterrolebinding.instance["subjects"][0]["name"]
        == f"{HOSTPATH_PROVISIONER_ADMIN}{hpp_cr_suffix_scope_module}"
    )


@pytest.mark.sno
@pytest.mark.polarion("CNV-8903")
@pytest.mark.s390x
def test_hpp_daemonset(hpp_daemonset_scope_module):
    assert (
        hpp_daemonset_scope_module.instance.status.numberReady
        == hpp_daemonset_scope_module.instance.status.desiredNumberScheduled
    )


@pytest.mark.sno
@pytest.mark.polarion("CNV-8904")
@pytest.mark.s390x
def test_hpp_operator_pod(hpp_operator_pod):
    assert hpp_operator_pod.status == Pod.Status.RUNNING, f"HPP operator pod {hpp_operator_pod.name} is not running"


@pytest.mark.destructive
@pytest.mark.polarion("CNV-3277")
def test_hpp_operator_recreate_after_deletion(
    hpp_operator_deployment,
    storage_class_matrix_hpp_matrix__module__,
):
    """
    Check that Hostpath-provisioner operator will be created again by HCO after its deletion.
    The Deployment is deleted, then its RepliceSet and Pod will be deleted and created again.
    """
    pre_delete_binding_mode = storage_class_matrix_hpp_matrix__module__.instance[VOLUME_BINDING_MODE]
    hpp_operator_deployment.delete()
    hpp_operator_deployment.wait_for_replicas(timeout=TIMEOUT_5MIN)
    recreated_binding_mode = storage_class_matrix_hpp_matrix__module__.instance[VOLUME_BINDING_MODE]
    assert pre_delete_binding_mode == recreated_binding_mode, (
        f"Pre delete binding mode: {pre_delete_binding_mode}, differs from recreated: {recreated_binding_mode}"
    )


@pytest.mark.sno
@pytest.mark.polarion("CNV-6097")
@pytest.mark.s390x
def test_hpp_operator_scc(hpp_scc, hpp_operator_pod):
    assert hpp_scc.exists, f"scc {hpp_scc.name} is not existed"
    user_id = hpp_operator_pod.instance.spec["containers"][0]["securityContext"]["runAsUser"]
    assert isinstance(user_id, int) and len(str(user_id)) == 10, (
        f"Container image is not runAsUser with user id {user_id}"
    )


@pytest.mark.sno
@pytest.mark.parametrize(
    "hpp_resources",
    [
        pytest.param(
            Pod,
            marks=(pytest.mark.polarion("CNV-7204")),
            id="hpp-pods",
        ),
        pytest.param(
            ServiceAccount,
            marks=(pytest.mark.polarion("CNV-7205")),
            id="hpp-service-accounts",
        ),
        pytest.param(
            Service,
            marks=(pytest.mark.polarion("CNV-7206")),
            id="hpp-service",
        ),
        pytest.param(
            Deployment,
            marks=(pytest.mark.polarion("CNV-7213")),
            id="hpp-deployment",
        ),
        pytest.param(
            CustomResourceDefinition,
            marks=(pytest.mark.polarion("CNV-7211")),
            id="hpp-crd",
        ),
        pytest.param(
            Role,
            marks=(pytest.mark.polarion("CNV-7212")),
            id="hpp-role",
        ),
        pytest.param(
            RoleBinding,
            marks=(pytest.mark.polarion("CNV-7209")),
            id="hpp-role-binding",
        ),
        pytest.param(
            ClusterRole,
            marks=(pytest.mark.polarion("CNV-7210")),
            id="hpp-cluster-role",
        ),
        pytest.param(
            ClusterRoleBinding,
            marks=(pytest.mark.polarion("CNV-7208")),
            id="hpp-cluster-role-binding",
        ),
    ],
    indirect=True,
)
@pytest.mark.s390x
def test_verify_hpp_res_app_label(
    hpp_resources,
    cnv_current_version,
):
    verify_hpp_app_label(hpp_resources=hpp_resources, cnv_version=cnv_current_version)

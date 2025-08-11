import logging

import pytest
from ocp_resources.cluster_role import ClusterRole
from ocp_resources.cluster_role_binding import ClusterRoleBinding
from ocp_resources.config_map import ConfigMap
from ocp_resources.custom_resource_definition import CustomResourceDefinition
from ocp_resources.datavolume import DataVolume
from ocp_resources.deployment import Deployment
from ocp_resources.pod import Pod
from ocp_resources.replica_set import ReplicaSet
from ocp_resources.resource import Resource
from ocp_resources.role import Role
from ocp_resources.role_binding import RoleBinding
from ocp_resources.secret import Secret
from ocp_resources.service import Service
from ocp_resources.service_account import ServiceAccount

from tests.storage.utils import import_image_to_dv, upload_image_to_dv
from utilities.constants import (
    CDI_APISERVER,
    CDI_CONFIGMAPS,
    CDI_LABEL,
    CDI_OPERATOR,
    CDI_SECRETS,
    CDI_UPLOAD,
    CDI_UPLOAD_TMP_PVC,
    SOURCE_POD,
    TIMEOUT_10MIN,
    Images,
)
from utilities.storage import (
    create_dv,
    data_volume,
    get_test_artifact_server_url,
    wait_for_cdi_worker_pod,
)

pytestmark = pytest.mark.post_upgrade

LOGGER = logging.getLogger(__name__)


def verify_label(cdi_resources):
    bad_pods = []
    for rcs in cdi_resources:
        if rcs.name.startswith(CDI_OPERATOR):
            continue
        if CDI_LABEL not in rcs.labels.keys():
            bad_pods.append(rcs.name)
    assert not bad_pods, " ".join(bad_pods)


def verify_cdi_app_label(cdi_resources, cnv_version):
    for resource in cdi_resources:
        if resource.kind == "Secret" and resource.name not in CDI_SECRETS:
            continue
        elif resource.kind == "ServiceAccount" and resource.name == CDI_OPERATOR:
            continue
        elif resource.kind == "ConfigMap" and resource.name not in CDI_CONFIGMAPS:
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
            if resource.name.startswith(CDI_OPERATOR):
                assert resource.labels[f"{Resource.ApiGroup.APP_KUBERNETES_IO}/managed-by"] == "olm", (
                    f"Missing label {Resource.ApiGroup.APP_KUBERNETES_IO}/managed-by for {resource.name}"
                )
            elif resource.kind == "Secret" and resource.name == "cdi-api-signing-key":
                assert resource.labels[f"{Resource.ApiGroup.APP_KUBERNETES_IO}/managed-by"] == CDI_APISERVER, (
                    f"Missing label {Resource.ApiGroup.APP_KUBERNETES_IO}/managed-by for {resource.name}"
                )
            else:
                assert resource.labels[f"{Resource.ApiGroup.APP_KUBERNETES_IO}/managed-by"] == CDI_OPERATOR, (
                    f"Missing label {Resource.ApiGroup.APP_KUBERNETES_IO}/managed-by for {resource.name}"
                )


@pytest.fixture(scope="module")
def cdi_resources_scope_module(request, admin_client):
    rcs_object = request.param
    LOGGER.info(f"Get all resources with kind: {rcs_object.kind}")
    resource_list = list(rcs_object.get(dyn_client=admin_client))
    return [rcs for rcs in resource_list if rcs.name.startswith("cdi-")]


@pytest.fixture()
def data_volume_without_snapshot_capability_scope_function(
    request,
    namespace,
    storage_class_matrix_without_snapshot_capability_matrix__function__,
    schedulable_nodes,
):
    yield from data_volume(
        request=request,
        namespace=namespace,
        storage_class_matrix=storage_class_matrix_without_snapshot_capability_matrix__function__,
        schedulable_nodes=schedulable_nodes,
    )


@pytest.mark.sno
@pytest.mark.parametrize(
    "cdi_resources_scope_module",
    [
        pytest.param(
            Pod,
            marks=(pytest.mark.polarion("CNV-1034")),
            id="cdi-pods",
        ),
        pytest.param(
            ServiceAccount,
            marks=(pytest.mark.polarion("CNV-3478")),
            id="cdi-service-accounts",
        ),
        pytest.param(
            Service,
            marks=(pytest.mark.polarion("CNV-3479")),
            id="cdi-service",
        ),
        pytest.param(
            Deployment,
            marks=(pytest.mark.polarion("CNV-3480")),
            id="cdi-deployment",
        ),
        pytest.param(
            ReplicaSet,
            marks=(pytest.mark.polarion("CNV-3481")),
            id="cdi-replicatset",
        ),
        pytest.param(
            CustomResourceDefinition,
            marks=(pytest.mark.polarion("CNV-3482")),
            id="cdi-crd",
        ),
        pytest.param(
            Role,
            marks=(pytest.mark.polarion("CNV-3483")),
            id="cdi-role",
        ),
        pytest.param(
            RoleBinding,
            marks=(pytest.mark.polarion("CNV-3484")),
            id="cdi-role-binding",
        ),
        pytest.param(
            ClusterRole,
            marks=(pytest.mark.polarion("CNV-3485")),
            id="cdi-cluster-role",
        ),
        pytest.param(
            ClusterRoleBinding,
            marks=(pytest.mark.polarion("CNV-3486")),
            id="cdi-cluster-role-binding",
        ),
    ],
    indirect=True,
)
@pytest.mark.s390x
def test_verify_pod_cdi_label(cdi_resources_scope_module):
    verify_label(cdi_resources=cdi_resources_scope_module)


@pytest.mark.sno
@pytest.mark.polarion("CNV-3475")
@pytest.mark.s390x
def test_importer_pod_cdi_label(namespace, https_server_certificate):
    # verify "cdi.kubevirt.io" label is included in importer pod
    with import_image_to_dv(
        dv_name="cnv-3475",
        images_https_server_name=get_test_artifact_server_url(schema="https"),
        storage_ns_name=namespace.name,
        https_server_certificate=https_server_certificate,
    ):
        wait_for_cdi_worker_pod(
            pod_name="importer",
            storage_ns_name=namespace.name,
        )


@pytest.mark.sno
@pytest.mark.polarion("CNV-3474")
@pytest.mark.s390x
def test_uploader_pod_cdi_label(unprivileged_client, namespace, storage_class_name_scope_module):
    """
    Verify "cdi.kubevirt.io" label is included in uploader pod
    """
    with upload_image_to_dv(
        dv_name="cnv-3474",
        storage_class=storage_class_name_scope_module,
        storage_ns_name=namespace.name,
        client=unprivileged_client,
    ):
        wait_for_cdi_worker_pod(
            pod_name=CDI_UPLOAD,
            storage_ns_name=namespace.name,
        )


@pytest.mark.sno
@pytest.mark.polarion("CNV-3476")
@pytest.mark.parametrize(
    "data_volume_without_snapshot_capability_scope_function",
    [
        pytest.param(
            {
                "dv_name": "dv-source",
                "image": f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}",
                "dv_size": Images.Cirros.DEFAULT_DV_SIZE,
            },
        ),
    ],
    indirect=True,
)
@pytest.mark.s390x
def test_cloner_pods_cdi_label(
    namespace,
    data_volume_without_snapshot_capability_scope_function,
):
    with create_dv(
        source="pvc",
        dv_name="dv-target",
        namespace=data_volume_without_snapshot_capability_scope_function.namespace,
        size=data_volume_without_snapshot_capability_scope_function.size,
        source_pvc=data_volume_without_snapshot_capability_scope_function.name,
        storage_class=data_volume_without_snapshot_capability_scope_function.storage_class,
    ) as cdv:
        cdv.wait_for_status(status=DataVolume.Status.CLONE_IN_PROGRESS, timeout=TIMEOUT_10MIN)
        wait_for_cdi_worker_pod(
            pod_name=CDI_UPLOAD_TMP_PVC if cdv.pvc.use_populator else f"{CDI_UPLOAD}-dv-target",
            storage_ns_name=cdv.namespace,
        )
        wait_for_cdi_worker_pod(
            pod_name=f"-{SOURCE_POD}",
            storage_ns_name=cdv.namespace,
        )


@pytest.mark.sno
@pytest.mark.parametrize(
    "cdi_resources_scope_module",
    [
        pytest.param(
            Pod,
            marks=(pytest.mark.polarion("CNV-6907")),
            id="cdi-pods",
        ),
        pytest.param(
            ServiceAccount,
            marks=(pytest.mark.polarion("CNV-7130")),
            id="cdi-service-accounts",
        ),
        pytest.param(
            Service,
            marks=(pytest.mark.polarion("CNV-7131")),
            id="cdi-service",
        ),
        pytest.param(
            Deployment,
            marks=(pytest.mark.polarion("CNV-7132")),
            id="cdi-deployment",
        ),
        pytest.param(
            CustomResourceDefinition,
            marks=(pytest.mark.polarion("CNV-7134")),
            id="cdi-crd",
        ),
        pytest.param(
            Role,
            marks=(pytest.mark.polarion("CNV-7138")),
            id="cdi-role",
        ),
        pytest.param(
            RoleBinding,
            marks=(pytest.mark.polarion("CNV-8971")),
            id="cdi-role-binding",
        ),
        pytest.param(
            ClusterRole,
            marks=(pytest.mark.polarion("CNV-7139")),
            id="cdi-cluster-role",
        ),
        pytest.param(
            ClusterRoleBinding,
            marks=(pytest.mark.polarion("CNV-7136")),
            id="cdi-cluster-role-binding",
        ),
        pytest.param(
            ConfigMap,
            marks=(pytest.mark.polarion("CNV-7137")),
            id="cdi-configmap",
        ),
        pytest.param(
            Secret,
            marks=(pytest.mark.polarion("CNV-7135")),
            id="cdi-secret",
        ),
    ],
    indirect=True,
)
@pytest.mark.s390x
def test_verify_cdi_res_app_label(
    cdi_resources_scope_module,
    cnv_current_version,
):
    verify_cdi_app_label(cdi_resources=cdi_resources_scope_module, cnv_version=cnv_current_version)

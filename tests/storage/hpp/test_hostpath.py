# -*- coding: utf-8 -*-

"""
Hostpath Provisioner test suite
"""

import logging

import pytest
from ocp_resources.cluster_role import ClusterRole
from ocp_resources.cluster_role_binding import ClusterRoleBinding
from ocp_resources.custom_resource_definition import CustomResourceDefinition
from ocp_resources.deployment import Deployment
from ocp_resources.hostpath_provisioner import HostPathProvisioner
from ocp_resources.pod import Pod
from ocp_resources.prometheus_rule import PrometheusRule
from ocp_resources.resource import Resource
from ocp_resources.role import Role
from ocp_resources.role_binding import RoleBinding
from ocp_resources.security_context_constraints import SecurityContextConstraints
from ocp_resources.service import Service
from ocp_resources.service_account import ServiceAccount
from ocp_resources.service_monitor import ServiceMonitor

from utilities.constants import (
    HOSTPATH_PROVISIONER_OPERATOR,
    HPP_POOL,
    TIMEOUT_1MIN,
    TIMEOUT_5MIN,
)
from utilities.infra import get_pod_by_name_prefix

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
def hpp_operator_deployment(hco_namespace):
    hpp_operator_deployment = Deployment(name=HOSTPATH_PROVISIONER_OPERATOR, namespace=hco_namespace.name)
    assert hpp_operator_deployment.exists
    return hpp_operator_deployment


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


@pytest.fixture(scope="module")
def hpp_pool_deployments_scope_module(admin_client, hco_namespace):
    return [
        dp
        for dp in Deployment.get(dyn_client=admin_client, namespace=hco_namespace.name)
        if dp.name.startswith(HPP_POOL)
    ]


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

import logging

import pytest
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.resource import ResourceEditor

from tests.observability.constants import BAD_HTTPGET_PATH
from tests.observability.metrics.utils import validate_initial_virt_operator_replicas_reverted
from tests.observability.virt.utils import (
    csv_dict_with_bad_virt_operator_httpget_path,
    delete_replica_set_by_prefix,
    wait_hco_csv_updated_virt_operator_httpget,
)
from utilities.constants import VIRT_HANDLER, VIRT_OPERATOR
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.infra import get_daemonset_by_name

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="class")
def modified_virt_operator_httpget_from_hco_and_delete_virt_operator_pods(
    admin_client,
    hco_namespace,
    prometheus,
    initial_virt_operator_replicas,
    csv_scope_class,
    initial_readiness_probe_httpget_path,
    virt_operator_deployment,
    disabled_olm_operator,
):
    with ResourceEditor(
        patches={
            csv_scope_class: csv_dict_with_bad_virt_operator_httpget_path(
                hco_csv_dict=csv_scope_class.instance.to_dict()
            )
        }
    ):
        wait_hco_csv_updated_virt_operator_httpget(namespace=hco_namespace.name, updated_hco_field=BAD_HTTPGET_PATH)
        delete_replica_set_by_prefix(
            dyn_client=admin_client,
            replica_set_prefix=VIRT_OPERATOR,
            namespace=hco_namespace.name,
        )
        yield
    wait_hco_csv_updated_virt_operator_httpget(
        namespace=hco_namespace.name, updated_hco_field=initial_readiness_probe_httpget_path
    )
    delete_replica_set_by_prefix(
        dyn_client=admin_client,
        replica_set_prefix=VIRT_OPERATOR,
        namespace=hco_namespace.name,
    )
    virt_operator_deployment.wait_for_replicas()
    validate_initial_virt_operator_replicas_reverted(
        prometheus=prometheus, initial_virt_operator_replicas=initial_virt_operator_replicas
    )


@pytest.fixture(scope="class")
def initial_readiness_probe_httpget_path(csv_scope_class):
    initial_readiness_probe_httpget_path = None
    for deployment in csv_scope_class.instance.spec.install.spec.deployments:
        if deployment["name"] == VIRT_OPERATOR:
            initial_readiness_probe_httpget_path = deployment.spec.template.spec.containers[
                0
            ].readinessProbe.httpGet.path
            break
    assert initial_readiness_probe_httpget_path, f"{VIRT_OPERATOR} deployment not found in hco csv"
    return initial_readiness_probe_httpget_path


@pytest.fixture(scope="class")
def virt_handler_daemonset_with_bad_image(virt_handler_daemonset_scope_class):
    with ResourceEditorValidateHCOReconcile(
        patches={
            virt_handler_daemonset_scope_class: {
                "spec": {"template": {"spec": {"containers": [{"name": "virt-handler", "image": "bad_image"}]}}}
            }
        },
        list_resource_reconcile=[KubeVirt],
    ):
        yield


@pytest.fixture(scope="class")
def virt_handler_daemonset_scope_class(hco_namespace, admin_client):
    return get_daemonset_by_name(
        admin_client=admin_client,
        daemonset_name=VIRT_HANDLER,
        namespace_name=hco_namespace.name,
    )

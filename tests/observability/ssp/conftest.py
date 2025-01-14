import pytest
from kubernetes.dynamic.exceptions import UnprocessibleEntityError
from ocp_resources.deployment import Deployment
from ocp_resources.ssp import SSP

from tests.observability.constants import SSP_HIGH_RATE_REJECTED_VMS
from utilities.constants import SSP_OPERATOR, VIRT_TEMPLATE_VALIDATOR
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.infra import get_pod_by_name_prefix
from utilities.ssp import verify_ssp_pod_is_running
from utilities.virt import VirtualMachineForTests


@pytest.fixture(scope="class")
def paused_ssp_operator(admin_client, hco_namespace, ssp_resource_scope_class):
    """
    Pause ssp-operator to avoid from reconciling any related objects
    """
    with ResourceEditorValidateHCOReconcile(
        patches={ssp_resource_scope_class: {"metadata": {"annotations": {"kubevirt.io/operator.paused": "true"}}}},
        list_resource_reconcile=[SSP],
    ):
        yield


@pytest.fixture(scope="class")
def template_validator_finalizer(hco_namespace):
    deployment = Deployment(name=VIRT_TEMPLATE_VALIDATOR, namespace=hco_namespace.name)
    with ResourceEditorValidateHCOReconcile(
        patches={deployment: {"metadata": {"finalizers": ["ssp.kubernetes.io/temporary-finalizer"]}}}
    ):
        yield


@pytest.fixture(scope="class")
def deleted_ssp_operator_pod(admin_client, hco_namespace):
    get_pod_by_name_prefix(
        dyn_client=admin_client,
        pod_prefix=SSP_OPERATOR,
        namespace=hco_namespace.name,
    ).delete(wait=True)
    yield
    verify_ssp_pod_is_running(dyn_client=admin_client, hco_namespace=hco_namespace)


@pytest.fixture(scope="class")
def template_modified(admin_client, base_templates):
    with ResourceEditorValidateHCOReconcile(
        patches={base_templates[0]: {"metadata": {"annotations": {"description": "New Description"}}}}
    ):
        yield


@pytest.fixture(scope="class")
def high_rate_rejected_vms_metric(prometheus_existing_records):
    for rule in prometheus_existing_records:
        if rule.get("alert") == SSP_HIGH_RATE_REJECTED_VMS:
            return int(rule["expr"][-1])


@pytest.fixture(scope="class")
def created_multiple_failed_vms(
    instance_type_for_test_scope_class,
    unprivileged_client,
    namespace,
    high_rate_rejected_vms_metric,
):
    """
    This fixture is trying to create wrong VMs multiple times for getting alert triggered
    """
    with instance_type_for_test_scope_class as vm_instance_type:
        for _ in range(high_rate_rejected_vms_metric + 1):
            with pytest.raises(UnprocessibleEntityError):
                with VirtualMachineForTests(
                    name="non-creatable-vm",
                    namespace=namespace.name,
                    client=unprivileged_client,
                    vm_instance_type=vm_instance_type,
                    diskless_vm=True,
                    vm_validation_rule={
                        "name": "minimal-required-memory",
                        "path": "jsonpath::.spec.domain.resources.requests.memory",
                        "rule": "integer",
                        "message": "This VM requires more memory.",
                        "min": 1073741824,
                    },
                ) as vm:
                    return vm

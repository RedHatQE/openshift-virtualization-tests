import logging

import pytest
from ocp_resources.migration_policy import MigrationPolicy
from ocp_resources.resource import Resource
from ocp_resources.template import Template

from tests.utils import (
    clean_up_migration_jobs,
    hotplug_resource_and_wait_hotplug_migration_finish,
    hotplug_spec_vm,
)
from tests.virt.utils import append_feature_gate_to_hco
from utilities.constants import (
    EIGHT_CPU_SOCKETS,
    FOUR_CPU_SOCKETS,
    FOUR_GI_MEMORY,
    ONE_CPU_CORE,
    ONE_CPU_THREAD,
    TEN_GI_MEMORY,
)
from utilities.virt import (
    VirtualMachineForTestsFromTemplate,
    running_vm,
    vm_instance_from_template,
)

LOGGER = logging.getLogger(__name__)


@pytest.fixture()
def vm_with_memory_load(
    request,
    unprivileged_client,
    namespace,
    golden_image_data_source_scope_function,
    modern_cpu_for_migration,
    vm_cpu_flags,
):
    with vm_instance_from_template(
        request=request,
        unprivileged_client=unprivileged_client,
        namespace=namespace,
        data_source=golden_image_data_source_scope_function,
        vm_cpu_model=modern_cpu_for_migration,
        vm_cpu_flags=vm_cpu_flags,
    ) as vm:
        yield vm


@pytest.fixture(scope="class")
def hotplugged_vm(
    request,
    namespace,
    unprivileged_client,
    golden_image_data_source_scope_class,
    modern_cpu_for_migration,
):
    with VirtualMachineForTestsFromTemplate(
        name=request.param["vm_name"],
        additional_labels=request.param.get("additional_labels"),
        labels=Template.generate_template_labels(**request.param["template_labels"]),
        namespace=namespace.name,
        client=unprivileged_client,
        data_source=golden_image_data_source_scope_class,
        cpu_max_sockets=EIGHT_CPU_SOCKETS,
        memory_max_guest=TEN_GI_MEMORY,
        cpu_sockets=FOUR_CPU_SOCKETS,
        cpu_threads=ONE_CPU_THREAD,
        cpu_cores=ONE_CPU_CORE,
        memory_guest=FOUR_GI_MEMORY,
        cpu_model=modern_cpu_for_migration,
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture()
def hotplugged_sockets_memory_guest(request, admin_client, hotplugged_vm, unprivileged_client):
    param = request.param
    if param.get("skip_migration"):
        hotplug_spec_vm(vm=hotplugged_vm, sockets=param.get("sockets"), memory_guest=param.get("memory_guest"))
    else:
        hotplug_resource_and_wait_hotplug_migration_finish(
            vm=hotplugged_vm,
            client=unprivileged_client,
            sockets=param.get("sockets"),
            memory_guest=param.get("memory_guest"),
        )
    yield
    clean_up_migration_jobs(client=admin_client, vm=hotplugged_vm)


@pytest.fixture()
def enabled_featuregate_scope_function(
    request,
    hyperconverged_resource_scope_function,
    kubevirt_feature_gates,
    admin_client,
    hco_namespace,
):
    feature_gate = request.param
    kubevirt_feature_gates.append(feature_gate)
    with append_feature_gate_to_hco(
        feature_gate=kubevirt_feature_gates,
        resource=hyperconverged_resource_scope_function,
        client=admin_client,
        namespace=hco_namespace,
    ):
        yield


@pytest.fixture(scope="class")
def migration_policy_with_allow_auto_converge(namespace):
    with MigrationPolicy(
        name="migration-policy-auto-converge",
        namespace_selector={f"{Resource.ApiGroup.KUBERNETES_IO}/metadata.name": namespace.name},
        allow_auto_converge=True,
    ):
        yield

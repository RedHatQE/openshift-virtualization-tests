import shlex

import pytest

from tests.network.ip_family_services.utils import (
    SERVICE_IP_FAMILY_POLICY_REQUIRE_DUAL_STACK,
    SERVICE_IP_FAMILY_POLICY_SINGLE_STACK,
)
from tests.network.utils import basic_expose_command, get_service
from utilities.constants import SSH_PORT_22
from utilities.infra import get_node_selector_dict, run_virtctl_command
from utilities.network import compose_cloud_init_data_dict
from utilities.virt import VirtualMachineForTests, fedora_vm_body


@pytest.fixture(scope="module")
def running_vm_for_exposure(
    worker_node1,
    namespace,
    unprivileged_client,
    dual_stack_network_data,
):
    vm_name = "exposed-vm"
    cloud_init_data = compose_cloud_init_data_dict(ipv6_network_data=dual_stack_network_data)

    with VirtualMachineForTests(
        namespace=namespace.name,
        name=vm_name,
        body=fedora_vm_body(name=vm_name),
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
        cloud_init_data=cloud_init_data,
        client=unprivileged_client,
    ) as vm:
        vm.start(wait=True)
        vm.wait_for_agent_connected()
        yield vm


@pytest.fixture()
def single_stack_service(running_vm_for_exposure, single_stack_service_ip_family):
    running_vm_for_exposure.custom_service_enable(
        service_name=f"single-stack-svc-{single_stack_service_ip_family.lower()}",
        port=SSH_PORT_22,
        ip_families=[single_stack_service_ip_family],
    )


@pytest.fixture()
def default_ip_family_policy_service(running_vm_for_exposure):
    running_vm_for_exposure.custom_service_enable(
        service_name="default-ip-family-policy-svc",
        port=SSH_PORT_22,
    )


@pytest.fixture()
def virtctl_expose_service(
    request,
    unprivileged_client,
    running_vm_for_exposure,
    dual_stack_cluster,
):
    ip_family_policy = request.param
    if ip_family_policy == SERVICE_IP_FAMILY_POLICY_REQUIRE_DUAL_STACK and not dual_stack_cluster:
        pytest.skip(
            f"{SERVICE_IP_FAMILY_POLICY_REQUIRE_DUAL_STACK} service cannot be created in a non-dual-stack cluster."
        )

    svc_name = f"ssh-{ip_family_policy.lower()}-svc"
    expose_command = basic_expose_command(resource_name=running_vm_for_exposure.name, svc_name=svc_name)
    expose_command += f" --ip-family-policy={ip_family_policy}"
    run_virtctl_command(command=shlex.split(expose_command), namespace=running_vm_for_exposure.namespace, check=True)

    svc = get_service(
        name=svc_name,
        namespace=running_vm_for_exposure.namespace,
        client=unprivileged_client,
    )
    yield svc
    svc.clean_up()


@pytest.fixture()
def expected_num_families_in_service(request, dual_stack_cluster):
    ip_family_policy = request.param
    if ip_family_policy != SERVICE_IP_FAMILY_POLICY_SINGLE_STACK and dual_stack_cluster:
        return 2
    return 1

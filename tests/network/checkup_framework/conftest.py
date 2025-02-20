import json
import logging
import random
import re

import pytest
import requests
from ocp_resources.resource import Resource
from ocp_resources.role_binding import RoleBinding
from packaging.version import Version

from tests.network.checkup_framework.constants import (
    API_GROUPS_STR,
    CHECKUP_NAD,
    CHECKUP_NODE_LABEL,
    DISCONNECTED_STR,
    DPDK_15_TIMEOUT,
    NONEXISTING_CONFIGMAP,
    RESOURCES_STR,
    SRIOV_CHECKUP_NAD,
    VERBS_STR,
)
from tests.network.checkup_framework.utils import (
    MAX_DESIRED_LATENCY_MILLISECONDS,
    assert_successful_latency_checkup,
    checkup_configmap_role,
    checkup_role_binding,
    create_checkup_job,
    create_latency_configmap,
    generate_checkup_resources_role,
    generate_checkup_service_account,
    get_job,
    latency_job_default_name_values,
    wait_for_job_failure,
    wait_for_job_finish,
)
from tests.utils import get_image_from_csv, get_image_name_from_csv
from utilities.constants import (
    CREATE_STR,
    DELETE_STR,
    GET_STR,
    LINUX_BRIDGE,
    SRIOV,
    TIMEOUT_1MIN,
)
from utilities.infra import create_ns, label_nodes
from utilities.network import network_device, network_nad

LOGGER = logging.getLogger(__name__)

LATENCY_DISCONNECTED_CONFIGMAP = "latency-disconnected-configmap"
KUBEVIRT_DPDK_CHECKUP = "kubevirt-dpdk-checkup"
DEFAULT_DPDK_CONFIGMAP_NAME = "dpdk-checkup-config"
VM_UNDER_TEST = "quay.io/openshift-cnv/kubevirt-dpdk-checkup-vm:latest"
NAD_NAME = "sriov-dpdk-test-network"
DPDK_HIGH_TRAFFIC = "7m"
DPDK_NORMAL_TRAFFIC = "1m"
COMMON_RESOURCE_RULES = [
    {
        API_GROUPS_STR: [Resource.ApiGroup.KUBEVIRT_IO],
        RESOURCES_STR: ["virtualmachineinstances"],
        VERBS_STR: [GET_STR, CREATE_STR, DELETE_STR],
    },
    {
        API_GROUPS_STR: [Resource.ApiGroup.SUBRESOURCES_KUBEVIRT_IO],
        RESOURCES_STR: ["virtualmachineinstances/console"],
        VERBS_STR: [GET_STR],
    },
]


@pytest.fixture(scope="module")
def checkup_ns(unprivileged_client):
    yield from create_ns(unprivileged_client=unprivileged_client, name="test-checkup-framework")


@pytest.fixture(scope="module")
def vm_latency_checkup_image_url(csv_related_images_scope_session):
    return get_image_from_csv(
        image_string="vm-network-latency-checkup",
        csv_related_images=csv_related_images_scope_session,
    )


@pytest.fixture(scope="module")
def framework_service_account(checkup_ns):
    with generate_checkup_service_account(
        sa_name_prefix=checkup_ns.name, checkup_namespace_name=checkup_ns.name
    ) as framework_sa:
        yield framework_sa


@pytest.fixture(scope="module")
def latency_rules():
    return COMMON_RESOURCE_RULES + [
        {
            API_GROUPS_STR: [Resource.ApiGroup.K8S_CNI_CNCF_IO],
            RESOURCES_STR: ["network-attachment-definitions"],
            VERBS_STR: [GET_STR],
        },
    ]


@pytest.fixture(scope="module")
def framework_latency_role(checkup_ns, latency_rules):
    with generate_checkup_resources_role(checkup_namespace_name=checkup_ns.name, rules=latency_rules) as latency_role:
        yield latency_role


@pytest.fixture(scope="module")
def framework_latency_role_binding(checkup_ns, framework_service_account, framework_latency_role):
    with checkup_role_binding(
        checkup_namespace_name=checkup_ns.name,
        checkup_service_account=framework_service_account,
        checkup_role=framework_latency_role,
    ) as role_binding:
        yield role_binding


@pytest.fixture(scope="module")
def framework_configmap_role(checkup_ns):
    with checkup_configmap_role(checkup_namespace_name=checkup_ns.name) as configmap_role:
        yield configmap_role


@pytest.fixture(scope="module")
def framework_configmap_role_binding(checkup_ns, framework_service_account, framework_configmap_role):
    with RoleBinding(
        name=framework_configmap_role.name,
        namespace=checkup_ns.name,
        subjects_kind=framework_service_account.kind,
        subjects_name=framework_service_account.name,
        role_ref_kind=framework_configmap_role.kind,
        role_ref_name=framework_configmap_role.name,
    ) as role_binding:
        yield role_binding


@pytest.fixture(scope="module")
def label_checkup_nodes(worker_node1, worker_node2):
    yield from label_nodes(nodes=[worker_node1, worker_node2], labels=CHECKUP_NODE_LABEL)


@pytest.fixture(scope="module")
def framework_resources(
    checkup_ns,
    framework_service_account,
    framework_latency_role,
    framework_latency_role_binding,
    framework_configmap_role,
    framework_configmap_role_binding,
):
    yield


@pytest.fixture(scope="module")
def checkup_linux_bridge_device(nodes_available_nics, label_checkup_nodes):
    bridge_name = "checkup-br"
    with network_device(
        interface_type=LINUX_BRIDGE,
        nncp_name=f"{bridge_name}-nncp",
        interface_name=bridge_name,
        node_selector_labels=CHECKUP_NODE_LABEL,
        ports=[list(nodes_available_nics.values())[0][-1]],
    ) as br_dev:
        yield br_dev


@pytest.fixture(scope="module")
def checkup_nad(
    checkup_ns,
    checkup_linux_bridge_device,
):
    with network_nad(
        namespace=checkup_ns,
        nad_type=checkup_linux_bridge_device.bridge_type,
        nad_name=CHECKUP_NAD,
        interface_name=checkup_linux_bridge_device.bridge_name,
    ) as nad:
        yield nad


@pytest.fixture(scope="module")
def checkup_sriov_network(
    sriov_node_policy,
    checkup_ns,
    sriov_namespace,
):
    """
    Create a SR-IOV network linked to SR-IOV policy.
    """
    with network_nad(
        nad_type=SRIOV,
        nad_name=SRIOV_CHECKUP_NAD,
        sriov_resource_name=sriov_node_policy.resource_name,
        namespace=sriov_namespace,
        sriov_network_namespace=checkup_ns.name,
    ) as sriov_network:
        yield sriov_network


@pytest.fixture(scope="module")
def checkup_sriov_disconnected_network(
    vlans_list,
    sriov_node_policy,
    checkup_ns,
    sriov_namespace,
):
    """
    Create a SR-IOV disconnected network linked to a SR-IOV policy. This is created using a non-configured VLAN tag.
    """
    with network_nad(
        nad_type=SRIOV,
        nad_name="sriov-checkup-disconnected-nad",
        sriov_resource_name=sriov_node_policy.resource_name,
        namespace=sriov_namespace,
        sriov_network_namespace=checkup_ns.name,
        vlan=random.choice([vlan for vlan in range(2, 4094) if vlan not in vlans_list]),
    ) as sriov_network:
        yield sriov_network


@pytest.fixture()
def network_nad_name(request):
    # This, combining with the lazy_fixture in the test, allows dynamic usage of different networks in the fixtures.
    if SRIOV in request.node.name:
        return SRIOV_CHECKUP_NAD
    return CHECKUP_NAD


@pytest.fixture()
def default_latency_configmap(
    checkup_ns,
    network_nad_name,
    index_number,
):
    with create_latency_configmap(
        namespace_name=checkup_ns.name,
        network_attachment_definition_namespace=checkup_ns.name,
        network_attachment_definition_name=network_nad_name,
        configmap_name=f"default-latency-configmap-{next(index_number)}",
        max_desired_latency_milliseconds=MAX_DESIRED_LATENCY_MILLISECONDS,
    ) as configmap:
        yield configmap


@pytest.fixture()
def first_latency_job_checkup_ready(unprivileged_client, checkup_ns, default_latency_configmap):
    first_latency_job = get_job(
        client=unprivileged_client,
        name=default_latency_configmap.name.replace("configmap", "job"),
        namespace_name=checkup_ns.name,
    )
    wait_for_job_finish(
        client=unprivileged_client,
        job=first_latency_job,
        checkup_ns=checkup_ns,
    )
    assert_successful_latency_checkup(
        configmap=default_latency_configmap,
    )


@pytest.fixture()
def latency_concurrent_job(
    vm_latency_checkup_image_url,
    framework_service_account,
    default_latency_configmap,
    first_latency_job_checkup_ready,
):
    # To prevent race condition we must first make sure the first job was configured successfully, and only then
    # create the concurrent one.
    with create_checkup_job(
        name="concurrent-checkup-job",
        service_account=framework_service_account,
        configmap_name=default_latency_configmap.name,
        vm_checkup_image=vm_latency_checkup_image_url,
    ) as job:
        yield job


@pytest.fixture()
def latency_disconnected_configmap(
    checkup_ns,
    disconnected_checkup_nad,
):
    with create_latency_configmap(
        configmap_name=LATENCY_DISCONNECTED_CONFIGMAP,
        namespace_name=checkup_ns.name,
        network_attachment_definition_namespace=disconnected_checkup_nad.namespace,
        network_attachment_definition_name=disconnected_checkup_nad.name,
        max_desired_latency_milliseconds=MAX_DESIRED_LATENCY_MILLISECONDS,
    ) as configmap:
        yield configmap


@pytest.fixture()
def latency_disconnected_configmap_sriov(
    checkup_ns,
    checkup_sriov_disconnected_network,
):
    with create_latency_configmap(
        configmap_name=f"{LATENCY_DISCONNECTED_CONFIGMAP}-sriov",
        namespace_name=checkup_ns.name,
        network_attachment_definition_namespace=checkup_ns.name,
        network_attachment_definition_name=checkup_sriov_disconnected_network.name,
        max_desired_latency_milliseconds=MAX_DESIRED_LATENCY_MILLISECONDS,
    ) as configmap:
        yield configmap


@pytest.fixture()
def latency_nonexistent_configmap_env_job(
    vm_latency_checkup_image_url,
    framework_service_account,
):
    with create_checkup_job(
        name=f"latency-{NONEXISTING_CONFIGMAP}-env-job",
        service_account=framework_service_account,
        configmap_name=NONEXISTING_CONFIGMAP,
        vm_checkup_image=vm_latency_checkup_image_url,
    ) as job:
        yield job


@pytest.fixture()
def latency_no_env_variables_job(
    vm_latency_checkup_image_url,
    framework_service_account,
):
    with create_checkup_job(
        name="latency-no-env-variables-job",
        service_account=framework_service_account,
        configmap_name="",
        env_variables=False,
        vm_checkup_image=vm_latency_checkup_image_url,
    ) as job:
        yield job


@pytest.fixture()
def latency_same_node_configmap(
    worker_node1,
    checkup_ns,
    network_nad_name,
):
    with create_latency_configmap(
        namespace_name=checkup_ns.name,
        network_attachment_definition_namespace=checkup_ns.name,
        network_attachment_definition_name=network_nad_name,
        source_node=worker_node1.hostname,
        target_node=worker_node1.hostname,
        configmap_name="latency-same-node-configmap",
        max_desired_latency_milliseconds=MAX_DESIRED_LATENCY_MILLISECONDS,
    ) as configmap:
        yield configmap


@pytest.fixture()
def latency_nonexistent_node_configmap(
    worker_node1,
    checkup_ns,
    network_nad_name,
):
    with create_latency_configmap(
        namespace_name=checkup_ns.name,
        network_attachment_definition_namespace=checkup_ns.name,
        network_attachment_definition_name=network_nad_name,
        source_node=worker_node1.hostname,
        target_node="non-existent-node",
        configmap_name="latency-nonexistent-node-configmap",
        max_desired_latency_milliseconds=MAX_DESIRED_LATENCY_MILLISECONDS,
    ) as configmap:
        yield configmap


@pytest.fixture()
def latency_nonexistent_nad_configmap(
    checkup_ns,
):
    with create_latency_configmap(
        namespace_name=checkup_ns.name,
        network_attachment_definition_namespace=checkup_ns.name,
        network_attachment_definition_name="non-existing-nad",
        configmap_name="latency-nonexistent-nad-configmap",
        max_desired_latency_milliseconds=MAX_DESIRED_LATENCY_MILLISECONDS,
    ) as configmap:
        yield configmap


@pytest.fixture()
def latency_nonexistent_namespace_configmap(
    checkup_ns,
    network_nad_name,
):
    with create_latency_configmap(
        namespace_name=checkup_ns.name,
        network_attachment_definition_namespace="non-existing-namespace",
        network_attachment_definition_name=network_nad_name,
        configmap_name="latency-nonexistent-ns-configmap",
        max_desired_latency_milliseconds=MAX_DESIRED_LATENCY_MILLISECONDS,
    ) as configmap:
        yield configmap


@pytest.fixture()
def latency_one_second_timeout_configmap(
    checkup_ns,
    checkup_nad,
):
    with create_latency_configmap(
        configmap_name="latency-one-second-timeout-configmap",
        network_attachment_definition_namespace=checkup_nad.namespace,
        network_attachment_definition_name=checkup_nad.name,
        namespace_name=checkup_ns.name,
        timeout="1s",
        max_desired_latency_milliseconds=MAX_DESIRED_LATENCY_MILLISECONDS,
    ) as configmap:
        yield configmap


@pytest.fixture()
def latency_zero_milliseconds_configmap(
    checkup_ns,
    checkup_nad,
):
    with create_latency_configmap(
        configmap_name="latency-zero-milliseconds-configmap",
        network_attachment_definition_namespace=checkup_nad.namespace,
        network_attachment_definition_name=checkup_nad.name,
        namespace_name=checkup_ns.name,
        max_desired_latency_milliseconds="0",
    ) as configmap:
        yield configmap


@pytest.fixture()
def default_latency_job(
    vm_latency_checkup_image_url,
    framework_service_account,
    default_latency_configmap,
):
    configmap_name = latency_job_default_name_values(latency_configmap=default_latency_configmap)
    with create_checkup_job(
        name=configmap_name["name"],
        service_account=framework_service_account,
        configmap_name=configmap_name["configmap_name"],
        vm_checkup_image=vm_latency_checkup_image_url,
    ) as job:
        yield job


@pytest.fixture()
def latency_job_disconnected_configmap_sriov(
    vm_latency_checkup_image_url,
    framework_service_account,
    latency_disconnected_configmap_sriov,
):
    configmap_name = latency_job_default_name_values(latency_configmap=latency_disconnected_configmap_sriov)
    with create_checkup_job(
        name=configmap_name["name"],
        service_account=framework_service_account,
        configmap_name=configmap_name["configmap_name"],
        vm_checkup_image=vm_latency_checkup_image_url,
    ) as job:
        yield job


@pytest.fixture()
def latency_disconnected_network_job(
    vm_latency_checkup_image_url,
    framework_service_account,
    latency_disconnected_configmap,
):
    configmap_name = latency_job_default_name_values(latency_configmap=latency_disconnected_configmap)
    with create_checkup_job(
        name=configmap_name["name"],
        service_account=framework_service_account,
        configmap_name=configmap_name["configmap_name"],
        vm_checkup_image=vm_latency_checkup_image_url,
    ) as job:
        yield job


@pytest.fixture()
def latency_same_node_job(
    vm_latency_checkup_image_url,
    framework_service_account,
    latency_same_node_configmap,
):
    configmap_name = latency_job_default_name_values(latency_configmap=latency_same_node_configmap)
    with create_checkup_job(
        name=configmap_name["name"],
        service_account=framework_service_account,
        configmap_name=configmap_name["configmap_name"],
        vm_checkup_image=vm_latency_checkup_image_url,
    ) as job:
        yield job


@pytest.fixture()
def latency_configmap_error_job(
    vm_latency_checkup_image_url,
    framework_service_account,
    latency_nonexistent_nad_configmap,
):
    configmap_name = latency_job_default_name_values(latency_configmap=latency_nonexistent_nad_configmap)
    with create_checkup_job(
        name=configmap_name["name"],
        service_account=framework_service_account,
        configmap_name=configmap_name["configmap_name"],
        vm_checkup_image=vm_latency_checkup_image_url,
    ) as job:
        yield job


@pytest.fixture()
def latency_nonexistent_namespace_job(
    vm_latency_checkup_image_url,
    framework_service_account,
    latency_nonexistent_namespace_configmap,
):
    configmap_name = latency_job_default_name_values(latency_configmap=latency_nonexistent_namespace_configmap)
    with create_checkup_job(
        name=configmap_name["name"],
        service_account=framework_service_account,
        configmap_name=configmap_name["configmap_name"],
        vm_checkup_image=vm_latency_checkup_image_url,
    ) as job:
        yield job


@pytest.fixture()
def latency_one_second_timeout_job(
    vm_latency_checkup_image_url,
    framework_service_account,
    latency_one_second_timeout_configmap,
):
    configmap_name = latency_job_default_name_values(latency_configmap=latency_one_second_timeout_configmap)
    with create_checkup_job(
        name=configmap_name["name"],
        service_account=framework_service_account,
        configmap_name=configmap_name["configmap_name"],
        vm_checkup_image=vm_latency_checkup_image_url,
    ) as job:
        yield job


@pytest.fixture()
def latency_zero_milliseconds_job(
    vm_latency_checkup_image_url,
    framework_service_account,
    latency_zero_milliseconds_configmap,
):
    configmap_name = latency_job_default_name_values(latency_configmap=latency_zero_milliseconds_configmap)
    with create_checkup_job(
        name=configmap_name["name"],
        service_account=framework_service_account,
        configmap_name=configmap_name["configmap_name"],
        vm_checkup_image=vm_latency_checkup_image_url,
    ) as job:
        yield job


@pytest.fixture()
def latency_nonexistent_node_job(
    vm_latency_checkup_image_url,
    framework_service_account,
    latency_nonexistent_node_configmap,
):
    configmap_name = latency_job_default_name_values(latency_configmap=latency_nonexistent_node_configmap)
    with create_checkup_job(
        name=configmap_name["name"],
        service_account=framework_service_account,
        configmap_name=configmap_name["configmap_name"],
        vm_checkup_image=vm_latency_checkup_image_url,
    ) as job:
        yield job


@pytest.fixture()
def linux_bridge_disconnected_device(label_checkup_nodes):
    bridge_name = f"{DISCONNECTED_STR}-br"
    with network_device(
        interface_type=LINUX_BRIDGE,
        nncp_name=f"{bridge_name}-nncp",
        interface_name=bridge_name,
        node_selector_labels=CHECKUP_NODE_LABEL,
    ) as br_dev:
        yield br_dev


@pytest.fixture()
def disconnected_checkup_nad(
    checkup_ns,
    linux_bridge_disconnected_device,
):
    with network_nad(
        namespace=checkup_ns,
        nad_type=linux_bridge_disconnected_device.bridge_type,
        nad_name=f"{DISCONNECTED_STR}-checkup-nad",
        interface_name=linux_bridge_disconnected_device.bridge_name,
    ) as nad:
        yield nad


@pytest.fixture()
def default_latency_job_success(unprivileged_client, checkup_ns, default_latency_configmap, default_latency_job):
    wait_for_job_finish(
        client=unprivileged_client,
        job=default_latency_job,
        checkup_ns=checkup_ns,
    )
    assert_successful_latency_checkup(
        configmap=default_latency_configmap,
    )


@pytest.fixture()
def latency_same_node_job_success(unprivileged_client, checkup_ns, latency_same_node_configmap, latency_same_node_job):
    wait_for_job_finish(
        client=unprivileged_client,
        job=latency_same_node_job,
        checkup_ns=checkup_ns,
    )
    assert_successful_latency_checkup(
        configmap=latency_same_node_configmap,
    )


@pytest.fixture()
def latency_concurrent_job_failure(latency_concurrent_job):
    wait_for_job_failure(job=latency_concurrent_job)


@pytest.fixture()
def latency_disconnected_network_job_failure(latency_disconnected_network_job):
    wait_for_job_failure(job=latency_disconnected_network_job)


@pytest.fixture()
def latency_disconnected_network_sriov_job_failure(latency_job_disconnected_configmap_sriov):
    wait_for_job_failure(job=latency_job_disconnected_configmap_sriov)


@pytest.fixture()
def latency_nonexistent_configmap_job_failure(latency_nonexistent_configmap_env_job):
    wait_for_job_failure(job=latency_nonexistent_configmap_env_job)


@pytest.fixture()
def latency_no_env_variables_job_failure(latency_no_env_variables_job):
    wait_for_job_failure(job=latency_no_env_variables_job)


@pytest.fixture()
def latency_configmap_error_job_failure(latency_configmap_error_job):
    wait_for_job_failure(job=latency_configmap_error_job)


@pytest.fixture()
def latency_nonexistent_namespace_job_failure(latency_nonexistent_namespace_job):
    wait_for_job_failure(job=latency_nonexistent_namespace_job)


@pytest.fixture()
def latency_one_second_timeout_job_failure(latency_one_second_timeout_job):
    wait_for_job_failure(job=latency_one_second_timeout_job)


@pytest.fixture()
def latency_zero_milliseconds_job_failure(latency_zero_milliseconds_job):
    wait_for_job_failure(job=latency_zero_milliseconds_job)


@pytest.fixture()
def latency_nonexistent_node_job_failure(latency_nonexistent_node_job):
    wait_for_job_failure(job=latency_nonexistent_node_job)


@pytest.fixture()
def latency_two_configmaps(checkup_ns, network_nad_name):
    with create_latency_configmap(
        namespace_name=checkup_ns.name,
        network_attachment_definition_namespace=checkup_ns.name,
        network_attachment_definition_name=network_nad_name,
        configmap_name="latency-first-configmap",
    ) as configmap1:
        with create_latency_configmap(
            namespace_name=checkup_ns.name,
            network_attachment_definition_namespace=checkup_ns.name,
            network_attachment_definition_name=network_nad_name,
            configmap_name="latency-second-configmap",
            max_desired_latency_milliseconds=MAX_DESIRED_LATENCY_MILLISECONDS,
        ) as configmap2:
            yield [configmap1, configmap2]


@pytest.fixture()
def latency_two_jobs(vm_latency_checkup_image_url, framework_service_account, latency_two_configmaps):
    with create_checkup_job(
        service_account=framework_service_account,
        configmap_name=latency_two_configmaps[0].name,
        name="latency-first-job",
        vm_checkup_image=vm_latency_checkup_image_url,
    ) as job1:
        with create_checkup_job(
            service_account=framework_service_account,
            configmap_name=latency_two_configmaps[1].name,
            name="latency-second-job",
            vm_checkup_image=vm_latency_checkup_image_url,
        ) as job2:
            yield [job1, job2]


@pytest.fixture(scope="module")
def dpdk_checkup_image_url(csv_related_images_scope_session):
    return get_image_from_csv(
        image_string=KUBEVIRT_DPDK_CHECKUP,
        csv_related_images=csv_related_images_scope_session,
    )


@pytest.fixture(scope="module")
def dpdk_checkup_namespace(unprivileged_client):
    yield from create_ns(unprivileged_client=unprivileged_client, name="dpdk-checkup")


@pytest.fixture(scope="module")
def dpdk_checkup_service_account(dpdk_checkup_namespace):
    with generate_checkup_service_account(
        sa_name_prefix=dpdk_checkup_namespace.name,
        checkup_namespace_name=dpdk_checkup_namespace.name,
    ) as dpdk_checkup_sa:
        yield dpdk_checkup_sa


@pytest.fixture(scope="module")
def dpdk_checkup_traffic_generator_service_account(dpdk_checkup_namespace):
    with generate_checkup_service_account(
        sa_name_prefix=f"{dpdk_checkup_namespace.name}-traffic-gen",
        checkup_namespace_name=dpdk_checkup_namespace.name,
    ) as dpdk_checkup_sa:
        yield dpdk_checkup_sa


@pytest.fixture(scope="module")
def dpdk_checkup_configmap_role(dpdk_checkup_namespace):
    with checkup_configmap_role(checkup_namespace_name=dpdk_checkup_namespace.name) as configmap_role:
        yield configmap_role


@pytest.fixture(scope="module")
def dpdk_checkup_configmap_role_binding(
    dpdk_checkup_namespace,
    dpdk_checkup_service_account,
    dpdk_checkup_configmap_role,
):
    with checkup_role_binding(
        checkup_namespace_name=dpdk_checkup_namespace.name,
        checkup_service_account=dpdk_checkup_service_account,
        checkup_role=dpdk_checkup_configmap_role,
    ) as role_binding:
        yield role_binding


@pytest.fixture(scope="module")
def dpdk_rules():
    return COMMON_RESOURCE_RULES + [
        {
            API_GROUPS_STR: [""],
            RESOURCES_STR: ["configmaps"],
            VERBS_STR: [CREATE_STR, DELETE_STR],
        },
    ]


@pytest.fixture(scope="module")
def dpdk_checkup_resources_role(dpdk_checkup_namespace, dpdk_rules):
    with generate_checkup_resources_role(
        checkup_namespace_name=dpdk_checkup_namespace.name, rules=dpdk_rules
    ) as checkup_resource_role:
        yield checkup_resource_role


@pytest.fixture(scope="module")
def dpdk_checkup_resources_role_binding(
    dpdk_checkup_namespace,
    dpdk_checkup_service_account,
    dpdk_checkup_resources_role,
):
    with checkup_role_binding(
        checkup_namespace_name=dpdk_checkup_namespace.name,
        checkup_service_account=dpdk_checkup_service_account,
        checkup_role=dpdk_checkup_resources_role,
    ) as role_binding:
        yield role_binding


@pytest.fixture()
def traffic_gen_image(dpdk_image_upstream_tag):
    return f"quay.io/kiagnose/kubevirt-dpdk-checkup-traffic-gen:{dpdk_image_upstream_tag}"


@pytest.fixture()
def dpdk_image_upstream_tag(csv_related_images_scope_session):
    image = get_image_name_from_csv(
        image_string=KUBEVIRT_DPDK_CHECKUP,
        csv_related_images=csv_related_images_scope_session,
    )
    version = Version(version=image.split(":")[1])

    return upstream_tag_from_job(base_version=f"v{version.base_version}", build=version.post)


@pytest.fixture(scope="module")
def sriov_network_for_dpdk(sriov_node_policy, sriov_namespace, dpdk_checkup_namespace):
    with network_nad(
        nad_type=SRIOV,
        nad_name=NAD_NAME,
        sriov_resource_name=sriov_node_policy.resource_name,
        namespace=sriov_namespace,
        sriov_network_namespace=dpdk_checkup_namespace.name,
    ) as sriov_network:
        yield sriov_network


@pytest.fixture()
def dpdk_configmap_same_node(dpdk_checkup_namespace, sriov_network_for_dpdk, worker_node1, traffic_gen_image):
    with create_latency_configmap(
        namespace_name=dpdk_checkup_namespace.name,
        network_attachment_definition_name=sriov_network_for_dpdk.name,
        configmap_name=DEFAULT_DPDK_CONFIGMAP_NAME,
        traffic_pps=DPDK_NORMAL_TRAFFIC,
        dpdk_gen_target_node=worker_node1.name,
        dpdk_test_target_node=worker_node1.name,
        dpdk_vmgen_container_diskimage=traffic_gen_image,
        dpdk_vmtest_container_diskimage=VM_UNDER_TEST,
        timeout=f"{DPDK_15_TIMEOUT}m",
    ) as configmap:
        yield configmap


@pytest.fixture()
def dpdk_high_traffic_configmap_same_node(
    dpdk_checkup_namespace, sriov_network_for_dpdk, worker_node1, traffic_gen_image
):
    with create_latency_configmap(
        namespace_name=dpdk_checkup_namespace.name,
        network_attachment_definition_name=sriov_network_for_dpdk.name,
        configmap_name=DEFAULT_DPDK_CONFIGMAP_NAME,
        traffic_pps=DPDK_HIGH_TRAFFIC,
        dpdk_gen_target_node=worker_node1.name,
        dpdk_test_target_node=worker_node1.name,
        dpdk_vmgen_container_diskimage=traffic_gen_image,
        dpdk_vmtest_container_diskimage=VM_UNDER_TEST,
        timeout=f"{DPDK_15_TIMEOUT}m",
    ) as configmap:
        yield configmap


@pytest.fixture()
def dpdk_high_traffic_configmap_different_node(
    dpdk_checkup_namespace, sriov_network_for_dpdk, worker_node1, worker_node2, traffic_gen_image
):
    with create_latency_configmap(
        namespace_name=dpdk_checkup_namespace.name,
        network_attachment_definition_name=sriov_network_for_dpdk.name,
        configmap_name=DEFAULT_DPDK_CONFIGMAP_NAME,
        traffic_pps=DPDK_HIGH_TRAFFIC,
        dpdk_gen_target_node=worker_node1.name,
        dpdk_test_target_node=worker_node2.name,
        dpdk_vmgen_container_diskimage=traffic_gen_image,
        dpdk_vmtest_container_diskimage=VM_UNDER_TEST,
        timeout=f"{DPDK_15_TIMEOUT}m",
    ) as configmap:
        yield configmap


@pytest.fixture()
def dpdk_job(
    dpdk_checkup_image_url,
    dpdk_checkup_service_account,
    unprivileged_client,
    dpdk_checkup_namespace,
):
    configmap_name = DEFAULT_DPDK_CONFIGMAP_NAME
    with create_checkup_job(
        name=configmap_name.replace("config", "job"),
        service_account=dpdk_checkup_service_account,
        configmap_name=configmap_name,
        vm_checkup_image=dpdk_checkup_image_url,
        security_context=True,
        env_variables=True,
        include_uid=True,
        client=unprivileged_client,
    ) as job:
        wait_for_job_finish(
            client=unprivileged_client,
            job=job,
            checkup_ns=dpdk_checkup_namespace,
            timeout=int(DPDK_15_TIMEOUT) * TIMEOUT_1MIN,
        )
        yield job


def upstream_tag_from_job(base_version, build):
    ref_value = requests.get(
        f"https://download.eng.bos.redhat.com/brewroot/packages/"
        f"{KUBEVIRT_DPDK_CHECKUP}-rhel9-container/{base_version}/"
        f"{build}/data/logs/osbs-build.log",
        verify=False,
    ).text

    match = re.findall(
        r"cachito - INFO - Waiting for request\s+(\d+)\s+to complete",
        ref_value,
        re.MULTILINE | re.IGNORECASE,
    )
    if match:
        return json.loads(
            requests.get(
                f"https://cachito.engineering.redhat.com/api/v1/requests/{match[0]}",
                verify=False,
            ).text
        )["ref"][:8]
    raise ValueError("Missing cachito reference in log")

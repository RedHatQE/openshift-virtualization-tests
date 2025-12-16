import logging
import random

import pytest
from ocp_resources.migration_policy import MigrationPolicy
from ocp_resources.resource import ResourceEditor

from tests.chaos.constants import HOST_LABEL
from tests.chaos.migration.utils import taint_node_for_migration
from tests.chaos.utils import rebooting_node
from utilities.constants import MIGRATION_POLICY_VM_LABEL

LOGGER = logging.getLogger(__name__)


@pytest.fixture()
def tainted_node_for_vm_chaos_rhel9_migration(chaos_vm_rhel9):
    yield from taint_node_for_migration(initial_node=chaos_vm_rhel9.vmi.node)


@pytest.fixture()
def tainted_node_for_vm_nginx_migration(vm_with_nginx_service):
    yield from taint_node_for_migration(initial_node=vm_with_nginx_service.vmi.node)


@pytest.fixture()
def tainted_node_for_vm_chaos_rhel9_with_dv_migration(chaos_vm_rhel9_with_dv_started):
    yield from taint_node_for_migration(initial_node=chaos_vm_rhel9_with_dv_started.vmi.node)


@pytest.fixture()
def chaos_migration_policy(admin_client):
    with MigrationPolicy(
        client=admin_client,
        name="chaos-migration-policy",
        bandwidth_per_migration="6Mi",
        vmi_selector=MIGRATION_POLICY_VM_LABEL,
    ) as mp:
        yield mp


@pytest.fixture()
def source_node(vm_with_nginx_service):
    initial_node = vm_with_nginx_service.vmi.node
    LOGGER.info(f"Get the source node {initial_node.name}")
    yield initial_node


@pytest.fixture()
def rebooted_source_node(source_node, workers_utility_pods):
    yield from rebooting_node(node=source_node, utility_pods=workers_utility_pods)


@pytest.fixture()
def rebooted_target_node(labeled_migration_target_node, workers_utility_pods):
    yield from rebooting_node(node=labeled_migration_target_node, utility_pods=workers_utility_pods)


@pytest.fixture()
def labeled_migration_target_node(workers, vm_with_nginx_service_and_node_selector):
    target_node = random.choice([
        node for node in workers if node.name != vm_with_nginx_service_and_node_selector.vmi.node.name
    ])
    LOGGER.info(f"Specify target node for migration: {target_node.name}")
    with ResourceEditor(patches={target_node: {"metadata": {"labels": HOST_LABEL}}}):
        yield target_node


@pytest.fixture()
def tainted_node_for_vm_nginx_with_node_selector_migration(
    vm_with_nginx_service_and_node_selector,
):
    yield from taint_node_for_migration(initial_node=vm_with_nginx_service_and_node_selector.vmi.node)


@pytest.fixture()
def labeled_source_node(workers):
    source_node = random.choice(workers)
    LOGGER.info(f"Label source node: {source_node.name}")
    with ResourceEditor(patches={source_node: {"metadata": {"labels": HOST_LABEL}}}):
        yield source_node

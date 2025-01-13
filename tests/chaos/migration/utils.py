import logging

from utilities.virt import taint_node_no_schedule, wait_for_vmi_relocation_and_running

LOGGER = logging.getLogger(__name__)


def assert_migration_result_and_cleanup(
    initial_node,
    vm,
    chaos_worker_background_process,
):
    wait_for_vmi_relocation_and_running(
        vm=vm,
        initial_node=initial_node,
    )
    chaos_worker_background_process.join()
    assert chaos_worker_background_process.exitcode == 0, "Background process execution failed"


def taint_node_for_migration(initial_node):
    with taint_node_no_schedule(node=initial_node):
        yield initial_node

"""
Pytest conftest file for CNV tests
"""

import pytest


@pytest.fixture(autouse=True)
def autouse_fixtures(
    leftovers_cleanup,  # Must be called first to avoid deleting created resources.
    artifactory_setup,
    bin_directory_to_os_path,
    cluster_info,
    term_handler_scope_function,
    term_handler_scope_class,
    term_handler_scope_module,
    term_handler_scope_session,
    admin_client,
    cluster_sanity_scope_session,
    cluster_sanity_scope_module,
    generated_ssh_key_for_vm_access,
    session_start_time,
):
    """call all autouse fixtures"""

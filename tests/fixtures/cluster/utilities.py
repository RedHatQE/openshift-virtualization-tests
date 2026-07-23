"""Cluster utility daemonset and service-account fixtures."""

import logging

import pytest
from ocp_resources.daemonset import DaemonSet
from ocp_resources.service_account import ServiceAccount

from utilities.constants.cluster import CNV_TEST_SERVICE_ACCOUNT
from utilities.infra import (
    add_scc_to_service_account,
    generate_openshift_pull_secret_file,
    get_daemonset_yaml_file_with_image_hash,
)

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def generated_pulled_secret(
    is_production_source,
    installing_cnv,
    admin_client,
):
    if is_production_source and installing_cnv:
        return
    return generate_openshift_pull_secret_file()


@pytest.fixture(scope="session")
def cnv_tests_utilities_service_account(admin_client, cnv_tests_utilities_namespace, installing_cnv):
    if installing_cnv:
        yield
    else:
        with ServiceAccount(
            client=admin_client,
            name=CNV_TEST_SERVICE_ACCOUNT,
            namespace=cnv_tests_utilities_namespace.name,
        ) as service_account:
            add_scc_to_service_account(
                namespace=cnv_tests_utilities_namespace.name,
                scc_name="privileged",
                sa_name=service_account.name,
            )
            yield service_account


@pytest.fixture(scope="session")
def utility_daemonset(
    admin_client,
    installing_cnv,
    generated_pulled_secret,
    cnv_tests_utilities_namespace,
    cnv_tests_utilities_service_account,
):
    """
    Deploy utility daemonset into the cnv-tests-utilities namespace.

    This daemonset deploys a pod on every node with hostNetwork and the main usage is to run commands on the hosts.
    For example to create linux bridge and other components related to the host configuration.
    """
    if installing_cnv:
        yield
    else:
        modified_ds_yaml_file = get_daemonset_yaml_file_with_image_hash(
            generated_pulled_secret=generated_pulled_secret,
            service_account=cnv_tests_utilities_service_account,
        )
        with DaemonSet(client=admin_client, yaml_file=modified_ds_yaml_file) as ds:
            ds.wait_until_deployed()
            yield ds

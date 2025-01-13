import logging

import pytest
from pytest_testconfig import config as py_config

from tests.virt.cluster.longevity_tests.constants import (
    LINUX_OS_PREFIX,
    WINDOWS_OS_PREFIX,
)
from tests.virt.cluster.longevity_tests.utils import (
    create_containerdisk_vms,
    create_dv_vms,
    create_multi_datasources,
    create_multi_dvs,
    wait_vms_booted_and_start_processes,
)

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def vm_deploys():
    deploys = int(py_config["vm_deploys"])
    if deploys < 1:
        raise ValueError("VM deploys value is less then 1!")
    return deploys


@pytest.fixture()
def container_disk_vms(vm_deploys, namespace, unprivileged_client):
    LOGGER.info("Deploying VM with container disk")
    yield from create_containerdisk_vms(
        vm_deploys=vm_deploys,
        client=unprivileged_client,
        namespace=namespace,
        name="linux-multi-mig-containerdisk-vm",
    )


@pytest.fixture()
def multi_vms(
    request,
    vm_deploys,
    namespace,
    unprivileged_client,
    multi_datasources,
    rhsm_created_secret,
    nodes_intel_cpu_model,
    vm_cpu_flags,
    fips_enabled_cluster,
):
    yield from create_dv_vms(
        vm_deploys=vm_deploys,
        client=unprivileged_client,
        namespace=namespace,
        datasources=multi_datasources,
        vm_params=request.param["vm_params"],
        nodes_common_cpu_model=nodes_intel_cpu_model,
        cpu_flags=vm_cpu_flags,
    )


@pytest.fixture()
def linux_vms_with_pids(multi_vms, container_disk_vms):
    return wait_vms_booted_and_start_processes(vms_list=multi_vms + container_disk_vms, os_type=LINUX_OS_PREFIX)


@pytest.fixture()
def windows_vms_with_pids(multi_vms):
    return wait_vms_booted_and_start_processes(vms_list=multi_vms, os_type=WINDOWS_OS_PREFIX)


@pytest.fixture()
def wsl2_vms_with_pids(multi_vms):
    return wait_vms_booted_and_start_processes(vms_list=multi_vms, os_type=WINDOWS_OS_PREFIX, wsl2_guest=True)


@pytest.fixture()
def multi_dv(request, admin_client, golden_images_namespace, fips_enabled_cluster):
    yield from create_multi_dvs(
        namespace=golden_images_namespace,
        client=admin_client,
        dv_params=request.param["dv_params"],
    )


@pytest.fixture()
def multi_datasources(admin_client, multi_dv):
    yield from create_multi_datasources(client=admin_client, dvs=multi_dv)

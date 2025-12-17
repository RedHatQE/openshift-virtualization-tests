# test_upgrade_scale
# Notes
# - statically linked stress-ng executable must be placed in the tests/scale/
#   directory prior to running to support use in cirros

import logging
import os
import random
import shlex

import pytest
from ocp_resources.data_source import DataSource
from ocp_resources.datavolume import DataVolume
from ocp_resources.migration_policy import MigrationPolicy
from ocp_resources.resource import Resource
from ocp_resources.virtual_machine import VirtualMachine
from ocp_resources.virtual_machine_cluster_instancetype import VirtualMachineClusterInstancetype
from ocp_resources.virtual_machine_cluster_preference import VirtualMachineClusterPreference
from ocp_scale_utilities.monitoring import MonitorResourceAPIServerRequests
from pyhelper_utils.shell import run_ssh_commands

from tests.scale.constants import GUEST_DATA_COMMANDS, VIRT_HANDLER_API_IDLE_STATE
from tests.scale.threaded_utils.utils import LocalThreadedScaleResources
from tests.scale.threaded_utils.virt import (
    threaded_get_vm_guest_data,
    threaded_run_vm_ssh_command,
    threaded_verify_guest_data,
    threaded_wait_for_accessible_vms,
    threaded_wait_for_running_vms,
    threaded_wait_for_scheduled_vms,
)
from tests.scale.utils import (
    capture_func_elapsed,
)
from tests.upgrade_params import (
    IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID,
    IUO_UPGRADE_TEST_ORDERING_NODE_ID,
    SCALE_NODE_ID_PREFIX,
    SCALE_VM_LOAD_RUNNING_AFTER_UPGRADE_ID,
)
from utilities.constants import (
    CNV_VM_SSH_KEY_PATH,
    DEPENDENCY_SCOPE_SESSION,
    OS_FLAVOR_CIRROS,
    PORT_80,
    TIMEOUT_5MIN,
    TIMEOUT_20MIN,
    TIMEOUT_30MIN,
    NamespacesNames,
    StorageClassNames,
)
from utilities.infra import create_ns, run_virtctl_command
from utilities.storage import data_volume_template_with_source_ref_dict
from utilities.virt import VirtualMachineForTests, create_vm_with_nginx_service, prepare_cloud_init_user_data

LOGGER = logging.getLogger(__name__)
DEPENDENCIES_NODE_ID_PREFIX = f"{os.path.abspath(__file__)}::TestUpgradeScale"
CACHE_KEY_PREFIX = "test_upgrade_scale"

TOTAL_VM_COUNT = int(os.environ.get("SCALE_TEST_TOTAL_VM_COUNT", 2))
CIRROS_IMG_URL = "https://download.cirros-cloud.net/0.6.2/cirros-0.6.2-x86_64-disk.img"
CIRROS_DV_SIZE = "150Mi"

STRESS_NG_PATH = "tests/scale/stress-ng"

U1_PICO = "u1.pico"
ALLOW_POST_COPY_MIGRATION_PROFILE_NAME = "allow-post-copy"

pytestmark = [
    pytest.mark.scale,
    pytest.mark.destructive,
    pytest.mark.threaded,
    pytest.mark.cpu_manager,
    pytest.mark.upgrade,
    pytest.mark.ocp_upgrade,
    pytest.mark.cnv_upgrade,
    pytest.mark.eus_upgrade,
    pytest.mark.usefixtures(
        "fail_if_no_stress_ng",
        "cache_key_scope_module",
        "increased_open_file_limit",
        "scale_client_configuration",
        "calculated_max_pods_per_virt_node",
        "patched_hco_for_scale_testing",
        "created_kubeletconfigs_for_scale",
    ),
    pytest.mark.parametrize(
        "cache_key_scope_module,increased_open_file_limit,scale_client_configuration,calculated_max_pods_per_virt_node",
        [
            pytest.param(
                "test_upgrade_scale",
                {"nofile_hard_limit": 2**19},
                {"connection_pool_maxsize": TOTAL_VM_COUNT},
                {"total_vm_count": TOTAL_VM_COUNT},
            ),
        ],
        indirect=True,
    ),
]


@pytest.fixture(scope="module")
def fail_if_no_stress_ng():
    assert os.path.isfile(STRESS_NG_PATH), f"File not found: {STRESS_NG_PATH}"


@pytest.fixture(scope="module")
def upgrade_scale_namespace(admin_client, unprivileged_client):
    yield from create_ns(
        name="test-upgrade-scale",
        admin_client=admin_client,
        unprivileged_client=unprivileged_client,
        delete_timeout=TIMEOUT_20MIN,
    )


@pytest.fixture(scope="module")
def created_pico_instancetype(admin_client):
    with VirtualMachineClusterInstancetype(
        name=U1_PICO,
        client=admin_client,
        cpu={"guest": 1},
        memory={"guest": "256Mi"},
    ) as instancetype:
        yield instancetype


@pytest.fixture(scope="module")
def created_data_source_for_scale(request, admin_client, created_pico_instancetype):
    with DataVolume(
        name=OS_FLAVOR_CIRROS,
        namespace=request.param["namespace_name"],
        client=admin_client,
        source="http",
        size=CIRROS_DV_SIZE,
        url=CIRROS_IMG_URL,
        storage_class=request.param["storage_class"],
        volume_mode=request.param["volume_mode"],
        access_modes=request.param["access_modes"],
    ) as data_volume:
        data_volume.wait_for_dv_success(timeout=TIMEOUT_20MIN)
        with DataSource(
            name=data_volume.name,
            namespace=data_volume.namespace,
            client=admin_client,
            label={
                f"{Resource.ApiGroup.INSTANCETYPE_KUBEVIRT_IO}/default-instancetype": created_pico_instancetype.name,
                f"{Resource.ApiGroup.INSTANCETYPE_KUBEVIRT_IO}/default-preference": OS_FLAVOR_CIRROS,
            },
            source={
                "pvc": {
                    "name": data_volume.name,
                    "namespace": data_volume.namespace,
                },
            },
        ) as data_source:
            yield data_source


@pytest.fixture(scope="module")
def created_post_copy_migration_policy_for_upgrade(admin_client, upgrade_scale_namespace):
    with MigrationPolicy(
        name=ALLOW_POST_COPY_MIGRATION_PROFILE_NAME,
        client=admin_client,
        allow_post_copy=True,
        namespace_selector={f"{Resource.ApiGroup.KUBERNETES_IO}/metadata.name": upgrade_scale_namespace.name},
        vmi_selector={f"{Resource.ApiGroup.KUBEVIRT_IO}/migration-profile": ALLOW_POST_COPY_MIGRATION_PROFILE_NAME},
    ) as migration_policy:
        yield migration_policy


@pytest.fixture(scope="module")
def vm_with_nginx_service_scope_module(upgrade_scale_namespace, admin_client, workers_utility_pods, workers):
    yield from create_vm_with_nginx_service(
        name="nginx-vm",
        namespace=upgrade_scale_namespace,
        client=admin_client,
        utility_pods=workers_utility_pods,
        node=random.choice(workers),
    )


@pytest.fixture(scope="module")
def stopped_nginx_vm(vm_with_nginx_service_scope_module, stress_ng_url_for_cirros, running_vms_for_upgrade_test):
    vm_with_nginx_service_scope_module.stop(wait=True)
    yield


@pytest.fixture(scope="module")
def stress_ng_url_for_cirros(vm_with_nginx_service_scope_module):
    run_virtctl_command(
        command=shlex.split(
            (
                f"scp -i '{os.environ[CNV_VM_SSH_KEY_PATH]}' "
                "--local-ssh-opts='-o StrictHostKeyChecking=no' "
                f"'{STRESS_NG_PATH}' "
                f"fedora@vm/{vm_with_nginx_service_scope_module.name}:~/stress-ng"
            )
        ),
        namespace=vm_with_nginx_service_scope_module.namespace,
    )
    run_ssh_commands(
        host=vm_with_nginx_service_scope_module.ssh_exec,
        commands=shlex.split("sudo cp ~/stress-ng /usr/share/nginx/html/"),
    )
    yield f"http://{vm_with_nginx_service_scope_module.custom_service.instance.spec.clusterIPs[0]}:{PORT_80}/stress-ng"


@pytest.fixture(scope="module")
def vms_for_upgrade_test(
    request,
    scale_unprivileged_client,
    upgrade_scale_namespace,
    created_data_source_for_scale,
    created_post_copy_migration_policy_for_upgrade,
):
    vms = []
    for entry in request.param:
        vm_instancetype = VirtualMachineClusterInstancetype(
            client=scale_unprivileged_client, name=entry["vm_instancetype"]
        )
        vm_preference = VirtualMachineClusterPreference(client=scale_unprivileged_client, name=entry["vm_preference"])
        cloud_init_data = None
        if entry.get("runcmd"):
            cloud_init_data = prepare_cloud_init_user_data(section="runcmd", data=entry["runcmd"])
        vms.extend([
            VirtualMachineForTests(
                client=scale_unprivileged_client,
                name=f"vm-scale-load-test-{vm_instancetype.name}-{vm_preference.name}-{index}",
                namespace=upgrade_scale_namespace.name,
                run_strategy="Always",
                data_volume_template=data_volume_template_with_source_ref_dict(
                    data_source=created_data_source_for_scale
                ),
                vm_instance_type=vm_instancetype,
                vm_preference=vm_preference,
                os_flavor=entry["os_flavor"],
                cloud_init_data=cloud_init_data,
                additional_labels={
                    f"{Resource.ApiGroup.KUBEVIRT_IO}/migration-profile": ALLOW_POST_COPY_MIGRATION_PROFILE_NAME
                }
                if index % 2
                else None,
            )
            for index in range(entry["vm_count"])
        ])


@pytest.fixture(scope="module")
def running_vms_for_upgrade_test(
    request, prometheus, cache_key_scope_module, stress_ng_url_for_cirros, vms_for_upgrade_test
):
    monitor_api_requests = MonitorResourceAPIServerRequests(
        prometheus=prometheus,
        resource_class=VirtualMachine,
        idle_requests_value=VIRT_HANDLER_API_IDLE_STATE * len(vms_for_upgrade_test),
    )

    monitor_api_requests.wait_for_idle()
    with LocalThreadedScaleResources(resources=vms_for_upgrade_test, cache_key_prefix=cache_key_scope_module):
        capture_func_elapsed(
            cache=request.config.cache,
            cache_key_prefix=cache_key_scope_module,
            func=threaded_wait_for_scheduled_vms,
            vms=vms_for_upgrade_test,
        )
        capture_func_elapsed(
            cache=request.config.cache,
            cache_key_prefix=cache_key_scope_module,
            func=threaded_wait_for_running_vms,
            vms=vms_for_upgrade_test,
        )
        capture_func_elapsed(
            cache=request.config.cache,
            cache_key_prefix=cache_key_scope_module,
            func=threaded_wait_for_accessible_vms,
            vms=vms_for_upgrade_test,
            timeout=TIMEOUT_30MIN,
            tcp_timeout=TIMEOUT_5MIN,
        )
        capture_func_elapsed(
            cache=request.config.cache,
            cache_key_prefix=cache_key_scope_module,
            func=threaded_run_vm_ssh_command,
            vms=vms_for_upgrade_test,
            commands=shlex.split(
                f"curl -LO {stress_ng_url_for_cirros} && chmod 0755 stress-ng && ./stress-ng --version"
            ),
        )
        yield vms_for_upgrade_test
    monitor_api_requests.wait_for_idle()


@pytest.fixture(scope="module")
def monitor_api_requests_object(prometheus, vms_for_upgrade_test) -> MonitorResourceAPIServerRequests:
    return MonitorResourceAPIServerRequests(
        prometheus=prometheus,
        resource_class=VirtualMachine,
        idle_requests_value=VIRT_HANDLER_API_IDLE_STATE * len(vms_for_upgrade_test),
    )


@pytest.fixture()
def idle_monitored_api_requests(monitor_api_requests_object):
    monitor_api_requests_object.wait_for_idle()


@pytest.fixture(scope="module")
def running_vms_with_load(running_vms_for_upgrade_test, stopped_nginx_vm):
    commands = "./stress-ng --iomix 1 --cpu 1 --cpu-load 20 --cpu-load-slice 0 --vm 1 --timeout 0 &>/dev/null &"
    threaded_run_vm_ssh_command(vms=running_vms_for_upgrade_test, commands=shlex.split(commands))
    yield vms_for_upgrade_test
    threaded_run_vm_ssh_command(vms=running_vms_for_upgrade_test, commands=shlex.split("killall -9 stress-ng"))


@pytest.fixture()
def cache_key_scope_func(request):
    return request.param


@pytest.fixture(scope="class")
def cache_key_scope_class(request):
    return request.param


@pytest.fixture(scope="module")
def cache_key_scope_module(request):
    return request.param


@pytest.fixture()
def get_vm_guest_data_scope_func(request, cache_key_scope_func, vms_for_upgrade_test):
    guest_data = threaded_get_vm_guest_data(vms=vms_for_upgrade_test, commands=GUEST_DATA_COMMANDS)
    request.config.cache.set(f"{cache_key_scope_func}::get_vm_guest_data_scope_func", guest_data)
    return guest_data


@pytest.fixture(scope="class")
def get_vm_guest_data_scope_class(request, cache_key_scope_class, vms_for_upgrade_test):
    guest_data = threaded_get_vm_guest_data(vms=vms_for_upgrade_test, commands=GUEST_DATA_COMMANDS)
    request.config.cache.set(f"{cache_key_scope_class}::get_vm_guest_data_scope_class", guest_data)
    return guest_data


@pytest.mark.polarion("CNV-12243")
@pytest.mark.usefixtures("stress_ng_url_for_cirros")
@pytest.mark.parametrize(
    "cache_key_scope_func,created_data_source_for_scale,vms_for_upgrade_test",
    [
        pytest.param(
            "test_scale",
            {
                "namespace_name": NamespacesNames.OPENSHIFT_VIRTUALIZATION_OS_IMAGES,
                "storage_class": StorageClassNames.CEPH_RBD_VIRTUALIZATION,
                "volume_mode": DataVolume.VolumeMode.BLOCK,
                "access_modes": DataVolume.AccessMode.RWX,
            },
            [
                {
                    "vm_count": TOTAL_VM_COUNT,
                    "vm_instancetype": U1_PICO,
                    "vm_preference": OS_FLAVOR_CIRROS,
                    "os_flavor": OS_FLAVOR_CIRROS,
                },
            ],
        )
    ],
    indirect=True,
)
def test_scale(
    request,
    running_vms_with_load,
    cache_key_scope_func,
    get_vm_guest_data_scope_func,
    idle_monitored_api_requests,
):
    guest_data_list = threaded_get_vm_guest_data(vms=running_vms_with_load, commands=GUEST_DATA_COMMANDS)
    request.config.cache.set(f"{cache_key_scope_func}::guest_data_list", guest_data_list)
    threaded_verify_guest_data(
        data_before_action_list=get_vm_guest_data_scope_func, data_after_action_list=guest_data_list
    )


@pytest.mark.usefixtures("stress_ng_url_for_cirros")
@pytest.mark.parametrize(
    "cache_key_scope_class,created_data_source_for_scale,vms_for_upgrade_test",
    [
        pytest.param(
            "TestUpgradeScale",
            {
                "namespace_name": NamespacesNames.OPENSHIFT_VIRTUALIZATION_OS_IMAGES,
                "storage_class": StorageClassNames.CEPH_RBD_VIRTUALIZATION,
                "volume_mode": DataVolume.VolumeMode.BLOCK,
                "access_modes": DataVolume.AccessMode.RWX,
            },
            [
                {
                    "vm_count": TOTAL_VM_COUNT,
                    "vm_instancetype": U1_PICO,
                    "vm_preference": OS_FLAVOR_CIRROS,
                    "os_flavor": OS_FLAVOR_CIRROS,
                },
            ],
        )
    ],
    indirect=True,
)
class TestUpgradeScale:
    """Pre-upgrade tests"""

    @pytest.mark.polarion("CNV-12242")
    @pytest.mark.order(before=IUO_UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(name=f"{SCALE_NODE_ID_PREFIX}::test_load_running_before_upgrade")
    def test_load_running_before_upgrade(
        self,
        request,
        cache_key_scope_class,
        running_vms_with_load,
        get_vm_guest_data_scope_class,
        idle_monitored_api_requests,
    ):
        before_upgrade_list = threaded_get_vm_guest_data(vms=running_vms_with_load, commands=GUEST_DATA_COMMANDS)
        request.config.cache.set(f"{cache_key_scope_class}::before_upgrade_list", before_upgrade_list)
        threaded_verify_guest_data(
            data_before_action_list=get_vm_guest_data_scope_class, data_after_action_list=before_upgrade_list
        )

    """ Post-upgrade tests """

    @pytest.mark.polarion("CNV-11308")
    @pytest.mark.order(after=IUO_UPGRADE_TEST_ORDERING_NODE_ID)
    @pytest.mark.dependency(
        name=SCALE_VM_LOAD_RUNNING_AFTER_UPGRADE_ID,
        depends=[
            IUO_UPGRADE_TEST_DEPENDENCY_NODE_ID,
            f"{SCALE_NODE_ID_PREFIX}::test_load_running_before_upgrade",
        ],
        scope=DEPENDENCY_SCOPE_SESSION,
    )
    def test_load_running_after_upgrade(
        self,
        request,
        cache_key_scope_class,
        running_vms_with_load,
        get_vm_guest_data_scope_class,
        idle_monitored_api_requests,
    ):
        after_upgrade_list = threaded_get_vm_guest_data(vms=running_vms_with_load, commands=GUEST_DATA_COMMANDS)
        request.config.cache.set(f"{cache_key_scope_class}::after_upgrade_list", after_upgrade_list)
        threaded_verify_guest_data(
            data_before_action_list=get_vm_guest_data_scope_class,
            data_after_action_list=after_upgrade_list,
        )

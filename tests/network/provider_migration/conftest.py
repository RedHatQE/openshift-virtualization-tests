import contextlib
import uuid
from collections.abc import Generator
from typing import Final

import pytest
from kubernetes.dynamic import DynamicClient
from ocp_resources.forklift_controller import ForkliftController
from ocp_resources.migration import Migration
from ocp_resources.namespace import Namespace
from ocp_resources.network_map import NetworkMap
from ocp_resources.plan import Plan
from ocp_resources.provider import Provider
from ocp_resources.resource import ResourceEditor
from ocp_resources.secret import Secret
from ocp_resources.storage_map import StorageMap
from pytest_testconfig import config as py_config

from libs.net.udn import UDN_BINDING_DEFAULT_PLUGIN_NAME, create_udn_namespace
from libs.vm.vm import BaseVirtualMachine
from tests.network.libs import cluster_user_defined_network as libcudn
from tests.network.libs.label_selector import LabelSelector
from tests.network.libs.vm_factory import udn_vm
from tests.network.provider_migration.libprovider import (
    SourceHypervisorProvider,
    VmNotFoundError,
    extract_vm_primary_network_data,
)
from utilities.bitwarden import get_cnv_tests_secret_by_name
from utilities.constants import OS_FLAVOR_FEDORA

CUDN_LABEL: Final[dict] = {"cudn": "mtv"}
CUDN_SUBNET_IPV4: Final[str] = "192.168.100.0/24"
MTV_RESOURCE_TIMEOUT_SEC: Final[int] = 30
SOURCE_VM_NAME: Final[str] = f"cnv-vm-for-mtv-import-{uuid.uuid4().hex[:8]}"
VDDK_IMAGE: Final[str] = "quay.io/libvirt_v2v_cnv/vddk:8.0.1"


@pytest.fixture(scope="session")
def source_hypervisor_data() -> dict:
    return get_cnv_tests_secret_by_name(secret_name="source_hypervisor")


@pytest.fixture(scope="module")
def cudn_namespace(admin_client: DynamicClient) -> Generator[Namespace]:
    yield from create_udn_namespace(name="cudn-ns-for-mtv", client=admin_client, labels={**CUDN_LABEL})


@pytest.fixture(scope="module")
def cudn_layer2_for_mtv_import(
    admin_client: DynamicClient, cudn_namespace: Namespace
) -> Generator[libcudn.ClusterUserDefinedNetwork]:
    with libcudn.ClusterUserDefinedNetwork(
        name="l2-cudn-mtv",
        namespace_selector=LabelSelector(matchLabels=CUDN_LABEL),
        network=libcudn.Network(
            topology=libcudn.Network.Topology.LAYER2.value,
            layer2=libcudn.Layer2(
                role=libcudn.Layer2.Role.PRIMARY.value,
                ipam=libcudn.Ipam(mode=libcudn.Ipam.Mode.ENABLED.value, lifecycle="Persistent"),
                subnets=[CUDN_SUBNET_IPV4],
            ),
        ),
        client=admin_client,
    ) as cudn:
        cudn.wait_for_status_success()
        yield cudn
        # teardown will fail if there are any pods attached to cudn_namespace, need to clean up the namespace first
        cudn_namespace.clean_up()


@pytest.fixture(scope="module")
def source_vm_network_data(source_hypervisor_data: dict) -> Generator[tuple[str, str]]:
    with SourceHypervisorProvider(
        host=source_hypervisor_data["host"],
        username=source_hypervisor_data["user"],
        password=source_hypervisor_data["password"],
    ) as sp:
        try:
            vm = sp.clone_vm(template_name=source_hypervisor_data["vm_name"], clone_name=SOURCE_VM_NAME, power_on=True)
            yield extract_vm_primary_network_data(vm=vm)
        finally:
            with contextlib.suppress(VmNotFoundError):
                sp.delete_vm(vm_name=SOURCE_VM_NAME)


@pytest.fixture(scope="module")
def forklift_controller_udn_static_ip_patched(
    admin_client: DynamicClient, mtv_namespace_scope_session: Namespace
) -> Generator[None]:
    forklift_controller = ForkliftController(
        name="forklift-controller", namespace=mtv_namespace_scope_session.name, client=admin_client, ensure_exists=True
    )
    patch = {
        forklift_controller: {
            "spec": {
                "controller_static_udn_ip_addresses": "true",
            }
        }
    }

    with ResourceEditor(patches=patch):
        yield


@pytest.fixture(scope="module")
def source_hypervisor_secret(
    admin_client: DynamicClient, mtv_namespace_scope_session: Namespace, source_hypervisor_data: dict
) -> Generator[Secret]:
    with Secret(
        name="source-hypervisor-creds",
        namespace=mtv_namespace_scope_session.name,
        string_data={
            "user": source_hypervisor_data["user"],
            "password": source_hypervisor_data["password"],
            "insecureSkipVerify": "true",
        },
        type="Opaque",
        client=admin_client,
    ) as secret:
        yield secret


@pytest.fixture(scope="module")
def mtv_source_provider(
    admin_client: DynamicClient,
    cudn_namespace: Namespace,
    source_hypervisor_data: dict,
    source_hypervisor_secret: Secret,
) -> Generator[Provider]:
    with Provider(
        name="mtv-source-provider",
        namespace=cudn_namespace.name,
        provider_type=Provider.ProviderType.VSPHERE,
        url=f"https://{source_hypervisor_data['host']}/sdk",
        secret_name=source_hypervisor_secret.name,
        secret_namespace=source_hypervisor_secret.namespace,
        vddk_init_image=VDDK_IMAGE,
        client=admin_client,
    ) as provider:
        provider.wait_for_condition(
            condition=provider.Condition.READY, status=provider.Condition.Status.TRUE, timeout=MTV_RESOURCE_TIMEOUT_SEC
        )
        yield provider


@pytest.fixture(scope="module")
def mtv_target_provider(admin_client: DynamicClient, cudn_namespace: Namespace) -> Generator[Provider]:
    with Provider(
        name="mtv-target-provider",
        namespace=cudn_namespace.name,
        provider_type=Provider.ProviderType.OPENSHIFT,
        client=admin_client,
    ) as provider:
        provider.wait_for_condition(
            condition=provider.Condition.READY, status=provider.Condition.Status.TRUE, timeout=MTV_RESOURCE_TIMEOUT_SEC
        )
        yield provider


@pytest.fixture(scope="module")
def mtv_storage_map(
    admin_client: DynamicClient,
    source_hypervisor_data: dict,
    mtv_source_provider: Provider,
    mtv_target_provider: Provider,
) -> Generator[StorageMap]:
    mapping = [
        {
            "source": {"name": source_hypervisor_data["datastore_name"]},
            "destination": {"storageClass": py_config["default_storage_class"]},
        }
    ]
    with StorageMap(
        client=admin_client,
        name="mtv-storage-map",
        namespace=mtv_target_provider.namespace,
        source_provider_name=mtv_source_provider.name,
        source_provider_namespace=mtv_source_provider.namespace,
        destination_provider_name=mtv_target_provider.name,
        destination_provider_namespace=mtv_target_provider.namespace,
        mapping=mapping,
    ) as storage_map:
        storage_map.wait_for_condition(
            condition=storage_map.Condition.READY,
            status=storage_map.Condition.Status.TRUE,
            timeout=MTV_RESOURCE_TIMEOUT_SEC,
        )
        yield storage_map


@pytest.fixture(scope="module")
def mtv_network_map(
    admin_client: DynamicClient,
    cudn_namespace: Namespace,
    cudn_layer2_for_mtv_import: libcudn.ClusterUserDefinedNetwork,
    source_hypervisor_data: dict,
    mtv_source_provider: Provider,
    mtv_target_provider: Provider,
) -> Generator[NetworkMap]:
    mapping = [
        {
            "source": {"name": source_hypervisor_data["network_name"]},
            "destination": {"type": "pod", "namespace": cudn_namespace.name},
        }
    ]
    with NetworkMap(
        client=admin_client,
        name="mtv-network-map",
        namespace=cudn_namespace.name,
        source_provider_name=mtv_source_provider.name,
        source_provider_namespace=mtv_source_provider.namespace,
        destination_provider_name=mtv_target_provider.name,
        destination_provider_namespace=mtv_target_provider.namespace,
        mapping=mapping,
    ) as network_map:
        network_map.wait_for_condition(
            condition=network_map.Condition.READY,
            status=network_map.Condition.Status.TRUE,
            timeout=MTV_RESOURCE_TIMEOUT_SEC,
        )
        yield network_map


@pytest.fixture(scope="module")
def mtv_migration_plan_to_cudn_ns(
    admin_client: DynamicClient,
    cudn_namespace: Namespace,
    source_hypervisor_data: dict,
    mtv_source_provider: Provider,
    mtv_target_provider: Provider,
    mtv_storage_map: StorageMap,
    mtv_network_map: NetworkMap,
    forklift_controller_udn_static_ip_patched: None,
    source_vm_network_data: tuple,
) -> Generator[Plan]:
    with Plan(
        client=admin_client,
        name="mtv-migration-plan-to-cudn-ns",
        namespace=cudn_namespace.name,
        network_map_name=mtv_network_map.name,
        network_map_namespace=mtv_network_map.namespace,
        storage_map_name=mtv_storage_map.name,
        storage_map_namespace=mtv_storage_map.namespace,
        source_provider_name=mtv_source_provider.name,
        source_provider_namespace=mtv_source_provider.namespace,
        destination_provider_name=mtv_target_provider.name,
        destination_provider_namespace=mtv_target_provider.namespace,
        target_namespace=cudn_namespace.name,
        virtual_machines_list=[{"name": SOURCE_VM_NAME}],
        type="cold",
        target_power_state="on",
        preserve_static_ips=True,
    ) as plan:
        plan.wait_for_condition(condition=plan.Condition.READY, status=plan.Condition.Status.TRUE, timeout=180)
        yield plan


@pytest.fixture(scope="module")
def mtv_migration_to_cudn_ns(admin_client: DynamicClient, mtv_migration_plan_to_cudn_ns: Plan) -> Generator[None]:
    with Migration(
        client=admin_client,
        name=mtv_migration_plan_to_cudn_ns.name,
        namespace=mtv_migration_plan_to_cudn_ns.namespace,
        plan_name=mtv_migration_plan_to_cudn_ns.name,
        plan_namespace=mtv_migration_plan_to_cudn_ns.namespace,
    ):
        mtv_migration_plan_to_cudn_ns.wait_for_condition(
            condition=mtv_migration_plan_to_cudn_ns.Condition.Type.SUCCEEDED,
            status=mtv_migration_plan_to_cudn_ns.Condition.Status.TRUE,
            timeout=1000,
            sleep_time=10,
        )
        yield


@pytest.fixture(scope="module")
def imported_cudn_vm(
    admin_client: DynamicClient, cudn_namespace: Namespace, source_hypervisor_data: dict, mtv_migration_to_cudn_ns: None
) -> Generator[BaseVirtualMachine]:
    vm = BaseVirtualMachine.from_existing(
        name=SOURCE_VM_NAME,
        namespace=cudn_namespace.name,
        client=admin_client,
        os_distribution=OS_FLAVOR_FEDORA,
    )
    try:
        vm.wait_for_agent_connected()
        yield vm
    finally:
        vm.clean_up()


@pytest.fixture(scope="module")
def local_cudn_vm(
    admin_client: DynamicClient,
    cudn_namespace: Namespace,
    cudn_layer2_for_mtv_import: libcudn.ClusterUserDefinedNetwork,
) -> Generator[BaseVirtualMachine]:
    with udn_vm(
        namespace_name=cudn_namespace.name,
        name="vm-local-cudn",
        client=admin_client,
        binding=UDN_BINDING_DEFAULT_PLUGIN_NAME,
    ) as vm:
        vm.start(wait=True)
        vm.wait_for_agent_connected()
        yield vm

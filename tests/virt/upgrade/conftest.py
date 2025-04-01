import logging
from contextlib import contextmanager
from copy import deepcopy

import pytest
from ocp_resources.data_source import DataSource
from ocp_resources.datavolume import DataVolume
from ocp_resources.template import Template
from ocp_resources.virtual_machine import VirtualMachine
from ocp_resources.virtual_machine_cluster_instancetype import VirtualMachineClusterInstancetype
from ocp_resources.virtual_machine_cluster_preference import VirtualMachineClusterPreference
from pytest_testconfig import py_config

from tests.virt.upgrade.utils import (
    get_all_migratable_vms,
    get_vm_boot_time,
    validate_vms_pod_updated,
    wait_for_automatic_vm_migrations,
)
from utilities.constants import (
    ES_LIVE_MIGRATE_IF_POSSIBLE,
    OS_FLAVOR_RHEL,
    TIMEOUT_30MIN,
    TIMEOUT_40MIN,
    TIMEOUT_90MIN,
    Images,
)
from utilities.infra import (
    check_pod_disruption_budget_for_completed_migrations,
)
from utilities.storage import (
    create_dv,
    data_volume_template_with_source_ref_dict,
    generate_data_source_dict,
    get_test_artifact_server_url,
)
from utilities.virt import (
    VirtualMachineForTests,
    VirtualMachineForTestsFromTemplate,
    get_base_templates_list,
    running_vm,
)

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def datasources_for_upgrade(admin_client, dvs_for_upgrade):
    data_source_list = []
    for dv in dvs_for_upgrade:
        data_source = DataSource(
            name=dv.name.replace("dv", "ds"),
            namespace=dv.namespace,
            client=admin_client,
            source=generate_data_source_dict(dv=dv),
        )
        data_source.deploy()
        data_source_list.append(data_source)

    yield data_source_list

    for data_source in data_source_list:
        data_source.clean_up()


@pytest.fixture(scope="session")
def vms_for_upgrade(
    unprivileged_client,
    upgrade_namespace_scope_session,
    datasources_for_upgrade,
    cpu_for_migration,
    rhel_latest_os_params,
    sno_cluster,
    vm_with_instancetypes_for_upgrade,
):
    vms_list = [vm_with_instancetypes_for_upgrade]
    try:
        for data_source in datasources_for_upgrade:
            vm = VirtualMachineForTestsFromTemplate(
                name=data_source.name.replace("ds", "vm")[0:26],
                namespace=upgrade_namespace_scope_session.name,
                client=unprivileged_client,
                labels=Template.generate_template_labels(**rhel_latest_os_params["rhel_template_labels"]),
                data_source=data_source,
                cpu_model=cpu_for_migration,
                sno_cluster=sno_cluster,
            )
            vm.deploy()
            vms_list.append(vm)
            vm.start(timeout=TIMEOUT_40MIN, wait=False)

        for vm in vms_list:
            running_vm(vm=vm, wait_for_cloud_init=True)

        yield vms_list

    finally:
        for vm in vms_list:
            vm.clean_up()


@pytest.fixture(scope="session")
def vm_cluster_preference_for_upgrade():
    with VirtualMachineClusterPreference(
        name="basic-cluster-preference-for-upgrade",
    ) as vm_cluster_preference:
        yield vm_cluster_preference


@pytest.fixture(scope="session")
def vm_cluster_instancetype_for_upgrade(cluster_common_node_cpu):
    with VirtualMachineClusterInstancetype(
        name="basic-cluster-instancetype-for-upgrade",
        cpu={"guest": 1, "model": cluster_common_node_cpu},
        memory={"guest": Images.Rhel.DEFAULT_MEMORY_SIZE},
    ) as cluster_instance_type:
        yield cluster_instance_type


@pytest.fixture(scope="session")
def vm_with_instancetypes_for_upgrade(
    unprivileged_client,
    upgrade_namespace_scope_session,
    vm_cluster_instancetype_for_upgrade,
    vm_cluster_preference_for_upgrade,
    datasources_for_upgrade,
):
    with VirtualMachineForTests(
        client=unprivileged_client,
        name="rhel-vm-with-instance-type",
        namespace=upgrade_namespace_scope_session.name,
        os_flavor=OS_FLAVOR_RHEL,
        vm_instance_type=vm_cluster_instancetype_for_upgrade,
        vm_preference=vm_cluster_preference_for_upgrade,
        data_volume_template=data_volume_template_with_source_ref_dict(data_source=datasources_for_upgrade[0]),
    ) as vm:
        yield vm


@pytest.fixture(scope="session")
def vms_for_upgrade_dict_before(vms_for_upgrade):
    vms_dict = {}
    for vm in vms_for_upgrade:
        vms_dict[vm.name] = deepcopy(vm.instance.to_dict())
    yield vms_dict


@pytest.fixture(scope="session")
def upgrade_namespaces(upgrade_namespace_scope_session, kmp_enabled_namespace):
    return [kmp_enabled_namespace, upgrade_namespace_scope_session]


@pytest.fixture(scope="session")
def migratable_vms(admin_client, hco_namespace, upgrade_namespaces):
    migratable_vms = get_all_migratable_vms(admin_client=admin_client, namespaces=upgrade_namespaces)
    LOGGER.info(f"All migratable vms: {[vm.name for vm in migratable_vms]}")
    return migratable_vms


@pytest.fixture()
def unupdated_vmi_pods_names(
    admin_client, hco_namespace, hco_target_csv_name, eus_hco_target_csv_name, upgrade_namespaces, migratable_vms
):
    wait_for_automatic_vm_migrations(vm_list=migratable_vms)

    for ns in upgrade_namespaces:
        LOGGER.info(f"Checking PodDisruptionBudget in namespaces: {ns.name}")
        check_pod_disruption_budget_for_completed_migrations(
            admin_client=admin_client, namespace=ns.name, timeout=TIMEOUT_90MIN
        )

    return validate_vms_pod_updated(
        admin_client=admin_client,
        hco_namespace=hco_namespace,
        hco_target_csv_name=hco_target_csv_name or eus_hco_target_csv_name,
        vm_list=migratable_vms,
    )


@pytest.fixture(scope="session")
def run_strategy_golden_image_dv(dvs_for_upgrade):
    # Give the priority to RWX storage
    rwx_dv = [dv for dv in dvs_for_upgrade if DataVolume.AccessMode.RWX in dv.pvc.instance.spec.accessModes]
    return rwx_dv[0] if rwx_dv else dvs_for_upgrade[0]


@contextmanager
def vm_from_template(
    client,
    namespace,
    vm_name,
    data_source,
    cpu_model,
    template_labels,
    networks=None,
    run_strategy=VirtualMachine.RunStrategy.HALTED,
    eviction_strategy=None,
):
    with VirtualMachineForTestsFromTemplate(
        name=vm_name,
        namespace=namespace,
        client=client,
        labels=Template.generate_template_labels(**template_labels),
        data_source=data_source,
        cpu_model=cpu_model,
        run_strategy=run_strategy,
        networks=networks,
        interfaces=sorted(networks.keys()) if networks else None,
        eviction_strategy=eviction_strategy,
    ) as vm:
        yield vm


@pytest.fixture(scope="session")
def manual_run_strategy_vm(
    unprivileged_client,
    upgrade_namespace_scope_session,
    run_strategy_golden_image_data_source,
    cpu_for_migration,
    rhel_latest_os_params,
):
    with vm_from_template(
        vm_name="manual-run-strategy-vm",
        namespace=upgrade_namespace_scope_session.name,
        client=unprivileged_client,
        template_labels=rhel_latest_os_params["rhel_template_labels"],
        data_source=run_strategy_golden_image_data_source,
        run_strategy=VirtualMachine.RunStrategy.MANUAL,
        cpu_model=cpu_for_migration,
        eviction_strategy=ES_LIVE_MIGRATE_IF_POSSIBLE,
    ) as vm:
        vm.start()
        yield vm


@pytest.fixture(scope="session")
def always_run_strategy_vm(
    unprivileged_client,
    upgrade_namespace_scope_session,
    run_strategy_golden_image_data_source,
    cpu_for_migration,
    rhel_latest_os_params,
):
    with vm_from_template(
        vm_name="always-run-strategy-vm",
        namespace=upgrade_namespace_scope_session.name,
        client=unprivileged_client,
        template_labels=rhel_latest_os_params["rhel_template_labels"],
        data_source=run_strategy_golden_image_data_source,
        run_strategy=VirtualMachine.RunStrategy.ALWAYS,
        cpu_model=cpu_for_migration,
        eviction_strategy=ES_LIVE_MIGRATE_IF_POSSIBLE,
    ) as vm:
        # No need to start the VM as the VM will be automatically started (RunStrategy Always)
        yield vm


@pytest.fixture()
def running_manual_run_strategy_vm(manual_run_strategy_vm):
    running_vm(vm=manual_run_strategy_vm, check_ssh_connectivity=False)


@pytest.fixture()
def running_always_run_strategy_vm(always_run_strategy_vm):
    running_vm(vm=always_run_strategy_vm, check_ssh_connectivity=False)


@pytest.fixture(scope="session")
def windows_vm(
    admin_client,
    unprivileged_client,
    upgrade_namespace_scope_session,
    modern_cpu_for_migration,
):
    latest_windows_dict = py_config["latest_windows_os_dict"]
    with create_dv(
        client=admin_client,
        dv_name=latest_windows_dict["os_version"],
        namespace=py_config["golden_images_namespace"],
        url=f"{get_test_artifact_server_url()}{latest_windows_dict['image_path']}",
        storage_class=py_config["default_storage_class"],
        access_modes=py_config["default_access_mode"],
        volume_mode=py_config["default_volume_mode"],
        size=latest_windows_dict["dv_size"],
    ) as dv:
        dv.wait_for_dv_success(timeout=TIMEOUT_30MIN)
        with DataSource(
            name=dv.name,
            namespace=dv.namespace,
            client=admin_client,
            source=generate_data_source_dict(dv=dv),
        ) as ds:
            with vm_from_template(
                vm_name="windows-vm",
                namespace=upgrade_namespace_scope_session.name,
                client=unprivileged_client,
                template_labels=latest_windows_dict["template_labels"],
                data_source=ds,
                cpu_model=modern_cpu_for_migration,
            ) as vm:
                running_vm(vm=vm, check_ssh_connectivity=False)
                yield vm


@pytest.fixture()
def base_templates_after_upgrade(admin_client):
    return get_base_templates_list(client=admin_client)


@pytest.fixture(scope="session")
def run_strategy_golden_image_data_source(admin_client, run_strategy_golden_image_dv):
    with DataSource(
        name=run_strategy_golden_image_dv.name,
        namespace=run_strategy_golden_image_dv.namespace,
        client=admin_client,
        source=generate_data_source_dict(dv=run_strategy_golden_image_dv),
    ) as ds:
        yield ds


@pytest.fixture(scope="session")
def linux_boot_time_before_upgrade(vms_for_upgrade):
    boot_time_dict = {}
    for vm in vms_for_upgrade:
        boot_time_dict[vm.name] = get_vm_boot_time(vm=vm)
    yield boot_time_dict


@pytest.fixture(scope="session")
def windows_boot_time_before_upgrade(windows_vm):
    yield get_vm_boot_time(vm=windows_vm)

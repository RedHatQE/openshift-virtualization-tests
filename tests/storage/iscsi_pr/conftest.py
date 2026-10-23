from contextlib import ExitStack, contextmanager
from logging import getLogger
from uuid import uuid4

from ocp_resources.datavolume import DataVolume
from ocp_resources.kubevirt import KubeVirt
from ocp_resources.virtual_machine_cluster_instancetype import VirtualMachineClusterInstancetype
from ocp_resources.virtual_machine_cluster_preference import VirtualMachineClusterPreference
from pytest import fixture
from pytest_testconfig import config as py_config

from tests.storage.iscsi_pr.bootstrap import prepared_hosts, prepared_multipath
from tests.storage.iscsi_pr.domain import isolated_domain, prepare_domain_controller, prepare_domain_member
from tests.storage.iscsi_pr.multipath import vm_multipath_readiness, windows_shared_luns
from tests.storage.iscsi_pr.networking import (
    guest_macs,
    guest_networks,
    router_cloud_init,
    router_readiness,
    windows_network_readiness,
    windows_network_setup_script,
)
from tests.storage.iscsi_pr.utils import (
    IscsiTarget,
    add_target_backing_disks,
    host_storage_preflight,
    shared_iscsi_claims,
    target_cloud_init,
    target_readiness,
    vm_body_with_root,
    wait_for_target_detach,
)
from utilities.artifactory import get_test_artifact_server_url
from utilities.constants.networking import FLAT_OVERLAY_STR, LINUX_BRIDGE
from utilities.constants.timeouts import TIMEOUT_5MIN, TIMEOUT_10MIN, TIMEOUT_50MIN
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.network import network_nad
from utilities.storage import create_dv, data_volume_template_with_source_ref_dict
from utilities.virt import (
    VirtualMachineForTests,
    get_or_create_golden_image_data_source,
    get_windows_os_dict,
    running_vm,
    wait_for_cloud_init_complete,
    wait_for_windows_vm,
)
from utilities.windows import run_powershell

LOGGER = getLogger(name=__name__)


@fixture(scope="module")
def iscsi_pr_windows_data_sources(admin_client, golden_images_namespace):
    """Reuse or import each required Windows source once; release it after consumers."""
    with ExitStack() as stack:
        sources = {}
        for version in ("2025", "2019"):
            image = get_windows_os_dict(windows_version=f"win-{version}")
            assert image, f"CI must supply Windows Server {version} in system_windows_os_matrix"
            sources[version] = stack.enter_context(
                cm=contextmanager(func=get_or_create_golden_image_data_source)(
                    admin_client=admin_client, golden_images_namespace=golden_images_namespace, os_dict=image
                )
            )
        yield sources


@fixture(scope="module")
def iscsi_pr_hosts(
    admin_client,
    schedulable_nodes,
    workers,
    workers_utility_pods,
    fedora_data_source_scope_module,
    iscsi_pr_windows_data_sources,
):
    """Resolve image sources before preparing workers; restore host state last."""
    eligible = [node for node in schedulable_nodes if node.name in {worker.name for worker in workers}]
    with prepared_hosts(client=admin_client, workers=eligible, utility_pods=workers_utility_pods) as hosts:
        hosts["initiators"] = host_storage_preflight(executors=hosts["executors"], networks=hosts["plan"].networks)
        yield hosts


@fixture(scope="module")
def iscsi_pr_target(
    admin_client,
    namespace,
    iscsi_pr_hosts,
    fedora_data_source_scope_module,
):
    """Supply the exported Fedora target; keep it alive until consumers detach."""
    networks = iscsi_pr_hosts["plan"].networks
    target = IscsiTarget(
        iqn=f"iqn.2026-10.com.redhat:cnv-{uuid4().hex}",
        portal_addresses=tuple(str(network.target_address.ip) for network in networks),
    )
    macs = guest_macs(names=("management", "storage0", "storage1"))
    with ExitStack() as stack:
        nads = tuple(
            stack.enter_context(
                cm=network_nad(
                    nad_type=LINUX_BRIDGE,
                    nad_name=f"iscsi-storage-{index}",
                    namespace=namespace,
                    client=admin_client,
                    interface_name=network.bridge,
                    mtu=network.mtu,
                    add_resource_name=False,
                )
            )
            for index, network in enumerate(networks)
        )
        root = data_volume_template_with_source_ref_dict(
            data_source=fedora_data_source_scope_module,
            storage_class=py_config["default_storage_class"],
            name="iscsi-target-root",
        )
        backings = tuple(
            stack.enter_context(
                cm=create_dv(
                    dv_name=f"iscsi-backing-{lun}",
                    namespace=namespace.name,
                    client=admin_client,
                    storage_class=py_config["default_storage_class"],
                    source="blank",
                    size=f"{size}Gi",
                    consume_wffc=False,
                )
            )
            for lun, size in enumerate((50, 70))
        )
        vm = VirtualMachineForTests(
            name="iscsi-target",
            namespace=namespace.name,
            client=admin_client,
            eviction_strategy="None",
            vm_preference=VirtualMachineClusterPreference(name="fedora", client=admin_client),
            memory_guest="2Gi",
            cpu_cores=2,
            node_selector={"kubernetes.io/hostname": iscsi_pr_hosts["workers"][0].hostname},
            interfaces=list(macs),
            interfaces_types={"management": "masquerade"},
            macs=macs,
            networks={f"storage{index}": nad.name for index, nad in enumerate(nads)},
            cloud_init_data=target_cloud_init(
                target=target,
                networks=networks,
                macs=macs,
                initiators=iscsi_pr_hosts["initiators"],
            ),
        )
        vm.body = vm_body_with_root(name=vm.name, data_volume_template=root)
        spec = vm.body["spec"]["template"]["spec"]
        spec["networks"] = [{"name": "management", "pod": {}}]
        add_target_backing_disks(template_spec=spec, volume_names=(backings[0].name, backings[1].name))
        stack.enter_context(cm=vm)
        running_vm(vm=vm)
        wait_for_cloud_init_complete(vm=vm, timeout=TIMEOUT_10MIN)
        serials = target_readiness(
            vm=vm,
            target=target,
            initiators=iscsi_pr_hosts["initiators"],
        )
        yield {"vm": vm, "target": target, "lun_wwns": serials, "workers": iscsi_pr_hosts["workers"], "wwids": set()}


@fixture(scope="module")
def enabled_iscsi_persistent_reservation_configuration_in_hco(
    admin_client, hco_namespace, hyperconverged_resource_scope_module, iscsi_pr_hosts
):
    """Enable reconciled PR before consumers start; restore it after they detach."""
    with ResourceEditorValidateHCOReconcile(
        admin_client=admin_client,
        hco_namespace=hco_namespace.name,
        patches={
            hyperconverged_resource_scope_module: {
                "spec": {"storage": {"persistentReservationConfiguration": {"enabled": True}}}
            }
        },
        list_resource_reconcile=[KubeVirt],
        wait_for_reconcile_post_update=True,
    ):
        assert hyperconverged_resource_scope_module.instance.spec.storage.persistentReservationConfiguration.enabled, (
            "HCO persistent reservations configuration is not enabled"
        )
        yield hyperconverged_resource_scope_module


@fixture(scope="module")
def iscsi_pr_shared_claims(
    admin_client,
    namespace,
    workers_utility_pods,
    iscsi_pr_target,
    enabled_iscsi_persistent_reservation_configuration_in_hco,
):
    """Keep claims and target available while consumer storage detaches."""
    with shared_iscsi_claims(client=admin_client, namespace=namespace.name, target=iscsi_pr_target["target"]) as claims:
        try:
            yield claims
        finally:
            wait_for_target_detach(
                workers=iscsi_pr_target["workers"],
                utility_pods=workers_utility_pods,
                target=iscsi_pr_target["target"],
                observed_wwids=iscsi_pr_target["wwids"],
            )


@fixture(scope="module")
def iscsi_pr_host_multipath(iscsi_pr_hosts, iscsi_pr_target, iscsi_pr_shared_claims):
    """Supply verified maps by worker; release sessions after Windows deletion."""
    with prepared_multipath(
        hosts=iscsi_pr_hosts,
        target=iscsi_pr_target["target"],
        lun_wwns=iscsi_pr_target["lun_wwns"],
        observed=iscsi_pr_target["wwids"],
    ) as mappings:
        yield mappings


@fixture(scope="module")
def iscsi_pr_guest_networks(iscsi_pr_hosts):
    return guest_networks()


@fixture(scope="module")
def iscsi_pr_guest_nads(admin_client, namespace, iscsi_pr_guest_networks):
    """Supply two isolated OVN Layer 2 networks without automatic IPAM."""
    with ExitStack() as stack:
        yield tuple(
            stack.enter_context(
                cm=network_nad(
                    nad_type=FLAT_OVERLAY_STR,
                    nad_name=f"iscsi-{network.name}",
                    namespace=namespace,
                    client=admin_client,
                    network_name=f"{namespace.name}-iscsi-{network.name}",
                    topology=FLAT_OVERLAY_STR,
                )
            )
            for network in iscsi_pr_guest_networks
        )


@fixture(scope="module")
def iscsi_pr_router(
    admin_client,
    namespace,
    iscsi_pr_hosts,
    iscsi_pr_guest_networks,
    iscsi_pr_guest_nads,
    fedora_data_source_scope_module,
):
    """Supply Fedora routing; delete its VM before the private root and networks."""
    networks = iscsi_pr_guest_networks
    macs = guest_macs(names=("management", *(network.name for network in networks)))
    root = data_volume_template_with_source_ref_dict(
        data_source=fedora_data_source_scope_module,
        storage_class=py_config["default_storage_class"],
        name="iscsi-router-root",
    )
    vm = VirtualMachineForTests(
        name="iscsi-router",
        namespace=namespace.name,
        client=admin_client,
        eviction_strategy="None",
        vm_preference=VirtualMachineClusterPreference(name="fedora", client=admin_client),
        memory_guest="2Gi",
        cpu_cores=2,
        node_selector={"kubernetes.io/hostname": iscsi_pr_hosts["workers"][0].hostname},
        interfaces=list(macs),
        interfaces_types={"management": "masquerade"},
        macs=macs,
        networks={network.name: nad.name for network, nad in zip(networks, iscsi_pr_guest_nads, strict=True)},
        cloud_init_data=router_cloud_init(networks=networks, macs=macs),
    )
    vm.body = vm_body_with_root(name=vm.name, data_volume_template=root)
    vm.body["spec"]["template"]["spec"]["networks"] = [{"name": "management", "pod": {}}]
    with vm:
        running_vm(vm=vm)
        wait_for_cloud_init_complete(vm=vm, timeout=TIMEOUT_10MIN)
        endpoint = router_readiness(vm=vm, networks=networks, artifact_url=get_test_artifact_server_url())
        yield {"vm": vm, "egress": endpoint}


@fixture(scope="module")
def iscsi_pr_windows_vms(
    admin_client,
    namespace,
    workers_utility_pods,
    iscsi_pr_target,
    iscsi_pr_shared_claims,
    iscsi_pr_guest_networks,
    iscsi_pr_guest_nads,
    iscsi_pr_router,
    iscsi_pr_host_multipath,
    iscsi_pr_windows_data_sources,
):
    """Boot Windows from private clones; keep image sources alive until VM cleanup."""
    workers = iscsi_pr_target["workers"]
    versions = ("2025", "2019", "2019")
    macs = tuple(
        guest_macs(names=("management", *(network.name for network in iscsi_pr_guest_networks))) for _ in versions
    )
    with ExitStack() as consumers:
        vms, roots, guest_luns = [], [], []
        for index, version in enumerate(versions):
            root = data_volume_template_with_source_ref_dict(
                data_source=iscsi_pr_windows_data_sources[version],
                storage_class=py_config["default_storage_class"],
                name=f"iscsi-windows-root-{index}",
            )
            vm = VirtualMachineForTests(
                name=f"iscsi-windows-{index}",
                namespace=namespace.name,
                client=admin_client,
                os_flavor="win",
                eviction_strategy="None",
                vm_instance_type=VirtualMachineClusterInstancetype(name="u1.xlarge", client=admin_client),
                vm_preference=VirtualMachineClusterPreference(name=f"windows.2k{version[-2:]}", client=admin_client),
                node_selector={"kubernetes.io/hostname": workers[index].hostname},
                interfaces=list(macs[index]),
                interfaces_types={"management": "masquerade"},
                macs=macs[index],
                networks={
                    network.name: nad.name
                    for network, nad in zip(iscsi_pr_guest_networks, iscsi_pr_guest_nads, strict=True)
                },
            )
            vm.body = vm_body_with_root(name=vm.name, data_volume_template=root)
            spec = vm.body["spec"]["template"]["spec"]
            spec["networks"] = [{"name": "management", "pod": {}}]
            for lun, claim in enumerate(iscsi_pr_shared_claims):
                name = f"shared-lun-{lun}"
                spec["domain"]["devices"]["disks"].append({
                    "name": name,
                    "lun": {"bus": "scsi", "reservation": True},
                    "shareable": True,
                    "cache": "none",
                })
                spec["volumes"].append({"name": name, "persistentVolumeClaim": {"claimName": claim.name}})
            consumers.enter_context(cm=vm)
            # The following CIM query verifies authenticated SSH and the expected guest OS.
            running_vm(vm=vm, check_ssh_connectivity=False, dv_wait_timeout=TIMEOUT_50MIN)
            wait_for_windows_vm(vm=vm, version=version)
            vm_multipath_readiness(
                vm=vm,
                client=admin_client,
                utility_pods=workers_utility_pods,
                mappings_by_worker=iscsi_pr_host_multipath,
            )
            guest_luns.append(windows_shared_luns(vm=vm, lun_wwns=iscsi_pr_target["lun_wwns"]))
            vms.append(vm)
            roots.append(
                DataVolume(
                    name=root["metadata"]["name"], namespace=namespace.name, client=admin_client, api_name="storage"
                )
            )
        yield {"vms": tuple(vms), "roots": tuple(roots), "macs": macs, "guest_luns": tuple(guest_luns)}


@fixture(scope="module")
def iscsi_pr_guest_networking(iscsi_pr_windows_vms, iscsi_pr_router, iscsi_pr_guest_networks):
    """Configure all Windows peers before checking guest routes once."""
    vms, macs = iscsi_pr_windows_vms["vms"], iscsi_pr_windows_vms["macs"]
    for index, vm in enumerate(vms):
        LOGGER.info(
            f"VM {vm.name}: applying static guest NIC addresses, routes, DNS registration and ICMP firewall rule"
        )
        run_powershell(
            ssh_exec=vm.ssh_exec,
            script=windows_network_setup_script(
                index=index,
                networks=iscsi_pr_guest_networks,
                macs=macs[index],
                egress=iscsi_pr_router["egress"],
            ),
            timeout=TIMEOUT_5MIN,
        )
        LOGGER.info(
            f"VM {vm.name}: guest network configuration applied; connectivity checks follow after all peers are configured"
        )
    for index, vm in enumerate(vms):
        windows_network_readiness(
            vm=vm,
            index=index,
            networks=iscsi_pr_guest_networks,
            macs=macs[index],
            egress=iscsi_pr_router["egress"],
        )
    return {**iscsi_pr_windows_vms, "router": iscsi_pr_router["vm"], "networks": iscsi_pr_guest_networks}


@fixture(scope="module")
def iscsi_pr_environment(iscsi_pr_guest_networking, enabled_iscsi_persistent_reservation_configuration_in_hco):
    """Supply a DC and two joined members using the already configured guests."""
    environment = iscsi_pr_guest_networking
    domain = isolated_domain()
    vms = environment["vms"]
    members = [prepare_domain_controller(vm=vms[0], domain=domain, network=environment["networks"][0])]
    members.extend(
        prepare_domain_member(vm=vm, domain=domain, network=environment["networks"][0], index=index)
        for index, vm in enumerate(vms[1:], start=1)
    )
    assert enabled_iscsi_persistent_reservation_configuration_in_hco.instance.spec.storage.persistentReservationConfiguration.enabled, (
        "HCO persistent reservations became disabled during preparation"
    )
    return {**environment, "domain": domain, "members": tuple(members)}

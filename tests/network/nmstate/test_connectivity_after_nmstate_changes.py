import logging
from collections import OrderedDict

import pytest
from ocp_resources.resource import ResourceEditor
from timeout_sampler import TimeoutSampler

from tests.network.utils import (
    assert_nncp_successfully_configured,
    assert_ssh_alive,
    run_ssh_in_background,
)
from utilities.constants import (
    LINUX_BRIDGE,
    NMSTATE_HANDLER,
    TIMEOUT_1MIN,
    TIMEOUT_5SEC,
)
from utilities.infra import get_node_selector_dict, get_pod_by_name_prefix, name_prefix
from utilities.network import (
    assert_ping_successful,
    compose_cloud_init_data_dict,
    get_vmi_ip_v4_by_name,
    is_destination_pingable_from_vm,
    network_device,
    network_nad,
)
from utilities.virt import VirtualMachineForTests, fedora_vm_body, running_vm

LOGGER = logging.getLogger(__name__)
BRIDGE_NAME = "br-nmstate"


def restart_nmstate_handler(admin_client, nmstate_ds, nmstate_namespace):
    LOGGER.info("Delete NMstate PODs")
    for pod in get_pod_by_name_prefix(
        dyn_client=admin_client,
        pod_prefix=NMSTATE_HANDLER,
        namespace=nmstate_namespace.name,
        get_all=True,
    ):
        pod.delete(wait=True)
    nmstate_ds.wait_until_deployed()


@pytest.fixture(scope="class")
def nmstate_linux_bridge_device_worker_1(nodes_available_nics, worker_node1):
    with network_device(
        interface_type=LINUX_BRIDGE,
        nncp_name=f"restart-nmstate-{name_prefix(worker_node1.name)}",
        interface_name=BRIDGE_NAME,
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
        ports=[nodes_available_nics[worker_node1.name][-1]],
    ) as br_dev:
        yield br_dev


@pytest.fixture(scope="class")
def nmstate_linux_bridge_device_worker_2(nodes_available_nics, worker_node2):
    with network_device(
        interface_type=LINUX_BRIDGE,
        nncp_name=f"restart-nmstate-{name_prefix(worker_node2.name)}",
        interface_name=BRIDGE_NAME,
        node_selector=get_node_selector_dict(node_selector=worker_node2.hostname),
        ports=[nodes_available_nics[worker_node2.name][-1]],
    ) as br_dev:
        yield br_dev


@pytest.fixture(scope="class")
def nmstate_linux_nad(
    namespace,
    nmstate_linux_bridge_device_worker_1,
    nmstate_linux_bridge_device_worker_2,
):
    with network_nad(
        namespace=namespace,
        nad_type=nmstate_linux_bridge_device_worker_1.bridge_type,
        nad_name="nmstate-br1test-nad",
        interface_name=nmstate_linux_bridge_device_worker_1.bridge_name,
    ) as nad:
        yield nad


@pytest.fixture(scope="class")
def nmstate_linux_bridge_attached_vma(
    worker_node1,
    namespace,
    unprivileged_client,
    nmstate_linux_nad,
):
    name = "vma"
    networks = OrderedDict()
    networks[nmstate_linux_nad.name] = nmstate_linux_nad.name
    network_data_data = {
        "ethernets": {
            "eth1": {"addresses": ["10.200.0.1/24"]},
        }
    }

    cloud_init_data = compose_cloud_init_data_dict(
        network_data=network_data_data,
    )

    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        body=fedora_vm_body(name=name),
        networks=networks,
        interfaces=networks.keys(),
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
        cloud_init_data=cloud_init_data,
        client=unprivileged_client,
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="class")
def nmstate_linux_bridge_attached_vmb(
    worker_node2,
    namespace,
    unprivileged_client,
    nmstate_linux_nad,
):
    name = "vmb"
    networks = OrderedDict()
    networks[nmstate_linux_nad.name] = nmstate_linux_nad.name
    network_data_data = {
        "ethernets": {
            "eth1": {"addresses": ["10.200.0.2/24"]},
        }
    }

    cloud_init_data = compose_cloud_init_data_dict(
        network_data=network_data_data,
    )

    with VirtualMachineForTests(
        namespace=namespace.name,
        name=name,
        body=fedora_vm_body(name=name),
        networks=networks,
        interfaces=networks.keys(),
        node_selector=get_node_selector_dict(node_selector=worker_node2.hostname),
        cloud_init_data=cloud_init_data,
        client=unprivileged_client,
    ) as vm:
        vm.start(wait=True)
        yield vm


@pytest.fixture(scope="class")
def nmstate_linux_bridge_attached_running_vma(nmstate_linux_bridge_attached_vma):
    return running_vm(vm=nmstate_linux_bridge_attached_vma, wait_for_cloud_init=True)


@pytest.fixture(scope="class")
def nmstate_linux_bridge_attached_running_vmb(nmstate_linux_bridge_attached_vmb):
    return running_vm(vm=nmstate_linux_bridge_attached_vmb, wait_for_cloud_init=True)


@pytest.fixture(scope="class")
def vma_src_ip(nmstate_linux_nad, nmstate_linux_bridge_attached_running_vma):
    return str(get_vmi_ip_v4_by_name(vm=nmstate_linux_bridge_attached_running_vma, name=nmstate_linux_nad.name))


@pytest.fixture(scope="class")
def vmb_dst_ip(nmstate_linux_nad, nmstate_linux_bridge_attached_running_vmb):
    return get_vmi_ip_v4_by_name(
        vm=nmstate_linux_bridge_attached_running_vmb,
        name=nmstate_linux_nad.name,
    )


@pytest.fixture(scope="class")
def vmb_pinged(vmb_dst_ip, nmstate_linux_bridge_attached_running_vma):
    assert_ping_successful(
        src_vm=nmstate_linux_bridge_attached_running_vma,
        dst_ip=vmb_dst_ip,
    )


@pytest.fixture(scope="class")
def ssh_in_vm_background(
    nmstate_linux_nad,
    nmstate_linux_bridge_attached_running_vma,
    nmstate_linux_bridge_attached_running_vmb,
):
    run_ssh_in_background(
        nad=nmstate_linux_nad,
        src_vm=nmstate_linux_bridge_attached_running_vma,
        dst_vm=nmstate_linux_bridge_attached_running_vmb,
        dst_vm_user=nmstate_linux_bridge_attached_running_vmb.username,
        dst_vm_password=nmstate_linux_bridge_attached_running_vmb.password,
    )


@pytest.fixture(scope="class")
def restarted_nmstate_handler(admin_client, nmstate_ds, nmstate_namespace):
    restart_nmstate_handler(
        admin_client=admin_client,
        nmstate_ds=nmstate_ds,
        nmstate_namespace=nmstate_namespace,
    )


@pytest.fixture()
def nncp_ready(nmstate_linux_bridge_device_worker_1, nmstate_linux_bridge_device_worker_2):
    yield
    for nncp in (
        nmstate_linux_bridge_device_worker_1,
        nmstate_linux_bridge_device_worker_2,
    ):
        assert_nncp_successfully_configured(nncp=nncp)


@pytest.fixture()
def modified_nncp(
    nodes_available_nics,
    worker_node1,
    worker_node2,
    nmstate_linux_bridge_device_worker_1,
    nmstate_linux_bridge_device_worker_2,
):
    nncps = [nmstate_linux_bridge_device_worker_1, nmstate_linux_bridge_device_worker_2]
    for nncp, worker_node in zip(nncps, [worker_node1, worker_node2]):
        interfaces = nncp.desired_state["interfaces"]
        interfaces[0]["bridge"]["port"][0]["name"] = nodes_available_nics[worker_node.name][
            -2
        ]  # NNCP was created with nodes_available_nics[-1]
        ResourceEditor(
            patches={
                nncp: {
                    "spec": {"desiredState": {"interfaces": interfaces}},
                },
            }
        ).update()
        nncp.wait_for_status_success()


class TestConnectivityAfterNmstateChanged:
    @pytest.mark.post_upgrade
    @pytest.mark.ipv4
    @pytest.mark.polarion("CNV-5780")
    def test_nmstate_restart_and_check_connectivity(
        self,
        nncp_ready,
        admin_client,
        nmstate_ds,
        nmstate_linux_bridge_attached_vma,
        nmstate_linux_bridge_attached_vmb,
        nmstate_linux_bridge_attached_running_vma,
        nmstate_linux_bridge_attached_running_vmb,
        nmstate_namespace,
        vmb_dst_ip,
        vmb_pinged,
    ):
        # Running 5 nmstate restarts since we saw some failures after few restarts.
        for idx in range(5):
            restart_nmstate_handler(
                admin_client=admin_client,
                nmstate_namespace=nmstate_namespace,
                nmstate_ds=nmstate_ds,
            )
            LOGGER.info(
                (
                    f"Check connectivity from {nmstate_linux_bridge_attached_running_vma.name} "
                    f"to {nmstate_linux_bridge_attached_running_vmb.name} "
                    f"IP {vmb_dst_ip}. NMstate restart number: {idx + 1}"
                )
            )

            assert_ping_successful(
                src_vm=nmstate_linux_bridge_attached_running_vma,
                dst_ip=vmb_dst_ip,
                count="60",
            )

    @pytest.mark.ipv4
    @pytest.mark.polarion("CNV-7746")
    def test_ssh_alive_after_restart_nmstate_handler(
        self,
        nncp_ready,
        vma_src_ip,
        nmstate_linux_bridge_attached_vma,
        nmstate_linux_bridge_attached_vmb,
        nmstate_linux_bridge_attached_running_vma,
        nmstate_linux_bridge_attached_running_vmb,
        ssh_in_vm_background,
        restarted_nmstate_handler,
    ):
        assert_ssh_alive(ssh_vm=nmstate_linux_bridge_attached_running_vmb, src_ip=vma_src_ip)

    @pytest.mark.gating
    @pytest.mark.ipv4
    @pytest.mark.polarion("CNV-5839")
    def test_connectivity_after_nncp_change(
        self,
        nmstate_linux_bridge_attached_vma,
        nmstate_linux_bridge_attached_vmb,
        nmstate_linux_bridge_attached_running_vma,
        nmstate_linux_bridge_attached_running_vmb,
        vmb_dst_ip,
        vmb_pinged,
        modified_nncp,
    ):
        """
        This test verifies that connectivity wasn't broken due to change of node network configuration.
        """
        # We expect some packets lost due to change of node network configuration.
        try:
            for sample in TimeoutSampler(
                wait_timeout=TIMEOUT_1MIN,
                sleep=TIMEOUT_5SEC,
                func=is_destination_pingable_from_vm,
                src_vm=nmstate_linux_bridge_attached_running_vma,
                dst_ip=vmb_dst_ip,
                count=10,
            ):
                if sample:
                    return
        except TimeoutError:
            LOGGER.error(f"Ping from {nmstate_linux_bridge_attached_running_vma.name} to {vmb_dst_ip} failed.")
            raise

import logging

from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.network.utils import DHCP_SERVER_CONF_FILE, update_cloud_init_extra_user_data
from utilities.infra import ExecCommandOnPod
from utilities.network import cloud_init_network_data

LOGGER = logging.getLogger(__name__)
DHCP_IP_SUBNET = "10.200.1"
DHCP_IP_RANGE_START = f"{DHCP_IP_SUBNET}.3"
DHCP_IP_RANGE_END = f"{DHCP_IP_SUBNET}.100"
TEST_TIMEOUT = 30
SAMPLING_INTERVAL = 1


def dhcp_server_cloud_init_data(dhcp_iface_ip_addr):
    # TODO: Move it to cloud init.
    # https://cloudinit.readthedocs.io/en/latest/topics/examples.html#writing-out-arbitrary-files
    dhcpd_data = DHCP_SERVER_CONF_FILE.format(
        DHCP_IP_SUBNET=DHCP_IP_SUBNET,
        DHCP_IP_RANGE_START=DHCP_IP_RANGE_START,
        DHCP_IP_RANGE_END=DHCP_IP_RANGE_END,
    )
    cloud_init_extra_user_data = {"runcmd": [dhcpd_data]}
    network_data_data = {"ethernets": {"eth1": {"addresses": [f"{dhcp_iface_ip_addr}/24"]}}}
    cloud_init_data = cloud_init_network_data(data=network_data_data)

    cloud_init_data["userData"] = {}  # update_cloud_init_extra_user_data needs to update userData.
    update_cloud_init_extra_user_data(
        cloud_init_data=cloud_init_data["userData"],
        cloud_init_extra_user_data=cloud_init_extra_user_data,
    )
    return cloud_init_data


def set_ipv4_dhcp_client(vlan_iface_nncp, enabled, selected_node=None):
    for iface_idx, interface in enumerate(vlan_iface_nncp.desired_state["interfaces"]):
        if interface["type"] == "vlan":
            vlan_iface = vlan_iface_nncp.desired_state["interfaces"].pop(iface_idx)
            vlan_iface.update({
                "ipv4": {"dhcp": enabled, "enabled": enabled},
                "ipv6": {"enabled": False},
            })
            vlan_iface_nncp.desired_state["interfaces"].insert(iface_idx, vlan_iface)

            resource_dict = {
                "metadata": {"name": vlan_iface_nncp.name},
                "spec": {"desiredState": {"interfaces": vlan_iface_nncp.desired_state["interfaces"]}},
            }
            if selected_node:
                resource_dict["spec"]["nodeSelector"] = {"kubernetes.io/hostname": selected_node}

            vlan_iface_nncp.update(resource_dict=resource_dict)
            vlan_iface_nncp.wait_for_status_success()


def enable_ipv4_dhcp_client(vlan_iface_nncp, selected_node=None):
    set_ipv4_dhcp_client(vlan_iface_nncp=vlan_iface_nncp, enabled=True, selected_node=selected_node)


def disable_ipv4_dhcp_client(vlan_iface_nncp, selected_node=None):
    set_ipv4_dhcp_client(vlan_iface_nncp=vlan_iface_nncp, enabled=False, selected_node=selected_node)


def sampling_handler(
    sampled_func,
    iface_name,
    timeout=TEST_TIMEOUT,
    interval=SAMPLING_INTERVAL,
    err_msg=None,
):
    node = None
    try:
        sampled_ip_search = TimeoutSampler(wait_timeout=timeout, sleep=interval, func=sampled_func)
        for sample in sampled_ip_search:
            if sample[0]:
                return
            node = sample[1]

    except TimeoutExpiredError:
        if err_msg is not None:
            LOGGER.error(err_msg.format(iface_name=iface_name, node=node))
        raise


def assert_vlan_dynamic_ip(iface_name, utility_pods, dhcp_clients_list):
    def _find_vlan_ip():
        node = None
        for node in dhcp_clients_list:
            vlan_ip = ExecCommandOnPod(utility_pods=utility_pods, node=node).get_interface_ip(interface=iface_name)
            if (vlan_ip is None) or (DHCP_IP_SUBNET not in vlan_ip):
                return False, node.name
        return True, node.name

    err_msg = "VLAN interface {iface_name} on node {node} was not assigned a dynamic IP."
    sampling_handler(sampled_func=_find_vlan_ip, err_msg=err_msg, iface_name=iface_name)


def assert_vlan_iface_no_ip(utility_pods, iface_name, no_dhcp_client_list):
    def _find_vlan_ip():
        node = None
        for node in no_dhcp_client_list:
            vlan_ip = ExecCommandOnPod(utility_pods=utility_pods, node=node).get_interface_ip(interface=iface_name)
            if vlan_ip is not None:
                return False, node.name
        return True, node.name

    err_msg = "VLAN interface {iface_name} on node {node} assigned a dynamic IP."
    sampling_handler(sampled_func=_find_vlan_ip, err_msg=err_msg, iface_name=iface_name)


def assert_vlan_interface(utility_pods, iface_name, schedulable_nodes):
    def _vlan_iface():
        node = None
        for node in schedulable_nodes:
            iface_status = ExecCommandOnPod(utility_pods=utility_pods, node=node).interface_status(interface=iface_name)
            if iface_status is None:
                return False, node
        return True, node

    err_msg = "No VLAN interface {iface_name} found on node {node}."
    sampling_handler(sampled_func=_vlan_iface, err_msg=err_msg, iface_name=iface_name)

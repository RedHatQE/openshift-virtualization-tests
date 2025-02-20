import logging

import pytest
from kubernetes.dynamic.exceptions import ResourceNotFoundError
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.network.utils import assert_nncp_successfully_configured
from utilities.constants import NMSTATE_HANDLER, TIMEOUT_5MIN, TIMEOUT_30SEC
from utilities.exceptions import ResourceValueError
from utilities.infra import get_node_selector_dict, get_pod_by_name_prefix, name_prefix
from utilities.network import (
    EthernetNetworkConfigurationPolicy,
    LinuxBridgeNodeNetworkConfigurationPolicy,
)

LOGGER = logging.getLogger(__name__)
IP_LIST = [{"ip": "1.1.1.1", "prefix-length": 24}]
BRIDGE_NAME = "nm-sanity-br"
NNCP_CONFIGURING_STATUS = LinuxBridgeNodeNetworkConfigurationPolicy.Conditions.Reason.CONFIGURATION_PROGRESSING

pytestmark = pytest.mark.sno


@pytest.fixture(scope="class")
def nmstate_linux_bridge_device_worker(nodes_available_nics, worker_node1):
    nmstate_br_dev = LinuxBridgeNodeNetworkConfigurationPolicy(
        name=f"nmstate-{name_prefix(worker_node1.name)}",
        bridge_name=BRIDGE_NAME,
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
        ports=[nodes_available_nics[worker_node1.name][-1]],
    )
    yield nmstate_br_dev

    nmstate_br_dev.clean_up()


@pytest.fixture()
def nmstate_pod_on_worker_1(admin_client, nmstate_namespace, worker_node1):
    for pod in get_pod_by_name_prefix(
        dyn_client=admin_client,
        pod_prefix=NMSTATE_HANDLER,
        namespace=nmstate_namespace.name,
        get_all=True,
    ):
        if pod.node.name == worker_node1.name:
            return pod
    raise ResourceNotFoundError(f"No {NMSTATE_HANDLER} Pod of worker node {worker_node1.name} found.")


@pytest.fixture()
def deleted_nmstate_pod_during_nncp_configuration(
    nmstate_ds, nmstate_linux_bridge_device_worker, nmstate_pod_on_worker_1
):
    # Bridge device created here as we need to catch it once in 'ConfigurationProgressing' status.
    nmstate_linux_bridge_device_worker.create()

    sampler = TimeoutSampler(
        wait_timeout=15,
        sleep=1,
        func=lambda: nmstate_linux_bridge_device_worker.status == NNCP_CONFIGURING_STATUS,
    )
    for sample in sampler:
        if sample:
            # Configuration in progress
            nmstate_pod_on_worker_1.delete(wait=True)
            return


@pytest.fixture()
def nncp_with_worker_hostname(nodes_available_nics, worker_node1):
    with LinuxBridgeNodeNetworkConfigurationPolicy(
        name=worker_node1.hostname,
        bridge_name=BRIDGE_NAME,
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
        ports=[nodes_available_nics[worker_node1.name][-1]],
    ) as nncp:
        yield nncp


@pytest.fixture(scope="class")
def deployed_linux_bridge_device_policy(nmstate_linux_bridge_device_worker):
    nmstate_linux_bridge_device_worker.deploy()
    yield nmstate_linux_bridge_device_worker


@pytest.mark.polarion("CNV-5721")
def test_no_ip(
    worker_node1,
    nodes_available_nics,
):
    with EthernetNetworkConfigurationPolicy(
        name=f"no-ip-{name_prefix(worker_node1.name)}",
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
        ipv4_dhcp=False,
        interfaces_name=[nodes_available_nics[worker_node1.name][-1]],
    ):
        LOGGER.info("NNCP: Test no IP")


@pytest.mark.post_upgrade
@pytest.mark.ipv4
@pytest.mark.polarion("CNV-5720")
def test_static_ip(
    worker_node1,
    nodes_available_nics,
):
    with EthernetNetworkConfigurationPolicy(
        name=f"static-ip-{name_prefix(worker_node1.name)}",
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
        ipv4_dhcp=False,
        ipv4_enable=True,
        ipv4_addresses=IP_LIST,
        interfaces_name=[nodes_available_nics[worker_node1.name][-1]],
    ):
        LOGGER.info("NMstate: Test with IP")


@pytest.mark.ipv4
@pytest.mark.polarion("CNV-5722")
def test_dynamic_ip(
    worker_node1,
    nodes_available_nics,
):
    with EthernetNetworkConfigurationPolicy(
        name=f"dynamic-ip-{name_prefix(worker_node1.name)}",
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
        ipv4_dhcp=True,
        ipv4_enable=True,
        interfaces_name=[nodes_available_nics[worker_node1.name][-1]],
    ):
        LOGGER.info("NMstate: Test with dynamic IP")


@pytest.mark.ipv4
@pytest.mark.polarion("CNV-5725")
def test_static_route(
    worker_node1,
    nodes_available_nics,
):
    iface_name = nodes_available_nics[worker_node1.name][-1]
    routes = {
        "config": [
            {
                "destination": "2.2.2.0/24",
                "metric": 150,
                "next-hop-address": "1.1.1.254",
                "next-hop-interface": iface_name,
            }
        ]
    }
    with EthernetNetworkConfigurationPolicy(
        name=f"static-route-{name_prefix(worker_node1.name)}",
        node_selector=get_node_selector_dict(node_selector=worker_node1.hostname),
        ipv4_dhcp=False,
        ipv4_enable=True,
        ipv4_addresses=IP_LIST,
        interfaces_name=[iface_name],
        routes=routes,
    ):
        LOGGER.info("NMstate: Test static route")


class TestNmstatePodDeletion:
    @pytest.mark.polarion("CNV-6559")
    @pytest.mark.dependency(name="TestNmstatePodDeletion::test_delete_nmstate_pod_during_nncp_configuration")
    def test_delete_nmstate_pod_during_nncp_configuration(
        self,
        nmstate_linux_bridge_device_worker,
        deleted_nmstate_pod_during_nncp_configuration,
    ):
        """
        Delete nmstate-handler pod while NNCP is on status 'ConfigurationProgressing'.
        Test that NNCP is NOT on status 'ConfigurationProgressing' after 30 seconds.
        """
        try:
            for sample in TimeoutSampler(
                wait_timeout=TIMEOUT_30SEC,
                sleep=10,
                func=lambda: nmstate_linux_bridge_device_worker.status != NNCP_CONFIGURING_STATUS,
            ):
                if sample:
                    break

        except TimeoutExpiredError:
            LOGGER.error(
                f"{nmstate_linux_bridge_device_worker.name} is still on status "
                f"{NNCP_CONFIGURING_STATUS} after nmstate pod has been deleted."
            )
            raise

    @pytest.mark.dependency(depends=["TestNmstatePodDeletion::test_delete_nmstate_pod_during_nncp_configuration"])
    @pytest.mark.polarion("CNV-6743")
    def test_nncp_configured_successfully_after_pod_deletion(
        self,
        nmstate_linux_bridge_device_worker,
    ):
        """
        Test that NNCP has been configured Successfully. (The nmstate-handler pod released the lock).
        """
        assert_nncp_successfully_configured(nncp=nmstate_linux_bridge_device_worker)


@pytest.mark.polarion("CNV-8232")
def test_nncp_named_as_worker_hostname(nncp_with_worker_hostname):
    with pytest.raises(TimeoutExpiredError):
        nncp_conditions = nncp_with_worker_hostname.wait_for_configuration_conditions_unknown_or_progressing(
            wait_timeout=TIMEOUT_5MIN
        )
        if nncp_conditions:
            raise ResourceValueError(
                f"nncp {nncp_with_worker_hostname.name} {nncp_with_worker_hostname.Conditions.Type.AVAILABLE} condition"
                f" was changed, conditions: {nncp_conditions}."
            )


class TestStandaloneNmstate:
    @pytest.mark.polarion("CNV-8519")
    def test_basic_nmstate(self, deployed_linux_bridge_device_policy):
        assert_nncp_successfully_configured(nncp=deployed_linux_bridge_device_policy)

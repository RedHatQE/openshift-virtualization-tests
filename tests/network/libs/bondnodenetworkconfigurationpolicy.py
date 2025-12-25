import os

from kubernetes.dynamic import DynamicClient
from ocp_resources.node_network_configuration_policy import NodeNetworkConfigurationPolicy
from timeout_sampler import retry

import utilities.infra
from utilities.constants import ACTIVE_BACKUP, TIMEOUT_8MIN, WORKERS_TYPE
from utilities.network import BOND


class BondNodeNetworkConfigurationPolicy(NodeNetworkConfigurationPolicy):
    def __init__(
        self,
        name: str,
        bond_name: str,
        bond_ports: list[str],
        client: DynamicClient,
        mode: str = ACTIVE_BACKUP,
        mtu: int | None = None,
        primary_bond_port: str | None = None,
        node_selector: dict | None = None,
        teardown: bool = True,
        ipv4_enable: bool = False,
        ipv4_dhcp: bool = False,
        ipv6_enable: bool = False,
        options: dict | None = None,
        dry_run: str | None = None,
        success_timeout: int = TIMEOUT_8MIN,
        teardown_absent_ifaces: bool = True,
    ) -> None:
        super().__init__(
            name=name,
            node_selector=node_selector,
            teardown=teardown,
            mtu=mtu,
            ipv4_enable=ipv4_enable,
            ipv4_dhcp=ipv4_dhcp,
            ipv6_enable=ipv6_enable,
            dry_run=dry_run,
            success_timeout=success_timeout,
            teardown_absent_ifaces=teardown_absent_ifaces,
            client=client,
        )
        self.bond_name = bond_name
        self.bond_ports = bond_ports
        self.mode = mode
        self.primary_bond_port = primary_bond_port
        self.ports = self.bond_ports
        self.options = options
        # PSI MTU cannot be greater than 1450
        if os.environ.get(WORKERS_TYPE) == utilities.infra.ClusterHosts.Type.VIRTUAL and not self.mtu:
            self.mtu: int = 1450

    def create_interface(self) -> None:
        options_dic = self.options or {}
        options_dic.update({"miimon": "120"})
        if self.mode == ACTIVE_BACKUP and self.primary_bond_port is not None:
            options_dic.update({"primary": self.primary_bond_port})

        self.iface = {
            "name": self.bond_name,
            "type": BOND,
            "state": NodeNetworkConfigurationPolicy.Interface.State.UP,
            "link-aggregation": {
                "mode": self.mode,
                "port": self.bond_ports,
                "options": options_dic,
            },
        }

    def configure_mtu_on_ports(self) -> None:
        if self.mtu:
            self.iface["mtu"] = self.mtu
        for port in self.ports:
            _port = {
                "name": port,
                "type": "ethernet",
                "state": NodeNetworkConfigurationPolicy.Interface.State.UP,
            }
            if self.mtu:
                _port["mtu"] = self.mtu
            self.set_interface(interface=_port)

    def to_dict(self) -> None:
        super().to_dict()
        if not self.iface:
            self.create_interface()
            self.add_interface(
                iface=self.iface,
                ipv4_enable=self.ipv4_enable,
                ipv4_dhcp=self.ipv4_dhcp,
                ipv6_enable=self.ipv6_enable,
            )

            if self.mtu:
                self.configure_mtu_on_ports()

    @retry(wait_timeout=300, sleep=5)
    def _wait_for_nncp_status_update(self, initial_transition_time: str) -> bool:
        for condition in self.instance.get("status", {}).get("conditions", []):
            if (
                condition.get("type") == self.Conditions.Type.AVAILABLE
                and condition.get("reason") == self.Conditions.Reason.SUCCESSFULLY_CONFIGURED
            ):
                current_ifaces = self.instance.get("status", {}).get("currentState", {}).get("interfaces", [])
                bond_iface = next(
                    (current_iface for current_iface in current_ifaces if current_iface["name"] == self.bond_name), None
                )
                if not bond_iface or bond_iface.get("state") == self.Interface.State.ABSENT:
                    return True
        return False

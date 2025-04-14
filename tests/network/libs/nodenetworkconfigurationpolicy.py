from copy import deepcopy
from dataclasses import asdict, dataclass
from typing import Any

from ocp_resources.exceptions import NNCPConfigurationFailed
from ocp_resources.node_network_configuration_policy_latest import NodeNetworkConfigurationPolicy as Nncp
from ocp_resources.resource import ResourceEditor
from timeout_sampler import retry

WAIT_FOR_STATUS_TIMEOUT_SEC = 90
WAIT_FOR_STATUS_INTERVAL_SEC = 5


@dataclass
class IP:
    enabled: bool
    dhcp: bool | None = None
    auto_dns: bool | None = None


@dataclass
class IPv4(IP):
    pass


@dataclass
class IPv6(IP):
    autoconf: bool | None = None


@dataclass
class STP:
    enabled: bool


@dataclass
class BridgeOptions:
    stp: STP


@dataclass
class Port:
    name: str


@dataclass
class Bridge:
    options: BridgeOptions | None = None
    port: list[Port] | None = None
    allow_extra_patch_ports: bool | None = None


@dataclass
class Interface:
    name: str
    type: str
    state: str
    ipv4: IPv4 | None = None
    ipv6: IPv6 | None = None
    bridge: Bridge | None = None


@dataclass
class DesiredState:
    """
    Represents the desired network configuration for NMstate.
    Following the NMstate YAML-based API specification:
    https://nmstate.io/devel/yaml_api.html
    """

    interfaces: list[Interface]


class NodeNetworkConfigurationPolicy(Nncp):
    """
    NodeNetworkConfigurationPolicy object.
    """

    def __init__(
        self,
        name: str,
        desired_state: DesiredState,
        node_selector: dict[str, str] | None = None,
    ):
        """
        Create and manage NodeNetworkConfigurationPolicy

        Args:
            name (str): Name of the NodeNetworkConfigurationPolicy object.
            desired_state (DesiredState): Desired policy configuration - interface creation, modification or removal.
            node_selector (dict, optional): A node selector that specifies the nodes to apply the node network
                configuration policy to.
        """
        self._desired_state = desired_state
        super().__init__(
            name=name,
            desired_state=asdict(desired_state, dict_factory=self._dict_normalization),
            node_selector=node_selector,
        )

    @staticmethod
    def _dict_normalization(data: list[tuple[str, Any]]) -> dict[str, Any]:
        """Filter out none values and converts key characters containing underscores into dashes."""
        return {key.replace("_", "-"): val for (key, val) in data if val is not None}

    @property
    def desired_state_spec(self) -> DesiredState:
        return self._desired_state

    def clean_up(self) -> bool:
        self._delete_interfaces()
        self.wait_for_status_success()
        return super().clean_up()

    @retry(
        wait_timeout=WAIT_FOR_STATUS_TIMEOUT_SEC,
        sleep=WAIT_FOR_STATUS_INTERVAL_SEC,
        exceptions_dict={AssertionError: []},  # Using a no-op exception so any other error will be raised
    )
    def wait_for_status_success(self) -> dict[str, Any]:
        conditions = (
            condition
            for condition in self.instance.status.conditions
            if condition["status"] == Nncp.Condition.Status.TRUE
        )

        for condition in conditions:
            if condition["type"] == Nncp.Condition.AVAILABLE:
                self.logger.info(f"{self.kind}/{self.name} configured successfully")
                return condition
            if condition["type"] == Nncp.Condition.DEGRADED:
                raise NNCPConfigurationFailed(f"{self.name} failed on condition:\n{condition}")
        return {}

    def _delete_interfaces(self) -> None:
        desired_state = deepcopy(self.desired_state)
        for iface in desired_state["interfaces"]:
            iface["state"] = Nncp.Interface.State.ABSENT
        if desired_state["interfaces"]:
            ResourceEditor(patches={self: {"spec": {"desiredState": desired_state}}}).update()

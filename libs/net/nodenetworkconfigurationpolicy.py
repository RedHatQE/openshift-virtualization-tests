from copy import deepcopy
from dataclasses import asdict, dataclass, field
from typing import Any

from ocp_resources.exceptions import NNCPConfigurationFailed
from ocp_resources.node_network_configuration_policy_latest import NodeNetworkConfigurationPolicy as Nncp
from ocp_resources.resource import Resource, ResourceEditor
from timeout_sampler import retry

WAIT_FOR_STATUS_TIMEOUT_IN_SEC = 90
WAIT_FOR_STATUS_INTERVAL_IN_SEC = 5


@dataclass
class IP:
    dhcp: bool
    auto_dns: bool = True
    enabled: bool = False


@dataclass
class IPv4(IP):
    pass


@dataclass
class IPv6(IP):
    autoconf: bool = False


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
    ipv4: IPv4
    ipv6: IPv6
    bridge: Bridge | None = None


@dataclass
class DesiredState:
    """
    Represents the desired network state for Nmstate.
    This class follows the Nmstate YAML API specification:
    https://nmstate.io/devel/yaml_api.html
    """

    interfaces: list[Interface] = field(default_factory=list)


class NNCPSuccessStatusNotMet(Exception):
    pass


class NodeNetworkConfigurationPolicy(Nncp):
    """
    NodeNetworkConfigurationPolicy object.
    """

    class Conditions:
        class Reason:
            SUCCESSFULLY_CONFIGURED = "SuccessfullyConfigured"
            FAILED_TO_CONFIGURE = "FailedToConfigure"
            NO_MATCHING_NODE = "NoMatchingNode"

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
        super().__init__(name=name, desired_state=desired_state, node_selector=node_selector)

    @staticmethod
    def _dict_normalization(data: list[tuple[str, Any]]) -> dict[str, Any]:
        """Filter out none values and converts key characters containing underscores into dashes."""
        return {key.replace("_", "-"): val for (key, val) in data if val is not None}

    @property
    def interfaces(self) -> list[dict]:
        return [asdict(interface) for interface in self.desired_state.interfaces]

    def to_dict(self) -> None:
        super().to_dict()
        if not self.kind_dict and not self.yaml_file:
            self.res.setdefault("spec", {}).update({
                "desiredState": asdict(self.desired_state, dict_factory=self._dict_normalization),
                "nodeSelector": self.node_selector if self.node_selector else {},
            })

    def clean_up(self) -> bool:
        self._delete_interfaces()
        self.wait_for_status_success()
        return super().clean_up()

    @retry(
        wait_timeout=WAIT_FOR_STATUS_TIMEOUT_IN_SEC,
        sleep=WAIT_FOR_STATUS_INTERVAL_IN_SEC,
        exceptions_dict={NNCPSuccessStatusNotMet: []},
    )
    def wait_for_status_success(self) -> bool:
        conditions = (
            condition
            for condition in self.instance.status.conditions
            if condition["status"] == self.Condition.Status.TRUE
        )

        for condition in conditions:
            if condition["type"] == Resource.Condition.AVAILABLE:
                self.logger.info(f"{self.kind} {self.name} configured successfully")
                return True
            if condition["type"] == Nncp.Condition.DEGRADED:
                raise NNCPConfigurationFailed(f"{self.kind} {self.name} failed to configure on condition:\n{condition}")

    def _delete_interfaces(self) -> None:
        desired_state_copy = deepcopy(self.desired_state)
        for iface in desired_state_copy.interfaces:
            iface.state = self.Interface.State.ABSENT
        desired_state = {"interfaces": [asdict(iface) for iface in desired_state_copy.interfaces]}
        if desired_state["interfaces"]:
            ResourceEditor(patches={self: {"spec": {"desiredState": desired_state}}}).update()

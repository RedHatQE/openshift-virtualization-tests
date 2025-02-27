# API: https://nmstate.io/devel/yaml_api.html#dhcp
from dataclasses import asdict, dataclass
from typing import Any

from ocp_resources.exceptions import NNCPConfigurationFailed
from ocp_resources.node_network_configuration_policy_latest import NodeNetworkConfigurationPolicy
from ocp_resources.resource import Resource, ResourceEditor
from timeout_sampler import retry

WAIT_FOR_STATUS_TIMEOUT = 90
WAIT_FOR_STATUS_SLEEP = 5


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
class Interface:
    name: str
    type: str
    state: str
    ipv4: IPv4
    ipv6: IPv6
    bridge: Bridge | None = None


@dataclass
class DesiredState:
    interfaces: list[Interface]


class NNCPSuccessStatusNotMet(Exception):
    pass


class NetLibsNodeNetworkConfigurationPolicy(NodeNetworkConfigurationPolicy):
    """
    NodeNetworkConfigurationPolicy object.
    """

    api_group = Resource.ApiGroup.NMSTATE_IO

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
        super().__init__(
            name=name,
        )
        self._desired_state = desired_state
        self._node_selector = node_selector

    @retry(
        wait_timeout=WAIT_FOR_STATUS_TIMEOUT, sleep=WAIT_FOR_STATUS_SLEEP, exceptions_dict={NNCPSuccessStatusNotMet: []}
    )
    def wait_for_status_success(self) -> list[dict]:
        conditions = [
            condition
            for condition in self.instance.status.conditions
            if condition["status"] == self.Condition.Status.TRUE
        ]

        for condition in conditions:
            if condition["reason"] == self.Conditions.Reason.SUCCESSFULLY_CONFIGURED:
                self.logger.info(f"{self.kind} {self.name} configured successfully")
                return condition

            if (
                condition["reason"] == self.Conditions.Reason.NO_MATCHING_NODE
                or condition["reason"] == self.Conditions.Reason.FAILED_TO_CONFIGURE
            ):
                raise NNCPConfigurationFailed(
                    f"{self.kind} {self.name} failed to configure on condition: {condition}\n"
                )

        raise NNCPSuccessStatusNotMet(f"{self.name}. None of the conditions were met.")

    @staticmethod
    def dict_normalization(data: list[tuple[str, Any]]) -> dict[str, Any]:
        """Filter out none values and converts key characters containing underscores into dashes."""
        return {key.replace("_", "-"): val for (key, val) in data if val is not None}

    def to_dict(self) -> None:
        super().to_dict()
        if not self.kind_dict and not self.yaml_file:
            self.res.setdefault("spec", {}).update({
                "desiredState": asdict(self._desired_state, dict_factory=self.dict_normalization),
                "nodeSelector": self._node_selector if self._node_selector else {},
            })

    def _delete_interfaces(self) -> None:
        desired_state = {}
        for iface in self._desired_state.interfaces:
            iface.state = self.Interface.State.ABSENT
        desired_state["interfaces"] = [asdict(iface) for iface in self._desired_state.interfaces]
        if desired_state["interfaces"]:
            ResourceEditor(patches={self: {"spec": {"desiredState": desired_state}}}).update()

    def clean_up(self) -> bool:
        try:
            self._delete_interfaces()
            self.wait_for_status_success()
        except Exception as exp:
            self.logger.error(exp)

        return super().clean_up()

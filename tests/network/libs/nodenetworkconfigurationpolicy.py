import contextlib
from collections.abc import Iterator
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from ocp_resources.exceptions import NNCPConfigurationFailed
from ocp_resources.node_network_configuration_policy_latest import NodeNetworkConfigurationPolicy as Nncp
from ocp_resources.resource import Resource, ResourceEditor
from timeout_sampler import retry

from tests.network.libs.apimachinery import dict_normalization_for_dataclass

WAIT_FOR_STATUS_TIMEOUT_SEC = 90
WAIT_FOR_STATUS_INTERVAL_SEC = 5
DEFAULT_OVN_EXTERNAL_BRIDGE = "br-ex"  # Default name for OVN-Kubernetes external bridge


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
class BridgeMappings:
    class State(Enum):
        PRESENT = "present"

    localnet: str
    bridge: str
    state: str


@dataclass
class OVN:
    bridge_mappings: list[BridgeMappings]


@dataclass
class DesiredState:
    """
    Represents the desired network configuration for NMstate.
    Following the NMstate YAML-based API specification:
    https://nmstate.io/devel/yaml_api.html
    """

    interfaces: list[Interface] | None = None
    ovn: OVN | None = None


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
            desired_state=asdict(desired_state, dict_factory=dict_normalization_for_dataclass),
            node_selector=node_selector,
            wait_for_resource=True,
        )

    @property
    def desired_state_spec(self) -> DesiredState:
        return self._desired_state

    def clean_up(self, wait: bool = True, timeout: int | None = None) -> bool:
        desired_state: dict[str, Any] = {}
        if to_delete_interfaces := self._interfaces_for_deletion():
            desired_state["interfaces"] = to_delete_interfaces
        if to_delete_ovn := self._ovn_for_deletion():
            desired_state["ovn"] = to_delete_ovn
        if desired_state:
            with self._confirm_status_success_on_update():
                ResourceEditor(patches={self: {"spec": {"desiredState": desired_state}}}).update()
        return super().clean_up(wait=wait, timeout=timeout)

    @retry(
        wait_timeout=WAIT_FOR_STATUS_TIMEOUT_SEC,
        sleep=WAIT_FOR_STATUS_INTERVAL_SEC,
        exceptions_dict={},  # Using a no-op exception so any other error will be raised
    )
    def wait_for_status_success(self, last_success_timestamp: str = "") -> dict[str, Any]:
        date_format = "%Y-%m-%dT%H:%M:%SZ"
        initial_transition_datetime = (
            datetime.strptime(last_success_timestamp, date_format) if last_success_timestamp else None
        )

        conditions = (
            condition
            for condition in self.instance.get("status", {}).get("conditions", {})
            if condition["status"] == Resource.Condition.Status.TRUE
        )

        for condition in conditions:
            if condition["type"] == Resource.Condition.AVAILABLE:
                if (
                    not initial_transition_datetime
                    or datetime.strptime(condition["lastTransitionTime"], date_format) > initial_transition_datetime
                ):
                    self.logger.info(f"{self.kind}/{self.name} configured successfully")
                    return condition
            if condition["type"] == Resource.Condition.DEGRADED:
                raise NNCPConfigurationFailed(f"{self.name} failed on condition:\n{condition}")
        return {}

    def _interfaces_for_deletion(self) -> list[Interface]:
        if isinstance(self.desired_state, dict):
            to_delete_interfaces = deepcopy(self.desired_state.get("interfaces", []))
            for iface in to_delete_interfaces:
                iface["state"] = Nncp.Interface.State.ABSENT
            return to_delete_interfaces

        return []

    def _ovn_for_deletion(self) -> OVN:
        if self.desired_state is not None:
            to_delete_ovn = deepcopy(self.desired_state.get("ovn", {}))
            for bridge_mapping in to_delete_ovn.get("bridge-mappings", []):
                bridge_mapping["state"] = Nncp.Interface.State.ABSENT
            return to_delete_ovn

        return OVN(bridge_mappings=[])

    @contextlib.contextmanager
    def _confirm_status_success_on_update(self) -> Iterator[None]:
        # The current time-stamp of the NNCP's available status will change after the NNCP is updated, therefore
        # it must be fetched and stored before the update, and compared with the new time-stamp after.
        initial_success_status_time = self._get_last_successful_transition_time()

        yield

        # In case the update has been executed before the NNCP reached a success status,
        # initial_success_status_time is empty and the wait is treated without considering the timestamp.
        self.wait_for_status_success(last_success_timestamp=initial_success_status_time)

    def _get_last_successful_transition_time(self) -> str:
        for condition in self.instance.status.conditions:
            if (
                condition["type"] == Resource.Condition.AVAILABLE
                and condition["status"] == Resource.Condition.Status.TRUE
            ):
                return condition["lastTransitionTime"]
        return ""

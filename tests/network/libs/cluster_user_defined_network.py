from dataclasses import asdict, dataclass
from enum import Enum

from ocp_resources.cluster_user_defined_network import ClusterUserDefinedNetwork as Cudn

from tests.network.libs.apimachinery import dict_normalization_for_dataclass
from tests.network.libs.label_selector import LabelSelector


@dataclass
class Access:
    id: int


@dataclass
class Vlan:
    class Mode(Enum):
        ACCESS = "Access"

    access: Access
    mode: str


@dataclass
class Ipam:
    class Mode(Enum):
        ENABLED = "Enabled"
        DISABLED = "Disabled"

    mode: str
    lifecycle: str | None = None


@dataclass
class Layer2:
    class Role(Enum):
        PRIMARY = "Primary"
        SECONDARY = "Secondary"

    role: str
    ipam: Ipam
    subnets: list[str]


@dataclass
class Localnet:
    class Role(Enum):
        SECONDARY = "Secondary"

    role: str
    physicalNetworkName: str  # noqa: N815
    ipam: Ipam
    vlan: Vlan | None = None


@dataclass
class Network:
    class Topology(Enum):
        LAYER2 = "Layer2"
        LOCALNET = "Localnet"

    topology: str
    layer2: Layer2 | None = None
    localnet: Localnet | None = None


class ClusterUserDefinedNetwork(Cudn):
    """
    ClusterUserDefinedNetwork object.
    """

    def __init__(
        self, name: str, namespace_selector: LabelSelector, network: Network, label: dict[str, str] | None = None
    ):
        """
        Create and manage ClusterUserDefinedNetwork

        API reference:
        https://ovn-kubernetes.io/api-reference/userdefinednetwork-api-spec/#clusteruserdefinednetwork

        Args:
            name (str): Name of the ClusterUserDefinedNetwork object.
            namespace_selector (NamespaceSelector): NamespaceSelector Label selector for which namespace network should
                be available for.
            network (Network): Network is the user-defined-network spec.
            label (dict[str, str]): Optional labels to apply to the ClusterUserDefinedNetwork.
        """
        super().__init__(
            name=name,
            namespace_selector=asdict(namespace_selector, dict_factory=dict_normalization_for_dataclass),
            network=asdict(network, dict_factory=dict_normalization_for_dataclass),
            label=label,
        )

    class Status:
        class Condition:
            class Type(str, Enum):
                NETWORK_CREATED = "NetworkCreated"

    def wait_for_status_success(self) -> None:
        self.wait_for_condition(
            condition=ClusterUserDefinedNetwork.Status.Condition.Type.NETWORK_CREATED.value,
            status=ClusterUserDefinedNetwork.Condition.Status.TRUE,
        )
        self.logger.info(f"{self.kind}/{self.name} configured successfully")

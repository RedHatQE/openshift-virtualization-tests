from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Final

from kubernetes.dynamic import DynamicClient
from ocp_resources.resource import NamespacedResource

_DEFAULT_CNI_VERSION: Final[str] = "0.3.1"


@dataclass
class CNIPluginConfig:
    type: str = field(init=False)


@dataclass
class CNIPluginBridgeConfig(CNIPluginConfig):
    """
    CNI Bridge Plugin
    Ref: https://www.cni.dev/plugins/current/main/bridge/#network-configuration-reference
    """

    bridge: str
    type: str = field(default="bridge", init=False)
    mtu: int | None = None
    vlan: int | None = None
    macspoofchk: bool | None = None
    disableContainerInterface: bool | None = None  # noqa: N815


@dataclass
class NetConfig:
    """
    CNI specification configuration
    Ref: https://www.cni.dev/docs/spec/#configuration-format
    """

    name: str
    plugins: list[CNIPluginConfig]
    cniVersion: str = _DEFAULT_CNI_VERSION  # noqa: N815


class NetworkAttachmentDefinition(NamespacedResource):
    """
    NetworkAttachmentDefinition object.
    """

    api_group = NamespacedResource.ApiGroup.K8S_CNI_CNCF_IO

    def __init__(
        self,
        name: str,
        namespace: str,
        config: NetConfig,
        resource_name: str | None = None,
        client: DynamicClient | None = None,
    ):
        """
        Create and manage NetworkAttachmentDefinition

        Args:
            name (str): Name of the NetworkAttachmentDefinition.
            namespace (str): Namespace of the NetworkAttachmentDefinition.
            config (NetConfig): Configuration body, as defined by the CNI spec.
            resource_name (str): Optional resource name marking
                (set on the object annotations).
            client: (DynamicClient): Optional DynamicClient to use.
        """
        super().__init__(
            name=name,
            namespace=namespace,
            annotations=resource_name_annotation(resource_name),
            client=client,
        )
        self._config = config

    def to_dict(self) -> None:
        super().to_dict()
        if not self.kind_dict and not self.yaml_file:
            self.res.setdefault("spec", {}).update({
                "config": json.dumps(asdict(self._config, dict_factory=filter_out_none_values))
            })


def filter_out_none_values(data: list[tuple[str, Any]]) -> dict[str, Any]:
    return {key: val for (key, val) in data if val is not None}


def resource_name_annotation(resource_name: str | None) -> dict[str, str] | None:
    if resource_name is not None:
        return {f"{NamespacedResource.ApiGroup.K8S_V1_CNI_CNCF_IO}/resourceName": resource_name}
    return None

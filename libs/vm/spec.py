from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ocp_resources.virtual_machine import VirtualMachine


@dataclass
class VMSpec:
    template: Template
    runStrategy: str = VirtualMachine.RunStrategy.HALTED


@dataclass
class Template:
    spec: VMISpec
    metadata: Metadata | None = None


@dataclass
class Metadata:
    labels: dict[str, str] | None = None
    annotations: dict[str, str] | None = None


@dataclass
class VMISpec:
    domain: Domain
    networks: list[Network] | None = None
    volumes: list[Volume] | None = None
    terminationGracePeriodSeconds: int | None = None
    affinity: Affinity | None = None


@dataclass
class Domain:
    cpu: CPU | None = None
    memory: Memory | None = None
    devices: Devices | None = None


@dataclass
class CPU:
    cores: int


@dataclass
class Memory:
    guest: str


@dataclass
class Devices:
    disks: list[SpecDisk] | None = None
    interfaces: list[Interface] | None = None
    rng: dict[Any, Any] | None = None


@dataclass
class SpecDisk:
    name: str
    disk: Disk


@dataclass
class Disk:
    bus: str


@dataclass
class Interface:
    name: str
    masquerade: dict[Any, Any] | None = None
    bridge: dict[Any, Any] | None = None
    sriov: dict[Any, Any] | None = None
    binding: NetBinding | None = None
    state: str | None = None


@dataclass
class NetBinding:
    name: str


@dataclass
class Network:
    name: str
    pod: dict[Any, Any] | None = None
    multus: Multus | None = None


@dataclass
class Multus:
    networkName: str


@dataclass
class Affinity:
    podAntiAffinity: PodAntiAffinity


@dataclass
class PodAntiAffinity:
    requiredDuringSchedulingIgnoredDuringExecution: list[PodAffinityTerm]


@dataclass
class PodAffinityTerm:
    labelSelector: LabelSelector
    topologyKey: str
    namespaceSelector: dict[str, Any] | None = None
    namespaces: list[str] | None = None


@dataclass
class LabelSelector:
    matchExpressions: list[LabelSelectorRequirement]


@dataclass
class LabelSelectorRequirement:
    operator: str
    key: str
    values: list[str]


@dataclass
class Volume:
    name: str
    containerDisk: ContainerDisk | None = None
    cloudInitNoCloud: CloudInitNoCloud | None = None


@dataclass
class ContainerDisk:
    image: str


@dataclass
class CloudInitNoCloud:
    networkData: str
    userData: str | None = None

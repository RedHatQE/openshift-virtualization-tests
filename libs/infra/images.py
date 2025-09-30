from dataclasses import dataclass

from ocp_resources.resource import Resource

BASE_IMAGES_DIR = "cnv-tests"


@dataclass
class Cirros:
    RAW_IMG: str | None = None
    RAW_IMG_GZ: str | None = None
    RAW_IMG_XZ: str | None = None
    QCOW2_IMG: str | None = None
    QCOW2_IMG_GZ: str | None = None
    QCOW2_IMG_XZ: str | None = None
    DISK_DEMO: str | None = None
    DIR: str = f"{BASE_IMAGES_DIR}/cirros-images"
    DEFAULT_DV_SIZE: str = "1Gi"
    DEFAULT_MEMORY_SIZE: str = "64M"
    OS_FLAVOR: str = "cirros"


@dataclass
class Alpine:
    QCOW2_IMG: str | None = None
    DIR: str = f"{BASE_IMAGES_DIR}/alpine-images"
    DEFAULT_DV_SIZE: str = "1Gi"
    DEFAULT_MEMORY_SIZE: str = "128M"


@dataclass
class Rhel:
    RHEL7_9_IMG: str | None = None
    RHEL8_0_IMG: str | None = None
    RHEL8_9_IMG: str | None = None
    RHEL8_10_IMG: str | None = None
    RHEL9_3_IMG: str | None = None
    RHEL9_4_IMG: str | None = None
    RHEL9_5_IMG: str | None = None
    RHEL9_6_IMG: str | None = None
    RHEL8_REGISTRY_GUEST_IMG: str = f"{Resource.ApiGroup.IMAGE_REGISTRY}/rhel8/rhel-guest-image"
    RHEL9_REGISTRY_GUEST_IMG: str = f"{Resource.ApiGroup.IMAGE_REGISTRY}/rhel9/rhel-guest-image"
    RHEL10_REGISTRY_GUEST_IMG: str = f"{Resource.ApiGroup.IMAGE_REGISTRY}/rhel10/rhel-guest-image"
    DIR: str = f"{BASE_IMAGES_DIR}/rhel-images"
    DEFAULT_DV_SIZE: str = "20Gi"
    DEFAULT_MEMORY_SIZE: str = "1.5Gi"
    LATEST_RELEASE_STR: str | None = None


@dataclass
class Windows:
    WIN10_IMG: str | None = None
    WIN10_WSL2_IMG: str | None = None
    WIN10_ISO_IMG: str | None = None
    WIN2k16_IMG: str | None = None
    WIN2k19_IMG: str | None = None
    WIN2k25_IMG: str | None = None
    WIN2k19_HA_IMG: str | None = None
    WIN11_IMG: str | None = None
    WIN11_WSL2_IMG: str | None = None
    WIN11_ISO_IMG: str | None = None
    WIN19_RAW: str | None = None
    WIN2022_IMG: str | None = None
    WIN2022_ISO_IMG: str | None = None
    WIN2025_ISO_IMG: str | None = None
    DIR: str = f"{BASE_IMAGES_DIR}/windows-images"
    UEFI_WIN_DIR: str = f"{DIR}/uefi"
    HA_DIR: str = f"{DIR}/HA-images"
    ISO_BASE_DIR = f"{DIR}/install_iso"
    ISO_WIN10_DIR: str = f"{ISO_BASE_DIR}/win10"
    ISO_WIN11_DIR: str = f"{ISO_BASE_DIR}/win11"
    ISO_WIN2022_DIR: str = f"{ISO_BASE_DIR}/win2022"
    ISO_WIN2025_DIR: str = f"{ISO_BASE_DIR}/win2025"
    DEFAULT_DV_SIZE: str = "70Gi"
    DEFAULT_MEMORY_SIZE: str = "8Gi"
    DEFAULT_MEMORY_SIZE_WSL: str = "12Gi"
    DEFAULT_CPU_CORES: int = 4
    DEFAULT_CPU_THREADS: int = 2
    LATEST_RELEASE_STR: str | None = None


@dataclass
class Fedora:
    FEDORA41_IMG: str | None = None
    FEDORA42_IMG: str | None = None
    FEDORA_CONTAINER_IMAGE: str | None = None
    DISK_DEMO: str | None = None
    DIR: str = f"{BASE_IMAGES_DIR}/fedora-images"
    DEFAULT_DV_SIZE: str = "10Gi"
    DEFAULT_MEMORY_SIZE: str = "1Gi"
    LATEST_RELEASE_STR: str | None = None


@dataclass
class Centos:
    CENTOS_STREAM_9_IMG: str | None = None
    DIR: str = f"{BASE_IMAGES_DIR}/centos-images"
    DEFAULT_DV_SIZE: str = "15Gi"
    LATEST_RELEASE_STR: str | None = None


@dataclass
class Cdi:
    QCOW2_IMG: str | None = None
    DIR: str = f"{BASE_IMAGES_DIR}/cdi-test-images"
    DEFAULT_DV_SIZE: str = "1Gi"

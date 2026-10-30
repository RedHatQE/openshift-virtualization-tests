"""OS image constants and architecture-specific image selection.

Covers OS flavor strings (OS_FLAVOR_*), image disk demo names, Alpine version,
the default Fedora registry URL, and the ArchImages class that maps each CPU
architecture to its image set. The Images alias (resolved at package import time)
points to the current cluster's architecture variant.
"""

from libs.infra.images import (
    BASE_IMAGES_DIR,
    Alpine,
    Cdi,
    Centos,
    Cirros,
    Fedora,
    Rhel,
    Windows,
)

#  OS constants
OS_FLAVOR_CIRROS = "cirros"
OS_FLAVOR_ALPINE = "alpine"
OS_FLAVOR_WINDOWS = "win"
OS_FLAVOR_RHEL = "rhel"
OS_FLAVOR_FEDORA = "fedora"
OS_FLAVOR_WIN_CONTAINER_DISK = "win-container-disk"

FEDORA_DISK_DEMO = "fedora-cloud-registry-disk-demo"
CIRROS_DISK_DEMO = "cirros-registry-disk-demo"
CIRROS_QCOW2_IMG = "cirros-qcow2.img"

ALPINE_VERSION = "3.20.1"

DEFAULT_FEDORA_REGISTRY_URL = "docker://quay.io/containerdisks/fedora:latest"


class ArchImages:
    class AMD64:
        BASE_CIRROS_NAME = "cirros-0.4.0-x86_64-disk"
        BASE_ALPINE_NAME = "alpine-x86_64-disk"
        BASE_VERSIONED_ALPINE_NAME = f"alpine-{ALPINE_VERSION}-x86_64-disk"
        Cirros = Cirros(
            RAW_IMG=f"{BASE_CIRROS_NAME}.raw",
            RAW_IMG_GZ=f"{BASE_CIRROS_NAME}.raw.gz",
            RAW_IMG_XZ=f"{BASE_CIRROS_NAME}.raw.xz",
            QCOW2_IMG=f"{BASE_CIRROS_NAME}.qcow2",
            QCOW2_IMG_GZ=f"{BASE_CIRROS_NAME}.qcow2.gz",
            QCOW2_IMG_XZ=f"{BASE_CIRROS_NAME}.qcow2.xz",
            DISK_DEMO=CIRROS_DISK_DEMO,
        )

        Alpine = Alpine(
            QCOW2_IMG=f"{BASE_ALPINE_NAME}.qcow2",
            QCOW2_IMG_VERSIONED=f"{BASE_VERSIONED_ALPINE_NAME}.qcow2",
            RAW_IMG_XZ=f"{BASE_VERSIONED_ALPINE_NAME}.raw.xz",
        )

        Rhel = Rhel(
            RHEL8_0_IMG="rhel-8.qcow2",
            RHEL8_9_IMG="rhel-89.qcow2",
            RHEL8_10_IMG="rhel-810.qcow2",
            RHEL9_3_IMG="rhel-93.qcow2",
            RHEL9_4_IMG="rhel-94.qcow2",
            RHEL9_6_IMG="rhel-96.qcow2",
        )
        Rhel.LATEST_RELEASE_STR = Rhel.RHEL9_6_IMG

        Windows = Windows(
            WIN10_ISO_IMG="Win10_22H2_English_x64.iso",
            WIN2k19_IMG="win_2k19_uefi.qcow2",
            WIN2k25_IMG="win_2k25_uefi.qcow2",
            WIN2k19_HA_IMG="win_2019_virtio.qcow2",
            WIN11_IMG="win_11.qcow2",
            WIN11_WSL2_IMG="win_11_wsl2.qcow2",
            WIN11_ISO_IMG="en-us_windows_11_business_editions_version_24h2_x64_dvd_59a1851e.iso",
            WIN19_RAW="win_2k19_uefi.raw",
            WIN2022_IMG="win_2022.qcow2",
            WIN2022_ISO_IMG="Windows_Server_2022_x64FRE_en-us.iso",
            WIN2025_ISO_IMG="windows_server_2025_x64_dvd_eval.iso",
        )
        Windows.LATEST_RELEASE_STR = Windows.WIN2022_IMG

        Fedora = Fedora(
            FEDORA42_IMG="Fedora-Cloud-Base-Generic-42-1.1.x86_64.qcow2",
            FEDORA43_IMG="Fedora-Cloud-Base-Generic-43-1.6.x86_64.qcow2",
            FEDORA_CONTAINER_IMAGE="quay.io/openshift-cnv/qe-cnv-tests-fedora:41",
            DISK_DEMO=FEDORA_DISK_DEMO,
        )
        Fedora.LATEST_RELEASE_STR = Fedora.FEDORA43_IMG

        Centos = Centos(CENTOS_STREAM_9_IMG="CentOS-Stream-GenericCloud-9-20220107.0.x86_64.qcow2")
        Centos.LATEST_RELEASE_STR = Centos.CENTOS_STREAM_9_IMG

        Cdi = Cdi(QCOW2_IMG=CIRROS_QCOW2_IMG)

    class ARM64:
        BASE_ALPINE_NAME = "alpine-aarch64-disk"
        BASE_VERSIONED_ALPINE_NAME = f"alpine-{ALPINE_VERSION}-aarch64-disk"
        # ARM64 has no Cirros image on ibmc Artifactory.
        # Reuse Alpine aarch64 — same pattern S390X uses with Fedora.
        # Tests that only need a bootable DV work fine (no SSH into the guest).
        # test_virtctl_image_upload_with_exist_pvc SSHes to the VM; Alpine uses
        # root/<empty>, set via os_login_param["alpine"] in global_config_multiarch_s390x_arm.py.
        Cirros = Cirros(
            QCOW2_IMG=f"{BASE_ALPINE_NAME}.qcow2",
            DISK_DEMO=CIRROS_DISK_DEMO,
            DIR=f"{BASE_IMAGES_DIR}/alpine-images",
            DEFAULT_DV_SIZE="2Gi",
            OS_FLAVOR=OS_FLAVOR_ALPINE,
        )

        Alpine = Alpine(
            QCOW2_IMG=f"{BASE_ALPINE_NAME}.qcow2",
            QCOW2_IMG_VERSIONED=f"{BASE_VERSIONED_ALPINE_NAME}.qcow2",
            RAW_IMG_XZ=f"{BASE_VERSIONED_ALPINE_NAME}.raw.xz",
        )

        Rhel = Rhel(
            RHEL9_5_IMG="rhel-95-aarch64.qcow2",
            RHEL9_6_IMG="rhel-96-aarch64.qcow2",
        )
        Rhel.LATEST_RELEASE_STR = Rhel.RHEL9_6_IMG

        Windows = Windows()
        Fedora = Fedora(
            # ibmc Artifactory has Fedora 43 aarch64; Fedora 42 aarch64 is absent
            FEDORA43_IMG="Fedora-Cloud-Base-Generic-43-1.6.aarch64.qcow2",
            FEDORA_CONTAINER_IMAGE="quay.io/openshift-cnv/qe-cnv-tests-fedora:41-arm64",
            DISK_DEMO=FEDORA_DISK_DEMO,
        )
        Fedora.LATEST_RELEASE_STR = Fedora.FEDORA43_IMG

        Centos = Centos(CENTOS_STREAM_9_IMG="CentOS-Stream-GenericCloud-9-latest.aarch64.qcow2")
        Centos.LATEST_RELEASE_STR = Centos.CENTOS_STREAM_9_IMG

        # ARM64 has no Cirros on ibmc Artifactory; reuse Alpine aarch64.
        Cdi = Cdi(
            QCOW2_IMG=f"{BASE_ALPINE_NAME}.qcow2",
            DIR=f"{BASE_IMAGES_DIR}/alpine-images",
            DEFAULT_DV_SIZE="2Gi",
        )

    class S390X:
        BASE_ALPINE_NAME = "alpine-s390x-disk"
        BASE_VERSIONED_ALPINE_NAME = f"alpine-{ALPINE_VERSION}-s390x-disk"
        Cirros = Cirros(
            # TODO: S390X does not support Cirros; this is a workaround until tests are moved to Fedora
            RAW_IMG="Fedora-Cloud-Base-Generic-41-1.4.s390x.raw",
            RAW_IMG_GZ="Fedora-Cloud-Base-Generic-41-1.4.s390x.raw.gz",
            RAW_IMG_XZ="Fedora-Cloud-Base-Generic-41-1.4.s390x.raw.xz",
            QCOW2_IMG="Fedora-Cloud-Base-Generic-41-1.4.s390x.qcow2",
            QCOW2_IMG_GZ="Fedora-Cloud-Base-Generic-41-1.4.s390x.qcow2.gz",
            QCOW2_IMG_XZ="Fedora-Cloud-Base-Generic-41-1.4.s390x.qcow2.xz",
            DISK_DEMO=FEDORA_DISK_DEMO,
            DIR=f"{BASE_IMAGES_DIR}/fedora-images",
            DEFAULT_DV_SIZE="10Gi",
            DEFAULT_MEMORY_SIZE="1Gi",
            OS_FLAVOR=OS_FLAVOR_FEDORA,
        )

        Alpine = Alpine(
            QCOW2_IMG=f"{BASE_ALPINE_NAME}.qcow2",
            QCOW2_IMG_VERSIONED=f"{BASE_VERSIONED_ALPINE_NAME}.qcow2",
            RAW_IMG_XZ=f"{BASE_VERSIONED_ALPINE_NAME}.raw.xz",
        )

        Rhel = Rhel(
            RHEL8_0_IMG="rhel-82-s390x.qcow2",
            RHEL8_9_IMG="rhel-89-s390x.qcow2",
            RHEL8_10_IMG="rhel-810-s390x.qcow2",
            RHEL9_3_IMG="rhel-93-s390x.qcow2",
            RHEL9_4_IMG="rhel-94-s390x.qcow2",
            RHEL9_5_IMG="rhel-95-s390x.qcow2",
            RHEL9_6_IMG="rhel-96-s390x.qcow2",
        )
        Rhel.LATEST_RELEASE_STR = Rhel.RHEL9_6_IMG

        Fedora = Fedora(
            FEDORA42_IMG="Fedora-Cloud-Base-Generic-42-1.1.s390x.qcow2",
            FEDORA_CONTAINER_IMAGE="quay.io/openshift-cnv/qe-cnv-tests-fedora:41-s390x",
            DISK_DEMO=FEDORA_DISK_DEMO,
        )
        Fedora.LATEST_RELEASE_STR = Fedora.FEDORA42_IMG

        Centos = Centos(CENTOS_STREAM_9_IMG="CentOS-Stream-GenericCloud-9-latest.s390x.qcow2")
        Centos.LATEST_RELEASE_STR = Centos.CENTOS_STREAM_9_IMG

        Cdi = Cdi(
            # TODO: S390X does not support Cirros; this is a workaround until tests are moved to Fedora
            QCOW2_IMG="Fedora-qcow2.img",
            DIR=f"{BASE_IMAGES_DIR}/fedora-images",
            DEFAULT_DV_SIZE="10Gi",
        )

        Windows = Windows()

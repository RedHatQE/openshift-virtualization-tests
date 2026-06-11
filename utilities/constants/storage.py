"""Storage constants.

Covers StorageClassNames, CDI (Containerized Data Importer) label keys and
configuration maps, HostPath Provisioner (HPP) capability flags, hotplug
constants, and image content source policy file names.
"""

from typing import Any

from ocp_resources.datavolume import DataVolume
from ocp_resources.resource import Resource


class StorageClassNames:
    CEPH_RBD = "ocs-storagecluster-ceph-rbd"
    CEPH_RBD_VIRTUALIZATION = f"{CEPH_RBD}-virtualization"
    CEPHFS = "ocs-storagecluster-cephfs"
    HOSTPATH = "hostpath-provisioner"
    NFS = "nfs"
    TOPOLVM = "lvms-vg1"
    PORTWORX_CSI_DB_SHARED = "px-csi-db-shared"
    RH_INTERNAL_NFS = "rh-internal-nfs"
    TRIDENT_CSI_FSX = "trident-csi-fsx"
    TRIDENT_CSI_NFS = "trident-csi-nfs"
    IO2_CSI = "io2-csi"
    GPFS = "ibm-spectrum-scale-sample"
    OCI = "oci-bv"
    OCI_UHP = "oci-bv-uhp"
    GCP = "sp-balanced-storage"
    GCNV = "gcnv-flex"


CDI_LABEL = Resource.ApiGroup.CDI_KUBEVIRT_IO
CDI_UPLOAD = "cdi-upload"
PVC = "pvc"
CDI_UPLOAD_TMP_PVC = f"cdi-upload-tmp-{PVC}"
SOURCE_POD = "source-pod"

CDI_SECRETS = [
    "cdi-apiserver-server-cert",
    "cdi-apiserver-signer",
    "cdi-uploadproxy-server-cert",
    "cdi-uploadproxy-signer",
    "cdi-uploadserver-client-cert",
    "cdi-uploadserver-client-signer",
    "cdi-uploadserver-signer",
]

CDI_CONFIGMAPS = [
    "cdi-apiserver-signer-bundle",
    "cdi-config",
    "cdi-controller-leader-election-helper",
    "cdi-insecure-registries",
    "cdi-uploadproxy-signer-bundle",
    "cdi-uploadserver-client-signer-bundle",
    "cdi-uploadserver-signer-bundle",
]

BREW_REGISTRY_SOURCE = "brew.registry.redhat.io"
ICSP_FILE = "imageContentSourcePolicy.yaml"
IDMS_FILE = "imageDigestMirrorSet.yaml"

ACCESS_MODE = "access_mode"
VOLUME_MODE = "volume_mode"

BIND_IMMEDIATE_ANNOTATION = {f"{Resource.ApiGroup.CDI_KUBEVIRT_IO}/storage.bind.immediate.requested": "true"}

HPP_CAPABILITIES: dict[str, Any] = {
    VOLUME_MODE: DataVolume.VolumeMode.FILE,
    ACCESS_MODE: DataVolume.AccessMode.RWO,
    "snapshot": False,
    "online_resize": False,
    "wffc": True,
}

# hotplug
HOTPLUG_DISK_SERIAL = "1234567890"
HOTPLUG_DISK_VIRTIO_BUS = "virtio"
HOTPLUG_DISK_SCSI_BUS = "scsi"

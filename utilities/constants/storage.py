"""Storage-related constants."""

from typing import Any

from ocp_resources.datavolume import DataVolume
from ocp_resources.resource import Resource

BIND_IMMEDIATE_ANNOTATION = {f"{Resource.ApiGroup.CDI_KUBEVIRT_IO}/storage.bind.immediate.requested": "true"}

HPP_CAPABILITIES: dict[str, Any] = {
    "volumeMode": DataVolume.VolumeMode.FILE,
    "accessMode": DataVolume.AccessMode.RWO,
    "snapshot": False,
    "online_resize": False,
    "wffc": True,
    "data_import_cron_source_format": "pvc",
}

# hotplug
HOTPLUG_DISK_SERIAL = "1234567890"
HOTPLUG_DISK_VIRTIO_BUS = "virtio"
HOTPLUG_DISK_SCSI_BUS = "scsi"

# DataVolume source type strings
REGISTRY_STR = "registry"

# DataImportCron / golden image constants
WILDCARD_CRON_EXPRESSION = "* * * * *"
OUTDATED = "Outdated"

# Built-in CNV ClusterRole granting create/clone permissions in an OS-images namespace
OS_IMAGES_EDIT_CLUSTER_ROLE = "os-images.kubevirt.io:edit"
# Built-in CDI ClusterRole (shipped by the CDI operator) granting the ``datavolumes/source`` permission
CDI_CLONE_SOURCER_CLUSTER_ROLE = "cdi.kubevirt.io:clone-sourcer"

# Storage capacity metric field names
CAPACITY = "capacity"
USED = "used"

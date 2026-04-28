import logging
from ast import literal_eval
from dataclasses import asdict, dataclass
from typing import Any

from ocp_resources.datavolume import DataVolume

from utilities.constants import HPP_CAPABILITIES, StorageClassNames
from utilities.storage import HppCsiStorageClass

LOGGER = logging.getLogger(__name__)


@dataclass
class StorageClass:
    name: str
    volume_mode: str
    access_mode: str
    snapshot: bool
    online_resize: bool
    wffc: bool


class StorageClassConfig:
    def __init__(self, name: str):
        self.name = name
        self.storage_config = self.get_storage_config()

    def supported_storage_classes(self) -> list[StorageClass]:
        return [
            StorageClass(
                name=StorageClassNames.CEPH_RBD_VIRTUALIZATION,
                volume_mode=DataVolume.VolumeMode.BLOCK,
                access_mode=DataVolume.AccessMode.RWX,
                snapshot=True,
                online_resize=True,
                wffc=False,
            ),
            StorageClass(name=HppCsiStorageClass.Name.HOSTPATH_CSI_BASIC, **HPP_CAPABILITIES),
            StorageClass(name=HppCsiStorageClass.Name.HOSTPATH_CSI_PVC_BLOCK, **HPP_CAPABILITIES),
            StorageClass(
                name=StorageClassNames.TRIDENT_CSI_NFS,
                volume_mode=DataVolume.VolumeMode.FILE,
                access_mode=DataVolume.AccessMode.RWX,
                snapshot=True,
                online_resize=True,
                wffc=False,
            ),
            StorageClass(
                name=StorageClassNames.IO2_CSI,
                volume_mode=DataVolume.VolumeMode.BLOCK,
                access_mode=DataVolume.AccessMode.RWX,
                snapshot=True,
                online_resize=True,
                wffc=True,
            ),
            StorageClass(
                name=StorageClassNames.PORTWORX_CSI_DB_SHARED,
                volume_mode=DataVolume.VolumeMode.FILE,
                access_mode=DataVolume.AccessMode.RWX,
                snapshot=True,
                online_resize=True,
                wffc=False,
            ),
            StorageClass(
                name=StorageClassNames.TRIDENT_CSI_FSX,
                volume_mode=DataVolume.VolumeMode.FILE,
                access_mode=DataVolume.AccessMode.RWX,
                snapshot=True,
                online_resize=True,
                wffc=False,
            ),
            StorageClass(
                name=StorageClassNames.GCP,
                volume_mode=DataVolume.VolumeMode.BLOCK,
                access_mode=DataVolume.AccessMode.RWX,
                snapshot=True,
                online_resize=True,
                wffc=False,
            ),
            StorageClass(
                name=StorageClassNames.GCNV,
                volume_mode=DataVolume.VolumeMode.FILE,
                access_mode=DataVolume.AccessMode.RWX,
                snapshot=True,
                online_resize=True,
                wffc=False,
            ),
            StorageClass(
                name=StorageClassNames.GPFS,
                volume_mode=DataVolume.VolumeMode.FILE,
                access_mode=DataVolume.AccessMode.RWX,
                snapshot=True,
                online_resize=True,
                wffc=False,
            ),
            StorageClass(
                name="sno-storage",
                volume_mode=DataVolume.VolumeMode.FILE,
                access_mode=DataVolume.AccessMode.RWO,
                snapshot=True,
                online_resize=True,
                wffc=True,
            ),
            StorageClass(
                name=StorageClassNames.TOPOLVM,
                volume_mode=DataVolume.VolumeMode.BLOCK,
                access_mode=DataVolume.AccessMode.RWO,
                snapshot=True,
                online_resize=True,
                wffc=True,
            ),
            StorageClass(
                name=StorageClassNames.NFS,
                volume_mode=DataVolume.VolumeMode.FILE,
                access_mode=DataVolume.AccessMode.RWX,
                snapshot=False,
                online_resize=False,
                wffc=False,
            ),
            StorageClass(
                name=StorageClassNames.OCI,
                volume_mode=DataVolume.VolumeMode.BLOCK,
                access_mode=DataVolume.AccessMode.RWX,
                snapshot=True,
                online_resize=True,
                wffc=True,
            ),
            StorageClass(
                name=StorageClassNames.OCI_UHP,
                volume_mode=DataVolume.VolumeMode.BLOCK,
                access_mode=DataVolume.AccessMode.RWX,
                snapshot=True,
                online_resize=True,
                wffc=True,
            ),
            StorageClass(
                name=StorageClassNames.RH_INTERNAL_NFS,
                volume_mode=DataVolume.VolumeMode.FILE,
                access_mode=DataVolume.AccessMode.RWX,
                snapshot=True,
                online_resize=True,
                wffc=False,
            ),
        ]

    def get_storage_config(self) -> dict[str, Any] | None:
        for storage_class in self.supported_storage_classes():
            if storage_class.name == self.name:
                return asdict(obj=storage_class)

        return None

    def construct_storage_class_matrix(self, storage_config: str | None = None) -> list[dict[str, Any]]:
        """
        Constructs a storage class matrix from the storage class config

        Args:
            storage_config (str | None): Storage class config.
                Format: `volume_mode=Block,access_mode=RWO,snapshot=True,online_resize=True,wffc=False`

        Returns:
            list[dict[str, str | bool]]: Storage class matrix

        """
        if sc_config := self.get_storage_config():
            sc_config["default"] = True
            LOGGER.info(f"Using {sc_config} for storage class {self.name}")

            return [{sc_config.pop("name"): sc_config}]

        else:
            LOGGER.info(f"Could not find storage class configuration for {self.name}. Constructing from user input")
            cmd_config = {}

            if storage_config:
                if not all("=" in item for item in storage_config.split(",")):
                    raise ValueError("Invalid format: all items must be key=value pairs, separated by comma")

                cmd_config = dict(item.split("=") for item in storage_config.split(","))

            sc_config = {
                self.name: {
                    "volume_mode": getattr(
                        DataVolume.VolumeMode,
                        cmd_config.get("volume_mode", "").upper(),
                        DataVolume.VolumeMode.FILE,
                    ),
                    "access_mode": getattr(
                        DataVolume.AccessMode,
                        cmd_config.get("access_mode", "").upper(),
                        DataVolume.AccessMode.RWO,
                    ),
                    "snapshot": literal_eval(cmd_config.get("snapshot", "False").title()),
                    "online_resize": literal_eval(cmd_config.get("online_resize", "False").title()),
                    "wffc": literal_eval(cmd_config.get("wffc", "False").title()),
                    "default": True,
                }
            }

            LOGGER.info(f"Setting {sc_config} for storage class {self.name}")

            return [sc_config]

from ocp_resources.template import Template

from tests.utils import generate_attached_rhsm_secret_dict, generate_rhsm_cloud_init_data
from utilities.constants import AMD, INTEL, REGEDIT_PROC_NAME, WIN_10, WIN_11, Images, StorageClassNames
from utilities.virt import (
    fetch_pid_from_linux_vm,
    fetch_pid_from_windows_vm,
    start_and_fetch_processid_on_linux_vm,
    start_and_fetch_processid_on_windows_vm,
)

LINUX_OS_PREFIX = "lin"
WINDOWS_OS_PREFIX = "win"

PROC_PER_OS_DICT = {
    LINUX_OS_PREFIX: {
        "proc_name": "sleep",
        "proc_args": "infinity",
        "fetch_pid": fetch_pid_from_linux_vm,
        "create_proc": start_and_fetch_processid_on_linux_vm,
    },
    WINDOWS_OS_PREFIX: {
        "proc_name": REGEDIT_PROC_NAME,
        "fetch_pid": fetch_pid_from_windows_vm,
        "create_proc": start_and_fetch_processid_on_windows_vm,
    },
}


LINUX_DV_PARAMS = [
    {
        "dv-ocs-lin": {
            "image_path": f"{Images.Rhel.DIR}/{Images.Rhel.RHEL8_9_IMG}",
            "dv_size": Images.Rhel.DEFAULT_DV_SIZE,
            "storage_class": StorageClassNames.CEPH_RBD_VIRTUALIZATION,
        }
    },
    {
        "dv-nfs-lin": {
            "image_path": f"{Images.Rhel.DIR}/{Images.Rhel.RHEL8_9_IMG}",
            "dv_size": Images.Rhel.DEFAULT_DV_SIZE,
            "storage_class": StorageClassNames.NFS,
        }
    },
]

WINDOWS_DV_PARAMS = [
    {
        "dv-ocs-win": {
            "image_path": f"{Images.Windows.UEFI_WIN_DIR}/{Images.Windows.WIN10_IMG}",
            "dv_size": Images.Windows.DEFAULT_DV_SIZE,
            "storage_class": StorageClassNames.CEPH_RBD_VIRTUALIZATION,
        }
    },
    {
        "dv-nfs-win": {
            "image_path": f"{Images.Windows.UEFI_WIN_DIR}/{Images.Windows.WIN10_IMG}",
            "dv_size": Images.Windows.DEFAULT_DV_SIZE,
            "storage_class": StorageClassNames.NFS,
        }
    },
]

WSL2_DV_PARAMS = [
    {
        "dv-win10-wsl2-win": {
            "image_path": f"{Images.Windows.UEFI_WIN_DIR}/{Images.Windows.WIN10_WSL2_IMG}",
            "dv_size": Images.Windows.DEFAULT_DV_SIZE,
            "storage_class": StorageClassNames.CEPH_RBD_VIRTUALIZATION,
        }
    },
    {
        "dv-win11-wsl2-win": {
            "image_path": f"{Images.Windows.DIR}/{Images.Windows.WIN11_WSL2_IMG}",
            "dv_size": Images.Windows.DEFAULT_DV_SIZE,
            "storage_class": StorageClassNames.CEPH_RBD_VIRTUALIZATION,
        }
    },
]

LINUX_VM_PARAMS = [
    {
        "linux-multi-mig-ocsdisk-vm": {
            "os_labels": {
                "os": "rhel8.9",
                "workload": Template.Workload.SERVER,
                "flavor": Template.Flavor.TINY,
            },
            "datasource_name": "dv-ocs-lin",
        }
    },
    {
        "linux-multi-mig-nfsdisk-vm": {
            "os_labels": {
                "os": "rhel8.9",
                "workload": Template.Workload.SERVER,
                "flavor": Template.Flavor.TINY,
            },
            "datasource_name": "dv-nfs-lin",
        }
    },
    {
        "linux-multi-mig-secret-vm": {
            "os_labels": {
                "os": "rhel8.9",
                "workload": Template.Workload.SERVER,
                "flavor": Template.Flavor.TINY,
            },
            "datasource_name": "dv-ocs-lin",
            "cloud_init_data": generate_rhsm_cloud_init_data(),
            "attached_secret": generate_attached_rhsm_secret_dict(),
        },
    },
]

WINDOWS_VM_PARAMS = [
    {
        "windows-multi-mig-ocsdisk-vm": {
            "os_labels": {
                "os": WIN_10,
                "workload": Template.Workload.DESKTOP,
                "flavor": Template.Flavor.MEDIUM,
            },
            "datasource_name": "dv-ocs-win",
        }
    },
    {
        "windows-multi-mig-nfsdisk-vm": {
            "os_labels": {
                "os": WIN_10,
                "workload": Template.Workload.DESKTOP,
                "flavor": Template.Flavor.MEDIUM,
            },
            "datasource_name": "dv-nfs-win",
        }
    },
]

WSL2_VM_PARAMS = [
    {
        "windows-multi-mig-win10-wsl2-vm": {
            "os_labels": {
                "os": WIN_10,
                "workload": Template.Workload.DESKTOP,
                "flavor": Template.Flavor.MEDIUM,
            },
            "datasource_name": "dv-win10-wsl2-win",
            "memory_guest": Images.Windows.DEFAULT_MEMORY_SIZE_WSL,
            "cpu_cores": 16,
            "cpu_threads": 1,
            "cpu_features": {INTEL: "vmx", AMD: "svm"},
        }
    },
    {
        "windows-multi-mig-win11-wsl2-vm": {
            "os_labels": {
                "os": WIN_11,
                "workload": Template.Workload.DESKTOP,
                "flavor": Template.Flavor.MEDIUM,
            },
            "datasource_name": "dv-win11-wsl2-win",
            "memory_guest": Images.Windows.DEFAULT_MEMORY_SIZE_WSL,
            "cpu_cores": 16,
            "cpu_threads": 1,
            "cpu_features": {INTEL: "vmx", AMD: "svm"},
        }
    },
]

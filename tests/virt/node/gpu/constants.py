# GPU/vGPU Common constants
# The GPU tests require GPU Device on the Worker Nodes.
# ~]$ lspci -nnv | grep -i NVIDIA  , should display the GPU_DEVICE_ID
GPU_DEVICE_MANUFACTURER = "nvidia.com"

# GPU Passthrough constants
NVIDIA_VFIO_MANAGER_DS = "nvidia-vfio-manager"

# vGPU constants
NVIDIA_VGPU_MANAGER_DS = "nvidia-vgpu-manager-daemonset"
NVIDIA_GRID_DRIVER_NAME = "NVIDIA GRID"


DEVICE_ID_STR = "device_id"
GPU_DEVICE_NAME_STR = "gpu_device_name"
VGPU_DEVICE_NAME_STR = "vgpu_device_name"
DEVICE_PRETTY_NAME_STR = "device_pretty_name"
GPU_PRETTY_NAME_STR = "gpu_pretty_name"
VGPU_PRETTY_NAME_STR = "vgpu_pretty_name"
MDEV_NAME_STR = "mdev_name"
MDEV_AVAILABLE_INSTANCES_STR = "mdev_available_instances"
MDEV_TYPE_STR = "mdev_type"
VGPU_GRID_NAME_STR = "vgpu_grid_name"
MDEV_GRID_NAME_STR = "mdev_grid_name"
MDEV_GRID_AVAILABLE_INSTANCES_STR = "mdev_grid_available_instances"
MDEV_GRID_TYPE_STR = "mdev_grid_type"

GPU_CARDS_MAP = {
    "10de:1eb8": {
        DEVICE_ID_STR: "10de:1eb8",
        GPU_DEVICE_NAME_STR: f"{GPU_DEVICE_MANUFACTURER}/TU104GL_Tesla_T4",
        VGPU_DEVICE_NAME_STR: f"{GPU_DEVICE_MANUFACTURER}/GRID_T4_2Q",
        GPU_PRETTY_NAME_STR: "NVIDIA Tesla T4",
        VGPU_PRETTY_NAME_STR: "GRID T4-2Q",
        MDEV_NAME_STR: "GRID T4-2Q",
        MDEV_AVAILABLE_INSTANCES_STR: "8",
        MDEV_TYPE_STR: "nvidia-231",
        VGPU_GRID_NAME_STR: f"{GPU_DEVICE_MANUFACTURER}/GRID_T4_16Q",
        MDEV_GRID_NAME_STR: "GRID T4-16Q",
        MDEV_GRID_AVAILABLE_INSTANCES_STR: "1",
        MDEV_GRID_TYPE_STR: "nvidia-234",
    },
    "10de:25b6": {
        DEVICE_ID_STR: "10de:25b6",
        GPU_DEVICE_NAME_STR: f"{GPU_DEVICE_MANUFACTURER}/GA107GL_Ampere_A2",
        VGPU_DEVICE_NAME_STR: f"{GPU_DEVICE_MANUFACTURER}/GRID_A2_2Q",
        GPU_PRETTY_NAME_STR: "NVIDIA A2",
        VGPU_PRETTY_NAME_STR: "NVIDIA A2",
        MDEV_NAME_STR: "NVIDIA A2-2Q",
        MDEV_AVAILABLE_INSTANCES_STR: "8",
        MDEV_TYPE_STR: "nvidia-745",
        VGPU_GRID_NAME_STR: f"{GPU_DEVICE_MANUFACTURER}/GRID_A2_4Q",
        MDEV_GRID_NAME_STR: "NVIDIA A2-4Q",
        MDEV_GRID_AVAILABLE_INSTANCES_STR: "4",
        MDEV_GRID_TYPE_STR: "nvidia-746",
    },
}

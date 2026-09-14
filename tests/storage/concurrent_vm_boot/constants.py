"""Constants for concurrent VM boot tests."""

NUM_CONCURRENT_VMS = 20
NUM_BLANK_DISKS_PER_VM = 3
NUM_FIXED_DISKS_PER_VM = 2  # boot disk (golden image clone) + cloud-init
BLANK_DV_SIZE = "1Gi"

# Memory budget: 2 GiB guest RAM (u1.small) + 1 GiB virt-launcher/OS overhead per VM.
GUEST_GI_PER_VM = 2  # u1.small provides 2 GiB guest RAM
VIRT_LAUNCHER_OVERHEAD_GI_PER_VM = 1  # per-VM overhead estimate (virt-launcher + kernel)
REQUIRED_CLUSTER_MEMORY_GI = NUM_CONCURRENT_VMS * (GUEST_GI_PER_VM + VIRT_LAUNCHER_OVERHEAD_GI_PER_VM)

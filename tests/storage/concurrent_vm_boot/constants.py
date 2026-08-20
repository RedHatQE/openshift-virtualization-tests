"""Constants for concurrent VM boot tests."""

NUM_CONCURRENT_VMS = 20
# Each VM has 5 VMI disk devices: 1 golden image boot (PVC clone) + 1 cloud-init + 3 blank data volumes
NUM_BLANK_DISKS_PER_VM = 3
# Fixed disks present on every VM regardless of configuration: boot volume + cloud-init
NUM_FIXED_DISKS_PER_VM = 2
BLANK_DV_SIZE = "1Gi"
# u1.micro (1Gi RAM) reduces aggregate memory from 40Gi to 20Gi compared to the default
# fedora preference (2Gi minimum); the test still requires sufficient schedulable memory
# and storage capacity — not all cluster sizes can schedule all 20 VMs simultaneously.
VM_INSTANCE_TYPE = "u1.micro"

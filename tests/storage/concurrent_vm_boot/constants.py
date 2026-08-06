"""Constants for concurrent VM boot tests."""

NUM_CONCURRENT_VMS = 20
# Each VM gets 5 VMI devices total: 1 golden image boot (PVC clone) + 1 cloud-init + 3 blank data volumes (PVCs)
NUM_BLANK_DISKS_PER_VM = 3
BLANK_DV_SIZE = "1Gi"

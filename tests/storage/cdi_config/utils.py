"""
Utility functions and constants for CDI Config tests
"""

STORAGE_WORKLOADS_DICT = {
    "limits": {"cpu": "505m", "memory": "2Gi"},
    "requests": {"cpu": "252m", "memory": "1Gi"},
}
NON_EXISTENT_SCRATCH_SC_DICT = {"scratchSpaceStorageClass": "NonExistentSC"}
INSECURE_REGISTRIES_LIST = ["added-private-registry:5000"]

from utilities.constants import (
    POD_LIMITS_CPU,
    POD_LIMITS_MEMORY,
    POD_REQUESTS_CPU,
    POD_REQUESTS_MEMORY,
    QUOTA_FOR_POD,
    REQUESTS_CPU_VMI_STR,
    REQUESTS_INSTANCES_VMI_STR,
    REQUESTS_MEMORY_VMI_STR,
    VM_CPU_CORES,
    VM_MEMORY_GUEST,
)

POD_RESOURCES_SPEC = {
    "resources": {
        "requests": {
            "memory": POD_REQUESTS_MEMORY,
            "cpu": POD_REQUESTS_CPU,
        },
        "limits": {
            "memory": POD_LIMITS_MEMORY,
            "cpu": POD_LIMITS_CPU,
        },
    }
}


QUOTA_FOR_TWO_VMI = {
    REQUESTS_INSTANCES_VMI_STR: "2",
    REQUESTS_CPU_VMI_STR: VM_CPU_CORES * 2,
    REQUESTS_MEMORY_VMI_STR: f"{int(VM_MEMORY_GUEST[:-2]) * 2}Gi",
}


ACRQ_QUOTA_HARD_SPEC = {**QUOTA_FOR_POD, **QUOTA_FOR_TWO_VMI}


CPU_MAX_SOCKETS = 4
MEMORY_MAX_GUEST = "4Gi"

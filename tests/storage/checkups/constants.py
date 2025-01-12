from ocp_resources.resource import Resource

from utilities.constants import CREATE_STR, DELETE_STR, GET_STR, UPDATE_STR

ACCESS_MODES = "accessModes"
NON_EXISTENT_STR = "nonexistent"
RESOURCES_STR = "resources"
API_GROUPS_STR = "apiGroups"
VERBS_STR = "verbs"
NAME_STR = "name"
SPEC_STR = "spec"
STORAGE_CHECKUP_STR = "storage-checkup"
VIRTUAL_MACHINE_INSTANCES_STR = "virtualmachineinstances"
KUBEVIRT_IO_API_GROUP = Resource.ApiGroup.KUBEVIRT_IO

CHECKUP_RULES = [
    {
        API_GROUPS_STR: [""],
        RESOURCES_STR: ["configmaps"],
        VERBS_STR: [GET_STR, UPDATE_STR],
    },
    {
        API_GROUPS_STR: [KUBEVIRT_IO_API_GROUP],
        RESOURCES_STR: ["virtualmachines"],
        VERBS_STR: [CREATE_STR, DELETE_STR],
    },
    {
        API_GROUPS_STR: [KUBEVIRT_IO_API_GROUP],
        RESOURCES_STR: [VIRTUAL_MACHINE_INSTANCES_STR],
        VERBS_STR: [GET_STR],
    },
    {
        API_GROUPS_STR: [Resource.ApiGroup.SUBRESOURCES_KUBEVIRT_IO],
        RESOURCES_STR: [
            f"{VIRTUAL_MACHINE_INSTANCES_STR}/addvolume",
            f"{VIRTUAL_MACHINE_INSTANCES_STR}/removevolume",
        ],
        VERBS_STR: [UPDATE_STR],
    },
    {
        API_GROUPS_STR: [KUBEVIRT_IO_API_GROUP],
        RESOURCES_STR: ["virtualmachineinstancemigrations"],
        VERBS_STR: [CREATE_STR],
    },
    {
        API_GROUPS_STR: [Resource.ApiGroup.CDI_KUBEVIRT_IO],
        RESOURCES_STR: ["datavolumes"],
        VERBS_STR: [CREATE_STR, DELETE_STR],
    },
    {
        API_GROUPS_STR: [""],
        RESOURCES_STR: ["persistentvolumeclaims"],
        VERBS_STR: [DELETE_STR],
    },
]

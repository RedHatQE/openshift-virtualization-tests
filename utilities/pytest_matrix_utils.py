"""
all function in this file must accept only matrix arg.
def foo_matrix(matrix):
    <customize matrix code>
    return matrix
"""

from ocp_resources.storage_class import StorageClass


def snapshot_matrix(matrix):
    matrix_to_return = []
    for storage_class in matrix:
        storage_class_name = [*storage_class][0]
        if storage_class[storage_class_name]["snapshot"] is True:
            matrix_to_return.append(storage_class)
    return matrix_to_return


def without_snapshot_capability_matrix(matrix):
    matrix_to_return = []
    for storage_class in matrix:
        storage_class_name = [*storage_class][0]
        if storage_class[storage_class_name]["snapshot"] is False:
            matrix_to_return.append(storage_class)
    return matrix_to_return


def online_resize_matrix(matrix):
    matrix_to_return = []
    for storage_class in matrix:
        # storage_class object must have allowVolumeExpansion: true
        storage_class_name = [*storage_class][0]
        if storage_class[storage_class_name]["online_resize"] is True:
            matrix_to_return.append(storage_class)
    return matrix_to_return


def hpp_matrix(matrix):
    matrix_to_return = []
    hpp_sc_provisioners = [
        StorageClass.Provisioner.HOSTPATH_CSI,
        StorageClass.Provisioner.HOSTPATH,
    ]

    for storage_class in matrix:
        if StorageClass(name=[*storage_class][0]).instance.provisioner in hpp_sc_provisioners:
            matrix_to_return.append(storage_class)
    return matrix_to_return


def wffc_matrix(matrix):
    matrix_to_return = []
    for storage_class in matrix:
        storage_class_name = [*storage_class][0]
        if storage_class[storage_class_name]["wffc"] is True:
            matrix_to_return.append(storage_class)
    return matrix_to_return

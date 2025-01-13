"""
all function in this file must accept only matrix arg.
def foo_matrix(matrix):
    <customize matrix code>
    return matrix
"""

from ocp_resources.resource import get_client
from ocp_resources.storage_class import StorageClass

from utilities.storage import is_snapshot_supported_by_sc, sc_volume_binding_mode_is_wffc


def snapshot_matrix(matrix):
    matrix_to_return = []
    for storage_class in matrix:
        if is_snapshot_supported_by_sc(
            sc_name=[*storage_class][0],
            client=get_client(),
        ):
            matrix_to_return.append(storage_class)
    return matrix_to_return


def without_snapshot_capability_matrix(matrix):
    matrix_to_return = []
    for storage_class in matrix:
        if not is_snapshot_supported_by_sc(
            sc_name=[*storage_class][0],
            client=get_client(),
        ):
            matrix_to_return.append(storage_class)
    return matrix_to_return


def online_resize_matrix(matrix):
    matrix_to_return = []
    for storage_class in matrix:
        storage_class_object = StorageClass(name=[*storage_class][0])
        if storage_class_object.instance.get("allowVolumeExpansion"):
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
        if sc_volume_binding_mode_is_wffc(sc=[*storage_class][0]):
            matrix_to_return.append(storage_class)
    return matrix_to_return

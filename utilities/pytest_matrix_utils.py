"""
all function in this file must accept only matrix arg.
def foo_matrix(matrix):
    <customize matrix code>
    return matrix
"""

from functools import cache

from kubernetes.dynamic import DynamicClient
from ocp_resources.resource import get_client
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
        # Using `get_client` explicitly as this function is dynamically called (like other functions in the module).
        # The other functions do not need a client.
        if (
            StorageClass(client=_cache_admin_client(), name=[*storage_class][0]).instance.provisioner
            in hpp_sc_provisioners
        ):
            matrix_to_return.append(storage_class)

    return matrix_to_return


def wffc_matrix(matrix):
    matrix_to_return = []
    for storage_class in matrix:
        storage_class_name = [*storage_class][0]
        if storage_class[storage_class_name]["wffc"] is True:
            matrix_to_return.append(storage_class)
    return matrix_to_return


def immediate_matrix(matrix):
    matrix_to_return = []
    for storage_class in matrix:
        storage_class_name = [*storage_class][0]
        if storage_class[storage_class_name]["wffc"] is False:
            matrix_to_return.append(storage_class)
    return matrix_to_return


@cache
def _cache_admin_client() -> DynamicClient:
    """Get admin_client once and reuse it

    This usage of this function is limited to places where `client` cannot be passed as an argument.

    Returns:
        DynamicClient: admin_client

    """

    return get_client()

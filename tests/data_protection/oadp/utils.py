from __future__ import annotations

import logging
from collections.abc import Generator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from kubernetes.dynamic.exceptions import NotFoundError
from ocp_resources.custom_resource_definition import CustomResourceDefinition
from ocp_resources.data_protection_application import DataProtectionApplication
from ocp_resources.datavolume import DataVolume
from ocp_resources.deployment import Deployment
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_resources.resource import ResourceEditor
from timeout_sampler import TimeoutSampler

from utilities.constants.namespaces import NamespacesNames
from utilities.constants.oadp import DPA_NAME, VELERO_BACKUP_HOOK_ANNOTATIONS
from utilities.constants.timeouts import TIMEOUT_5MIN, TIMEOUT_10SEC, TIMEOUT_15SEC
from utilities.exceptions import ResourceMissingFieldError

if TYPE_CHECKING:
    from kubernetes.dynamic import DynamicClient

    from utilities.virt import VirtualMachineForTests

LOGGER = logging.getLogger(__name__)

FILE_PATH_FOR_WINDOWS_BACKUP = "C:/oadp_file_before_backup.txt"
_DPA_CRD_NAME = "dataprotectionapplications.oadp.openshift.io"
_CSI_SNAPSHOT_EARLY_FREQUENT_POLLING_FIELD = "enableCSISnapshotEarlyFrequentPolling"
_CSI_SNAPSHOT_EARLY_FREQUENT_POLLING_ARG = "--csi-snapshot-early-frequent-polling"
_VELERO_DEPLOYMENT_NAME = "velero"
_VELERO_CONTAINER_NAME = "velero"
_VELERO_SCHEMA_PATH = (
    "schema",
    "openAPIV3Schema",
    "properties",
    "spec",
    "properties",
    "configuration",
    "properties",
    "velero",
    "properties",
)


def wait_for_restored_dv(dv: DataVolume) -> None:
    """
    Wait for a restored DataVolume to be ready after OADP restore.

    Args:
        dv: DataVolume to wait for

    Raises:
        TimeoutExpiredError: If PVC does not reach BOUND status within 15 seconds
            or DataVolume does not succeed within 10 seconds
    """
    dv.pvc.wait_for_status(status=PersistentVolumeClaim.Status.BOUND, timeout=TIMEOUT_15SEC)
    dv.wait_for_dv_success(timeout=TIMEOUT_10SEC)


def assert_velero_backup_hooks_not_injected(vm: VirtualMachineForTests, admin_client: DynamicClient) -> None:
    """Assert virt-launcher has no Velero freeze/unfreeze hook annotations.

    Absence of these annotations means Velero will not execute filesystem
    freeze/unfreeze during backup.

    Args:
        vm: VirtualMachine whose virt-launcher pod is checked.
        admin_client: Privileged client used to access the virt-launcher pod.

    Raises:
        AssertionError: If any Velero hook annotations are found on the virt-launcher pod.
    """
    virt_launcher_pod = vm.vmi.get_virt_launcher_pod(privileged_client=admin_client)
    pod_annotations = virt_launcher_pod.instance.metadata.annotations or {}
    present_hook_annotations = [
        annotation_key for annotation_key in VELERO_BACKUP_HOOK_ANNOTATIONS if annotation_key in pod_annotations
    ]
    assert not present_hook_annotations, (
        f"VM {vm.name} virt-launcher pod has Velero hook annotations {present_hook_annotations} "
        f"but backup hooks should be disabled"
    )


def _mapping_at(source: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any] | None:
    current: Any = source
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    if not isinstance(current, dict):
        return None
    return current


def _dpa_crd_defines_csi_snapshot_early_frequent_polling(client: DynamicClient) -> bool:
    crd = CustomResourceDefinition(name=_DPA_CRD_NAME, client=client)
    try:
        crd_dict = crd.instance.to_dict()
    except NotFoundError as not_found:
        raise ResourceMissingFieldError(f"CustomResourceDefinition {_DPA_CRD_NAME} was not found") from not_found
    try:
        versions = crd_dict["spec"]["versions"]
    except KeyError as missing_key:
        raise ResourceMissingFieldError(
            f"CustomResourceDefinition {_DPA_CRD_NAME} is missing spec.versions"
        ) from missing_key
    try:
        storage_version = next(version for version in versions if version["storage"])
    except StopIteration as missing_storage:
        raise ResourceMissingFieldError(
            f"CustomResourceDefinition {_DPA_CRD_NAME} has no storage version"
        ) from missing_storage
    except KeyError as missing_key:
        raise ResourceMissingFieldError(
            f"CustomResourceDefinition {_DPA_CRD_NAME} version is missing storage"
        ) from missing_key
    velero_properties = _mapping_at(source=storage_version, keys=_VELERO_SCHEMA_PATH)
    field_defined = velero_properties is not None and _CSI_SNAPSHOT_EARLY_FREQUENT_POLLING_FIELD in velero_properties
    if not field_defined:
        LOGGER.info(
            f"Skipping {_CSI_SNAPSHOT_EARLY_FREQUENT_POLLING_FIELD}; "
            f"field is not in the storage schema of {_DPA_CRD_NAME}"
        )
    return field_defined


def _csi_snapshot_early_frequent_polling_value(dpa: DataProtectionApplication) -> bool | None:
    try:
        spec = dpa.instance.to_dict()["spec"]
    except NotFoundError as not_found:
        raise ResourceMissingFieldError(
            f"DataProtectionApplication {dpa.name} in namespace {dpa.namespace} was not found"
        ) from not_found
    except KeyError as missing_key:
        raise ResourceMissingFieldError(
            f"DataProtectionApplication {dpa.name} in namespace {dpa.namespace} is missing spec"
        ) from missing_key
    velero_configuration = _mapping_at(source=spec, keys=("configuration", "velero"))
    if velero_configuration is None or _CSI_SNAPSHOT_EARLY_FREQUENT_POLLING_FIELD not in velero_configuration:
        return None
    value = velero_configuration[_CSI_SNAPSHOT_EARLY_FREQUENT_POLLING_FIELD]
    if isinstance(value, bool):
        return value
    raise ResourceMissingFieldError(
        f"DataProtectionApplication {dpa.name} in namespace {dpa.namespace} "
        f"has {_CSI_SNAPSHOT_EARLY_FREQUENT_POLLING_FIELD}={value!r}; expected a boolean"
    )


def _csi_snapshot_early_frequent_polling_patch(
    dpa: DataProtectionApplication,
    enabled: bool | None,
) -> dict[str, Any]:
    return {
        "metadata": {"name": dpa.name},
        "spec": {
            "configuration": {
                "velero": {
                    _CSI_SNAPSHOT_EARLY_FREQUENT_POLLING_FIELD: enabled,
                }
            }
        },
    }


def _deployment_instance(deployment: Deployment) -> dict[str, Any]:
    try:
        return deployment.instance.to_dict()
    except NotFoundError as not_found:
        raise ResourceMissingFieldError(
            f"Deployment {deployment.name} in namespace {deployment.namespace} was not found"
        ) from not_found


def _velero_container_args(deployment: Deployment, instance: dict[str, Any]) -> list[str]:
    try:
        containers = instance["spec"]["template"]["spec"]["containers"]
    except KeyError as missing_key:
        raise ResourceMissingFieldError(
            f"Deployment {deployment.name} in namespace {deployment.namespace} is missing spec.template.spec.containers"
        ) from missing_key
    for container in containers:
        try:
            container_name = container["name"]
        except KeyError as missing_key:
            raise ResourceMissingFieldError(
                f"Deployment {deployment.name} in namespace {deployment.namespace} has a container without a name"
            ) from missing_key
        if container_name != _VELERO_CONTAINER_NAME:
            continue
        args = container.get("args", [])
        if not isinstance(args, list) or any(not isinstance(arg, str) for arg in args):
            raise ResourceMissingFieldError(
                f"Deployment {deployment.name} in namespace {deployment.namespace} "
                f"container {_VELERO_CONTAINER_NAME} args must be a list of strings"
            )
        return args
    raise ResourceMissingFieldError(
        f"Deployment {deployment.name} in namespace {deployment.namespace} has no {_VELERO_CONTAINER_NAME} container"
    )


def _polling_arg_enabled(args: list[str]) -> bool:
    flag_prefix = f"{_CSI_SNAPSHOT_EARLY_FREQUENT_POLLING_ARG}="
    for arg in args:
        if arg == _CSI_SNAPSHOT_EARLY_FREQUENT_POLLING_ARG:
            return True
        if arg.startswith(flag_prefix):
            return arg.removeprefix(flag_prefix).lower() == "true"
    return False


def _velero_polling_arg_matches(deployment: Deployment, enabled: bool) -> bool:
    instance = _deployment_instance(deployment=deployment)
    try:
        generation = instance["metadata"]["generation"]
    except KeyError as missing_key:
        raise ResourceMissingFieldError(
            f"Deployment {deployment.name} in namespace {deployment.namespace} is missing metadata.generation"
        ) from missing_key
    status = instance.get("status")
    if not isinstance(status, dict) or status.get("observedGeneration") != generation:
        return False
    return _polling_arg_enabled(args=_velero_container_args(deployment=deployment, instance=instance)) == enabled


def _wait_for_velero_polling_arg(client: DynamicClient, enabled: bool) -> None:
    deployment = Deployment(
        name=_VELERO_DEPLOYMENT_NAME,
        namespace=NamespacesNames.ADP_NAMESPACE,
        client=client,
    )
    LOGGER.info(
        f"Waiting for Deployment {deployment.name} in {deployment.namespace} "
        f"to set {_CSI_SNAPSHOT_EARLY_FREQUENT_POLLING_ARG} enabled={enabled}"
    )
    for sample in TimeoutSampler(
        wait_timeout=TIMEOUT_5MIN,
        sleep=TIMEOUT_10SEC,
        func=_velero_polling_arg_matches,
        deployment=deployment,
        enabled=enabled,
    ):
        if sample:
            break
    deployment.wait_for_replicas(timeout=TIMEOUT_5MIN)


@contextmanager
def enable_csi_snapshot_early_frequent_polling(
    client: DynamicClient,
) -> Generator[DataProtectionApplication]:
    """Enable CSI snapshot early frequent polling on the DataProtectionApplication.

    Windows VSS backups need spec.configuration.velero.enableCSISnapshotEarlyFrequentPolling.
    Velero is rolled until its container args include --csi-snapshot-early-frequent-polling=true.
    On exit the previous value is restored and Velero is rolled again. An already-true value is
    left unchanged. Older OADP installs whose DPA CRD does not define the field are left unchanged.

    Args:
        client: Privileged client used to read and patch cluster resources.

    Yields:
        The cluster DataProtectionApplication.

    Raises:
        ResourceMissingFieldError: If the DataProtectionApplication CRD, the DataProtectionApplication,
            or the velero Deployment cannot be read.
        TimeoutExpiredError: If Velero does not report the expected polling arg and ready replicas
            within 5 minutes.
    """
    dpa = DataProtectionApplication(
        name=DPA_NAME,
        namespace=NamespacesNames.ADP_NAMESPACE,
        client=client,
    )
    if not _dpa_crd_defines_csi_snapshot_early_frequent_polling(client=client):
        yield dpa
        return

    original_value = _csi_snapshot_early_frequent_polling_value(dpa=dpa)
    if original_value:
        LOGGER.info(
            f"DataProtectionApplication {dpa.name} in {dpa.namespace} already has "
            f"{_CSI_SNAPSHOT_EARLY_FREQUENT_POLLING_FIELD} enabled"
        )
        yield dpa
        return

    LOGGER.info(
        f"Enabling {_CSI_SNAPSHOT_EARLY_FREQUENT_POLLING_FIELD} on "
        f"DataProtectionApplication {dpa.name} in {dpa.namespace}"
    )
    enable_patch = _csi_snapshot_early_frequent_polling_patch(dpa=dpa, enabled=True)
    restore_patch = _csi_snapshot_early_frequent_polling_patch(dpa=dpa, enabled=original_value)
    # Pass the restore patch explicitly. ResourceEditor's generated backup sets a
    # missing parent key to null, which would remove spec.configuration on restore.
    try:
        with ResourceEditor(patches={dpa: enable_patch}, user_backups={dpa: restore_patch}):
            _wait_for_velero_polling_arg(client=client, enabled=True)
            yield dpa
    finally:
        _wait_for_velero_polling_arg(client=client, enabled=False)

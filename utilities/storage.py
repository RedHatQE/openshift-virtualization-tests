import logging
import math
import os
import shlex
from contextlib import contextmanager

import kubernetes
import requests
from kubernetes.dynamic import DynamicClient
from kubernetes.dynamic.exceptions import NotFoundError
from ocp_resources.cdi import CDI
from ocp_resources.cdi_config import CDIConfig
from ocp_resources.data_source import DataSource
from ocp_resources.datavolume import DataVolume
from ocp_resources.hostpath_provisioner import HostPathProvisioner
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_resources.pod import Pod
from ocp_resources.resource import NamespacedResource, ResourceEditor
from ocp_resources.storage_class import StorageClass
from ocp_resources.storage_profile import StorageProfile
from ocp_resources.virtual_machine_snapshot import VirtualMachineSnapshot
from ocp_resources.volume_snapshot import VolumeSnapshot
from ocp_resources.volume_snapshot_class import VolumeSnapshotClass
from pyhelper_utils.shell import run_ssh_commands
from pytest_testconfig import config as py_config
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

import utilities.infra
import utilities.virt as virt_util
from utilities import console
from utilities.constants import (
    CDI_LABEL,
    HOTPLUG_DISK_SERIAL,
    HPP_POOL,
    OS_FLAVOR_WINDOWS,
    POD_CONTAINER_SPEC,
    TIMEOUT_1MIN,
    TIMEOUT_1SEC,
    TIMEOUT_2MIN,
    TIMEOUT_3MIN,
    TIMEOUT_5MIN,
    TIMEOUT_5SEC,
    TIMEOUT_6MIN,
    TIMEOUT_10MIN,
    TIMEOUT_10SEC,
    TIMEOUT_20SEC,
    TIMEOUT_30MIN,
    TIMEOUT_30SEC,
    TIMEOUT_60MIN,
    Images,
)
from utilities.exceptions import UrlNotFoundError

HOTPLUG_VOLUME = "hotplugVolume"
DATA_IMPORT_CRON_SUFFIX = "-image-cron"
RESOURCE_MANAGED_BY_DATA_IMPORT_CRON_LABEL = f"{NamespacedResource.ApiGroup.CDI_KUBEVIRT_IO}/dataImportCron"
HOSTPATH_CSI = "hostpath-csi"
HPP_CSI = "hpp-csi"


LOGGER = logging.getLogger(__name__)


def create_dummy_first_consumer_pod(volume_mode=DataVolume.VolumeMode.FILE, dv=None, pvc=None):
    """
    Create a dummy pod that will become the PVCs first consumer
    Triggers start of CDI worker pod

    To consume PVCs that are not backed by DVs, just pass in pvc param
    Otherwise, it is needed to pass in dv
    """

    if not (pvc or dv):
        raise ValueError("Exactly one of the args: (dv,pvc) must be passed")
    if dv:
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_20SEC,
            sleep=TIMEOUT_1SEC,
            func=lambda: (
                dv.instance.get("status").get("phase")
                in [
                    dv.Status.PENDING_POPULATION,
                    dv.Status.WAIT_FOR_FIRST_CONSUMER,
                ]
            ),
        ):
            if sample:
                break
    pvc = pvc or dv.pvc
    with PodWithPVC(
        namespace=pvc.namespace,
        name=f"first-consumer-{pvc.name}",
        pvc_name=pvc.name,
        containers=get_containers_for_pods_with_pvc(volume_mode=volume_mode, pvc_name=pvc.name),
    ) as pod:
        LOGGER.info(
            f"Created dummy pod {pod.name} to be the first consumer of the PVC, "
            "this triggers the start of CDI worker pods in case the PVC is backed by DV"
        )


@contextmanager
def create_dv(
    dv_name,
    namespace,
    storage_class,
    volume_mode=None,
    url=None,
    source="http",
    content_type=DataVolume.ContentType.KUBEVIRT,
    size="5Gi",
    secret=None,
    cert_configmap=None,
    hostpath_node=None,
    access_modes=None,
    client=None,
    source_pvc=None,
    source_namespace=None,
    multus_annotation=None,
    teardown=True,
    consume_wffc=True,
    bind_immediate=None,
    preallocation=None,
    api_name="storage",
):
    artifactory_secret = None
    cert_created = None
    if source in ("http", "https"):
        if not utilities.infra.url_excluded_from_validation(url):
            # Make sure URL exists
            validate_file_exists_in_url(url=url)
        if not secret:
            secret = utilities.infra.get_artifactory_secret(namespace=namespace)
            artifactory_secret = secret
        if not cert_configmap:
            cert_created = utilities.infra.get_artifactory_config_map(namespace=namespace)
            cert_configmap = cert_created.name

    with DataVolume(
        source=source,
        name=dv_name,
        namespace=namespace,
        url=url,
        content_type=content_type,
        size=size,
        storage_class=storage_class,
        cert_configmap=cert_configmap,
        volume_mode=volume_mode,
        hostpath_node=hostpath_node,
        access_modes=access_modes,
        secret=secret,
        client=client,
        source_pvc=source_pvc,
        source_namespace=source_namespace,
        bind_immediate_annotation=bind_immediate,
        multus_annotation=multus_annotation,
        teardown=teardown,
        preallocation=preallocation,
        api_name=api_name,
    ) as dv:
        if sc_volume_binding_mode_is_wffc(sc=storage_class) and consume_wffc:
            create_dummy_first_consumer_pod(dv=dv)
        yield dv
    utilities.infra.cleanup_artifactory_secret_and_config_map(
        artifactory_secret=artifactory_secret, artifactory_config_map=cert_created
    )


def data_volume(
    namespace,
    storage_class_matrix=None,
    storage_class=None,
    schedulable_nodes=None,
    request=None,
    os_matrix=None,
    check_dv_exists=False,
    admin_client=None,
    bind_immediate=None,
):
    """
    DV creation using create_dv.

    Args:
        namespace (:obj: `Namespace`): namespace resource
        storage_class_matrix (dict): Contains current storage_class_matrix attributes
        storage_class (str): Storage class name
        schedulable_nodes (list): List of schedulable nodes objects
        os_matrix (dict): Contains current os_matrix attributes
        check_dv_exists (bool): Skip DV creation if DV exists. Used for golden images. IF the DV exists in golden images
        namespace, it can be used for cloning.
        bind_immediate (bool): if True, cdi.kubevirt.io/storage.bind.immediate.requested annotation

    Yields:
        obj `DataVolume`: DV resource

    """
    if not storage_class_matrix:
        storage_class_matrix = get_storage_class_dict_from_matrix(storage_class=storage_class)

    storage_class = [*storage_class_matrix][0]
    # Save with a different name to avoid confusing.

    params_dict = request.param if request else {}

    # Set DV attributes
    # DV name is the only mandatory value
    # Values can be extracted from request.param or from
    # rhel_os_matrix or windows_os_matrix (passed as os_matrix)
    source = params_dict.get("source", "http")
    consume_wffc = params_dict.get("consume_wffc", True)

    # DV namespace may not be in the same namespace as the originating test
    # If a namespace is passes in request.param, use it instead of the test's namespace
    dv_namespace = params_dict.get("dv_namespace", namespace.name)

    if os_matrix:
        os_matrix_key = [*os_matrix][0]
        image = os_matrix[os_matrix_key]["image_path"]
        dv_name = os_matrix_key
        dv_size = os_matrix[os_matrix_key].get("dv_size")
    else:
        image = params_dict.get("image", "")
        dv_name = params_dict.get("dv_name").replace(".", "-").lower()
        dv_size = params_dict.get("dv_size")

    # Don't need URL for DVs that are not http
    url = f"{get_test_artifact_server_url()}{image}" if source == "http" else None

    is_golden_image = False
    # For golden images; images are created once per module in
    # golden images namepace and cloned when using common templates.
    # If the DV exists, yield the DV else create a new one in
    # golden images namespace
    # If SC is HPP, cdi.kubevirt.io/storage.bind.immediate.requested annotation
    # should be used to avoid wffc
    if check_dv_exists:
        consume_wffc = False
        bind_immediate = True
        is_golden_image = True
        try:
            golden_image = list(DataVolume.get(dyn_client=admin_client, name=dv_name, namespace=dv_namespace))
            yield golden_image[0]
        except NotFoundError:
            LOGGER.warning(f"Golden image {dv_name} not found; DV will be created.")

    # In hpp, volume must reside on the same worker as the VM
    # This is not needed for golden image PVC
    hostpath_node = (
        schedulable_nodes[0].name
        if (sc_is_hpp_with_immediate_volume_binding(sc=storage_class) and not is_golden_image)
        else None
    )

    dv_kwargs = {
        "dv_name": dv_name,
        "namespace": dv_namespace,
        "source": source,
        "size": dv_size,
        "storage_class": params_dict.get("storage_class", storage_class),
        "access_modes": params_dict.get("access_modes"),
        "volume_mode": params_dict.get("volume_mode"),
        "content_type": DataVolume.ContentType.KUBEVIRT,
        "hostpath_node": hostpath_node,
        "consume_wffc": consume_wffc,
        "bind_immediate": bind_immediate,
        "preallocation": params_dict.get("preallocation", None),
        "url": url,
    }
    if params_dict.get("cert_configmap"):
        dv_kwargs["cert_configmap"] = params_dict.get("cert_configmap")
    # Create dv
    with create_dv(**{k: v for k, v in dv_kwargs.items() if v is not None}) as dv:
        if params_dict.get("wait", True):
            if source == "upload":
                dv.wait_for_status(status=DataVolume.Status.UPLOAD_READY, timeout=TIMEOUT_3MIN)
            else:
                if (
                    not consume_wffc
                    and sc_volume_binding_mode_is_wffc(sc=storage_class)
                    and check_cdi_feature_gate_enabled(feature="HonorWaitForFirstConsumer")
                    and not bind_immediate
                ):
                    # In the case of WFFC Storage Class && caller asking to NOT consume && WFFC feature gate enabled
                    # and bind_immediate is False (i.e bind_immediate annotation will be added, import will not wait
                    # first consumer)
                    # We will hand out a DV that has nothing on it, just waiting to be further consumed by kubevirt
                    # It will be in a status 'PendingPopulation' (for csi storage)
                    dv.wait_for_status(status="PendingPopulation", timeout=TIMEOUT_10SEC)
                else:
                    dv.wait_for_dv_success(timeout=TIMEOUT_60MIN if OS_FLAVOR_WINDOWS in image else TIMEOUT_30MIN)
        yield dv


def get_downloaded_artifact(remote_name, local_name):
    """
    Download image or artifact to local tmpdir path
    """
    artifactory_header = utilities.infra.get_artifactory_header()
    url = f"{get_test_artifact_server_url()}{remote_name}"
    resp = requests.head(
        url,
        headers=artifactory_header,
        verify=False,
        allow_redirects=True,
    )
    assert resp.status_code == requests.codes.ok, f"Unable to connect to {url} with error: {resp}."
    LOGGER.info(f"Download {url} to {local_name}")
    with requests.get(url, headers=artifactory_header, verify=False, stream=True) as created_request:
        created_request.raise_for_status()
        with open(local_name, "wb") as file_downloaded:
            for chunk in created_request.iter_content(chunk_size=8192):
                file_downloaded.write(chunk)
    try:
        assert os.path.isfile(local_name)
    except FileNotFoundError as err:
        LOGGER.error(err)
        raise


def get_storage_class_dict_from_matrix(storage_class):
    storages = py_config["system_storage_class_matrix"]
    matching_storage_classes = [sc for sc in storages if [*sc][0] == storage_class]
    if not matching_storage_classes:
        raise ValueError(f"{storage_class} not found in {storages}")
    return matching_storage_classes[0]


def sc_is_hpp_with_immediate_volume_binding(sc):
    return (
        sc == "hostpath-provisioner"
        and StorageClass(name=sc).instance["volumeBindingMode"] == StorageClass.VolumeBindingMode.Immediate
    )


def sc_volume_binding_mode_is_wffc(sc):
    return StorageClass(name=sc).instance["volumeBindingMode"] == StorageClass.VolumeBindingMode.WaitForFirstConsumer


def check_cdi_feature_gate_enabled(feature):
    return feature in CDIConfig(name="config").instance.to_dict().get("spec", {}).get("featureGates", [])


@contextmanager
def virtctl_volume(
    action,
    namespace,
    vm_name,
    volume_name,
    serial=None,
    persist=None,
):
    operation = {"add": "addvolume"}
    volume_operation = operation[action]
    command = [
        f"{volume_operation}",
        f"{vm_name}",
        f"--volume-name={volume_name}",
    ]
    if serial:
        command.append(f"--serial={serial}")
    if persist:
        command.append("--persist")

    yield utilities.infra.run_virtctl_command(command=command, namespace=namespace)
    # clean up:
    command = [
        "removevolume",
        f"{vm_name}",
        f"--volume-name={volume_name}",
    ]
    utilities.infra.run_virtctl_command(command=command, namespace=namespace)


def virtctl_memory_dump(
    namespace,
    action,
    vm_name,
    claim_name=None,
    storage_class=None,
    create_claim=None,
):
    """
    Dump the memory of a running VM to a PVC.

    Args:
        namespace (:obj: `Namespace`): namespace resource
        action (str): get - trigger memory dump; remove - disassociation of the memory dump pvc
        vm_name (str): virtual machine name
        claim_name (str): PVC name to contain the memory dump
        storage_class (str): Storage class for the memory dump PVC
        create_claim (bool): If true, create new PVC that will contain memory dump
    """
    command = [
        "memory-dump",
        action,
        vm_name,
    ]
    if claim_name:
        command.append(f"--claim-name={claim_name}")
    if create_claim:
        command.append("--create-claim")
    if storage_class:
        command.append(f"--storage-class={storage_class}")

    return utilities.infra.run_virtctl_command(command=command, namespace=namespace)


@contextmanager
def virtctl_upload_dv(
    namespace,
    name,
    image_path,
    size,
    pvc=False,
    storage_class=None,
    volume_mode=None,
    access_mode=None,
    uploadproxy_url=None,
    wait_secs=None,
    insecure=False,
    no_create=False,
    consume_wffc=True,
    cleanup=True,
):
    command = [
        "image-upload",
        f"{'dv' if not pvc else pvc}",
        f"{name}",
        f"--image-path={image_path}",
        f"--size={size}",
    ]
    resource_to_cleanup = (
        PersistentVolumeClaim(namespace=namespace, name=name) if pvc else DataVolume(namespace=namespace, name=name)
    )
    if pvc:
        command[1] = "pvc"
    if storage_class:
        if not (
            volume_mode and access_mode
        ):  # In case either one of them is missing, must fetch missing mode/s from matrix
            storage_class_dict = get_storage_class_dict_from_matrix(storage_class=storage_class)
            storage_class = [*storage_class_dict][0]
        # There is still an option that one mode was passed by caller, will use the passed value
        volume_mode = volume_mode or storage_class_dict[storage_class]["volume_mode"]
        access_mode = access_mode or storage_class_dict[storage_class]["access_mode"]
        command.append(f"--storage-class={storage_class}")
    if access_mode:
        command.append(f"--access-mode={access_mode}")
    if uploadproxy_url:
        command.append(f"--uploadproxy-url={uploadproxy_url}")
    if wait_secs:
        command.append(f"--wait-secs={wait_secs}")
    if insecure:
        command.append("--insecure")
    if volume_mode:
        command.append(f"--volume-mode={volume_mode.lower()}")
    if no_create:
        command.append("--no-create")
    if sc_volume_binding_mode_is_wffc(sc=storage_class) and consume_wffc and not no_create:
        command.append("--force-bind")

    yield utilities.infra.run_virtctl_command(command=command, namespace=namespace)

    if cleanup:
        resource_to_cleanup.clean_up()


def check_upload_virtctl_result(
    result,
    expected_success=True,
    expected_output="Processing completed successfully",
    assert_message=None,
):
    LOGGER.info("Check status and output of virtctl")
    status, out, err = result
    assert_message = assert_message or err
    if expected_success:
        assert status, assert_message
        assert expected_output in out, out
    else:
        assert not status, assert_message
        assert expected_output in err, err


class ErrorMsg:
    """
    error messages that might show in pod containers
    """

    EXIT_STATUS_2 = (
        "Unable to process data: "
        "Unable to transfer source data to target directory: unable to untar files from endpoint: exit status 2"
    )
    CERTIFICATE_SIGNED_UNKNOWN_AUTHORITY = "certificate signed by unknown authority"
    DISK_IMAGE_IN_CONTAINER_NOT_FOUND = (
        "Unable to process data: Unable to transfer source data to scratch space: "
        "Failed to read registry image: Failed to find VM disk image file in the container image"
    )
    DATA_VOLUME_TOO_SMALL = "DataVolume too small to contain image"
    LARGER_PVC_REQUIRED = "A larger PVC is required"
    LARGER_PVC_REQUIRED_CLONE = "target resources requests storage size is smaller than the source"
    INVALID_FORMAT_FOR_QCOW = "Unable to process data: Invalid format qcow for image "
    COULD_NOT_OPEN_SIZE_TOO_BIG = "Unable to process data: qemu-img: Could not open '/data/disk.img': L1 size too big"
    REQUESTED_RANGE_NOT_SATISFIABLE = (
        "Unable to process data: qemu-img: curl: The requested URL returned error: 416 Requested Range Not Satisfiable"
    )
    CANNOT_CREATE_RESOURCE = r".*cannot create resource.*|.*has insufficient permissions in clone source namespace.*"
    CANNOT_DELETE_RESOURCE = r".*cannot delete resource.*|.*has insufficient permissions in clone source namespace.*"
    ASSUMING_PVC_SUCCESSFULLY_POPULATED = "PVC {pvc_name} already successfully {populated}"


def get_containers_for_pods_with_pvc(volume_mode, pvc_name):
    if volume_mode == DataVolume.VolumeMode.BLOCK:
        volume_path = {"volumeDevices": [{"devicePath": "/pvc/disk.img", "name": pvc_name}]}
    else:
        volume_path = {"volumeMounts": [{"mountPath": "/pvc", "name": pvc_name}]}
    return [{**POD_CONTAINER_SPEC, **volume_path}]


class PodWithPVC(Pod):
    def __init__(self, name, namespace, pvc_name, containers, teardown=True):
        super().__init__(name=name, namespace=namespace, containers=containers, teardown=teardown)
        self._pvc_name = pvc_name

    def to_dict(self):
        super().to_dict()
        self.res.update({
            "spec": {
                "containers": self.containers,
                "volumes": [
                    {
                        "name": self._pvc_name,
                        "persistentVolumeClaim": {"claimName": self._pvc_name},
                    }
                ],
            }
        })

    def delete(self, wait=False, timeout=TIMEOUT_3MIN, body=None):
        return super().delete(
            wait=wait,
            timeout=timeout,
            body=kubernetes.client.V1DeleteOptions(grace_period_seconds=0),
        )


def data_volume_template_dict(
    target_dv_name,
    target_dv_namespace,
    source_dv,
    volume_mode=None,
    size=None,
    storage_class=None,
):
    source_dv_pvc_spec = source_dv.pvc.instance.spec
    dv = DataVolume(
        name=target_dv_name,
        namespace=target_dv_namespace,
        source="pvc",
        storage_class=storage_class or source_dv_pvc_spec.storageClassName,
        volume_mode=volume_mode or source_dv_pvc_spec.volumeMode,
        size=size or source_dv.size,
        source_pvc=source_dv.name,
        source_namespace=source_dv.namespace,
        api_name=source_dv.api_name,
    )
    dv.to_dict()
    return dv.res


def data_volume_template_with_source_ref_dict(data_source, storage_class=None):
    source_dict = data_source.source.instance.to_dict()
    source_spec_dict = source_dict["spec"]
    dv = DataVolume(
        name=data_source.name,
        namespace=data_source.namespace,
        size=source_spec_dict.get("resources", {}).get("requests", {}).get("storage")
        or source_dict.get("status", {}).get("restoreSize"),
        storage_class=storage_class or source_spec_dict.get("storageClassName"),
        api_name="storage",
        source_ref={
            "kind": data_source.kind,
            "name": data_source.name,
            "namespace": data_source.namespace,
        },
    )
    dv.to_dict()
    # dataVolumeTemplate is not required to have the namespace explicitly set
    dv.res["metadata"].pop("namespace", None)
    return dv.res


def get_test_artifact_server_url(schema="https"):
    """
    Verify https server server connectivity (regardless of schema).
    Return the requested "registry" or "https" server url.

    Args:
        schema (str): registry or https.

    Returns:
        str: Server URL.

    Raises:
        URLError: If server is not accessible.
    """
    artifactory_connection_url = py_config["servers"]["https_server"]
    LOGGER.info(f"Testing connectivity to {artifactory_connection_url} {schema.upper()} server")
    sample = None
    try:
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_1MIN,
            sleep=TIMEOUT_5SEC,
            func=lambda: requests.get(
                artifactory_connection_url, headers=utilities.infra.get_artifactory_header(), verify=False
            ),
        ):
            if sample.status_code == requests.codes.ok:
                return py_config["servers"][f"{schema}_server"]
    except TimeoutExpiredError:
        LOGGER.error(
            f"Unable to connect to test image server: {artifactory_connection_url} "
            f"{schema.upper()}, with error code: {sample.status_code}, error: {sample.text}"
        )
        raise


def overhead_size_for_dv(image_size, overhead_value):
    """
    Calculate the size of the dv to include overhead and rounds up

    DV creation can be with a fraction only if the corresponding  mebibyte is an integer
    """
    dv_size = image_size / (1 - overhead_value) * 1024
    return f"{math.ceil(dv_size)}Mi"


def cdi_feature_gate_list_with_added_feature(feature):
    return [
        *CDIConfig(name="config").instance.to_dict().get("spec", {}).get("featureGates", []),
        feature,
    ]


def wait_for_default_sc_in_cdiconfig(cdi_config, sc):
    """
    Wait for the default storage class to propagate to CDIConfig as the storage class for scratch space
    """
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_20SEC,
        sleep=TIMEOUT_1SEC,
        func=lambda: cdi_config.scratch_space_storage_class_from_status == sc,
    )
    for sample in samples:
        if sample:
            return


def get_hyperconverged_cdi(admin_client):
    for cdi in CDI.get(
        dyn_client=admin_client,
        name="cdi-kubevirt-hyperconverged",
    ):
        return cdi


def write_file(vm, filename, content, stop_vm=True):
    """Start VM if not running, write a file in the VM and stop the VM"""
    if not vm.ready:
        vm.start(wait=True)
    with console.Console(vm=vm) as vm_console:
        vm_console.sendline(f"echo '{content}' >> {filename}")
    if stop_vm:
        vm.stop(wait=True)


def run_command_on_cirros_vm_and_check_output(vm, command, expected_result):
    with console.Console(vm=vm) as vm_console:
        vm_console.sendline(command)
        vm_console.expect(expected_result, timeout=20)


def assert_disk_serial(vm, command=shlex.split("sudo ls /dev/disk/by-id")):
    assert HOTPLUG_DISK_SERIAL in run_ssh_commands(host=vm.ssh_exec, commands=command)[0], (
        f"hotplug disk serial id {HOTPLUG_DISK_SERIAL} is not in VM"
    )


def assert_hotplugvolume_nonexist_optional_restart(vm, restart=False):
    if restart:
        virt_util.restart_vm_wait_for_running_vm(vm=vm)
    volume_status = vm.vmi.instance.status.volumeStatus[0]
    assert HOTPLUG_VOLUME not in volume_status, (
        f"{HOTPLUG_VOLUME} in {volume_status}, hotplug disk should become a regular disk for VM after restart"
    )


def wait_for_vm_volume_ready(vm):
    sampler = TimeoutSampler(
        wait_timeout=TIMEOUT_2MIN,
        sleep=TIMEOUT_1SEC,
        func=lambda: vm.vmi.instance,
    )
    for sample in sampler:
        if sample.status.volumeStatus[0]["reason"] == "VolumeReady":
            return


def generate_data_source_dict(dv):
    return {"pvc": {"name": dv.name, "namespace": dv.namespace}}


def create_or_update_data_source(admin_client, dv):
    """
    Create or updates a data source referencing a provided DV.

    As dataSources are automatically created with CNV deployment for golden images support, they can be re-used.
    If a dataSource already exists (with the same name as the target dv), it will be updated.
    Otherwise a new dataSource will be created.

    Args:
        admin_client (client)
        dv (DataVolume): which will be referenced in the data source

    Yields:
        DataSource object
    """
    target_name = dv.name
    target_namespaces = dv.namespace
    try:
        for data_source in DataSource.get(dyn_client=admin_client, name=target_name, namespace=target_namespaces):
            LOGGER.info(f"Updating existing dataSource {data_source.name}")
            with ResourceEditor(patches={data_source: generate_data_source_dict(dv=dv)}):
                yield data_source
    except NotFoundError:
        with DataSource(
            name=target_name,
            namespace=target_namespaces,
            client=admin_client,
            source=generate_data_source_dict(dv=dv),
        ) as data_source:
            yield data_source


class HppCsiStorageClass(StorageClass):
    class Name:
        # Without explicit storage pool, used with the Legacy HPP CR
        HOSTPATH_CSI_LEGACY = f"{HOSTPATH_CSI}-legacy"
        HOSTPATH_CSI_BASIC = f"{HOSTPATH_CSI}-basic"  # Part of fresh deployment
        HOSTPATH_CSI_PVC_BLOCK = f"{HOSTPATH_CSI}-pvc-block"  # Part of fresh deployment
        HOSTPATH_CSI_PVC_TEMPLATE_OCS_BLOCK = f"{HOSTPATH_CSI}-pvc-template-ocs-block"
        HOSTPATH_CSI_PVC_TEMPLATE_OCS_FS = f"{HOSTPATH_CSI}-pvc-template-ocs-fs"
        HOSTPATH_CSI_PVC_TEMPLATE_LSO = f"{HOSTPATH_CSI}-pvc-template-lso"

    class StoragePool:
        HOSTPATH_CSI_BASIC = f"{HPP_CSI}-local-basic"
        HOSTPATH_CSI_PVC_BLOCK = f"{HPP_CSI}-pvc-block"
        HOSTPATH_CSI_PVC_TEMPLATE_OCS_BLOCK = f"{HPP_CSI}-pvc-template-ocs-block"
        HOSTPATH_CSI_PVC_TEMPLATE_OCS_FS = f"{HPP_CSI}-pvc-template-ocs-fs"
        HOSTPATH_CSI_PVC_TEMPLATE_LSO = f"{HPP_CSI}-pvc-template-lso"

    def __init__(self, name, storage_pool=None, teardown=True):
        super().__init__(
            name=name,
            teardown=teardown,
            provisioner=StorageClass.Provisioner.HOSTPATH_CSI,
            reclaim_policy=StorageClass.ReclaimPolicy.DELETE,
            volume_binding_mode=StorageClass.VolumeBindingMode.WaitForFirstConsumer,
        )
        self._storage_pool = storage_pool

    def to_dict(self):
        super().to_dict()
        if self._storage_pool:
            self.res.update({
                "parameters": {"storagePool": self._storage_pool},
            })


def get_default_storage_class():
    storage_classes = list(StorageClass.get())
    for annotation in [StorageClass.Annotations.IS_DEFAULT_VIRT_CLASS, StorageClass.Annotations.IS_DEFAULT_CLASS]:
        for sc in storage_classes:
            if sc.instance.metadata.get("annotations", {}).get(annotation) == "true":
                return sc
    raise ValueError("No default storage class defined")


def is_snapshot_supported_by_sc(sc_name, client):
    sc_instance = StorageClass(client=client, name=sc_name).instance
    for vsc in VolumeSnapshotClass.get(dyn_client=client):
        if vsc.instance.get("driver") == sc_instance.get("provisioner"):
            return True
    return False


def create_cirros_dv_for_snapshot_dict(name, namespace, storage_class, artifactory_secret, artifactory_config_map):
    dv = DataVolume(
        api_name="storage",
        name=f"dv-{name}",
        namespace=namespace,
        source="http",
        url=utilities.infra.get_http_image_url(image_directory=Images.Cirros.DIR, image_name=Images.Cirros.QCOW2_IMG),
        storage_class=storage_class,
        size=Images.Cirros.DEFAULT_DV_SIZE,
        secret=artifactory_secret,
        cert_configmap=artifactory_config_map.name,
    )
    dv.to_dict()
    return dv.res


def check_disk_count_in_vm(vm):
    LOGGER.info("Check disk count.")
    out = run_ssh_commands(
        host=vm.ssh_exec,
        commands=[shlex.split("lsblk | grep disk | grep -v SWAP| wc -l")],
    )[0].strip()
    assert out == str(len(vm.instance.spec.template.spec.domain.devices.disks)), (
        "Failed to verify actual disk count against VMI"
    )


def add_dv_to_vm(vm, dv_name=None, template_dv=None):
    """
    Add another DV to a VM

    Can also be used to add a dataVolumeTemplate DV, just pass in template_dv param
    """
    if not (dv_name or template_dv):
        raise ValueError("Either a dv_name (of an existing DV) or template_dv (dataVolumeTemplate spec) must be passed")
    vm_instance = vm.instance.to_dict()
    template_spec = vm_instance["spec"]["template"]["spec"]
    dv_name = dv_name or template_dv["metadata"]["name"]
    patch = {
        "spec": {
            "template": {
                "spec": {
                    "domain": {
                        "devices": {
                            "disks": [
                                *template_spec["domain"]["devices"]["disks"],
                                {"disk": {"bus": "virtio"}, "name": dv_name},
                            ]
                        }
                    },
                    "volumes": [
                        *template_spec["volumes"],
                        {"name": dv_name, "dataVolume": {"name": dv_name}},
                    ],
                },
            },
        }
    }
    if template_dv:
        patch["spec"]["dataVolumeTemplates"] = [
            *vm_instance["spec"].setdefault("dataVolumeTemplates", []),
            template_dv,
        ]
    ResourceEditor(patches={vm: patch}).update()


def create_hpp_storage_class(
    storage_class_name,
):
    storage_class = HppCsiStorageClass(
        name=storage_class_name,
    )
    storage_class.deploy()


class HPPWithStoragePool(HostPathProvisioner):
    def __init__(self, name, backend_storage_class_name, volume_size, teardown=False):
        super().__init__(name=name, teardown=teardown)
        self.backend_storage_class_name = backend_storage_class_name
        self.volume_size = volume_size

    def to_dict(self):
        super().to_dict()
        self.res.update({
            "spec": {
                "imagePullPolicy": "IfNotPresent",
                "storagePools": [
                    {
                        "name": HppCsiStorageClass.StoragePool.HOSTPATH_CSI_BASIC,
                        "path": f"/var/{HppCsiStorageClass.StoragePool.HOSTPATH_CSI_BASIC}",
                    },
                    {
                        "name": HppCsiStorageClass.StoragePool.HOSTPATH_CSI_PVC_BLOCK,
                        "pvcTemplate": {
                            "volumeMode": "Block",
                            "storageClassName": self.backend_storage_class_name,
                            "accessModes": ["ReadWriteOnce"],
                            "resources": {
                                "requests": {"storage": self.volume_size},
                            },
                        },
                        "path": f"/var/{HppCsiStorageClass.StoragePool.HOSTPATH_CSI_PVC_BLOCK}",
                    },
                ],
                "workload": {
                    "nodeSelector": {"kubernetes.io/os": "linux"},
                },
            }
        })


def wait_for_hpp_pool_pods_to_be_running(client, schedulable_nodes):
    LOGGER.info(f"Wait for {HPP_POOL} pods to be Running")
    for hpp_pool_pods in wait_for_hpp_pods(client=client, pod_prefix=HPP_POOL):
        if len(hpp_pool_pods) == len(schedulable_nodes):
            for pod in hpp_pool_pods:
                pod.wait_for_status(status=pod.Status.RUNNING, timeout=TIMEOUT_2MIN)
            break


def verify_hpp_pool_pvcs_are_bound(schedulable_nodes, hco_namespace):
    LOGGER.info(f"Wait for {HPP_POOL} PVCs to be Bound")
    pvcs = utilities.infra.get_resources_by_name_prefix(
        prefix=HPP_POOL,
        namespace=hco_namespace.name,
        api_resource_name=PersistentVolumeClaim,
    )
    num_of_pvcs = len(pvcs)
    num_of_schedulable_nodes = len(schedulable_nodes)
    assert num_of_pvcs == num_of_schedulable_nodes, (
        f"There are {num_of_pvcs} {HPP_POOL} PVCs, but expected to be {num_of_schedulable_nodes}."
        f"Existing PVC: {[pvc.name for pvc in pvcs]}"
    )
    for pvc in pvcs:
        pvc.wait_for_status(status=pvc.Status.BOUND, timeout=TIMEOUT_5MIN)


def wait_for_hpp_pods(client, pod_prefix):
    return TimeoutSampler(
        wait_timeout=TIMEOUT_2MIN,
        sleep=3,
        func=utilities.infra.get_pod_by_name_prefix,
        dyn_client=client,
        namespace=py_config["hco_namespace"],
        pod_prefix=f"{pod_prefix}-",
        get_all=True,
    )


def verify_hpp_pool_health(admin_client, schedulable_nodes, hco_namespace):
    wait_for_hpp_pool_pods_to_be_running(client=admin_client, schedulable_nodes=schedulable_nodes)
    # Check there are as many 'hpp-pool-' PVCs as schedulable_nodes, and they are Bound
    verify_hpp_pool_pvcs_are_bound(schedulable_nodes=schedulable_nodes, hco_namespace=hco_namespace)


def wait_for_cdi_worker_pod(pod_name, storage_ns_name):
    try:
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_30SEC,
            sleep=TIMEOUT_1SEC,
            func=lambda: list(
                Pod.get(
                    namespace=storage_ns_name,
                    label_selector=CDI_LABEL,
                )
            ),
        ):
            if sample:
                pods = [pod for pod in sample if pod_name in pod.name]
                if pods:
                    return pods[0]
    except TimeoutExpiredError:
        LOGGER.error(f"Pod: {pod_name} with label: {CDI_LABEL} not found in namespace: {storage_ns_name}")
        raise


def get_storage_class_with_specified_volume_mode(volume_mode, sc_names):
    sc_with_volume_mode = f"Storage class with volume mode '{volume_mode}'"
    for storage_class_name in sc_names:
        for claim_property_set in StorageProfile(name=storage_class_name).instance.status["claimPropertySets"]:
            if claim_property_set["volumeMode"] == volume_mode:
                LOGGER.info(f"{sc_with_volume_mode}: '{storage_class_name}'")
                return storage_class_name
    LOGGER.error(f"No {sc_with_volume_mode} among {sc_names}")


@contextmanager
def create_vm_from_dv(
    dv,
    vm_name="cirros-vm",
    image=None,
    start=True,
    os_flavor=Images.Cirros.OS_FLAVOR,
    node_selector=None,
    cpu_model=None,
    memory_guest=Images.Cirros.DEFAULT_MEMORY_SIZE,
    wait_for_cloud_init=False,
    wait_for_interfaces=False,
):
    with virt_util.VirtualMachineForTests(
        name=vm_name,
        namespace=dv.namespace,
        data_volume=dv,
        image=image,
        node_selector=node_selector,
        cpu_model=cpu_model,
        memory_guest=memory_guest,
        os_flavor=os_flavor,
    ) as vm:
        if start:
            virt_util.running_vm(
                vm=vm,
                wait_for_interfaces=wait_for_interfaces,
                wait_for_cloud_init=wait_for_cloud_init,
            )
        yield vm


@contextmanager
def update_default_sc(default, storage_class):
    is_default = str(default).lower()
    with ResourceEditor(
        patches={
            storage_class: {
                "metadata": {
                    "annotations": {
                        StorageClass.Annotations.IS_DEFAULT_CLASS: is_default,
                        StorageClass.Annotations.IS_DEFAULT_VIRT_CLASS: is_default,
                    },
                    "name": storage_class.name,
                },
            }
        }
    ):
        yield


def verify_dv_and_pvc_does_not_exist(name, namespace, timeout=TIMEOUT_10MIN):
    dv = DataVolume(namespace=namespace, name=name)
    pvc = PersistentVolumeClaim(namespace=namespace, name=name)

    samples = TimeoutSampler(wait_timeout=timeout, sleep=TIMEOUT_5SEC, func=lambda: dv.exists or pvc.exists)
    try:
        for sample in samples:
            if not sample:
                return
    except TimeoutExpiredError:
        LOGGER.error(f"The PVC and DV {name} should be deleted\n{pvc.instance.get('status', {})}")
        raise


def wait_for_volume_snapshot_ready_to_use(namespace, name):
    ready_to_use_status = "readyToUse"
    LOGGER.info(f"Wait for VolumeSnapshot '{name}' in '{namespace}' to be '{ready_to_use_status}'")
    volume_snapshot = VolumeSnapshot(namespace=namespace, name=name)
    try:
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_5MIN,
            sleep=TIMEOUT_5SEC,
            func=lambda: volume_snapshot.instance.get("status", {}).get(ready_to_use_status) is True,
        ):
            if sample:
                return volume_snapshot
    except TimeoutExpiredError:
        fail_msg = f"failed to reach {ready_to_use_status} status" if volume_snapshot.exists else "failed to create"
        LOGGER.error(f"The volume snapshot {name} {fail_msg}")
        raise


def wait_for_succeeded_dv(namespace, dv_name):
    dv = DataVolume(namespace=namespace, name=dv_name)
    try:
        samples = TimeoutSampler(
            wait_timeout=TIMEOUT_2MIN,
            sleep=TIMEOUT_5SEC,
            func=lambda: dv.exists,
        )
        for sample in samples:
            if sample:
                dv.wait_for_dv_success(timeout=TIMEOUT_6MIN)
                return
    except TimeoutExpiredError:
        fail_msg = f"failed to import successfully\n {dv.instance}" if dv.exists else "does not exist"
        LOGGER.error(f"The DV {dv_name} {fail_msg}")
        raise


def get_data_sources_managed_by_data_import_cron(namespace):
    return list(
        DataSource.get(
            namespace=namespace,
            label_selector=RESOURCE_MANAGED_BY_DATA_IMPORT_CRON_LABEL,
        )
    )


def verify_boot_sources_reimported(admin_client: DynamicClient, namespace: str) -> bool:
    """
    Verify that the boot sources are re-imported while changing a storage class.
    """
    try:
        for data_source in get_data_sources_managed_by_data_import_cron(namespace=namespace):
            LOGGER.info(f"Waiting for DataSource {data_source.name} consistent ready status")
            utilities.infra.wait_for_consistent_resource_conditions(
                dynamic_client=admin_client,
                expected_conditions={DataSource.Condition.READY: DataSource.Condition.Status.TRUE},
                resource_kind=DataSource,
                namespace=namespace,
                total_timeout=TIMEOUT_10MIN,
                consecutive_checks_count=6,
                resource_name=data_source.name,
            )
        return True
    except (TimeoutExpiredError, Exception) as exception:
        fail_message = (
            "Failed to re-import boot sources, exiting the pytest execution"
            if isinstance(exception, TimeoutExpiredError)
            else str(exception)
        )
        LOGGER.error(fail_message)
        return False


@contextmanager
def remove_default_storage_classes(cluster_storage_classes):
    sc_resources = []
    for sc in cluster_storage_classes:
        sc_annotations = sc.instance.metadata.get("annotations", {})
        if (
            sc_annotations.get(StorageClass.Annotations.IS_DEFAULT_VIRT_CLASS) == "true"
            or sc_annotations.get(StorageClass.Annotations.IS_DEFAULT_CLASS) == "true"
        ):
            sc_resources.append(
                ResourceEditor(
                    patches={
                        sc: {
                            "metadata": {
                                "annotations": {
                                    StorageClass.Annotations.IS_DEFAULT_CLASS: "false",
                                    StorageClass.Annotations.IS_DEFAULT_VIRT_CLASS: "false",
                                },
                                "name": sc.name,
                            }
                        }
                    }
                )
            )
    for editor in sc_resources:
        editor.update(backup_resources=True)
    yield
    for editor in sc_resources:
        editor.restore()


@contextmanager
def vm_snapshot(vm, name):
    vm.stop(wait=True)
    with VirtualMachineSnapshot(
        name=name,
        namespace=vm.namespace,
        vm_name=vm.name,
    ) as snapshot:
        snapshot.wait_snapshot_done()
        virt_util.running_vm(vm=vm, wait_for_interfaces=False)
        yield snapshot


def validate_file_exists_in_url(url):
    response = requests.head(url, headers=utilities.infra.get_artifactory_header(), verify=False)
    if response.status_code != 200:
        raise UrlNotFoundError(url_request=response)

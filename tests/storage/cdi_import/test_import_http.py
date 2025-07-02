"""
Import from HTTP server
"""

import logging
import math
import re

import pytest
from bitmath import GiB
from kubernetes.dynamic.exceptions import UnprocessibleEntityError
from ocp_resources.datavolume import DataVolume
from ocp_resources.resource import Resource
from ocp_resources.storage_profile import StorageProfile
from pytest_testconfig import config as py_config
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.os_params import FEDORA_LATEST, RHEL_LATEST
from tests.storage.constants import (
    CIRROS_QCOW2_IMG,
    HTTP,
    HTTPS,
    HTTPS_CONFIG_MAP_NAME,
    INTERNAL_HTTP_CONFIGMAP_NAME,
)
from tests.storage.utils import (
    assert_disk_img,
    assert_num_files_in_pod,
    assert_use_populator,
    create_pod_for_pvc,
    create_vm_and_verify_image_permission,
    create_vm_from_dv,
    get_file_url,
    get_importer_pod,
    wait_for_importer_container_message,
)
from utilities import console
from utilities.constants import (
    OS_FLAVOR_RHEL,
    TIMEOUT_1MIN,
    TIMEOUT_4MIN,
    TIMEOUT_5MIN,
    TIMEOUT_5SEC,
    TIMEOUT_12MIN,
    TIMEOUT_20SEC,
    Images,
)
from utilities.infra import get_node_selector_dict
from utilities.ssp import validate_os_info_vmi_vs_windows_os
from utilities.storage import (
    ErrorMsg,
    PodWithPVC,
    check_disk_count_in_vm,
    create_dummy_first_consumer_pod,
    create_dv,
    get_containers_for_pods_with_pvc,
    get_test_artifact_server_url,
    sc_volume_binding_mode_is_wffc,
)
from utilities.virt import running_vm

pytestmark = [
    pytest.mark.post_upgrade,
]

LOGGER = logging.getLogger(__name__)

ISO_IMG = "Core-current.iso"
TAR_IMG = "archive.tar"
DEFAULT_DV_SIZE = Images.Cirros.DEFAULT_DV_SIZE
SMALL_DV_SIZE = "200Mi"

DV_PARAMS = {
    "file_name": Images.Cdi.QCOW2_IMG,
    "source": HTTPS,
    "configmap_name": INTERNAL_HTTP_CONFIGMAP_NAME,
}

LATEST_WINDOWS_OS_DICT = py_config.get("latest_windows_os_dict", {})


def get_importer_pod_node(importer_pod):
    for sample in TimeoutSampler(
        wait_timeout=TIMEOUT_1MIN,
        sleep=TIMEOUT_5SEC,
        func=lambda: importer_pod.instance.get("spec", {}).get(
            "nodeName",
        ),
    ):
        if sample:
            return sample


def wait_for_pvc_recreate(pvc, pvc_original_timestamp):
    for sample in TimeoutSampler(
        wait_timeout=TIMEOUT_20SEC,
        sleep=1,
        func=lambda: pvc.instance.metadata.creationTimestamp != pvc_original_timestamp,
    ):
        if sample:
            break


def wait_dv_and_get_importer(dv, admin_client):
    dv.wait_for_status(
        status=DataVolume.Status.IMPORT_IN_PROGRESS,
        timeout=TIMEOUT_1MIN,
        stop_status=DataVolume.Status.SUCCEEDED,
    )
    return get_importer_pod(dyn_client=admin_client, namespace=dv.namespace)


@pytest.fixture()
def dv_with_annotation(admin_client, namespace, linux_nad):
    with create_dv(
        dv_name="dv-annotation",
        namespace=namespace.name,
        url=f"{get_test_artifact_server_url()}{FEDORA_LATEST['image_path']}",
        storage_class=py_config["default_storage_class"],
        multus_annotation=linux_nad.name,
    ) as dv:
        return wait_dv_and_get_importer(dv=dv, admin_client=admin_client).instance.metadata.annotations


@pytest.mark.sno
@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_function",
    [
        pytest.param(
            {
                "dv_name": "import-http-dv",
                "source": HTTP,
                "image": CIRROS_QCOW2_IMG,
                "dv_size": DEFAULT_DV_SIZE,
            },
            marks=pytest.mark.polarion("CNV-675"),
        ),
    ],
    indirect=True,
)
def test_delete_pvc_after_successful_import(
    data_volume_multi_storage_scope_function,
):
    pvc = data_volume_multi_storage_scope_function.pvc
    pvc_original_timestamp = pvc.instance.metadata.creationTimestamp
    pvc.delete()
    wait_for_pvc_recreate(pvc=pvc, pvc_original_timestamp=pvc_original_timestamp)
    storage_class = data_volume_multi_storage_scope_function.storage_class
    if sc_volume_binding_mode_is_wffc(sc=storage_class):
        create_dummy_first_consumer_pod(pvc=pvc)
    data_volume_multi_storage_scope_function.wait_for_dv_success()
    with create_pod_for_pvc(
        pvc=data_volume_multi_storage_scope_function.pvc,
        volume_mode=StorageProfile(name=storage_class).instance.status["claimPropertySets"][0]["volumeMode"],
    ) as pod:
        assert_disk_img(pod=pod)


@pytest.mark.sno
@pytest.mark.polarion("CNV-876")
def test_invalid_url(dv_non_exist_url):
    dv_non_exist_url.wait_for_status(
        status=DataVolume.Status.IMPORT_IN_PROGRESS,
        timeout=TIMEOUT_5MIN,
        stop_status=DataVolume.Status.SUCCEEDED,
    )
    dv_non_exist_url.wait_for_condition(
        condition=DataVolume.Condition.Type.READY,
        status=DataVolume.Condition.Status.FALSE,
        timeout=TIMEOUT_5MIN,
    )


@pytest.mark.sno
@pytest.mark.polarion("CNV-674")
def test_empty_url(namespace, storage_class_name_scope_module):
    with pytest.raises(UnprocessibleEntityError):
        with create_dv(
            dv_name=f"cnv-674-{storage_class_name_scope_module}",
            namespace=namespace.name,
            url="",
            size=DEFAULT_DV_SIZE,
            storage_class=storage_class_name_scope_module,
        ):
            pass


@pytest.mark.parametrize(
    "dv_from_http_import",
    [
        pytest.param(
            {
                "dv_name": "cnv-2145",
                "file_name": TAR_IMG,
                "content_type": DataVolume.ContentType.ARCHIVE,
            },
        ),
    ],
    indirect=True,
)
@pytest.mark.sno
@pytest.mark.polarion("CNV-2145")
def test_successful_import_archive(
    skip_block_volumemode_scope_module,
    running_pod_with_dv_pvc,
):
    """
    Skip block volume mode - archive does not support block mode DVs,
    https://github.com/kubevirt/containerized-data-importer/blob/main/doc/supported_operations.md
    """
    assert_num_files_in_pod(pod=running_pod_with_dv_pvc, expected_num_of_files=3)


@pytest.mark.sno
@pytest.mark.gating
@pytest.mark.parametrize(
    "dv_from_http_import",
    [
        pytest.param(
            {
                "dv_name": "cnv-2143",
                "file_name": Images.Cdi.QCOW2_IMG,
            },
            marks=pytest.mark.polarion("CNV-2143"),
        ),
        pytest.param(
            {
                "dv_name": "cnv-377",
                "file_name": ISO_IMG,
            },
            marks=pytest.mark.polarion("CNV-377"),
        ),
    ],
    indirect=True,
)
def test_successful_import_image(
    running_pod_with_dv_pvc,
    dv_from_http_import,
    storage_class_name_scope_module,
    cluster_csi_drivers_names,
):
    assert_disk_img(pod=running_pod_with_dv_pvc)
    assert_use_populator(
        pvc=dv_from_http_import.pvc,
        storage_class=storage_class_name_scope_module,
        cluster_csi_drivers_names=cluster_csi_drivers_names,
    )


@pytest.mark.parametrize(
    "dv_from_http_import",
    [
        pytest.param(
            {
                "dv_name": "cnv-2338",
                "file_name": TAR_IMG,
                "source": HTTPS,
                "content_type": DataVolume.ContentType.ARCHIVE,
                "configmap_name": INTERNAL_HTTP_CONFIGMAP_NAME,
            },
            marks=pytest.mark.polarion("CNV-2338"),
        ),
    ],
    indirect=True,
)
@pytest.mark.sno
def test_successful_import_secure_archive(
    skip_block_volumemode_scope_module, internal_http_configmap, running_pod_with_dv_pvc
):
    """
    Skip block volume mode - archive does not support block mode DVs,
    https://github.com/kubevirt/containerized-data-importer/blob/main/doc/supported_operations.md
    """
    assert_num_files_in_pod(pod=running_pod_with_dv_pvc, expected_num_of_files=3)


@pytest.mark.parametrize(
    "dv_from_http_import",
    [
        pytest.param(
            DV_PARAMS,
            marks=pytest.mark.polarion("CNV-2719"),
        ),
    ],
    indirect=True,
)
@pytest.mark.sno
@pytest.mark.gating
def test_successful_import_secure_image(internal_http_configmap, running_pod_with_dv_pvc):
    assert_disk_img(pod=running_pod_with_dv_pvc)


@pytest.mark.sno
@pytest.mark.parametrize(
    ("content_type", "file_name"),
    [
        pytest.param(
            DataVolume.ContentType.ARCHIVE,
            TAR_IMG,
            marks=(pytest.mark.polarion("CNV-2339")),
        ),
        pytest.param(
            DataVolume.ContentType.KUBEVIRT,
            Images.Cirros.RAW_IMG_XZ,
            marks=(pytest.mark.polarion("CNV-784"), pytest.mark.smoke(), pytest.mark.s390x()),
        ),
    ],
    ids=["import_basic_auth_archive", "import_basic_auth_kubevirt"],
)
def test_successful_import_basic_auth(
    namespace,
    storage_class_matrix__module__,
    storage_class_name_scope_module,
    images_internal_http_server,
    internal_http_secret,
    content_type,
    file_name,
):
    if (
        content_type == DataVolume.ContentType.ARCHIVE
        and storage_class_matrix__module__[storage_class_name_scope_module]["volume_mode"] == "Block"
    ):
        pytest.skip("Skipping test, can't use archives with volumeMode block")
    with create_dv(
        dv_name="import-http-dv",
        namespace=namespace.name,
        url=get_file_url(url=images_internal_http_server["http_auth"], file_name=file_name),
        content_type=content_type,
        size=DEFAULT_DV_SIZE,
        secret=internal_http_secret,
        storage_class=storage_class_name_scope_module,
    ) as dv:
        dv.wait_for_dv_success()
        pvc = dv.pvc
        with PodWithPVC(
            namespace=pvc.namespace,
            name=f"{pvc.name}-pod",
            pvc_name=pvc.name,
            containers=get_containers_for_pods_with_pvc(
                volume_mode=storage_class_matrix__module__[storage_class_name_scope_module]["volume_mode"],
                pvc_name=pvc.name,
            ),
        ) as pod:
            pod.wait_for_status(status=pod.Status.RUNNING)


@pytest.mark.sno
@pytest.mark.parametrize(
    "dv_from_http_import",
    [
        pytest.param(
            {
                "dv_name": "cnv-2144",
                "file_name": Images.Cdi.QCOW2_IMG,
                "content_type": DataVolume.ContentType.ARCHIVE,
            },
            marks=pytest.mark.polarion("CNV-2144"),
        ),
    ],
    indirect=True,
)
def test_wrong_content_type(
    admin_client,
    dv_from_http_import,
):
    wait_for_importer_container_message(
        importer_pod=wait_dv_and_get_importer(
            dv=dv_from_http_import,
            admin_client=admin_client,
        ),
        msg=ErrorMsg.EXIT_STATUS_2,
    )


@pytest.mark.sno
@pytest.mark.parametrize(
    "dv_from_http_import",
    [
        pytest.param(
            {
                "dv_name": "cnv-2220",
                "file_name": Images.Cirros.RAW_IMG_XZ,
                "content_type": DataVolume.ContentType.ARCHIVE,
                "size": SMALL_DV_SIZE,
            },
            marks=pytest.mark.polarion("CNV-2220"),
            id="compressed_xz_archive_content_type",
        ),
        pytest.param(
            {
                "dv_name": "cnv-2710",
                "file_name": Images.Cirros.RAW_IMG_GZ,
                "content_type": DataVolume.ContentType.ARCHIVE,
                "size": SMALL_DV_SIZE,
            },
            marks=pytest.mark.polarion("CNV-2710"),
            id="compressed_gz_archive_content_type",
        ),
    ],
    indirect=True,
)
def test_unpack_compressed(
    admin_client,
    dv_from_http_import,
):
    wait_for_importer_container_message(
        importer_pod=wait_dv_and_get_importer(
            dv=dv_from_http_import,
            admin_client=admin_client,
        ),
        msg=ErrorMsg.EXIT_STATUS_2,
    )


@pytest.mark.parametrize(
    "dv_from_http_import",
    [
        pytest.param(
            DV_PARAMS,
            marks=pytest.mark.polarion("CNV-2811"),
        ),
    ],
    indirect=True,
)
@pytest.mark.sno
def test_certconfigmap(internal_http_configmap, running_pod_with_dv_pvc):
    assert_num_files_in_pod(pod=running_pod_with_dv_pvc, expected_num_of_files=1)


@pytest.mark.sno
@pytest.mark.parametrize(
    ("https_config_map", "dv_from_http_import"),
    [
        pytest.param(
            {"data": "-----BEGIN CERTIFICATE-----"},
            {
                "dv_name": "cnv-2812",
                "file_name": Images.Cdi.QCOW2_IMG,
                "source": HTTPS,
                "configmap_name": HTTPS_CONFIG_MAP_NAME,
            },
            marks=(pytest.mark.polarion("CNV-2812")),
        ),
        pytest.param(
            {"data": None},
            {
                "dv_name": "cnv-2813",
                "file_name": Images.Cdi.QCOW2_IMG,
                "source": HTTPS,
                "configmap_name": HTTPS_CONFIG_MAP_NAME,
            },
            marks=(pytest.mark.polarion("CNV-2813")),
        ),
    ],
    indirect=True,
)
def test_certconfigmap_incorrect_cert(
    admin_client,
    https_config_map,
    dv_from_http_import,
):
    wait_for_importer_container_message(
        importer_pod=wait_dv_and_get_importer(dv=dv_from_http_import, admin_client=admin_client),
        msg=ErrorMsg.CERTIFICATE_SIGNED_UNKNOWN_AUTHORITY,
    )


@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_function",
    [
        pytest.param(
            {
                "dv_name": "cnv-2815",
                "source": HTTP,
                "image": CIRROS_QCOW2_IMG,
                "dv_size": DEFAULT_DV_SIZE,
                "cert_configmap": "wrong_name",
                "wait": False,
            },
            marks=pytest.mark.polarion("CNV-2815"),
        ),
    ],
    indirect=True,
)
@pytest.mark.sno
@pytest.mark.polarion("CNV-2815")
def test_certconfigmap_missing_or_wrong_cm(data_volume_multi_storage_scope_function):
    with pytest.raises(TimeoutExpiredError):
        samples = TimeoutSampler(
            wait_timeout=TIMEOUT_1MIN,
            sleep=10,
            func=lambda: data_volume_multi_storage_scope_function.status != DataVolume.Status.IMPORT_SCHEDULED,
        )
        for sample in samples:
            if sample:
                LOGGER.error(
                    f"DV status is not as expected."
                    f"Expected: {DataVolume.Status.IMPORT_SCHEDULED}. "
                    f"Found: {data_volume_multi_storage_scope_function.status}"
                )


@pytest.mark.sno
@pytest.mark.parametrize(
    "number_of_processes",
    [
        pytest.param(
            1,
            marks=(pytest.mark.polarion("CNV-2151")),
        ),
        pytest.param(
            4,
            marks=(pytest.mark.polarion("CNV-2001")),
        ),
    ],
)
def test_successful_concurrent_blank_disk_import(
    dv_list_created_by_multiprocess,
    vm_list_created_by_multiprocess,
):
    for vm in vm_list_created_by_multiprocess:
        running_vm(vm=vm, wait_for_interfaces=False)
        check_disk_count_in_vm(vm=vm)


@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_function",
    [{"dv_name": "cnv-2004", "source": "blank", "image": "", "dv_size": SMALL_DV_SIZE}],
    indirect=True,
)
@pytest.mark.sno
@pytest.mark.polarion("CNV-2004")
def test_blank_disk_import_validate_status(data_volume_multi_storage_scope_function):
    data_volume_multi_storage_scope_function.wait_for_dv_success(timeout=TIMEOUT_5MIN)


@pytest.mark.sno
@pytest.mark.parametrize(
    ("size", "unit", "dv_name"),
    [
        pytest.param(64, "M", "cnv-1404", marks=(pytest.mark.polarion("CNV-1404"))),
        pytest.param(1, "G", "cnv-6532", marks=(pytest.mark.polarion("CNV-6532"))),
        pytest.param(13, "G", "cnv-6536", marks=(pytest.mark.polarion("CNV-6536"))),
    ],
)
def test_vmi_image_size(
    namespace,
    storage_class_matrix__module__,
    storage_class_name_scope_module,
    images_internal_http_server,
    internal_http_configmap,
    size,
    unit,
    dv_name,
    default_fs_overhead,
):
    m_byte = "M"
    assert size >= 1, "This test support only dv size >= 1"
    with create_dv(
        dv_name=dv_name,
        namespace=namespace.name,
        size=f"{size}{unit}i",
        storage_class=storage_class_name_scope_module,
        url=get_file_url(url=images_internal_http_server[HTTPS], file_name=Images.Cdi.QCOW2_IMG),
        cert_configmap=internal_http_configmap.name,
    ) as dv:
        dv.wait_for_dv_success(timeout=TIMEOUT_4MIN)
        containers = get_containers_for_pods_with_pvc(
            volume_mode=storage_class_matrix__module__[storage_class_name_scope_module]["volume_mode"], pvc_name=dv.name
        )
        with create_vm_from_dv(dv=dv, start=False):
            with PodWithPVC(
                namespace=dv.namespace,
                name=f"{dv.name}-pod",
                pvc_name=dv.name,
                containers=containers,
            ) as pod:
                # In case of file system volume mode, the FS overhead should be taken into account
                # the default overhead is 5.5%, so in order to reserve the 5.5% for the overhead
                # the actual size for the disk will be smaller than the requested size
                if dv.volume_mode == DataVolume.VolumeMode.FILE:
                    size *= 1 - default_fs_overhead
                    # In case that size < 1, convert from Gi to Mi
                    if size < 1:
                        size = GiB(size).to_MiB().value
                        unit = m_byte
                pod.wait_for_status(status=pod.Status.RUNNING)
                virtual_size_output_line = pod.execute(
                    command=[
                        "bash",
                        "-c",
                        "qemu-img info /pvc/disk.img|grep 'virtual size'",
                    ]
                )
                match = re.search(
                    r":\s*(\d+)\s*([MG])",
                    virtual_size_output_line,
                )
                assert match, (
                    "Incorrect virtual size found on disk image /pvc/disk.img\n"
                    f"Virtual size reported as: {virtual_size_output_line}"
                )
                assert unit == match.group(2)
                assert math.floor(size) == float(match.group(1))


@pytest.mark.parametrize(
    "dv_from_http_import",
    [
        pytest.param(
            {
                "dv_name": "cnv-3065",
                "file_name": Images.Cdi.QCOW2_IMG,
                "source": HTTPS,
                "size": "100Mi",
                "configmap_name": INTERNAL_HTTP_CONFIGMAP_NAME,
            },
            marks=pytest.mark.polarion("CNV-3065"),
        ),
    ],
    indirect=True,
)
@pytest.mark.sno
def test_disk_falloc(internal_http_configmap, dv_from_http_import):
    dv_from_http_import.wait_for_dv_success()
    with create_vm_from_dv(dv=dv_from_http_import) as vm_dv:
        with console.Console(vm=vm_dv) as vm_console:
            LOGGER.info("Fill disk space.")
            vm_console.sendline("dd if=/dev/zero of=file bs=1M")
            vm_console.expect("dd: writing 'file': No space left on device", timeout=TIMEOUT_1MIN)


@pytest.mark.destructive
@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_function",
    [
        pytest.param(
            {
                "dv_name": "cnv-3362",
                "source": HTTP,
                "image": RHEL_LATEST["image_path"],
                "dv_size": "25Gi",
                "access_modes": DataVolume.AccessMode.RWX,
                "wait": False,
            },
            marks=pytest.mark.polarion("CNV-3632"),
        ),
    ],
    indirect=True,
)
def test_vm_from_dv_on_different_node(
    admin_client,
    skip_access_mode_rwo_scope_function,
    skip_non_shared_storage,
    schedulable_nodes,
    data_volume_multi_storage_scope_function,
):
    """
    Test that create and run VM from DataVolume (only use RWX access mode) on different node.
    It applies to shared storage like Ceph or NFS. It cannot be tested on local storage like HPP.
    """
    importer_pod = get_importer_pod(
        dyn_client=admin_client,
        namespace=data_volume_multi_storage_scope_function.namespace,
    )
    importer_node_name = get_importer_pod_node(importer_pod=importer_pod)
    nodes = list(filter(lambda node: importer_node_name != node.name, schedulable_nodes))
    data_volume_multi_storage_scope_function.wait_for_dv_success(timeout=TIMEOUT_12MIN)
    with create_vm_from_dv(
        dv=data_volume_multi_storage_scope_function,
        vm_name=Images.Rhel.RHEL8_2_IMG,
        os_flavor=OS_FLAVOR_RHEL,
        node_selector=get_node_selector_dict(node_selector=nodes[0].name),
        memory_guest=Images.Rhel.DEFAULT_MEMORY_SIZE,
    ) as vm_dv:
        assert vm_dv.vmi.node.name != importer_node_name


@pytest.mark.tier3
@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_function,"
    "vm_instance_from_template_multi_storage_scope_function,"
    "started_windows_vm",
    [
        pytest.param(
            {
                "dv_name": "dv-win-19",
                "source": HTTP,
                "image": f"{Images.Windows.UEFI_WIN_DIR}/{Images.Windows.WIN19_RAW}",
                "dv_size": Images.Windows.DEFAULT_DV_SIZE,
            },
            {
                "vm_name": f"vm-win-{LATEST_WINDOWS_OS_DICT.get('os_version')}",
                "template_labels": LATEST_WINDOWS_OS_DICT.get("template_labels"),
                "ssh": True,
            },
            {"os_version": LATEST_WINDOWS_OS_DICT.get("os_version")},
            marks=pytest.mark.polarion("CNV-3637"),
        ),
    ],
    indirect=True,
)
def test_successful_vm_from_imported_dv_windows(
    unprivileged_client,
    namespace,
    data_volume_multi_storage_scope_function,
    vm_instance_from_template_multi_storage_scope_function,
    started_windows_vm,
):
    validate_os_info_vmi_vs_windows_os(
        vm=vm_instance_from_template_multi_storage_scope_function,
    )


@pytest.mark.polarion("CNV-4032")
@pytest.mark.sno
def test_disk_image_after_import(skip_block_volumemode_scope_module, cirros_dv_unprivileged):
    create_vm_and_verify_image_permission(dv=cirros_dv_unprivileged)


@pytest.mark.polarion("CNV-4724")
@pytest.mark.sno
def test_dv_api_version_after_import(cirros_dv_unprivileged):
    assert (
        cirros_dv_unprivileged.api_version
        == f"{cirros_dv_unprivileged.api_group}/{cirros_dv_unprivileged.ApiVersion.V1BETA1}"
    )


@pytest.mark.polarion("CNV-5509")
def test_importer_pod_annotation(dv_with_annotation, linux_nad):
    # verify "k8s.v1.cni.cncf.io/networks" can pass to the importer pod
    assert dv_with_annotation.get(f"{Resource.ApiGroup.K8S_V1_CNI_CNCF_IO}/networks") == linux_nad.name
    assert '"interface": "net1"' in dv_with_annotation.get(f"{Resource.ApiGroup.K8S_V1_CNI_CNCF_IO}/network-status")

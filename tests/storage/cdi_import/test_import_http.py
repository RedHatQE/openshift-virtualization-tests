"""
Import from HTTP server
"""

import logging

import pytest
from kubernetes.dynamic.exceptions import UnprocessibleEntityError
from ocp_resources.datavolume import DataVolume
from pytest_testconfig import config as py_config
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.storage.cdi_import.utils import (
    wait_dv_and_get_importer,
)
from tests.storage.constants import (
    ALPINE_QCOW2_IMG,
    HTTP,
    HTTPS,
    HTTPS_CONFIG_MAP_NAME,
    INTERNAL_HTTP_CONFIGMAP_NAME,
)
from tests.storage.utils import (
    assert_num_files_in_pod,
    assert_use_populator,
    get_file_url,
    wait_for_importer_container_message,
)
from utilities.constants import (
    QUARANTINED,
    TIMEOUT_1MIN,
    TIMEOUT_5MIN,
    Images,
)
from utilities.ssp import validate_os_info_vmi_vs_windows_os
from utilities.storage import (
    ErrorMsg,
    create_dv,
)
from utilities.virt import running_vm

pytestmark = [
    pytest.mark.post_upgrade,
]

LOGGER = logging.getLogger(__name__)

ISO_IMG = "Core-current.iso"
TAR_IMG = "archive.tar"
DEFAULT_DV_SIZE = Images.Alpine.DEFAULT_DV_SIZE
SMALL_DV_SIZE = "200Mi"
LATEST_WINDOWS_OS_DICT = py_config.get("latest_windows_os_dict", {})


@pytest.mark.xfail(
    reason=f"{QUARANTINED}: Automation bug after wait_for_condition change; tracked in CNV-73197",
    run=False,
)
@pytest.mark.sno
@pytest.mark.polarion("CNV-876")
@pytest.mark.s390x
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
@pytest.mark.s390x
def test_empty_url(namespace, storage_class_name_scope_module, unprivileged_client):
    with pytest.raises(UnprocessibleEntityError):
        with create_dv(
            client=unprivileged_client,
            dv_name=f"cnv-674-{storage_class_name_scope_module}",
            namespace=namespace.name,
            url="",
            size=DEFAULT_DV_SIZE,
            storage_class=storage_class_name_scope_module,
        ):
            pass


@pytest.mark.sno
@pytest.mark.gating
@pytest.mark.parametrize(
    "dv_from_http_import",
    [
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
    dv_from_http_import,
    storage_class_name_scope_module,
    cluster_csi_drivers_names,
):
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
@pytest.mark.s390x
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
            {
                "dv_name": "cnv-2719",
                "file_name": Images.Alpine.QCOW2_IMG_VERSIONED,
                "source": HTTPS,
                "configmap_name": INTERNAL_HTTP_CONFIGMAP_NAME,
            },
            marks=pytest.mark.polarion("CNV-2719"),
        ),
    ],
    indirect=True,
)
@pytest.mark.sno
@pytest.mark.gating
def test_successful_import_secure_image(internal_http_configmap, dv_from_http_import):
    dv_from_http_import.wait_for_dv_success()


@pytest.mark.sno
@pytest.mark.parametrize(
    "content_type, file_name",
    [
        pytest.param(
            DataVolume.ContentType.KUBEVIRT,
            Images.Alpine.RAW_IMG_XZ,
            marks=(pytest.mark.polarion("CNV-784"), pytest.mark.smoke()),
        ),
    ],
)
@pytest.mark.s390x
def test_successful_import_basic_auth(
    admin_client,
    namespace,
    storage_class_matrix__module__,
    storage_class_name_scope_module,
    images_internal_http_server,
    internal_http_secret,
    content_type,
    file_name,
):
    with create_dv(
        client=admin_client,
        dv_name="import-http-dv",
        namespace=namespace.name,
        url=get_file_url(url=images_internal_http_server["http_auth"], file_name=file_name),
        content_type=content_type,
        size=DEFAULT_DV_SIZE,
        secret=internal_http_secret,
        storage_class=storage_class_name_scope_module,
    ) as dv:
        dv.wait_for_dv_success()


@pytest.mark.sno
@pytest.mark.parametrize(
    "dv_from_http_import",
    [
        pytest.param(
            {
                "dv_name": "cnv-2144",
                "file_name": Images.Alpine.QCOW2_IMG_VERSIONED,
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
    ("https_config_map", "dv_from_http_import"),
    [
        pytest.param(
            {"data": "-----BEGIN CERTIFICATE-----"},
            {
                "dv_name": "cnv-2812",
                "file_name": Images.Alpine.QCOW2_IMG_VERSIONED,
                "source": HTTPS,
                "configmap_name": HTTPS_CONFIG_MAP_NAME,
            },
            marks=(pytest.mark.polarion("CNV-2812")),
        ),
        pytest.param(
            {"data": None},
            {
                "dv_name": "cnv-2813",
                "file_name": Images.Alpine.QCOW2_IMG_VERSIONED,
                "source": HTTPS,
                "configmap_name": HTTPS_CONFIG_MAP_NAME,
            },
            marks=(pytest.mark.polarion("CNV-2813")),
        ),
    ],
    indirect=True,
)
@pytest.mark.s390x
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
                "image": ALPINE_QCOW2_IMG,
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
@pytest.mark.s390x
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
    "number_of_dvs",
    [
        pytest.param(
            4,
            marks=(pytest.mark.polarion("CNV-2001")),
        ),
    ],
)
@pytest.mark.s390x
def test_successful_concurrent_blank_disk_import(
    created_vm_list,
):
    for vm in created_vm_list:
        running_vm(vm=vm)


@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_function",
    [{"dv_name": "cnv-2004", "source": "blank", "image": "", "dv_size": SMALL_DV_SIZE}],
    indirect=True,
)
@pytest.mark.sno
@pytest.mark.polarion("CNV-2004")
@pytest.mark.s390x
def test_blank_disk_import_validate_status(data_volume_multi_storage_scope_function):
    data_volume_multi_storage_scope_function.wait_for_dv_success(timeout=TIMEOUT_5MIN)


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

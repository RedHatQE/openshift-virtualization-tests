# -*- coding: utf-8 -*-

"""
Upload using virtctl
"""

import logging
import subprocess
import time

import pytest
from kubernetes.dynamic.exceptions import NotFoundError
from ocp_resources.datavolume import DataVolume
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_resources.route import Route
from ocp_resources.storage_class import StorageClass
from pytest_testconfig import config as py_config

from tests.storage.cdi_upload.utils import get_storage_profile_minimum_supported_pvc_size
from tests.storage.utils import assert_use_populator, create_windows_vm_validate_guest_agent_info
from utilities.constants import CDI_UPLOADPROXY, QUARANTINED, TIMEOUT_1MIN, Images
from utilities.storage import (
    ErrorMsg,
    check_upload_virtctl_result,
    create_dummy_first_consumer_pod,
    create_vm_from_dv,
    get_downloaded_artifact,
    sc_volume_binding_mode_is_wffc,
    virtctl_upload_dv,
)
from utilities.virt import VirtualMachineForTests, running_vm

pytestmark = pytest.mark.post_upgrade

LOGGER = logging.getLogger(__name__)
POPULATED_STR = "populated"
NON_CSI_POPULATED_STR = "imported/cloned/updated"
DEFAULT_DV_SIZE = Images.Cdi.DEFAULT_DV_SIZE
LOCAL_PATH = f"/tmp/{Images.Cdi.QCOW2_IMG}"

LATEST_WINDOWS_OS_DICT = py_config.get("latest_windows_os_dict", {})


def get_population_method_by_provisioner(storage_class, cluster_csi_drivers_names):
    return (
        POPULATED_STR
        if StorageClass(name=storage_class).instance.get("provisioner") in cluster_csi_drivers_names
        else NON_CSI_POPULATED_STR
    )


@pytest.fixture(scope="function")
def skip_no_reencrypt_route(upload_proxy_route):
    if not upload_proxy_route.termination == "reencrypt":
        pytest.skip("Skip testing. The upload proxy route is not re-encrypt.")


@pytest.fixture(scope="function")
def cdi_uploadproxy_url(admin_client, hco_namespace):
    """
    Get CDI upload proxy URL.

    On IPv6 single-stack clusters, set up port-forward to the CDI upload proxy service
    and return localhost URL instead of the route (which resolves to IPv4).
    """
    if not py_config.get("ipv6_single_stack_cluster"):
        return None

    port = 8443
    subprocess.run(
        f"nohup oc port-forward svc/{CDI_UPLOADPROXY} {port}:443 -n {hco_namespace.name} &",
        shell=True,
    )
    # Wait for port-forward to be ready
    time.sleep(2)

    yield f"https://localhost:{port}"

    # Cleanup: kill port-forward process
    subprocess.run("pkill -f 'oc port-forward'", shell=True, check=False)


@pytest.mark.sno
@pytest.mark.polarion("CNV-2192")
def test_successful_virtctl_upload_no_url(unprivileged_client, namespace, tmpdir):
    local_name = f"{tmpdir}/{Images.Cdi.QCOW2_IMG}"
    get_downloaded_artifact(remote_name=f"{Images.Cdi.DIR}/{Images.Cdi.QCOW2_IMG}", local_name=local_name)
    pvc_name = "cnv-2192"
    with virtctl_upload_dv(
        client=namespace.client,
        namespace=namespace.name,
        name=pvc_name,
        size=DEFAULT_DV_SIZE,
        storage_class=py_config["default_storage_class"],
        image_path=local_name,
        insecure=True,
    ) as virtctl_upload:
        check_upload_virtctl_result(result=virtctl_upload)
        assert PersistentVolumeClaim(name=pvc_name, namespace=namespace.name, client=unprivileged_client).bound()


@pytest.mark.destructive
@pytest.mark.polarion("CNV-2191")
def test_successful_virtctl_upload_no_route(
    admin_client,
    hco_namespace,
    namespace,
    tmpdir,
    uploadproxy_route_deleted,
):
    route = Route(name=CDI_UPLOADPROXY, namespace=hco_namespace.name, client=admin_client)
    with pytest.raises(NotFoundError):
        route.instance

    local_name = f"{tmpdir}/{Images.Cdi.QCOW2_IMG}"
    get_downloaded_artifact(remote_name=f"{Images.Cdi.DIR}/{Images.Cdi.QCOW2_IMG}", local_name=local_name)
    pvc_name = "cnv-2191"
    with virtctl_upload_dv(
        client=namespace.client,
        namespace=namespace.name,
        name=pvc_name,
        size="1Gi",
        storage_class=py_config["default_storage_class"],
        image_path=local_name,
        insecure=True,
    ) as res:
        check_upload_virtctl_result(
            result=res,
            expected_success=False,
            expected_output="uploadproxy URL not found",
            assert_message="virtctl image-upload command successful, must fail with a non-zero rc",
        )


@pytest.mark.sno
@pytest.mark.polarion("CNV-2217")
def test_image_upload_with_overridden_url(
    unprivileged_client,
    namespace,
    tmpdir,
    cdi_config_upload_proxy_overridden,
):
    pvc_name = "cnv-2217"
    local_name = f"{tmpdir}/{Images.Cdi.QCOW2_IMG}"
    get_downloaded_artifact(remote_name=f"{Images.Cdi.DIR}/{Images.Cdi.QCOW2_IMG}", local_name=local_name)
    with virtctl_upload_dv(
        client=namespace.client,
        namespace=namespace.name,
        name=pvc_name,
        size=DEFAULT_DV_SIZE,
        storage_class=py_config["default_storage_class"],
        image_path=local_name,
        insecure=True,
    ) as virtctl_upload:
        check_upload_virtctl_result(result=virtctl_upload)
        assert PersistentVolumeClaim(name=pvc_name, namespace=namespace.name, client=unprivileged_client).bound()


@pytest.mark.sno
@pytest.mark.polarion("CNV-3031")
@pytest.mark.s390x
@pytest.mark.xfail(
    reason=f"{QUARANTINED}: Test fails when running from container; tracked in CNV-18870",
    run=False,
)
def test_virtctl_image_upload_with_ca(
    unprivileged_client,
    enabled_ca,
    skip_no_reencrypt_route,
    tmpdir,
    namespace,
):
    local_path = f"{tmpdir}/{Images.Cdi.QCOW2_IMG}"
    get_downloaded_artifact(remote_name=f"{Images.Cdi.DIR}/{Images.Cdi.QCOW2_IMG}", local_name=local_path)
    pvc_name = "cnv-3031"
    with virtctl_upload_dv(
        client=namespace.client,
        namespace=namespace.name,
        name=pvc_name,
        size=DEFAULT_DV_SIZE,
        storage_class=py_config["default_storage_class"],
        image_path=local_path,
    ) as res:
        check_upload_virtctl_result(result=res)
        pvc = PersistentVolumeClaim(namespace=namespace.name, name=pvc_name, client=unprivileged_client)
        assert pvc.bound()


@pytest.mark.smoke
@pytest.mark.sno
@pytest.mark.polarion("CNV-3724")
def test_virtctl_image_upload_dv(
    unprivileged_client,
    namespace,
    storage_class_name_immediate_binding_scope_module,
    download_image,
):
    """
    Check that upload a local disk image to a newly created DataVolume
    """
    dv_name = f"cnv-3724-{storage_class_name_immediate_binding_scope_module}"
    with virtctl_upload_dv(
        client=namespace.client,
        namespace=namespace.name,
        name=dv_name,
        size=DEFAULT_DV_SIZE,
        image_path=LOCAL_PATH,
        storage_class=storage_class_name_immediate_binding_scope_module,
        insecure=True,
    ) as res:
        check_upload_virtctl_result(result=res)
        dv = DataVolume(namespace=namespace.name, name=dv_name, client=unprivileged_client)
        dv.wait_for_dv_success(timeout=TIMEOUT_1MIN)
        create_vm_from_dv(client=unprivileged_client, dv=dv, start=True)


@pytest.mark.sno
@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_function",
    [
        pytest.param(
            {
                "dv_name": "cnv-3726",
                "image": f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}",
                "dv_size": Images.Cirros.DEFAULT_DV_SIZE,
            },
            marks=(pytest.mark.polarion("CNV-3726")),
        ),
    ],
    indirect=True,
)
@pytest.mark.s390x
def test_virtctl_image_upload_with_exist_dv_image(
    data_volume_multi_storage_scope_function,
    storage_class_name_scope_function,
    download_image,
    namespace,
    cluster_csi_drivers_names,
):
    """
    Check that virtctl fails gracefully when attempting to upload an image to a data volume that already has disk.img
    """
    dv_name = data_volume_multi_storage_scope_function.name
    with virtctl_upload_dv(
        client=namespace.client,
        namespace=namespace.name,
        name=dv_name,
        size=DEFAULT_DV_SIZE,
        image_path=LOCAL_PATH,
        storage_class=storage_class_name_scope_function,
        insecure=True,
        no_create=True,
    ) as res:
        check_upload_virtctl_result(
            result=res,
            expected_success=False,
            expected_output=ErrorMsg.ASSUMING_PVC_SUCCESSFULLY_POPULATED.format(
                pvc_name=dv_name,
                populated=get_population_method_by_provisioner(
                    storage_class=storage_class_name_scope_function,
                    cluster_csi_drivers_names=cluster_csi_drivers_names,
                ),
            ),
        )


@pytest.mark.sno
@pytest.mark.gating
@pytest.mark.polarion("CNV-3728")
@pytest.mark.s390x
def test_virtctl_image_upload_pvc(download_image, namespace, storage_class_name_scope_module, cdi_uploadproxy_url):
    """
    Check that virtctl can create a new PVC and upload an image to it
    """
    pvc_name = "cnv-3728"
    with virtctl_upload_dv(
        client=namespace.client,
        namespace=namespace.name,
        pvc=True,
        name=pvc_name,
        size=DEFAULT_DV_SIZE,
        image_path=LOCAL_PATH,
        storage_class=storage_class_name_scope_module,
        uploadproxy_url=cdi_uploadproxy_url,
        insecure=True,
    ) as res:
        check_upload_virtctl_result(result=res)
        pvc = PersistentVolumeClaim(namespace=namespace.name, name=pvc_name)
        assert pvc.bound()


@pytest.mark.sno
class TestVirtctlUploadExistingDV:
    @pytest.mark.polarion("CNV-3725")
    def test_virtctl_image_upload_to_existing_dv_and_create_vm(self, unprivileged_client, uploaded_dv_scope_class):
        uploaded_dv_scope_class.wait_for_dv_success()
        with create_vm_from_dv(dv=uploaded_dv_scope_class, client=unprivileged_client, start=True):
            pass

    @pytest.mark.polarion("CNV-4033")
    def test_virtctl_image_upload_to_existing_dv_and_validate_populator(
        self, uploaded_dv_scope_class, storage_class_name_scope_class, cluster_csi_drivers_names
    ):
        assert_use_populator(
            pvc=uploaded_dv_scope_class.pvc,
            storage_class=storage_class_name_scope_class,
            cluster_csi_drivers_names=cluster_csi_drivers_names,
        )


@pytest.fixture()
def empty_pvc(
    namespace,
    storage_class_matrix__module__,
    storage_class_name_scope_module,
):
    storage_profile_minimum_supported_pvc_size = get_storage_profile_minimum_supported_pvc_size(
        storage_class_name=storage_class_name_scope_module,
        client=namespace.client,
    )
    sc_config = storage_class_matrix__module__[storage_class_name_scope_module]
    with PersistentVolumeClaim(
        name="empty-pvc",
        namespace=namespace.name,
        storage_class=storage_class_name_scope_module,
        volume_mode=sc_config["volume_mode"],
        accessmodes=sc_config["access_mode"],
        size=storage_profile_minimum_supported_pvc_size or DEFAULT_DV_SIZE,
        client=namespace.client,
    ) as pvc:
        if sc_volume_binding_mode_is_wffc(sc=storage_class_name_scope_module, client=namespace.client):
            # For PVC to bind on WFFC, it must be consumed
            # (this was previously solved by hard coding hostpath_node at all times)
            create_dummy_first_consumer_pod(pvc=pvc)
        pvc.wait_for_status(status=PersistentVolumeClaim.Status.BOUND, timeout=60)
        yield pvc


@pytest.mark.sno
@pytest.mark.polarion("CNV-3727")
def test_virtctl_image_upload_with_exist_pvc(
    empty_pvc,
    download_image,
    namespace,
    storage_class_name_scope_module,
):
    """
    Check that virtctl can upload an local disk image to an existing empty PVC
    """
    with virtctl_upload_dv(
        client=namespace.client,
        namespace=namespace.name,
        name=empty_pvc.name,
        size=DEFAULT_DV_SIZE,
        pvc=True,
        image_path=LOCAL_PATH,
        storage_class=storage_class_name_scope_module,
        insecure=True,
        no_create=True,
    ) as res:
        check_upload_virtctl_result(result=res)
        if not sc_volume_binding_mode_is_wffc(sc=storage_class_name_scope_module, client=namespace.client):
            with VirtualMachineForTests(
                name="cnv-3727-vm",
                namespace=empty_pvc.namespace,
                os_flavor=Images.Cirros.OS_FLAVOR,
                memory_guest=Images.Cirros.DEFAULT_MEMORY_SIZE,
                pvc=empty_pvc,
                client=namespace.client,
            ) as vm:
                running_vm(vm=vm, wait_for_interfaces=False)


@pytest.mark.polarion("CNV-3729")
@pytest.mark.s390x
def test_virtctl_image_upload_with_exist_pvc_image(
    download_image,
    namespace,
    storage_class_name_scope_module,
    cluster_csi_drivers_names,
):
    """
    Check that virtctl fails gracefully when attempting to upload an image to a PVC that already has disk.img
    """
    pvc_name = f"cnv-3729-{storage_class_name_scope_module}"
    with virtctl_upload_dv(
        client=namespace.client,
        namespace=namespace.name,
        name=pvc_name,
        size=DEFAULT_DV_SIZE,
        image_path=LOCAL_PATH,
        storage_class=storage_class_name_scope_module,
        insecure=True,
    ) as res:
        check_upload_virtctl_result(result=res)
        with virtctl_upload_dv(
            client=namespace.client,
            namespace=namespace.name,
            name=pvc_name,
            size=DEFAULT_DV_SIZE,
            image_path=LOCAL_PATH,
            storage_class=storage_class_name_scope_module,
            insecure=True,
            no_create=True,
        ) as res_new:
            check_upload_virtctl_result(
                result=res_new,
                expected_success=False,
                expected_output=ErrorMsg.ASSUMING_PVC_SUCCESSFULLY_POPULATED.format(
                    pvc_name=pvc_name,
                    populated=get_population_method_by_provisioner(
                        storage_class=storage_class_name_scope_module,
                        cluster_csi_drivers_names=cluster_csi_drivers_names,
                    ),
                ),
            )


@pytest.mark.polarion("CNV-3730")
@pytest.mark.s390x
def test_virtctl_image_upload_dv_with_exist_pvc(
    empty_pvc,
    download_image,
    namespace,
    storage_class_name_scope_module,
    schedulable_nodes,
):
    """
    Check that virtctl fails gracefully when attempting to upload an image to a new data volume
    - PVC with the same name already exists.
    """
    with virtctl_upload_dv(
        client=namespace.client,
        namespace=namespace.name,
        name=empty_pvc.name,
        size=DEFAULT_DV_SIZE,
        image_path=LOCAL_PATH,
        storage_class=storage_class_name_scope_module,
        insecure=True,
    ) as res:
        check_upload_virtctl_result(
            result=res,
            expected_success=False,
            expected_output="No DataVolume is associated with the existing PVC",
        )


@pytest.mark.tier3
@pytest.mark.parametrize(
    ("uploaded_dv_with_immediate_binding", "vm_params"),
    [
        pytest.param(
            {
                "dv_size": Images.Windows.DEFAULT_DV_SIZE,
                "remote_name": LATEST_WINDOWS_OS_DICT.get("image_path"),
                "image_file": LATEST_WINDOWS_OS_DICT.get("image_name"),
            },
            {
                "vm_name": f"vm-win-{LATEST_WINDOWS_OS_DICT.get('os_version')}",
                "template_labels": LATEST_WINDOWS_OS_DICT.get("template_labels"),
                "ssh": True,
                "os_version": LATEST_WINDOWS_OS_DICT.get("os_version"),
            },
            marks=(pytest.mark.polarion("CNV-3410")),
        ),
    ],
    indirect=["uploaded_dv_with_immediate_binding"],
)
def test_successful_vm_from_uploaded_dv_windows(
    unprivileged_client,
    namespace,
    uploaded_dv_with_immediate_binding,
    vm_params,
):
    create_windows_vm_validate_guest_agent_info(
        dv=uploaded_dv_with_immediate_binding,
        namespace=namespace,
        unprivileged_client=unprivileged_client,
        vm_params=vm_params,
    )


@pytest.mark.parametrize(
    "download_specified_image",
    [
        pytest.param(
            {
                "image_path": py_config["latest_rhel_os_dict"]["image_path"],
                "image_file": py_config["latest_rhel_os_dict"]["image_name"],
            },
            marks=(pytest.mark.polarion("CNV-4512")),
        ),
    ],
    indirect=True,
)
@pytest.mark.s390x
@pytest.mark.jira("CNV-76657", run=False)
def test_print_response_body_on_error_upload_virtctl(
    namespace, download_specified_image, storage_class_name_scope_module
):
    """
    Check that CDI now reports validation failures as part of the body response
    in case for instance the disk image virtual size > PVC size > disk size
    """
    dv_name = f"cnv-4512-{storage_class_name_scope_module}"
    with virtctl_upload_dv(
        client=namespace.client,
        namespace=namespace.name,
        name=dv_name,
        size="3G",
        image_path=download_specified_image,
        storage_class=storage_class_name_scope_module,
        insecure=True,
    ) as res:
        check_upload_virtctl_result(
            result=res,
            expected_success=False,
            expected_output=ErrorMsg.LARGER_PVC_REQUIRED,
        )

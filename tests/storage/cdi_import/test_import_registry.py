import logging

import pytest
from kubernetes.client.rest import ApiException
from ocp_resources.datavolume import DataVolume

from tests.storage.constants import QUAY_FEDORA_CONTAINER_IMAGE, REGISTRY_STR
from tests.storage.utils import (
    create_vm_from_dv,
    get_importer_pod,
    wait_for_importer_container_message,
)
from utilities.constants import OS_FLAVOR_FEDORA, TIMEOUT_5MIN, Images
from utilities.ssp import wait_for_condition_message_value
from utilities.storage import ErrorMsg, check_disk_count_in_vm, create_dv
from utilities.virt import running_vm

pytestmark = pytest.mark.post_upgrade
LOGGER = logging.getLogger(__name__)


@pytest.mark.sno
@pytest.mark.parametrize(
    ("dv_name", "url"),
    [
        pytest.param(
            "cnv-2198",
            "docker://quay.io/openshift-cnv/qe-cnv-tests-registry-official-cirros",
            marks=pytest.mark.polarion("CNV-2198"),
            id="image-registry-not-conform-registrydisk",
        ),
        pytest.param(
            "cnv-2340",
            "docker://quay.io/openshift-cnv/qe-cnv-tests-registry-fedora29-qcow2-rootdir",
            marks=pytest.mark.polarion("CNV-2340"),
            id="import-registry-fedora29-qcow-rootdir",
        ),
    ],
)
def test_disk_image_not_conform_to_registy_disk(
    admin_client, dv_name, url, namespace, storage_class_matrix__function__
):
    with create_dv(
        source=REGISTRY_STR,
        dv_name=dv_name,
        namespace=namespace.name,
        url=url,
        storage_class=[*storage_class_matrix__function__][0],
    ) as dv:
        dv.wait_for_status(
            status=DataVolume.Status.IMPORT_IN_PROGRESS,
            timeout=TIMEOUT_5MIN,
            stop_status=DataVolume.Status.SUCCEEDED,
        )
        importer_pod = get_importer_pod(dyn_client=admin_client, namespace=dv.namespace)
        wait_for_importer_container_message(
            importer_pod=importer_pod,
            msg=ErrorMsg.DISK_IMAGE_IN_CONTAINER_NOT_FOUND,
        )


@pytest.mark.sno
@pytest.mark.polarion("CNV-2028")
def test_public_registry_multiple_data_volume(
    namespace, storage_class_name_scope_function, dvs_and_vms_from_public_registry
):
    for vm in dvs_and_vms_from_public_registry:
        running_vm(vm=vm)
        check_disk_count_in_vm(vm=vm)


@pytest.mark.sno
@pytest.mark.parametrize(
    ("dv_name", "content_type"),
    [
        pytest.param(
            "import-public-registry-no-content-type-dv",
            None,
            marks=(pytest.mark.polarion("CNV-2195")),
        ),
        pytest.param(
            "import-public-registry-empty-content-type-dv",
            "",
            marks=(pytest.mark.polarion("CNV-2197"), pytest.mark.smoke(), pytest.mark.s390x()),
        ),
        pytest.param(
            "import-public-registry-quay-dv",
            DataVolume.ContentType.KUBEVIRT,
            marks=(pytest.mark.polarion("CNV-2026")),
        ),
    ],
    ids=[
        "import-public-registry-no-content-type-dv",
        "import-public-registry-empty-content-type-dv",
        "import-public-registry-quay-dv",
    ],
)
def test_public_registry_data_volume(
    namespace,
    dv_name,
    content_type,
    storage_class_name_scope_function,
):
    with create_dv(
        source=REGISTRY_STR,
        dv_name=dv_name,
        namespace=namespace.name,
        url=QUAY_FEDORA_CONTAINER_IMAGE,
        content_type=content_type,
        size=Images.Fedora.DEFAULT_DV_SIZE,
        storage_class=storage_class_name_scope_function,
    ) as dv:
        dv.wait_for_dv_success()
        with create_vm_from_dv(
            dv=dv,
            vm_name="fedora-vm-from-dv",
            os_flavor=OS_FLAVOR_FEDORA,
            memory_guest=Images.Fedora.DEFAULT_MEMORY_SIZE,
            wait_for_cloud_init=True,
        ) as vm_dv:
            check_disk_count_in_vm(vm=vm_dv)


# The following test is to show after imports fails because low capacity storage,
# we can overcome by updating to the right requested volume size and import successfully
@pytest.mark.sno
@pytest.mark.polarion("CNV-2024")
def test_public_registry_data_volume_low_capacity(namespace, storage_class_name_scope_function):
    dv_param = {
        "dv_name": "import-public-registry-low-capacity-dv",
        "source": REGISTRY_STR,
        "url": QUAY_FEDORA_CONTAINER_IMAGE,
        "storage_class": storage_class_name_scope_function,
    }
    # negative flow - low capacity volume
    with create_dv(
        source=dv_param["source"],
        dv_name=dv_param["dv_name"],
        namespace=namespace.name,
        url=dv_param["url"],
        content_type="",
        size="16Mi",
        storage_class=dv_param["storage_class"],
    ) as dv:
        dv.wait_for_status(
            status=DataVolume.Status.IMPORT_IN_PROGRESS,
            timeout=TIMEOUT_5MIN,
            stop_status=DataVolume.Status.SUCCEEDED,
        )
        wait_for_condition_message_value(resource=dv, expected_message=ErrorMsg.DATA_VOLUME_TOO_SMALL)
    # positive flow
    with create_dv(
        source=dv_param["source"],
        dv_name=dv_param["dv_name"],
        namespace=namespace.name,
        url=dv_param["url"],
        storage_class=dv_param["storage_class"],
    ) as dv:
        dv.wait_for_dv_success()
        with create_vm_from_dv(
            dv=dv,
            vm_name="fedora-vm-from-dv",
            os_flavor=OS_FLAVOR_FEDORA,
            memory_guest=Images.Fedora.DEFAULT_MEMORY_SIZE,
            wait_for_cloud_init=True,
        ) as vm_dv:
            check_disk_count_in_vm(vm=vm_dv)


@pytest.mark.sno
@pytest.mark.polarion("CNV-2150")
def test_public_registry_data_volume_archive(namespace, storage_class_name_scope_function):
    with pytest.raises(ApiException, match=r".*ContentType must be kubevirt when Source is Registry.*"):
        with create_dv(
            source=REGISTRY_STR,
            dv_name="import-public-registry-archive",
            namespace=namespace.name,
            url=QUAY_FEDORA_CONTAINER_IMAGE,
            content_type=DataVolume.ContentType.ARCHIVE,
            storage_class=[*storage_class_name_scope_function][0],
        ):
            return

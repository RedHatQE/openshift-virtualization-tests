"""
Automation for DataImportCron
"""

import logging
import re

import pytest
from ocp_resources.data_import_cron import DataImportCron
from ocp_resources.datavolume import DataVolume
from ocp_resources.image_stream import ImageStream
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_resources.resource import ResourceEditor
from ocp_resources.storage_profile import StorageProfile
from ocp_resources.volume_snapshot import VolumeSnapshot
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from utilities.constants import (
    BIND_IMMEDIATE_ANNOTATION,
    OUTDATED,
    TIMEOUT_1MIN,
    TIMEOUT_3MIN,
    TIMEOUT_5SEC,
    WILDCARD_CRON_EXPRESSION,
    Images,
)
from utilities.storage import (
    wait_for_succeeded_dv,
    wait_for_volume_snapshot_ready_to_use,
)

RHEL8_STR = "rhel8"
RHEL8_IMAGE_STREAM = f"{RHEL8_STR}-image-stream"
RHEL8_DIGEST = "947541648d7f12fd56d2224d55ce708d369f76ffeb4938c8846b287197f30970"
# Login Red Hat Registry using the Customer Portal credentials,
# and get the rhel8 digest from oc image info registry.redhat.io/rhel8/rhel-guest-image:8.4.0-423


LOGGER = logging.getLogger(__name__)


def wait_for_succeeded_imported_object(namespace, name, storage_with_import_cron_source_snapshot):
    if storage_with_import_cron_source_snapshot:
        wait_for_volume_snapshot_ready_to_use(namespace=namespace, name=name)
    else:
        wait_for_succeeded_dv(namespace=namespace, dv_name=name)


def assert_first_imported_object_was_deleted(namespace, name):
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_3MIN,
        sleep=TIMEOUT_5SEC,
        func=lambda: PersistentVolumeClaim(namespace=namespace, name=name).exists
        or VolumeSnapshot(namespace=namespace, name=name).exists,
    )
    try:
        for sample in samples:
            if not sample:
                return
    except TimeoutExpiredError:
        LOGGER.error(f"Garbage collection failed, first object '{name}' was not deleted")
        raise


@pytest.fixture()
def storage_with_import_cron_source_snapshot(
    storage_class_name_scope_function,
):
    sc_storage_profile = StorageProfile(name=storage_class_name_scope_function)
    yield sc_storage_profile.instance.status.get("dataImportCronSourceFormat") == "snapshot"


@pytest.fixture()
def rhel8_image_stream(admin_client, namespace):
    tags = [
        {
            "from": {
                "kind": "DockerImage",
                "name": Images.Rhel.RHEL8_REGISTRY_GUEST_IMG,
            },
            "importPolicy": {"scheduled": True},
            "name": "latest",
            "referencePolicy": {"type": "Source"},
        }
    ]
    with ImageStream(
        name=RHEL8_IMAGE_STREAM,
        namespace=namespace.name,
        tags=tags,
    ) as image_stream:
        yield image_stream


@pytest.fixture()
def rhel8_latest_image_truncated_sha_from_image_stream(namespace, rhel8_image_stream):
    samples = TimeoutSampler(
        wait_timeout=TIMEOUT_1MIN,
        sleep=TIMEOUT_5SEC,
        func=lambda: rhel8_image_stream.instance.status.tags[0]["items"][0]["image"],
    )
    for sample in samples:
        if sample:
            match = re.match(r"^.*sha256:(.*)$", sample)
            assert match, f"image sha256 doesn't exist in {sample}"
            return match.group(1)[
                0:12
            ]  # The DV is created by dataimportcron which named datasource_name + [0:12] of the digest


@pytest.fixture()
def data_import_cron_image_stream(namespace, storage_class_name_scope_function):
    with DataImportCron(
        name=f"{RHEL8_STR}-image-import-cron",
        namespace=namespace.name,
        garbage_collect=OUTDATED,
        imports_to_keep=1,
        managed_data_source=RHEL8_STR,
        schedule=WILDCARD_CRON_EXPRESSION,
        annotations=BIND_IMMEDIATE_ANNOTATION,
        template={
            "spec": {
                "source": {
                    "registry": {
                        "imageStream": RHEL8_IMAGE_STREAM,
                        "pullMethod": "node",
                    }
                },
                "storage": {
                    "resources": {"requests": {"storage": Images.Rhel.DEFAULT_DV_SIZE}},
                    "storageClassName": storage_class_name_scope_function,
                },
            }
        },
    ) as data_import_cron:
        yield data_import_cron


@pytest.fixture()
def first_object_name(rhel8_latest_image_truncated_sha_from_image_stream):
    # The DV is created by dataimportcron which named datasource_name + [0:12] of the digest
    yield f"{RHEL8_STR}-{rhel8_latest_image_truncated_sha_from_image_stream}"


@pytest.fixture()
def first_imported_object(namespace, first_object_name, storage_with_import_cron_source_snapshot):
    wait_for_succeeded_imported_object(
        namespace=namespace.name,
        name=first_object_name,
        storage_with_import_cron_source_snapshot=storage_with_import_cron_source_snapshot,
    )


@pytest.fixture()
def second_object_name():
    yield f"{RHEL8_STR}-{RHEL8_DIGEST[0:12]}"


@pytest.fixture()
def second_imported_object(
    namespace,
    second_object_name,
    storage_with_import_cron_source_snapshot,
):
    wait_for_succeeded_imported_object(
        namespace=namespace.name,
        name=second_object_name,
        storage_with_import_cron_source_snapshot=storage_with_import_cron_source_snapshot,
    )


@pytest.fixture()
def rhel8_image_stream_digest_update(rhel8_image_stream):
    ResourceEditor(
        patches={
            rhel8_image_stream: {
                "spec": {
                    "tags": [
                        {
                            "from": {
                                "kind": "DockerImage",
                                "name": f"{rhel8_image_stream.instance.spec['tags'][0]['from']['name']}"
                                f"@sha256:{RHEL8_DIGEST}",
                            },
                            "name": "8.4.0-423",
                        }
                    ]
                }
            }
        }
    ).update()


@pytest.fixture()
def second_object_cleanup(
    namespace,
    second_object_name,
    storage_with_import_cron_source_snapshot,
):
    yield
    LOGGER.info(
        f"Cleanup the remaining second_object '{second_object_name}' "
        f"(DV/PVC or VolumeSnapshot) that was created by the DataImportCron"
    )
    resource_class = VolumeSnapshot if storage_with_import_cron_source_snapshot else DataVolume
    resource_class(namespace=namespace.name, name=second_object_name).clean_up()


@pytest.mark.gating
@pytest.mark.polarion("CNV-7602")
def test_data_import_cron_garbage_collection(
    namespace,
    second_object_cleanup,
    rhel8_image_stream,
    data_import_cron_image_stream,
    first_imported_object,
    first_object_name,
    rhel8_image_stream_digest_update,
    second_imported_object,
    second_object_name,
    storage_with_import_cron_source_snapshot,
):
    assert_first_imported_object_was_deleted(namespace=namespace.name, name=first_object_name)
    resource_class = VolumeSnapshot if storage_with_import_cron_source_snapshot else PersistentVolumeClaim
    assert resource_class(namespace=namespace.name, name=second_object_name).exists, (
        f"Second {resource_class.kind} '{second_object_name}' does not exist"
    )

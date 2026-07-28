import os

import pytest
from ocp_resources.image_image_openshift_io import Image
from ocp_resources.image_stream import ImageStream
from ocp_resources.imagestreamtag import ImageStreamTag

from tests.install_upgrade_operators.must_gather.utils import (
    VALIDATE_UID_NAME,
    check_list_of_resources,
)
from utilities.constants.namespaces import NamespacesNames

pytestmark = [
    pytest.mark.sno,
    pytest.mark.post_upgrade,
    pytest.mark.skip_must_gather_collection,
    pytest.mark.arm64,
    pytest.mark.s390x,
]

IMAGESTREAMTAGS_PATH = f"namespaces/{NamespacesNames.OPENSHIFT}/imagestreamtags"


class TestImageGathering:
    @pytest.mark.parametrize(
        "resource_path, resource",
        [
            pytest.param(
                "cluster-scoped-resources/images/{name}.yaml",
                Image,
                marks=(pytest.mark.polarion("CNV-9234")),
            ),
            pytest.param(
                f"namespaces/{NamespacesNames.OPENSHIFT}/imagestreams/{{name}}.yaml",
                ImageStream,
                marks=(pytest.mark.polarion("CNV-9235")),
            ),
        ],
    )
    def test_image_gather(self, admin_client, gathered_images, resource, resource_path):
        check_list_of_resources(
            client=admin_client,
            resource_type=resource,
            temp_dir=gathered_images,
            resource_path=resource_path,
            checks=VALIDATE_UID_NAME,
            filter_resource="redhat",
        )

    @pytest.mark.polarion("CNV-9236")
    def test_image_stream_tag_gather(self, admin_client, gathered_images):
        istag_dir = os.path.join(gathered_images, IMAGESTREAMTAGS_PATH)
        collected_count = len(os.listdir(istag_dir))
        cluster_count = len(list(ImageStreamTag.get(client=admin_client, namespace=NamespacesNames.OPENSHIFT)))
        assert collected_count == cluster_count, (
            f"Expected {cluster_count} ImageStreamTags, but collected {collected_count}"
        )
        check_list_of_resources(
            client=admin_client,
            resource_type=ImageStreamTag,
            temp_dir=gathered_images,
            resource_path=f"{IMAGESTREAMTAGS_PATH}/{{name}}.yaml",
            checks=VALIDATE_UID_NAME,
            filter_resource="redhat",
        )

import pytest
from ocp_resources.image_image_openshift_io import Image
from ocp_resources.image_stream import ImageStream
from ocp_resources.imagestreamtag import ImageStreamTag

from tests.install_upgrade_operators.must_gather.utils import (
    VALIDATE_UID_NAME,
    check_list_of_resources,
)
from utilities.constants import NamespacesNames

pytestmark = [pytest.mark.sno, pytest.mark.post_upgrade, pytest.mark.skip_must_gather_collection, pytest.mark.arm64]


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
            pytest.param(
                f"namespaces/{NamespacesNames.OPENSHIFT}/imagestreamtags/{{name}}.yaml",
                ImageStreamTag,
                marks=(pytest.mark.polarion("CNV-9236")),
            ),
        ],
    )
    @pytest.mark.s390x
    def test_image_gather(self, admin_client, gathered_images, resource, resource_path):
        check_list_of_resources(
            dyn_client=admin_client,
            resource_type=resource,
            temp_dir=gathered_images,
            resource_path=resource_path,
            checks=VALIDATE_UID_NAME,
            filter_resource="redhat",
        )

import pytest
from kubernetes.client.rest import ApiException
from ocp_resources.pod import Pod

from utilities.storage import ErrorMsg

pytestmark = [pytest.mark.post_upgrade, pytest.mark.sno]


def check_pod_creation_failed(pod_name, client, namespace):
    with pytest.raises(
        ApiException,
        match=ErrorMsg.CANNOT_CREATE_RESOURCE,
    ):
        with Pod(
            name=pod_name,
            namespace=namespace.name,
            client=client,
            containers=[{"name": "dummy", "image": "kubevirt/cdi-importer:latest"}],
        ):
            return


@pytest.mark.polarion("CNV-4900")
@pytest.mark.s390x
def test_regular_user_cant_create_pod_in_ns(
    golden_images_namespace,
    unprivileged_client,
):
    check_pod_creation_failed(
        pod_name="pod-cnv-4900",
        client=unprivileged_client,
        namespace=golden_images_namespace,
    )


@pytest.mark.polarion("CNV-5276")
@pytest.mark.s390x
def test_regular_user_with_dv_create_rolebinding_cannot_create_pod_in_golden_image_ns(
    golden_images_namespace,
    golden_images_edit_rolebinding,
    unprivileged_client,
):
    check_pod_creation_failed(
        pod_name="pod-cnv-5276",
        client=unprivileged_client,
        namespace=golden_images_namespace,
    )

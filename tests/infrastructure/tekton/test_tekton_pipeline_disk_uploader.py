import pytest
from ocp_resources.resource import Resource

from utilities.constants import PVC

pytestmark = [pytest.mark.tier3, pytest.mark.special_infra]


@pytest.mark.parametrize(
    "pipelinerun_for_disk_uploader",
    [
        pytest.param("vm", marks=pytest.mark.polarion("CNV-11721")),
        pytest.param(PVC, marks=pytest.mark.polarion("CNV-11785")),
    ],
    indirect=True,
)
@pytest.mark.usefixtures("extracted_kubevirt_tekton_resources", "processed_yaml_files", "vm_for_disk_uploader")
@pytest.mark.s390x
def test_disk_uploader_pipelinerun(
    pipelinerun_for_disk_uploader,
    final_status_pipelinerun_for_disk_uploader,
):
    assert (
        final_status_pipelinerun_for_disk_uploader.status == Resource.Condition.Status.TRUE
        and final_status_pipelinerun_for_disk_uploader.type == Resource.Condition.Phase.SUCCEEDED
    ), f"Pipelines failed to succeed. Pipeline status: {final_status_pipelinerun_for_disk_uploader.instance.status}"

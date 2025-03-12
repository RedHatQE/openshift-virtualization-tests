import pytest
from ocp_resources.resource import Resource

pytestmark = [pytest.mark.tier3, pytest.mark.special_infra]


@pytest.mark.usefixtures("extracted_kubevirt_tekton_resources", "processed_yaml_files")
@pytest.mark.polarion("CNV-11721")
def test_disk_uploader_pipelinerun(
    vm_for_disk_uploader,
    pipelinerun_for_disk_uploader,
    final_status_pipelinerun_for_disk_uploader,
):
    assert (
        final_status_pipelinerun_for_disk_uploader.status == Resource.Condition.Status.TRUE
        and final_status_pipelinerun_for_disk_uploader.type == Resource.Condition.Phase.SUCCEEDED
    ), f"Pipelines failed to succeed. Pipeline status: {final_status_pipelinerun_for_disk_uploader.instance.status}"

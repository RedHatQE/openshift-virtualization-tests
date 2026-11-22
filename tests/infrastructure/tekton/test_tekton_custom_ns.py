"""
Tekton Pipeline Use Cases
"""

import pytest
from ocp_resources.pipeline import Pipeline
from ocp_resources.resource import Resource
from ocp_resources.task import Task

from tests.infrastructure.tekton.utils import (
    wait_for_tekton_resource_availability,
)
from utilities.constants.virt import (
    WIN_2K22,
    WIN_2K25,
    WIN_10,
    WIN_11,
)

pytestmark = [pytest.mark.tier3, pytest.mark.special_infra, pytest.mark.tekton]


@pytest.mark.usefixtures("extracted_kubevirt_tekton_resources", "processed_yaml_files")
@pytest.mark.dependency(name="TestTektonResources")
class TestTektonResources:
    def test_validate_tekton_pipeline_resources(
        self,
        unprivileged_client,
        custom_pipeline_namespace,
        cnv_tekton_pipelines_resource_matrix__class__,
    ):
        """
        Jira: https://redhat.atlassian.net/browse/CNV-43056 # <skip-jira-utils-check>
        Polarion: CNV-11254
        """
        wait_for_tekton_resource_availability(
            tekton_namespace=custom_pipeline_namespace,
            tekton_resource_kind=Pipeline,
            resource_name=cnv_tekton_pipelines_resource_matrix__class__,
            client=unprivileged_client,
        )

    def test_validate_tekton_tasks_resources(
        self,
        unprivileged_client,
        custom_pipeline_namespace,
        cnv_tekton_tasks_resource_matrix__class__,
    ):
        """
        Jira: https://redhat.atlassian.net/browse/CNV-43056 # <skip-jira-utils-check>
        Polarion: CNV-11252
        """
        wait_for_tekton_resource_availability(
            tekton_namespace=custom_pipeline_namespace,
            tekton_resource_kind=Task,
            resource_name=cnv_tekton_tasks_resource_matrix__class__,
            client=unprivileged_client,
        )


@pytest.mark.windows
@pytest.mark.dependency(depends=["TestTektonResources"])
class TestTektonEfiPipelineExecution:
    @pytest.mark.parametrize(
        "pipeline_dv_name",
        [
            WIN_10,
            WIN_11,
            WIN_2K22,
            WIN_2K25,
        ],
    )
    def test_run_pipelines_in_custom_namespace(
        self,
        resource_editor_efi_pipelines,
        custom_pipeline_namespace,
        pipelinerun_from_pipeline_template,
        final_status_pipelinerun,
    ):
        """
        Jira: https://redhat.atlassian.net/browse/CNV-47592 # <skip-jira-utils-check>
        Polarion: CNV-10373
        Polarion: CNV-10374
        Polarion: CNV-10375
        Polarion: CNV-11676
        """
        assert (
            final_status_pipelinerun.status == Resource.Condition.Status.TRUE
            and final_status_pipelinerun.type == Resource.Condition.Phase.SUCCEEDED
        ), f"Pipelines failed to succeed. Pipeline status: {final_status_pipelinerun.instance.status}"

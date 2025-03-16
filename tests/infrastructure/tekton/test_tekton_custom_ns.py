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
from utilities.constants import WIN_2K22, WIN_2K25, WIN_10, WIN_11

pytestmark = [pytest.mark.tier3, pytest.mark.special_infra]


@pytest.mark.usefixtures("extracted_kubevirt_tekton_resources", "processed_yaml_files")
@pytest.mark.dependency(name="TestTektonResources")
class TestTektonResources:
    @pytest.mark.polarion("CNV-11254")
    def test_validate_tekton_pipeline_resources(
        self,
        custom_pipeline_namespace,
        cnv_tekton_pipelines_resource_matrix__class__,
    ):
        wait_for_tekton_resource_availability(
            tekton_namespace=custom_pipeline_namespace,
            tekton_resource_kind=Pipeline,
            resource_name=cnv_tekton_pipelines_resource_matrix__class__,
        )

    @pytest.mark.polarion("CNV-11252")
    def test_validate_tekton_tasks_resources(
        self,
        custom_pipeline_namespace,
        cnv_tekton_tasks_resource_matrix__class__,
    ):
        wait_for_tekton_resource_availability(
            tekton_namespace=custom_pipeline_namespace,
            tekton_resource_kind=Task,
            resource_name=cnv_tekton_tasks_resource_matrix__class__,
        )


@pytest.mark.dependency(depends=["TestTektonResources"])
class TestTektonEfiPipelineExecution:
    @pytest.mark.parametrize(
        "pipeline_dv_name",
        [
            pytest.param(
                WIN_10,
                marks=pytest.mark.polarion("CNV-10373"),
            ),
            pytest.param(
                WIN_11,
                marks=pytest.mark.polarion("CNV-10374"),
            ),
            pytest.param(
                WIN_2K22,
                marks=pytest.mark.polarion("CNV-10375"),
            ),
            pytest.param(
                WIN_2K25,
                marks=pytest.mark.polarion("CNV-11676"),
            ),
        ],
    )
    def test_run_pipelines_in_custom_namespace(
        self,
        resource_editor_efi_pipelines,
        custom_pipeline_namespace,
        pipelinerun_from_pipeline_template,
        final_status_pipelinerun,
    ):
        assert (
            final_status_pipelinerun.status == Resource.Condition.Status.TRUE
            and final_status_pipelinerun.type == Resource.Condition.Phase.SUCCEEDED
        ), f"Pipelines failed to succeed. Pipeline status: {final_status_pipelinerun.instance.status}"

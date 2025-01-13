import logging
import shlex

import pytest
import yaml
from ocp_resources.datavolume import DataVolume
from ocp_resources.pipeline import Pipeline
from ocp_resources.pipelineruns import PipelineRun
from ocp_resources.resource import Resource, ResourceEditor
from ocp_resources.task import Task
from ocp_resources.virtual_machine import VirtualMachine
from pyhelper_utils.shell import run_command
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.infrastructure.tekton.utils import (
    filter_yaml_files,
    get_component_image_digest,
    process_yaml_files,
    win_iso_download_url_for_pipelineref,
    yaml_files_in_dir,
)
from utilities.constants import (
    BREW_REGISTERY_SOURCE,
    TEKTON_AVAILABLE_PIPELINEREF,
    TEKTON_AVAILABLE_TASKS,
    TIMEOUT_1MIN,
    TIMEOUT_50MIN,
    WINDOWS_EFI_INSTALLER_STR,
)
from utilities.infra import create_ns, get_artifactory_config_map, get_artifactory_secret, get_resources_by_name_prefix

LOGGER = logging.getLogger(__name__)

DATAVOLUME_TASK = "kubevirt-tekton-tasks-create-datavolume-rhel9"
DISK_VIRT_TASK = "kubevirt-tekton-tasks-disk-virt-customize-rhel9"
KUBEVIRT_TEKTON_AVAILABLE_TASKS_TEST = "kubevirt-tekton-tasks-test-rhel9"

COMMON_PIPELINEREF_PARAMS = {
    WINDOWS_EFI_INSTALLER_STR: {
        "useBiosMode": "false",
        "acceptEula": "True",
        "instanceTypeName": "u1.large",
        "instanceTypeKind": "VirtualMachineClusterInstancetype",
        "virtualMachinePreferenceKind": "VirtualMachineClusterPreference",
    },
}


@pytest.fixture(scope="session")
def datavolume_image_reference(csv_scope_session):
    return get_component_image_digest(component_name=DATAVOLUME_TASK, csv_object=csv_scope_session)


@pytest.fixture(scope="session")
def disk_virt_image_reference(csv_scope_session):
    return get_component_image_digest(component_name=DISK_VIRT_TASK, csv_object=csv_scope_session)


@pytest.fixture(scope="session")
def tekton_manifests_dir(tmp_path_factory):
    yield tmp_path_factory.mktemp("tekton_manifests")


@pytest.fixture(scope="session")
def csv_instance(csv_scope_session):
    return csv_scope_session.instance


@pytest.fixture(scope="session")
def extracted_tekton_test_image(csv_instance):
    annotation = csv_instance.metadata.annotations.get("test-images-nvrs", "")
    for image in annotation.split(","):
        if KUBEVIRT_TEKTON_AVAILABLE_TASKS_TEST in image:
            return f"{BREW_REGISTERY_SOURCE}/rh-osbs/container-native-virtualization-{image.strip()}"
    raise ValueError("Tekton test image not found in CSV annotations.")


@pytest.fixture(scope="session")
def extracted_virtio_image_container(csv_instance):
    for env_var in csv_instance.spec.install.spec.deployments[0].spec.template.spec.containers[0].env:
        if env_var["name"] == "VIRTIOWIN_CONTAINER":
            return env_var["value"]
    raise ValueError("VIRTIOWIN_CONTAINER environment variable not found in CSV object.")


@pytest.fixture(scope="session")
def extracted_kubevirt_tekton_resources(tekton_manifests_dir, extracted_tekton_test_image, generated_pulled_secret):
    run_command(
        command=shlex.split(
            f"oc image extract --registry-config={generated_pulled_secret} "
            f"--path release/*:{tekton_manifests_dir} {extracted_tekton_test_image}"
        )
    )


@pytest.fixture(scope="module")
def pipelines_yaml_files(tekton_manifests_dir):
    return filter_yaml_files(
        all_yaml_files=yaml_files_in_dir(root_dir=tekton_manifests_dir, sub_dir="pipelines"),
        included_patterns=[f"{pipelines_ref}.yaml" for pipelines_ref in TEKTON_AVAILABLE_PIPELINEREF],
    )


@pytest.fixture(scope="module")
def tasks_yaml_files(tekton_manifests_dir):
    return filter_yaml_files(
        all_yaml_files=yaml_files_in_dir(root_dir=tekton_manifests_dir, sub_dir="tasks"),
        included_patterns=[f"{tasks_ref}.yaml" for tasks_ref in TEKTON_AVAILABLE_TASKS],
    )


@pytest.fixture(scope="module")
def processed_yaml_files(
    custom_pipeline_namespace,
    tekton_manifests_dir,
    datavolume_image_reference,
    disk_virt_image_reference,
    extracted_virtio_image_container,
    pipelines_yaml_files,
    tasks_yaml_files,
):
    tekton_resources_dict = {
        Pipeline: {
            "files": pipelines_yaml_files,
            "replacements": {
                r"default:\s*quay\.io/kubevirt/virtio-container-disk:v\d+\.\d+\.\d+": "default: "
                f"{extracted_virtio_image_container}",
            },
        },
        Task: {
            "files": tasks_yaml_files,
            "replacements": {
                r'image: "quay\.io/kubevirt/tekton-tasks:[^"]*"': f"image: {datavolume_image_reference}",
                r'image: "quay\.io/kubevirt/tekton-tasks-disk-virt:[^"]*"': f"image: {disk_virt_image_reference}",
            },
        },
    }

    resources = {Pipeline: [], Task: []}

    for resource_kind, config in tekton_resources_dict.items():
        resources[resource_kind] = process_yaml_files(
            file_paths=config["files"],
            replacements=config["replacements"],
            resource_kind=resource_kind,
            namespace=custom_pipeline_namespace.name,
        )

    yield resources

    for kind, kind_resources in resources.items():
        for resource in kind_resources:
            kind(name=resource.metadata.name, namespace=custom_pipeline_namespace.name).delete(wait=True)


@pytest.fixture(scope="module")
def resource_editor_efi_pipelines(
    custom_pipeline_namespace,
    artifactory_secret_custom_pipeline_namespace,
    artifactory_config_map_custom_pipeline_namespace,
):
    pipeline = Pipeline(name=WINDOWS_EFI_INSTALLER_STR, namespace=custom_pipeline_namespace.name)
    pipeline_dict = pipeline.instance.to_dict()

    for task in pipeline_dict["spec"]["tasks"]:
        if task["name"] == "import-win-iso":
            for param in task["params"]:
                if param["name"] == "manifest":
                    manifest = yaml.safe_load(param["value"])
                    if manifest["spec"]["source"]["http"]["url"] == "$(params.winImageDownloadURL)":
                        manifest["spec"]["source"]["http"]["secretRef"] = (
                            artifactory_secret_custom_pipeline_namespace.name
                        )
                        manifest["spec"]["source"]["http"]["certConfigMap"] = (
                            artifactory_config_map_custom_pipeline_namespace.name
                        )
                    param["value"] = yaml.dump(manifest)

    with ResourceEditor(patches={pipeline: {"spec": {"tasks": pipeline_dict["spec"]["tasks"]}}}):
        yield pipeline


@pytest.fixture(scope="module")
def custom_pipeline_namespace(admin_client):
    yield from create_ns(name="test-custom-pipeline-ns", admin_client=admin_client)


@pytest.fixture(scope="module")
def artifactory_secret_custom_pipeline_namespace(custom_pipeline_namespace):
    artifactory_secret = get_artifactory_secret(namespace=custom_pipeline_namespace.name)
    yield artifactory_secret
    if artifactory_secret.exists:
        artifactory_secret.clean_up()


@pytest.fixture(scope="module")
def artifactory_config_map_custom_pipeline_namespace(custom_pipeline_namespace):
    artifactory_config_map = get_artifactory_config_map(namespace=custom_pipeline_namespace.name)
    yield artifactory_config_map
    if artifactory_config_map.exists:
        artifactory_config_map.clean_up()


@pytest.fixture()
def pipeline_dv_name(request):
    return request.param


@pytest.fixture()
def configured_windows_efi_pipelinerun_parameters(
    pipeline_dv_name,
    extracted_virtio_image_container,
):
    windows_version = pipeline_dv_name.split("win")[1]
    autounattend_type = "efi-" if windows_version == "10" else ""
    params_dict = {
        "autounattendConfigMapName": f"windows{windows_version}-{autounattend_type}autounattend",
        "baseDvName": f"win{windows_version}",
        "isoDVName": f"win{windows_version}",
        "preferenceName": f"windows.{windows_version}.virtio",
        "virtioContainerDiskName": extracted_virtio_image_container,
        **COMMON_PIPELINEREF_PARAMS[WINDOWS_EFI_INSTALLER_STR],
        **win_iso_download_url_for_pipelineref()[pipeline_dv_name],
    }
    return params_dict


@pytest.fixture()
def pipelinerun_from_pipeline_template(
    admin_client,
    pipeline_dv_name,
    custom_pipeline_namespace,
    configured_windows_efi_pipelinerun_parameters,
):
    with PipelineRun(
        name=f"{WINDOWS_EFI_INSTALLER_STR}-{pipeline_dv_name.split('win')[1]}-test",
        namespace=custom_pipeline_namespace.name,
        client=admin_client,
        params=configured_windows_efi_pipelinerun_parameters,
        pipelineref=WINDOWS_EFI_INSTALLER_STR,
    ) as pipelinerun:
        pipelinerun.wait_for_conditions()
        yield pipelinerun

    [
        vm.delete(wait=True)
        for vm in get_resources_by_name_prefix(
            prefix=WINDOWS_EFI_INSTALLER_STR,
            namespace=custom_pipeline_namespace.name,
            api_resource_name=VirtualMachine,
        )
        if vm.exists
    ]
    [
        dv.delete(wait=True)
        for dv in get_resources_by_name_prefix(
            prefix=pipeline_dv_name,
            namespace=custom_pipeline_namespace.name,
            api_resource_name=DataVolume,
        )
    ]


@pytest.fixture()
def final_status_pipelinerun(pipelinerun_from_pipeline_template):
    try:
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_50MIN,
            sleep=TIMEOUT_1MIN,
            func=lambda: pipelinerun_from_pipeline_template.instance.status.conditions[0],
        ):
            if sample and sample["status"] != Resource.Condition.Status.UNKNOWN:
                # There are 3 conditions.status possible : Unknown, False, True.
                LOGGER.info(f"PipelineRun Condition : {sample}")
                return sample

    except TimeoutExpiredError:
        LOGGER.error(
            f"Pipelinerun: {pipelinerun_from_pipeline_template.name} , "
            f"Preparing for VM teardown due to Timeout Error.Last available sample: {sample}"
        )
        raise

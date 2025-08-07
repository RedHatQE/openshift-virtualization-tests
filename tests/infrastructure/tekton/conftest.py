import logging
import os
import shlex

import pytest
import yaml
from ocp_resources.data_source import DataSource
from ocp_resources.datavolume import DataVolume
from ocp_resources.pipeline import Pipeline
from ocp_resources.pipeline_run import PipelineRun
from ocp_resources.resource import ResourceEditor
from ocp_resources.secret import Secret
from ocp_resources.task import Task
from ocp_resources.virtual_machine import VirtualMachine
from pyhelper_utils.shell import run_command
from pytest_testconfig import py_config

from tests.infrastructure.tekton.utils import (
    filter_yaml_files,
    get_component_image_digest,
    process_yaml_files,
    wait_for_final_status_pipelinerun,
    win_iso_download_url_for_pipelineref,
    yaml_files_in_dir,
)
from utilities.constants import (
    BREW_REGISTERY_SOURCE,
    OS_FLAVOR_FEDORA,
    TEKTON_AVAILABLE_PIPELINEREF,
    TEKTON_AVAILABLE_TASKS,
    TIMEOUT_1MIN,
    TIMEOUT_2MIN,
    TIMEOUT_10MIN,
    TIMEOUT_30SEC,
    TIMEOUT_50MIN,
    WINDOWS_EFI_INSTALLER_STR,
)
from utilities.infra import (
    base64_encode_str,
    create_ns,
    get_artifactory_config_map,
    get_artifactory_secret,
    get_resources_by_name_prefix,
)
from utilities.storage import data_volume_template_with_source_ref_dict
from utilities.virt import VirtualMachineForTests

LOGGER = logging.getLogger(__name__)

DATAVOLUME_TASK = "kubevirt-tekton-tasks-create-datavolume-rhel9"
DISK_VIRT_TASK = "kubevirt-tekton-tasks-disk-virt-customize-rhel9"
KUBEVIRT_TEKTON_AVAILABLE_TASKS_TEST = "kubevirt-tekton-tasks-test-rhel9"
DISK_UPLOADER_TASK = "disk-uploader"
EXPORT_SOURCE_KIND = "EXPORT_SOURCE_KIND"
EXPORT_SOURCE_NAME = "EXPORT_SOURCE_NAME"
VOLUME_NAME = "VOLUME_NAME"
IMAGE_DESTINATION = "IMAGE_DESTINATION"
PUSH_TIMEOUT = "PUSH_TIMEOUT"
SECRET_NAME = "SECRET_NAME"


COMMON_PIPELINEREF_PARAMS = {
    WINDOWS_EFI_INSTALLER_STR: {
        "useBiosMode": "false",
        "acceptEula": "True",
        "instanceTypeName": "u1.large",
        "instanceTypeKind": "VirtualMachineClusterInstancetype",
        "virtualMachinePreferenceKind": "VirtualMachineClusterPreference",
    },
}


DISK_UPLOADER_PIPELINE_PARAMS = [
    {"name": EXPORT_SOURCE_KIND, "type": "string"},
    {"name": EXPORT_SOURCE_NAME, "type": "string"},
    {"name": VOLUME_NAME, "type": "string"},
    {"name": IMAGE_DESTINATION, "type": "string"},
    {"name": PUSH_TIMEOUT, "type": "string", "default": TIMEOUT_2MIN},
    {"name": SECRET_NAME, "type": "string"},
]

DISK_UPLOADER_PIPELINE_TASK = [
    {
        "name": DISK_UPLOADER_TASK,
        "params": [
            {"name": EXPORT_SOURCE_KIND, "value": f"$(params.{EXPORT_SOURCE_KIND})"},
            {"name": EXPORT_SOURCE_NAME, "value": f"$(params.{EXPORT_SOURCE_NAME})"},
            {"name": VOLUME_NAME, "value": f"$(params.{VOLUME_NAME})"},
            {"name": IMAGE_DESTINATION, "value": f"$(params.{IMAGE_DESTINATION})"},
            {"name": PUSH_TIMEOUT, "value": f"$(params.{PUSH_TIMEOUT})"},
            {"name": SECRET_NAME, "value": f"$(params.{SECRET_NAME})"},
        ],
        "taskRef": {"kind": "Task", "name": DISK_UPLOADER_TASK},
    }
]


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
    return [{"name": key, "value": value} for key, value in params_dict.items()]


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
        pipeline_ref={"name": WINDOWS_EFI_INSTALLER_STR},
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


@pytest.fixture(scope="module")
def quay_disk_uploader_secret(custom_pipeline_namespace):
    with Secret(
        name="quay-disk-uploader-secret",
        namespace=custom_pipeline_namespace.name,
        accesskeyid=base64_encode_str(os.environ["QUAY_ACCESS_KEY_TEKTON_TASKS"]),
        secretkey=base64_encode_str(os.environ["QUAY_SECRET_KEY_TEKTON_TASKS"]),
    ) as quay_disk_uploader_secret:
        yield quay_disk_uploader_secret


@pytest.fixture(scope="module")
def vm_for_disk_uploader(admin_client, custom_pipeline_namespace, golden_images_namespace):
    with VirtualMachineForTests(
        name="fedora-vm-diskuploader",
        namespace=custom_pipeline_namespace.name,
        client=admin_client,
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=DataSource(name=OS_FLAVOR_FEDORA, namespace=golden_images_namespace.name),
            storage_class=py_config["default_storage_class"],
        ),
        vm_instance_type_infer=True,
        vm_preference_infer=True,
    ) as vm:
        yield vm


@pytest.fixture(scope="module")
def pipeline_disk_uploader(
    admin_client,
    custom_pipeline_namespace,
):
    with Pipeline(
        name="pipeline-disk-uploader",
        namespace=custom_pipeline_namespace.name,
        client=admin_client,
        tasks=DISK_UPLOADER_PIPELINE_TASK,
        params=DISK_UPLOADER_PIPELINE_PARAMS,
    ) as pipeline:
        yield pipeline


@pytest.fixture()
def pipelinerun_for_disk_uploader(
    admin_client,
    custom_pipeline_namespace,
    quay_disk_uploader_secret,
    pipeline_disk_uploader,
    vm_for_disk_uploader,
    request,
):
    pipeline_run_params = {
        EXPORT_SOURCE_KIND: request.param,
        EXPORT_SOURCE_NAME: (vm_for_disk_uploader.name if request.param == "vm" else OS_FLAVOR_FEDORA),
        VOLUME_NAME: OS_FLAVOR_FEDORA,
        IMAGE_DESTINATION: "quay.io/openshift-cnv/tekton-tasks",
        SECRET_NAME: quay_disk_uploader_secret.name,
    }

    with PipelineRun(
        name=f"pipelinerun-disk-uploader-{request.param}",
        namespace=custom_pipeline_namespace.name,
        client=admin_client,
        params=[{"name": key, "value": value} for key, value in pipeline_run_params.items()],
        pipeline_ref={"name": pipeline_disk_uploader.name},
    ) as pipelinerun:
        pipelinerun.wait_for_conditions()
        yield pipelinerun


@pytest.fixture()
def final_status_pipelinerun(pipelinerun_from_pipeline_template):
    return wait_for_final_status_pipelinerun(
        pipelinerun=pipelinerun_from_pipeline_template, wait_timeout=TIMEOUT_50MIN, sleep_interval=TIMEOUT_1MIN
    )


@pytest.fixture()
def final_status_pipelinerun_for_disk_uploader(pipelinerun_for_disk_uploader):
    return wait_for_final_status_pipelinerun(
        pipelinerun=pipelinerun_for_disk_uploader, wait_timeout=TIMEOUT_10MIN, sleep_interval=TIMEOUT_30SEC
    )

import pytest
from ocp_resources.data_source import DataSource
from ocp_resources.datavolume import DataVolume
from ocp_resources.resource import Resource
from ocp_resources.validating_admission_policy import ValidatingAdmissionPolicy
from ocp_resources.validating_admission_policy_binding import ValidatingAdmissionPolicyBinding
from ocp_resources.virtual_machine_cluster_instancetype import (
    VirtualMachineClusterInstancetype,
)
from ocp_resources.virtual_machine_cluster_preference import (
    VirtualMachineClusterPreference,
)
from pytest_testconfig import config as py_config

from utilities.artifactory import (
    cleanup_artifactory_secret_and_config_map,
    get_artifactory_config_map,
    get_artifactory_secret,
    get_test_artifact_server_url,
)
from utilities.constants import CONTAINER_DISK_IMAGE_PATH_STR, OS_FLAVOR_WIN_CONTAINER_DISK, Images
from utilities.storage import (
    create_dummy_first_consumer_pod,
    data_volume_template_with_source_ref_dict,
    generate_data_source_dict,
    sc_volume_binding_mode_is_wffc,
)
from utilities.virt import VirtualMachineForTests

COMMON_INSTANCETYPE_SELECTOR = f"{Resource.ApiGroup.INSTANCETYPE_KUBEVIRT_IO}/vendor=redhat.com"


@pytest.fixture(scope="session")
def base_vm_cluster_preferences(unprivileged_client):
    return list(
        VirtualMachineClusterPreference.get(
            client=unprivileged_client,
            label_selector=COMMON_INSTANCETYPE_SELECTOR,
        )
    )


@pytest.fixture(scope="session")
def base_vm_cluster_instancetypes(unprivileged_client):
    return list(
        VirtualMachineClusterInstancetype.get(
            client=unprivileged_client,
            label_selector=COMMON_INSTANCETYPE_SELECTOR,
        )
    )


@pytest.fixture(scope="class")
def windows_validating_admission_policy(admin_client):
    with ValidatingAdmissionPolicy(
        client=admin_client,
        name="windows-vcpu-overcommit",
        failure_policy="Fail",
        match_conditions=[
            {
                "expression": (
                    "(('kubevirt.io/preference-name' in object.metadata.annotations) && "
                    "(object.metadata.annotations['kubevirt.io/preference-name'].lowerAscii().contains('windows'))) || "
                    "(('kubevirt.io/cluster-preference-name' in object.metadata.annotations) && "
                    "(object.metadata.annotations['kubevirt.io/cluster-preference-name']"
                    ".lowerAscii().contains('windows'))) || "
                    "(('vm.kubevirt.io/os' in object.metadata.annotations) && "
                    "(object.metadata.annotations['vm.kubevirt.io/os'].lowerAscii().contains('windows')))"
                ),
                "name": "windows-vcpu-overcommit",
            }
        ],
        match_constraints={
            "resourceRules": [
                {
                    "apiGroups": ["kubevirt.io"],
                    "apiVersions": ["*"],
                    "operations": ["CREATE", "UPDATE"],
                    "resources": ["virtualmachineinstances"],
                }
            ]
        },
        validations=[
            {
                "expression": (
                    "has(object.spec.domain.cpu.dedicatedCpuPlacement) && "
                    "object.spec.domain.cpu.dedicatedCpuPlacement == true"
                ),
                "message": (
                    "Windows VMIs require dedicated CPU placement. Set spec.domain.cpu.dedicatedCpuPlacement to true."
                ),
            }
        ],
    ) as vap:
        yield vap


@pytest.fixture(scope="class")
def windows_validating_admission_policy_binding(admin_client):
    with ValidatingAdmissionPolicyBinding(
        client=admin_client,
        name="windows-vcpu-overcommit-binding",
        policy_name="windows-vcpu-overcommit",
        validation_actions=["Deny"],
    ) as vapb:
        yield vapb


@pytest.fixture(scope="class")
def latest_windows_data_volume(
    unprivileged_client,
    default_sc,
    namespace,
):
    secret = get_artifactory_secret(namespace=namespace.name)
    cert = get_artifactory_config_map(namespace=namespace.name)
    with DataVolume(
        client=unprivileged_client,
        name="latest-windows",
        namespace=namespace.name,
        api_name="storage",
        source="registry",
        size=Images.Windows.CONTAINER_DISK_DV_SIZE,
        storage_class=default_sc.name,
        url=f"{get_test_artifact_server_url(schema='registry')}/"
        f"{py_config['latest_windows_os_dict'][CONTAINER_DISK_IMAGE_PATH_STR]}",
        secret=secret,
        cert_configmap=cert.name,
    ) as win_dv:
        if sc_volume_binding_mode_is_wffc(sc=default_sc.name, client=win_dv.client):
            create_dummy_first_consumer_pod(pvc=win_dv.pvc)
        yield win_dv
    cleanup_artifactory_secret_and_config_map(artifactory_secret=secret, artifactory_config_map=cert)


@pytest.fixture(scope="class")
def latest_windows_data_source(
    unprivileged_client,
    latest_windows_data_volume,
):
    with DataSource(
        name="latest-windows",
        namespace=latest_windows_data_volume.namespace,
        client=unprivileged_client,
        source=generate_data_source_dict(dv=latest_windows_data_volume),
    ) as win_ds:
        yield win_ds


@pytest.fixture()
def windows_vm_for_dedicated_cpu(request, unprivileged_client, namespace, latest_windows_data_source):
    instance_type_name = request.param["instance_type_name"]
    with VirtualMachineForTests(
        client=unprivileged_client,
        name=request.param["vm_name"],
        namespace=namespace.name,
        vm_instance_type=VirtualMachineClusterInstancetype(client=unprivileged_client, name=instance_type_name),
        vm_preference=VirtualMachineClusterPreference(client=unprivileged_client, name="windows.2k19"),
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=latest_windows_data_source,
        ),
        os_flavor=OS_FLAVOR_WIN_CONTAINER_DISK,
        disk_type=None,
    ) as vm:
        yield vm

import pytest
from ocp_resources.cluster_role import ClusterRole
from ocp_resources.data_source import DataSource
from ocp_resources.datavolume import DataVolume
from ocp_resources.namespace import Namespace
from ocp_resources.resource import Resource
from ocp_resources.role_binding import RoleBinding
from ocp_resources.validating_admission_policy import ValidatingAdmissionPolicy
from ocp_resources.validating_admission_policy_binding import ValidatingAdmissionPolicyBinding
from ocp_resources.virtual_machine_cluster_instancetype import (
    VirtualMachineClusterInstancetype,
)
from ocp_resources.virtual_machine_cluster_preference import (
    VirtualMachineClusterPreference,
)
from pytest_testconfig import config as py_config

from tests.infrastructure.instance_types.constants import WINDOWS_DEDICATED_CPU_MESSAGE, WINDOWS_VCPU_OVERCOMMIT_STR
from utilities.artifactory import (
    cleanup_artifactory_secret_and_config_map,
    get_artifactory_config_map,
    get_artifactory_secret,
    get_test_artifact_server_url,
)
from utilities.constants import (
    CONTAINER_DISK_IMAGE_PATH_STR,
    OS_FLAVOR_RHEL,
    OS_FLAVOR_WIN_CONTAINER_DISK,
    TIMEOUT_15MIN,
    Images,
)
from utilities.storage import (
    create_dummy_first_consumer_pod,
    data_volume_template_with_source_ref_dict,
    generate_data_source_dict,
    sc_volume_binding_mode_is_wffc,
)
from utilities.virt import VirtualMachineForTests

COMMON_INSTANCETYPE_SELECTOR = f"{Resource.ApiGroup.INSTANCETYPE_KUBEVIRT_IO}/vendor=redhat.com"
LATEST_WINDOWS_IMAGE_NAMESPACE = "latest-windows-image"


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
        name=WINDOWS_VCPU_OVERCOMMIT_STR,
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
                "name": WINDOWS_VCPU_OVERCOMMIT_STR,
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
                "message": WINDOWS_DEDICATED_CPU_MESSAGE,
            }
        ],
    ) as vap:
        yield vap


@pytest.fixture(scope="class")
def windows_validating_admission_policy_binding(admin_client):
    with ValidatingAdmissionPolicyBinding(
        client=admin_client,
        name=f"{WINDOWS_VCPU_OVERCOMMIT_STR}-binding",
        policy_name=WINDOWS_VCPU_OVERCOMMIT_STR,
        validation_actions=["Deny"],
    ) as vapb:
        yield vapb


@pytest.fixture(scope="session")
def windows_test_images_namespace(admin_client):
    windows_images_namespace = Namespace(
        client=admin_client,
        name=LATEST_WINDOWS_IMAGE_NAMESPACE,
    )
    if windows_images_namespace.exists:
        yield windows_images_namespace
    else:
        with windows_images_namespace as win_namespace:
            yield win_namespace


@pytest.fixture(scope="session")
def windows_test_images_namespace_role_binding(admin_client, windows_test_images_namespace):
    windows_images_view_role_binding = RoleBinding(
        client=admin_client,
        name="windows-test-images-view",
        namespace=windows_test_images_namespace.name,
        subjects_kind="Group",
        subjects_name="system:authenticated",
        role_ref_kind=ClusterRole.kind,
        role_ref_name="view",
    )
    if windows_images_view_role_binding.exists:
        yield windows_images_view_role_binding
    else:
        with windows_images_view_role_binding as win_view_role_binding:
            yield win_view_role_binding


@pytest.fixture(scope="session")
def latest_windows_data_volume(
    admin_client,
    default_sc,
    windows_test_images_namespace_role_binding,
    windows_namespace_artifactory_secret_and_configmap,
):
    windows_data_volume = DataVolume(
        client=admin_client,
        name="latest-windows",
        namespace=windows_test_images_namespace_role_binding.namespace,
        api_name="storage",
        source="registry",
        size=Images.Windows.CONTAINER_DISK_DV_SIZE,
        storage_class=default_sc.name,
        url=f"{get_test_artifact_server_url(schema='registry')}/"
        f"{py_config['latest_windows_os_dict'][CONTAINER_DISK_IMAGE_PATH_STR]}",
        secret=windows_namespace_artifactory_secret_and_configmap["secret"],
        cert_configmap=windows_namespace_artifactory_secret_and_configmap["config_map"].name,
    )
    if windows_data_volume.exists:
        yield windows_data_volume
    else:
        with windows_data_volume as win_dv:
            if sc_volume_binding_mode_is_wffc(sc=default_sc.name, client=windows_data_volume.client):
                create_dummy_first_consumer_pod(pvc=windows_data_volume.pvc)
            yield win_dv


@pytest.fixture(scope="session")
def latest_windows_data_source(
    admin_client,
    latest_windows_data_volume,
):
    windows_data_source = DataSource(
        name=latest_windows_data_volume.name,
        namespace=latest_windows_data_volume.namespace,
        client=admin_client,
        source=generate_data_source_dict(dv=latest_windows_data_volume),
    )
    if windows_data_source.exists:
        yield windows_data_source
    else:
        with windows_data_source as win_ds:
            windows_data_source.wait_for_condition(
                condition=windows_data_source.Condition.READY,
                status=windows_data_source.Condition.Status.TRUE,
                timeout=TIMEOUT_15MIN,
            )
            yield win_ds


@pytest.fixture()
def windows_vm_for_dedicated_cpu(request, unprivileged_client, namespace, latest_windows_data_source):
    with VirtualMachineForTests(
        client=unprivileged_client,
        name=request.param["vm_name"],
        namespace=namespace.name,
        vm_instance_type=VirtualMachineClusterInstancetype(
            client=unprivileged_client, name=request.param["instance_type_name"]
        ),
        vm_preference_infer=True,
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=latest_windows_data_source,
        ),
        os_flavor=OS_FLAVOR_WIN_CONTAINER_DISK,
        disk_type=None,
    ) as vm:
        vm.start()
        yield vm


@pytest.fixture()
def rhel_vm_for_dedicated_cpu(unprivileged_client, namespace, latest_rhel_data_source):
    with VirtualMachineForTests(
        client=unprivileged_client,
        name="rhel-d1-vm",
        namespace=namespace.name,
        vm_instance_type=VirtualMachineClusterInstancetype(client=unprivileged_client, name="d1.large"),
        vm_preference_infer=True,
        data_volume_template=data_volume_template_with_source_ref_dict(
            data_source=latest_rhel_data_source,
        ),
        os_flavor=OS_FLAVOR_RHEL,
    ) as vm:
        vm.start()
        yield vm


@pytest.fixture(scope="session")
def windows_namespace_artifactory_secret_and_configmap(windows_test_images_namespace_role_binding):
    secret = get_artifactory_secret(namespace=windows_test_images_namespace_role_binding.namespace)
    cert = get_artifactory_config_map(namespace=windows_test_images_namespace_role_binding.namespace)
    yield {"secret": secret, "config_map": cert}
    cleanup_artifactory_secret_and_config_map(
        artifactory_secret=secret,
        artifactory_config_map=cert,
    )

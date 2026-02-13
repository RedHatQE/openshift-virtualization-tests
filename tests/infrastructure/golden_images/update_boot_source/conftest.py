import logging

import pytest
from kubernetes.dynamic.exceptions import NotFoundError
from ocp_resources.cdi import CDI
from ocp_resources.data_import_cron import DataImportCron
from ocp_resources.data_source import DataSource
from ocp_resources.datavolume import DataVolume
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_resources.resource import ResourceEditor
from ocp_resources.ssp import SSP
from pytest_testconfig import py_config
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.infrastructure.golden_images.update_boot_source.utils import (
    generate_data_import_cron_dict,
    get_all_dic_volume_names,
    get_all_release_versions_from_docs,
)
from utilities.constants import (
    BIND_IMMEDIATE_ANNOTATION,
    DEFAULT_FEDORA_REGISTRY_URL,
    TIMEOUT_1MIN,
    TIMEOUT_2MIN,
    TIMEOUT_5SEC,
    TIMEOUT_10MIN,
    Images,
)
from utilities.hco import (
    ResourceEditorValidateHCOReconcile,
    enable_common_boot_image_import_spec_wait_for_data_import_cron,
)
from utilities.infra import create_ns
from utilities.ssp import (
    wait_for_condition_message_value,
)
from utilities.storage import data_volume_template_with_source_ref_dict
from utilities.virt import VirtualMachineForTests, running_vm

LOGGER = logging.getLogger(__name__)


@pytest.fixture()
def enabled_common_boot_image_import_feature_gate_scope_function(
    admin_client,
    hyperconverged_resource_scope_function,
    golden_images_namespace,
):
    enable_common_boot_image_import_spec_wait_for_data_import_cron(
        hco_resource=hyperconverged_resource_scope_function,
        admin_client=admin_client,
        namespace=golden_images_namespace,
    )


@pytest.fixture(scope="class")
def enabled_common_boot_image_import_feature_gate_scope_class(
    admin_client,
    hyperconverged_resource_scope_class,
    golden_images_namespace,
):
    enable_common_boot_image_import_spec_wait_for_data_import_cron(
        hco_resource=hyperconverged_resource_scope_class,
        admin_client=admin_client,
        namespace=golden_images_namespace,
    )


@pytest.fixture()
def updated_hco_with_custom_data_import_cron_scope_function(request, hyperconverged_resource_scope_function):
    data_import_cron_dict = generate_data_import_cron_dict(
        name=request.param["data_import_cron_name"],
        source_url=request.param["data_import_cron_source_url"],
        managed_data_source_name=request.param["managed_data_source_name"],
    )
    with ResourceEditorValidateHCOReconcile(
        patches={
            hyperconverged_resource_scope_function: {"spec": {"dataImportCronTemplates": [data_import_cron_dict]}}
        },
        list_resource_reconcile=[SSP, CDI],
    ):
        yield data_import_cron_dict


@pytest.fixture()
def custom_data_import_cron_scope_function(
    admin_client,
    golden_images_namespace,
    updated_hco_with_custom_data_import_cron_scope_function,
):
    expected_data_import_cron_name = updated_hco_with_custom_data_import_cron_scope_function["metadata"]["name"]
    for sample in TimeoutSampler(
        wait_timeout=TIMEOUT_2MIN,
        sleep=5,
        func=lambda: list(
            DataImportCron.get(
                client=admin_client,
                name=expected_data_import_cron_name,
                namespace=golden_images_namespace.name,
            )
        ),
        exceptions_dict={NotFoundError: []},
    ):
        if sample:
            return sample[0]


@pytest.fixture()
def custom_data_source_scope_function(admin_client, custom_data_import_cron_scope_function):
    custom_data_source_name = custom_data_import_cron_scope_function.instance.spec.managedDataSource
    try:
        return list(
            DataSource.get(
                client=admin_client,
                name=custom_data_source_name,
                namespace=custom_data_import_cron_scope_function.namespace,
            )
        )[0]
    except NotFoundError:
        LOGGER.error(
            f"DataSource {custom_data_source_name} is not found under "
            f"{custom_data_import_cron_scope_function.namespace} namespace."
        )
        raise


@pytest.fixture(scope="module")
def latest_rhel_release_versions_dict():
    """
    Parse RHEL documentation pages to find the latest released versions.

    Returns:
        Dictionary mapping major versions to their latest minor versions
        e.g., {rhel8: "8.10", rhel9: "9.7", rhel10: "10.1"}
    """
    latest_versions = {}

    for major_ver_num in [8, 9, 10]:
        all_versions = get_all_release_versions_from_docs(major_ver_num=major_ver_num)
        if not all_versions:
            raise ValueError(f"Failed to find RHEL {major_ver_num} versions from documentation")
        latest_versions[major_ver_num] = max(all_versions)

    return {f"rhel{major}": f"{major}.{minor}" for major, minor in latest_versions.items()}


@pytest.fixture()
def failed_volume_creation(custom_data_import_cron_scope_function):
    LOGGER.info("Verify volume was not created.")
    wait_for_condition_message_value(
        resource=custom_data_import_cron_scope_function,
        expected_message="No current import",
    )


@pytest.fixture()
def updated_data_import_cron(
    updated_hco_with_custom_data_import_cron_scope_function,
    hyperconverged_resource_scope_function,
):
    updated_hco_with_custom_data_import_cron_scope_function["spec"]["template"]["spec"]["source"]["registry"]["url"] = (
        DEFAULT_FEDORA_REGISTRY_URL
    )
    with ResourceEditor(
        patches={
            hyperconverged_resource_scope_function: {
                "spec": {"dataImportCronTemplates": [updated_hco_with_custom_data_import_cron_scope_function]}
            }
        }
    ):
        yield


@pytest.fixture()
def reconciled_custom_data_source(custom_data_source_scope_function):
    try:
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_10MIN,
            sleep=TIMEOUT_5SEC,
            func=lambda: custom_data_source_scope_function.source.exists,
        ):
            if sample:
                return
    except TimeoutExpiredError:
        LOGGER.error(
            f"DataSource '{custom_data_source_scope_function.name}' was not reconciled "
            f"to reference a PVC or VolumeSnapshot, "
            f"DataSource spec: {custom_data_source_scope_function.instance.spec}"
        )
        raise


@pytest.fixture()
def vm_from_custom_data_import_cron(custom_data_source_scope_function, namespace, unprivileged_client):
    with VirtualMachineForTests(
        name=f"{custom_data_source_scope_function.name}-vm",
        namespace=namespace.name,
        client=unprivileged_client,
        memory_guest=Images.Fedora.DEFAULT_MEMORY_SIZE,
        data_volume_template=data_volume_template_with_source_ref_dict(data_source=custom_data_source_scope_function),
    ) as vm:
        running_vm(vm=vm)
        yield vm


@pytest.fixture()
def data_import_cron_namespace(admin_client, unprivileged_client):
    yield from create_ns(
        admin_client=admin_client,
        unprivileged_client=unprivileged_client,
        name="data-import-cron-using-default-sc",
    )


@pytest.fixture()
def created_persistent_volume_claim(unprivileged_client, data_import_cron_namespace):
    def _get_first_pvc():
        return next(
            PersistentVolumeClaim.get(
                client=unprivileged_client,
                namespace=data_import_cron_namespace.name,
            ),
            None,
        )

    try:
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_1MIN,
            sleep=TIMEOUT_5SEC,
            func=_get_first_pvc,
        ):
            if sample:
                created_dv = DataVolume(
                    name=sample.name,
                    namespace=sample.namespace,
                    client=unprivileged_client,
                    api_name="pvc",
                )
                created_dv.wait_for_dv_success()
                yield sample
                created_dv.clean_up()
                return
    except TimeoutExpiredError:
        LOGGER.error(f"No PVCs were created in {data_import_cron_namespace.name}")
        raise


@pytest.fixture(scope="class")
def golden_images_data_import_cron_spec(
    golden_images_data_import_crons_scope_class,
):
    assert golden_images_data_import_crons_scope_class, (
        f"No data import cron job found in {py_config['golden_images_namespace']}"
    )
    selected_dic = min(golden_images_data_import_crons_scope_class, key=lambda dic: dic.name)
    LOGGER.info(f"Using spec from DataImportCron '{selected_dic.name}' as template")
    return selected_dic.instance.spec


@pytest.fixture()
def created_data_import_cron(
    unprivileged_client,
    data_import_cron_namespace,
    golden_images_data_import_cron_spec,
):
    cron_template_spec = golden_images_data_import_cron_spec.template.spec
    with DataImportCron(
        name="data-import-cron-for-test",
        namespace=data_import_cron_namespace.name,
        managed_data_source=golden_images_data_import_cron_spec.managedDataSource,
        schedule=golden_images_data_import_cron_spec.schedule,
        annotations=BIND_IMMEDIATE_ANNOTATION,
        template={
            "spec": {
                "source": {
                    "registry": {
                        "url": cron_template_spec.source.registry.url,
                        "pullMethod": "node",
                    }
                },
                "storage": {
                    "resources": {"requests": {"storage": cron_template_spec.storage.resources.requests.storage}}
                },
            }
        },
    ) as data_import_cron:
        yield data_import_cron


@pytest.fixture
def existing_dic_volumes_before_disable(admin_client, golden_images_namespace):
    return get_all_dic_volume_names(client=admin_client, namespace=golden_images_namespace.name)

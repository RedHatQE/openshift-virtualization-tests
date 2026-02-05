import logging
from contextlib import contextmanager

import pytest
from kubernetes.dynamic.exceptions import ResourceNotFoundError
from ocp_resources.data_import_cron import DataImportCron
from ocp_resources.data_source import DataSource
from ocp_resources.datavolume import DataVolume
from ocp_resources.resource import ResourceEditor
from pytest_testconfig import py_config
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.infrastructure.golden_images.constants import (
    CUSTOM_DATA_IMPORT_CRON_NAME,
    CUSTOM_DATA_SOURCE_NAME,
    DATA_SOURCE_READY_FOR_CONSUMPTION_MESSAGE,
    PVC_NOT_FOUND_ERROR,
)
from tests.utils import get_parameters_from_template
from utilities.artifactory import (
    cleanup_artifactory_secret_and_config_map,
    get_artifactory_config_map,
    get_artifactory_secret,
    get_http_image_url,
)
from utilities.constants import DATA_SOURCE_NAME, DEFAULT_FEDORA_REGISTRY_URL, TIMEOUT_5MIN, TIMEOUT_10MIN, Images
from utilities.exceptions import ResourceValueError
from utilities.ssp import wait_for_condition_message_value

LOGGER = logging.getLogger(__name__)

TESTS_AUTO_UPDATE_BOOT_SOURCE_NAME = [*py_config["auto_update_data_source_matrix"][0]][0]
DUMMY_VOLUME_NAME = "dummy"
DATA_SOURCE_MANAGED_BY_CDI_LABEL = f"{DataSource.ApiGroup.CDI_KUBEVIRT_IO}/dataImportCron"

pytestmark = pytest.mark.post_upgrade


@contextmanager
def dv_for_data_source(name, data_source, admin_client):
    artifactory_secret = get_artifactory_secret(namespace=data_source.namespace)
    artifactory_config_map = get_artifactory_config_map(namespace=data_source.namespace)
    with DataVolume(
        client=admin_client,
        name=name,
        namespace=data_source.namespace,
        # underlying OS is not relevant
        url=get_http_image_url(image_directory=Images.Cirros.DIR, image_name=Images.Cirros.QCOW2_IMG),
        source="http",
        secret=artifactory_secret,
        cert_configmap=artifactory_config_map.name,
        size=Images.Cirros.DEFAULT_DV_SIZE,
        storage_class=py_config["default_storage_class"],
        bind_immediate_annotation=True,
        api_name="storage",
    ) as dv:
        dv.wait_for_dv_success()
        wait_for_condition_message_value(
            resource=data_source,
            expected_message=DATA_SOURCE_READY_FOR_CONSUMPTION_MESSAGE,
        )
        yield dv
    cleanup_artifactory_secret_and_config_map(
        artifactory_secret=artifactory_secret, artifactory_config_map=artifactory_config_map
    )


def opt_in_status_str(opt_in):
    return f"opt-{'in' if opt_in else 'out'}"


def wait_for_data_source_reconciliation_after_update(
    data_source, opt_in, volume_name_before_reconcile=DUMMY_VOLUME_NAME
):
    LOGGER.info(f"{opt_in_status_str(opt_in=opt_in)}: Verify DataSource {data_source.name} is reconciled after update.")
    try:
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_10MIN,
            sleep=5,
            func=lambda: data_source.source.name != volume_name_before_reconcile,
        ):
            if sample:
                return
    except TimeoutExpiredError:
        LOGGER.error(f"dataSource {data_source.name} was not reconciled")
        raise


def wait_for_data_source_unchanged_referenced_volume(data_source, volume_name):
    try:
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_10MIN,
            sleep=5,
            func=lambda: data_source.source.name != volume_name,
        ):
            if sample:
                raise ResourceValueError(
                    f"DataSource {data_source.name} volume reference was updated, "
                    f"expected {volume_name}, "
                    f"spec: {data_source.instance.spec}"
                )
    except TimeoutExpiredError:
        return


def wait_for_data_source_updated_referenced_volume(data_source, volume_name):
    try:
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_10MIN,
            sleep=5,
            func=lambda: data_source.source.name == volume_name,
        ):
            if sample:
                return
    except TimeoutExpiredError:
        LOGGER.error(
            f"dataSource {data_source.name} volume reference was not updated, "
            f"expected {volume_name}, "
            f"spec: {data_source.instance.spec}"
        )
        raise


def delete_data_source_and_wait_for_reconciliation(data_source, opt_in):
    LOGGER.info(
        f"{opt_in_status_str(opt_in=opt_in)}: Verify DataSource {data_source.name} is reconciled after deletion."
    )

    data_source_orig_uid = data_source.instance.metadata.uid
    # Not passing 'wait' as creation time is almost instant
    data_source.delete()

    try:
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_5MIN,
            sleep=5,
            func=lambda: data_source.instance.metadata.uid != data_source_orig_uid,
        ):
            if sample:
                return
    except TimeoutExpiredError:
        LOGGER.error("DataSource was not reconciled after deletion")
        raise


def assert_missing_data_sources(opt_in, data_sources_names_from_templates, golden_images_data_sources):
    LOGGER.info(
        f"{opt_in_status_str(opt_in=opt_in)}: Verify all expected DataSources from templates "
        f"{[data_source.name for data_source in golden_images_data_sources]} are created."
    )
    missing_data_sources = [
        data_source_ref
        for data_source_ref in data_sources_names_from_templates
        if data_source_ref not in [data_source.name for data_source in golden_images_data_sources]
    ]
    assert not missing_data_sources, f"Not all dataSources are created, missing: {missing_data_sources}"


def data_source_labels_by_opt_in_status(data_source, opt_in):
    data_source_labels = data_source.instance.to_dict()["metadata"]["labels"]
    if opt_in:
        data_source_labels[DATA_SOURCE_MANAGED_BY_CDI_LABEL] = "true"
    else:
        del data_source_labels[DATA_SOURCE_MANAGED_BY_CDI_LABEL]
    return data_source_labels


def opt_in_data_source(data_source):
    with ResourceEditor(
        patches={
            data_source: {
                "metadata": {"labels": data_source_labels_by_opt_in_status(data_source=data_source, opt_in=True)}
            }
        }
    ):
        wait_for_condition_message_value(
            resource=data_source,
            expected_message=DATA_SOURCE_READY_FOR_CONSUMPTION_MESSAGE,
        )
        yield


def wait_for_data_import_cron_label_in_data_source_when_opt_in(data_source, opt_in):
    LOGGER.info(
        f"{opt_in_status_str(opt_in=opt_in)}: Verify DataSource {data_source.name} {DATA_SOURCE_MANAGED_BY_CDI_LABEL} "
        f"label {'' if opt_in else 'does not'} exist."
    )
    try:
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_5MIN,
            sleep=5,
            func=lambda: DATA_SOURCE_MANAGED_BY_CDI_LABEL in data_source.labels,
        ):
            if (sample and opt_in) or not (sample and opt_in):
                return
    except TimeoutExpiredError:
        LOGGER.error(
            f"DataSource {data_source.name} {'does not' if opt_in else ''} have "
            f"{DATA_SOURCE_MANAGED_BY_CDI_LABEL} label."
        )
        raise


@contextmanager
def update_data_source(data_source):
    source = "pvc" if data_source.instance.spec.source.get("pvc") else "snapshot"
    with ResourceEditor(
        patches={
            data_source: {
                "spec": {
                    "source": {
                        source: {
                            "name": DUMMY_VOLUME_NAME,
                            "namespace": data_source.namespace,
                        }
                    }
                }
            }
        }
    ):
        yield data_source


@pytest.fixture()
def golden_images_data_sources_scope_function(admin_client, golden_images_namespace):
    return list(DataSource.get(client=admin_client, namespace=golden_images_namespace.name))


@pytest.fixture()
def data_sources_managed_by_data_import_crons_scope_function(
    golden_images_data_sources_scope_function,
):
    return [
        data_source
        for data_source in golden_images_data_sources_scope_function
        if DATA_SOURCE_MANAGED_BY_CDI_LABEL in data_source.labels.keys()
    ]


@pytest.fixture()
def data_sources_names_from_templates_scope_function(base_templates):
    return set([
        get_parameters_from_template(template=template, parameter_subset=DATA_SOURCE_NAME)[DATA_SOURCE_NAME]
        for template in base_templates
    ])


@pytest.fixture()
def data_sources_from_templates_scope_function(admin_client, data_sources_names_from_templates_scope_function):
    return [
        DataSource(client=admin_client, name=data_source_name, namespace=py_config["golden_images_namespace"])
        for data_source_name in data_sources_names_from_templates_scope_function
    ]


@pytest.fixture()
def data_source_by_name_scope_function(request, unprivileged_client, golden_images_namespace):
    return DataSource(client=unprivileged_client, name=request.param, namespace=golden_images_namespace.name)


@pytest.fixture(scope="class")
def data_source_by_name_scope_class(request, admin_client, golden_images_namespace):
    return DataSource(client=admin_client, name=request.param, namespace=golden_images_namespace.name)


@pytest.fixture(scope="class")
def data_source_by_name_managing_data_import_cron_scope_class(admin_client, data_source_by_name_scope_class):
    return DataImportCron(
        client=admin_client,
        name=data_source_by_name_scope_class.labels[DATA_SOURCE_MANAGED_BY_CDI_LABEL],
        namespace=data_source_by_name_scope_class.namespace,
    )


@pytest.fixture(scope="class")
def data_source_referenced_volume_scope_class(data_source_by_name_scope_class):
    return data_source_by_name_scope_class.source.name


@pytest.fixture(scope="class")
def opted_in_data_source_scope_class(data_source_by_name_scope_class):
    yield from opt_in_data_source(data_source=data_source_by_name_scope_class)


@pytest.fixture(scope="class")
def opted_out_data_source_scope_class(
    data_source_by_name_scope_class,
    created_dv_for_data_import_cron_managed_data_source_scope_class,
):
    with ResourceEditor(
        patches={
            data_source_by_name_scope_class: {
                "metadata": {
                    "labels": data_source_labels_by_opt_in_status(
                        data_source=data_source_by_name_scope_class, opt_in=False
                    )
                }
            }
        }
    ):
        wait_for_data_source_updated_referenced_volume(
            data_source=data_source_by_name_scope_class,
            volume_name=created_dv_for_data_import_cron_managed_data_source_scope_class.name,
        )
        yield


@pytest.fixture()
def uploaded_dv_for_dangling_data_source_scope_function(admin_client, data_source_by_name_scope_function):
    expected_pvc_name = data_source_by_name_scope_function.instance.spec.source.pvc.name
    LOGGER.info(f"Create DV {expected_pvc_name} for DataSource {data_source_by_name_scope_function.name}")
    with dv_for_data_source(
        name=expected_pvc_name,
        data_source=data_source_by_name_scope_function,
        admin_client=admin_client,
    ) as dv:
        yield dv


@pytest.fixture()
def created_dv_for_data_import_cron_managed_data_source_scope_function(
    admin_client, golden_images_namespace, data_source_by_name_scope_function
):
    with dv_for_data_source(
        name=data_source_by_name_scope_function.instance.spec.source.pvc.name,
        data_source=data_source_by_name_scope_function,
        admin_client=admin_client,
    ) as dv:
        yield dv


@pytest.fixture(scope="class")
def created_dv_for_data_import_cron_managed_data_source_scope_class(
    admin_client, golden_images_namespace, data_source_by_name_scope_class
):
    with dv_for_data_source(
        name=data_source_by_name_scope_class.instance.spec.source.pvc.name,
        data_source=data_source_by_name_scope_class,
        admin_client=admin_client,
    ) as dv:
        yield dv


@pytest.fixture()
def updated_opted_in_data_source_scope_function(
    data_sources_managed_by_data_import_crons_scope_function,
):
    with update_data_source(data_source=data_sources_managed_by_data_import_crons_scope_function[0]) as data_source:
        yield data_source


@pytest.fixture()
def updated_opted_out_data_source_scope_function(
    data_sources_from_templates_scope_function,
):
    with update_data_source(data_source=data_sources_from_templates_scope_function[0]) as data_source:
        yield data_source


@pytest.fixture()
def updated_data_source_with_existing_pvc_scope_function(
    data_source_by_name_scope_class,
):
    with update_data_source(data_source=data_source_by_name_scope_class) as data_source:
        yield data_source


@pytest.mark.polarion("CNV-7578")
def test_opt_in_all_referenced_data_sources_in_templates_exist(
    data_sources_names_from_templates_scope_function,
    golden_images_data_sources_scope_function,
):
    assert_missing_data_sources(
        opt_in=True,
        data_sources_names_from_templates=data_sources_names_from_templates_scope_function,
        golden_images_data_sources=golden_images_data_sources_scope_function,
    )


@pytest.mark.polarion("CNV-8234")
def test_opt_out_all_referenced_data_sources_in_templates_exist(
    disabled_common_boot_image_import_hco_spec_scope_function,
    data_sources_names_from_templates_scope_function,
    golden_images_data_sources_scope_function,
):
    assert_missing_data_sources(
        opt_in=False,
        data_sources_names_from_templates=data_sources_names_from_templates_scope_function,
        golden_images_data_sources=golden_images_data_sources_scope_function,
    )


@pytest.mark.polarion("CNV-7667")
def test_opt_in_data_source_reconciles_after_deletion(
    golden_images_data_sources_scope_function,
):
    delete_data_source_and_wait_for_reconciliation(
        data_source=golden_images_data_sources_scope_function[0], opt_in=True
    )


@pytest.mark.polarion("CNV-8030")
def test_opt_in_data_source_reconciles_after_update(
    updated_opted_in_data_source_scope_function,
):
    wait_for_data_source_reconciliation_after_update(
        data_source=updated_opted_in_data_source_scope_function, opt_in=True
    )


@pytest.mark.parametrize(
    "data_source_by_name_scope_function, delete_dv, expected_condition_message",
    [
        pytest.param(
            "win2k19",
            False,
            DATA_SOURCE_READY_FOR_CONSUMPTION_MESSAGE,
            marks=(pytest.mark.polarion("CNV-7755")),
        ),
        pytest.param(
            "win2k19",
            True,
            PVC_NOT_FOUND_ERROR,
            marks=(pytest.mark.polarion("CNV-8099")),
        ),
    ],
    indirect=["data_source_by_name_scope_function"],
)
def test_upload_dv_for_auto_update_dangling_data_sources(
    data_source_by_name_scope_function,
    uploaded_dv_for_dangling_data_source_scope_function,
    delete_dv,
    expected_condition_message,
):
    LOGGER.info("Verify DataSource condition is updated when referenced PVC is ready.")
    if delete_dv:
        uploaded_dv_for_dangling_data_source_scope_function.delete(wait=True)
    wait_for_condition_message_value(
        resource=data_source_by_name_scope_function,
        expected_message=expected_condition_message,
    )


@pytest.mark.polarion("CNV-7668")
def test_opt_out_data_source_reconciles_after_deletion(
    disabled_common_boot_image_import_hco_spec_scope_function,
    data_sources_from_templates_scope_function,
):
    delete_data_source_and_wait_for_reconciliation(
        data_source=data_sources_from_templates_scope_function[0], opt_in=False
    )


@pytest.mark.polarion("CNV-8095")
def test_opt_out_data_source_reconciles_after_update(
    disabled_common_boot_image_import_hco_spec_scope_function,
    updated_opted_out_data_source_scope_function,
):
    wait_for_data_source_reconciliation_after_update(
        data_source=updated_opted_out_data_source_scope_function, opt_in=False
    )


@pytest.mark.polarion("CNV-8100")
@pytest.mark.s390x
def test_opt_out_data_source_update(
    disabled_common_boot_image_import_hco_spec_scope_function,
    data_sources_from_templates_scope_function,
):
    LOGGER.info("Verify DataSources are updated to not reference auto-update PVCs")
    for data_source in data_sources_from_templates_scope_function:
        wait_for_condition_message_value(
            resource=data_source,
            expected_message=PVC_NOT_FOUND_ERROR,
        )


@pytest.mark.parametrize(
    "updated_hco_with_custom_data_import_cron_scope_function",
    [
        pytest.param(
            {
                "data_import_cron_name": CUSTOM_DATA_IMPORT_CRON_NAME,
                "data_import_cron_source_url": DEFAULT_FEDORA_REGISTRY_URL,
                "managed_data_source_name": CUSTOM_DATA_SOURCE_NAME,
            },
            marks=(pytest.mark.polarion("CNV-8048")),
        ),
    ],
    indirect=True,
)
def test_opt_out_custom_data_sources_not_deleted(
    admin_client,
    golden_images_namespace,
    updated_hco_with_custom_data_import_cron_scope_function,
    disabled_common_boot_image_import_hco_spec_scope_function,
):
    custom_data_source_name = updated_hco_with_custom_data_import_cron_scope_function["spec"]["managedDataSource"]
    LOGGER.info(f"Verify custom DataSource {custom_data_source_name} is not deleted after opt-out")
    if not DataSource(
        client=admin_client,
        name=custom_data_source_name,
        namespace=golden_images_namespace.name,
    ).exists:
        raise ResourceNotFoundError(f"Custom DataSource {custom_data_source_name} not found after opt out")


@pytest.mark.parametrize(
    "data_source_by_name_scope_function",
    [
        pytest.param(
            TESTS_AUTO_UPDATE_BOOT_SOURCE_NAME,
            marks=(pytest.mark.polarion("CNV-7757")),
        ),
    ],
    indirect=True,
)
def test_data_source_with_existing_golden_image_pvc(
    disabled_common_boot_image_import_hco_spec_scope_function,
    data_source_by_name_scope_function,
    created_dv_for_data_import_cron_managed_data_source_scope_function,
    enabled_common_boot_image_import_feature_gate_scope_function,
):
    LOGGER.info(f"Verify DataSource {data_source_by_name_scope_function.name} consumes an existing DV")
    wait_for_condition_message_value(
        resource=data_source_by_name_scope_function,
        expected_message=DATA_SOURCE_READY_FOR_CONSUMPTION_MESSAGE,
    )

    LOGGER.info("Verify DataSource reference is not updated if there's an existing PVC.")
    wait_for_data_source_unchanged_referenced_volume(
        data_source=data_source_by_name_scope_function,
        volume_name=created_dv_for_data_import_cron_managed_data_source_scope_function.name,
    )


@pytest.mark.parametrize(
    "data_source_by_name_scope_class",
    [
        pytest.param(
            TESTS_AUTO_UPDATE_BOOT_SOURCE_NAME,
        ),
    ],
    indirect=True,
)
@pytest.mark.usefixtures(
    "data_source_by_name_scope_class",
    "data_source_referenced_volume_scope_class",
    "disabled_common_boot_image_import_hco_spec_scope_class",
    "created_dv_for_data_import_cron_managed_data_source_scope_class",
    "enabled_common_boot_image_import_feature_gate_scope_class",
    "opted_in_data_source_scope_class",
)
class TestDataSourcesOptInLabel:
    @pytest.mark.polarion("CNV-8029")
    @pytest.mark.dependency(name="TestDataSourcesOptInLabel::test_opt_in_label_data_source_when_pvc_exists")
    def test_opt_in_label_data_source_when_pvc_exists(
        self, data_source_by_name_scope_class, data_source_referenced_volume_scope_class
    ):
        LOGGER.info("Verify DataSource is managed by DataImportCron after labelled and a PVC exists.")
        wait_for_data_source_updated_referenced_volume(
            data_source=data_source_by_name_scope_class,
            volume_name=data_source_referenced_volume_scope_class,
        )

    @pytest.mark.polarion("CNV-8253")
    @pytest.mark.dependency(depends=["TestDataSourcesOptInLabel::test_opt_in_label_data_source_when_pvc_exists"])
    def test_opt_in_label_data_source_reconciles_after_update_with_existing_pvc(
        self, updated_data_source_with_existing_pvc_scope_function
    ):
        wait_for_data_source_reconciliation_after_update(
            data_source=updated_data_source_with_existing_pvc_scope_function,
            opt_in=True,
        )
        wait_for_data_import_cron_label_in_data_source_when_opt_in(
            data_source=updated_data_source_with_existing_pvc_scope_function,
            opt_in=True,
        )

    @pytest.mark.polarion("CNV-8245")
    @pytest.mark.dependency(depends=["TestDataSourcesOptInLabel::test_opt_in_label_data_source_when_pvc_exists"])
    def test_opt_in_label_data_source_reconciles_after_deletion_with_existing_pvc(
        self, data_source_by_name_scope_class
    ):
        delete_data_source_and_wait_for_reconciliation(data_source=data_source_by_name_scope_class, opt_in=True)
        wait_for_data_import_cron_label_in_data_source_when_opt_in(
            data_source=data_source_by_name_scope_class, opt_in=True
        )


@pytest.mark.parametrize(
    "data_source_by_name_scope_class",
    [
        pytest.param(
            TESTS_AUTO_UPDATE_BOOT_SOURCE_NAME,
        ),
    ],
    indirect=True,
)
@pytest.mark.usefixtures(
    "data_source_by_name_scope_class",
    "data_source_by_name_managing_data_import_cron_scope_class",
    "data_source_referenced_volume_scope_class",
    "disabled_common_boot_image_import_hco_spec_scope_class",
    "created_dv_for_data_import_cron_managed_data_source_scope_class",
    "enabled_common_boot_image_import_feature_gate_scope_class",
    "opted_in_data_source_scope_class",
    "opted_out_data_source_scope_class",
)
class TestDataSourcesOptOutLabel:
    @pytest.mark.polarion("CNV-8244")
    @pytest.mark.dependency(name="TestDataSourcesOptOutLabel::test_remove_data_source_dic_label_when_pvc_exists")
    def test_remove_data_source_dic_label_when_pvc_exists(
        self, data_source_by_name_managing_data_import_cron_scope_class
    ):
        LOGGER.info("Verify DataSource is not managed by DataImportCron when label is removed and a PVC exists.")
        data_source_by_name_managing_data_import_cron_scope_class.wait_deleted()

    @pytest.mark.polarion("CNV-8254")
    @pytest.mark.dependency(depends=["TestDataSourcesOptOutLabel::test_remove_data_source_dic_label_when_pvc_exists"])
    def test_opt_out_label_data_source_reconciles_after_update_with_existing_pvc(
        self, updated_data_source_with_existing_pvc_scope_function
    ):
        wait_for_data_source_reconciliation_after_update(
            data_source=updated_data_source_with_existing_pvc_scope_function,
            opt_in=False,
        )
        wait_for_data_import_cron_label_in_data_source_when_opt_in(
            data_source=updated_data_source_with_existing_pvc_scope_function,
            opt_in=False,
        )

    @pytest.mark.polarion("CNV-8252")
    @pytest.mark.dependency(depends=["TestDataSourcesOptOutLabel::test_remove_data_source_dic_label_when_pvc_exists"])
    def test_opt_out_label_data_source_reconciles_after_deletion_with_existing_pvc(
        self, data_source_by_name_scope_class
    ):
        delete_data_source_and_wait_for_reconciliation(data_source=data_source_by_name_scope_class, opt_in=False)
        wait_for_data_import_cron_label_in_data_source_when_opt_in(
            data_source=data_source_by_name_scope_class, opt_in=False
        )

    @pytest.mark.polarion("CNV-8258")
    @pytest.mark.dependency(depends=["TestDataSourcesOptOutLabel::test_remove_data_source_dic_label_when_pvc_exists"])
    def test_opt_out_label_data_source_delete_existing_dv(
        self,
        data_source_by_name_scope_class,
        created_dv_for_data_import_cron_managed_data_source_scope_class,
    ):
        created_dv_for_data_import_cron_managed_data_source_scope_class.delete(wait=True)
        wait_for_data_import_cron_label_in_data_source_when_opt_in(
            data_source=data_source_by_name_scope_class, opt_in=True
        )
        wait_for_data_source_reconciliation_after_update(
            data_source=data_source_by_name_scope_class,
            opt_in=True,
            volume_name_before_reconcile=created_dv_for_data_import_cron_managed_data_source_scope_class.name,
        )

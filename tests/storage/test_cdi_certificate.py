# -*- coding: utf-8 -*-

"""
Automatic refresh of CDI certificates test suite
"""

import datetime
import logging
import subprocess
import time

import pytest
from ocp_resources.cdi import CDI
from ocp_resources.config_map import ConfigMap
from ocp_resources.datavolume import DataVolume
from ocp_resources.network_addons_config import NetworkAddonsConfig
from ocp_resources.resource import Resource, ResourceEditor
from ocp_resources.secret import Secret
from pytest_testconfig import config as py_config
from timeout_sampler import TimeoutSampler

import tests.storage.utils as storage_utils
from utilities.constants import (
    CDI_SECRETS,
    TIMEOUT_1MIN,
    TIMEOUT_3MIN,
    TIMEOUT_5SEC,
    TIMEOUT_10MIN,
    Images,
)
from utilities.hco import ResourceEditorValidateHCOReconcile
from utilities.storage import (
    check_disk_count_in_vm,
    check_upload_virtctl_result,
    create_dv,
    get_downloaded_artifact,
    virtctl_upload_dv,
)
from utilities.virt import running_vm

pytestmark = pytest.mark.post_upgrade


LOGGER = logging.getLogger(__name__)
RFC3339_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
LOCAL_QCOW2_IMG_PATH = f"/tmp/{Images.Cdi.QCOW2_IMG}"


def x509_cert_is_valid(cert, seconds):
    """
    Checks if the certificate expires within the next {seconds} seconds.
    """
    try:
        subprocess.check_output(
            f"openssl x509 -checkend {seconds}",
            input=cert,
            shell=True,
            universal_newlines=True,
        )
    except subprocess.CalledProcessError as e:
        if "Certificate will expire" in e.output:
            return False
        raise e
    return True


@pytest.fixture(scope="module")
def secrets(admin_client, hco_namespace):
    return Secret.get(dyn_client=admin_client, namespace=hco_namespace.name)


@pytest.fixture()
def valid_cdi_certificates(secrets):
    """
    Check whether all CDI certificates are valid.
    The cert time abstracted from CDI respective Secret annotations are like:
    auth.openshift.io/certificate-not-after: "2020-04-24T04:02:12Z"
    auth.openshift.io/certificate-not-before: "2020-04-22T04:02:11Z"
    """
    for secret in secrets:
        for cdi_secret in CDI_SECRETS:
            if secret.name == cdi_secret:
                LOGGER.info(f"Checking {cdi_secret}...")

                start = secret.certificate_not_before
                start_timestamp = time.mktime(time.strptime(start, RFC3339_FORMAT))

                end = secret.certificate_not_after
                end_timestamp = time.mktime(time.strptime(end, RFC3339_FORMAT))

                current_time = datetime.datetime.now().strftime(RFC3339_FORMAT)
                current_timestamp = time.mktime(time.strptime(current_time, RFC3339_FORMAT))
                assert start_timestamp <= current_timestamp <= end_timestamp, f"Certificate of {cdi_secret} expired"


@pytest.fixture()
def valid_aggregated_api_client_cert(kube_system_namespace):
    """
    Performing the following steps will determine whether the extension-apiserver-authentication cert
    has been renewed within the valid time frame
    """
    aggregated_cm = "extension-apiserver-authentication"
    cert_end = "-----END CERTIFICATE-----\n"
    cm_data = ConfigMap(namespace=kube_system_namespace.name, name=aggregated_cm).instance["data"]
    for cert_attr, cert_data in cm_data.items():
        if "ca-file" not in cert_attr:
            continue
        # Multiple certs can exist in one dict value (client-ca-file, for example)
        cert_list = [cert + cert_end for cert in cert_data.split(cert_end) if cert not in ("", cert_end)]
        for cert in cert_list:
            # Check if certificate won't expire in next 10 minutes
            if not x509_cert_is_valid(cert=cert, seconds=TIMEOUT_10MIN):
                raise pytest.fail(f"Certificate located in: {cert_attr} expires in less than 10 minutes")


@pytest.fixture()
def refresh_cdi_certificates(secrets):
    """
    Update the secret annotation "auth.openshift.io/certificate-not-after" to be equal to
    "auth.openshift.io/certificate-not-before" will trigger the cert renewal.
    This fixture refresh all CDI certificates.
    """
    for secret in secrets:
        for cdi_secret in CDI_SECRETS:
            if secret.name == cdi_secret:
                new_end = secret.certificate_not_before
                res = ResourceEditor(
                    patches={
                        secret: {"metadata": {"annotations": {"auth.openshift.io/certificate-not-after": f"{new_end}"}}}
                    }
                )
                LOGGER.info(f"Wait for Secret {secret.name} to be updated")
                res.update()
                for sample in TimeoutSampler(
                    wait_timeout=TIMEOUT_1MIN,
                    sleep=TIMEOUT_5SEC,
                    func=lambda: secret.certificate_not_before != secret.certificate_not_after,
                ):
                    if sample:
                        break


@pytest.fixture()
def dv_of_multi_storage_cirros_vm(
    data_volume_template_metadata,
):
    return DataVolume(
        name=data_volume_template_metadata["name"],
        namespace=data_volume_template_metadata["namespace"],
    )


@pytest.mark.parametrize(
    "multi_storage_cirros_vm",
    [
        pytest.param(
            {
                "dv_name": "dv-3686",
                "vm_name": "vm-3686",
                "annotations": {
                    f"{Resource.ApiGroup.KUBEVIRT_IO}/immediate-data-volume-creation": "false",
                },
            },
            marks=pytest.mark.polarion("CNV-3686"),
        ),
    ],
    indirect=True,
)
def test_dv_delete_from_vm(
    valid_cdi_certificates,
    namespace,
    multi_storage_cirros_vm,
    dv_of_multi_storage_cirros_vm,
):
    """
    Check that create VM with dataVolumeTemplates, once DV is deleted, the owner VM will create one.
    This will trigger the import process so that cert code will be exercised one more time.
    """
    multi_storage_cirros_vm.stop(wait=True)
    assert dv_of_multi_storage_cirros_vm.delete(wait=True, timeout=TIMEOUT_1MIN), "DV was not deleted"
    # DV re-creation is triggered by VM
    running_vm(vm=multi_storage_cirros_vm, wait_for_interfaces=False)
    check_disk_count_in_vm(vm=multi_storage_cirros_vm)


@pytest.mark.sno
@pytest.mark.polarion("CNV-3667")
def test_upload_after_certs_renewal(
    skip_if_sc_volume_binding_mode_is_wffc,
    refresh_cdi_certificates,
    download_image,
    namespace,
    storage_class_name_scope_module,
):
    """
    Check that CDI can do upload operation after certs get refreshed
    """
    dv_name = "cnv-3667"
    with virtctl_upload_dv(
        namespace=namespace.name,
        name=dv_name,
        size="1Gi",
        image_path=LOCAL_QCOW2_IMG_PATH,
        storage_class=storage_class_name_scope_module,
        insecure=True,
    ) as res:
        check_upload_virtctl_result(result=res)
        dv = DataVolume(namespace=namespace.name, name=dv_name)
        dv.wait_for_dv_success(timeout=TIMEOUT_1MIN)
        with storage_utils.create_vm_from_dv(dv=dv, start=True) as vm:
            check_disk_count_in_vm(vm=vm)


@pytest.mark.parametrize(
    "data_volume_multi_storage_scope_module",
    [
        pytest.param(
            {
                "dv_name": "dv-source",
                "image": f"{Images.Cirros.DIR}/{Images.Cirros.QCOW2_IMG}",
                "dv_size": "1Gi",
                "wait": True,
            },
        ),
    ],
    indirect=True,
)
@pytest.mark.sno
@pytest.mark.polarion("CNV-3678")
def test_import_clone_after_certs_renewal(
    refresh_cdi_certificates,
    data_volume_multi_storage_scope_module,
    namespace,
):
    """
    Check that CDI can do import and clone operation after certs get refreshed
    """
    with create_dv(
        source="pvc",
        dv_name="dv-target",
        namespace=namespace.name,
        size=data_volume_multi_storage_scope_module.size,
        source_pvc=data_volume_multi_storage_scope_module.name,
        storage_class=data_volume_multi_storage_scope_module.storage_class,
    ) as cdv:
        cdv.wait_for_dv_success(timeout=TIMEOUT_3MIN)
        with storage_utils.create_vm_from_dv(dv=cdv, start=True) as vm:
            check_disk_count_in_vm(vm=vm)


@pytest.mark.sno
@pytest.mark.polarion("CNV-3977")
def test_upload_after_validate_aggregated_api_cert(
    skip_if_sc_volume_binding_mode_is_wffc,
    valid_aggregated_api_client_cert,
    namespace,
    storage_class_name_scope_module,
    download_image,
):
    """
    Check that upload is successful after verifying validity of aggregated api client certificate
    """
    dv_name = "cnv-3977"
    with virtctl_upload_dv(
        namespace=namespace.name,
        name=dv_name,
        size="1Gi",
        image_path=LOCAL_QCOW2_IMG_PATH,
        storage_class=storage_class_name_scope_module,
        insecure=True,
    ) as res:
        check_upload_virtctl_result(result=res)
        dv = DataVolume(namespace=namespace.name, name=dv_name)
        dv.wait_for_dv_success(timeout=TIMEOUT_1MIN)
        with storage_utils.create_vm_from_dv(dv=dv, start=True) as vm:
            check_disk_count_in_vm(vm=vm)


@pytest.fixture()
def certificate_exists(cdi_spec, hco_spec):
    # Verify CDI and HCO spec for cert configuration
    for spec in (cdi_spec, hco_spec):
        assert spec.get("certConfig"), "No certConfig found in spec."


@pytest.fixture()
def updated_certconfig_in_hco_cr(hyperconverged_resource_scope_function, certificate_exists):
    # Update cert rotation with a short interval for easy testing.
    with ResourceEditorValidateHCOReconcile(
        patches={
            hyperconverged_resource_scope_function: {
                "spec": {
                    "certConfig": {
                        "ca": {"duration": "1h20m0s", "renewBefore": "1h10m0s"},
                        "server": {"duration": "1h10m0s", "renewBefore": "1h5m0s"},
                    }
                }
            }
        },
        list_resource_reconcile=[CDI, NetworkAddonsConfig],
    ):
        yield


@pytest.fixture()
def downloaded_cirros_image(tmpdir):
    local_path = f"{tmpdir}/{Images.Cdi.QCOW2_IMG}"
    get_downloaded_artifact(remote_name=f"{Images.Cdi.DIR}/{Images.Cdi.QCOW2_IMG}", local_name=local_path)
    return local_path


@pytest.mark.s390x
@pytest.mark.polarion("CNV-5708")
def test_cert_exposure_rotation(
    enabled_ca,
    updated_certconfig_in_hco_cr,
    namespace,
    downloaded_cirros_image,
):
    with virtctl_upload_dv(
        namespace=namespace.name,
        name="cnv-5708",
        size="1Gi",
        storage_class=py_config["default_storage_class"],
        image_path=downloaded_cirros_image,
        insecure=False,
    ) as res:
        check_upload_virtctl_result(result=res)

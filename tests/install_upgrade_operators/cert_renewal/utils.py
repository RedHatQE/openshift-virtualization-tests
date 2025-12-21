import logging
import os
import re
from base64 import b64decode

import py
from kubernetes.dynamic import DynamicClient
from ocp_resources.api_service import APIService
from ocp_resources.namespace import Namespace
from ocp_resources.resource import NamespacedResource
from ocp_resources.secret import Secret
from pyhelper_utils.shell import run_command
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from tests.install_upgrade_operators.cert_renewal.constants import (
    SSP_OPERATOR_SERVICE_CERT,
    VIRT_TEMPLATE_VALIDATOR_CERTS,
)
from utilities.constants import TIMEOUT_2MIN, TIMEOUT_10MIN, TIMEOUT_20SEC

LOGGER = logging.getLogger(__name__)


SECRETS = [
    "kubemacpool-service",
    SSP_OPERATOR_SERVICE_CERT,
    VIRT_TEMPLATE_VALIDATOR_CERTS,
]
API_SERVICES = [
    f"{NamespacedResource.ApiVersion.V1}.subresources.kubevirt.io",
    f"{NamespacedResource.ApiVersion.V1ALPHA3}.subresources.kubevirt.io",
    f"{NamespacedResource.ApiVersion.V1BETA1}.{NamespacedResource.ApiGroup.UPLOAD_CDI_KUBEVIRT_IO}",
]


def get_certificates_validity_period_and_checkend_result(
    hco_namespace_name: str,
    tmpdir: py._path.local.LocalPath,
    secrets_to_skip: tuple,
    admin_client: DynamicClient,
    seconds: int = 0,
) -> dict[str, dict[str, str]]:
    """
    Get CNV certificates dates

    Args:
        hco_namespace_name (str): HCO namespace string
        tmpdir (py._path.local.LocalPath): temporary folder in which the certificates files will reside
        secrets_to_skip (tuple): names of secret entries that should not be checked due to open bugs
        admin_client (DynamicClient): Dynamic client object
        seconds (int, default: 0): number of seconds to test whether the certificate will expire or not
            according to openssl -checkend command

    Returns:
        dict[str, dict[str, str]]: a dict with certificate data:
        key is the resource name, value is a dict containing the notbefore, notafter
        and the checkend response string
    """
    certificates_to_check = dict(
        {
            os.path.join(tmpdir, secret): get_base64_decoded_certificate(
                certificate_data=Secret(name=secret, namespace=hco_namespace_name, client=admin_client).instance.data[
                    "tls.crt"
                ]
            )
            for secret in SECRETS
            if secret not in secrets_to_skip
        },
        **{
            os.path.join(tmpdir, api_service): get_base64_decoded_certificate(
                certificate_data=APIService(name=api_service, client=admin_client).instance.spec.caBundle
            )
            for api_service in API_SERVICES
        },
    )

    dump_certificates_to_files(certificates_filenames_dict=certificates_to_check)
    certificates_results: dict[str, dict[str, str]] = {}
    for cert in certificates_to_check:
        command = f"openssl x509 -in {cert} -dates -checkend {seconds}"
        _, out, err = run_command(command=[command], shell=True, check=False)
        stripped_output = out.strip()
        not_before_match = re.search("notBefore=(.*)", stripped_output)
        not_after_match = re.search("notAfter=(.*)", stripped_output)
        checkend_match = re.search("Certificate will (not )?expire", stripped_output)
        if not (not_before_match and not_after_match and checkend_match):
            raise ValueError(f"Failed to parse openssl output for certificate {cert}: {stripped_output}")
        certificates_results[os.path.basename(cert)] = {
            "not_before": not_before_match.group(1),
            "not_after": not_after_match.group(1),
            "checkend_result": checkend_match.group(),
        }
        LOGGER.info(f"openssl command output: command={command} error={err} output=\n{out}")
    return certificates_results


def get_base64_decoded_certificate(certificate_data):
    """
    Decode the Base64 certificate

    Args:
         certificate_data (str): raw certificate string

    Returns:
        str: decoded Base64 certificate string
    """
    return b64decode(certificate_data).decode(encoding="utf-8")


def dump_certificates_to_files(certificates_filenames_dict: dict[str, str]) -> None:
    """
    Dump the certificates PEM content to file in order to files in order to later on use them in openssl command

    Args:
        certificates_filenames_dict (dict[str, str]): dict of certificates
        filenames and data: filename as key, data as value
    """
    for filename, cert_data in certificates_filenames_dict.items():
        with open(file=filename, mode="w") as file_object:
            file_object.write(cert_data)


def wait_for_certificates_renewal(
    hco_namespace: Namespace,
    initial_certificates_dates: dict[str, dict[str, str]],
    secrets_to_skip: tuple,
    tmpdir: py._path.local.LocalPath,
    admin_client: DynamicClient,
) -> None:
    """
    Wait for certificate renewal to occur, by practically comparing the actual certificates dates (notBefore/notAfter)
    to the initial certificate data.

    Args:
        hco_namespace (Namespace): HCO namespace
        initial_certificates_dates (dict[str, dict[str, str]]): dict with the initial certificates data
        secrets_to_skip (tuple): names of secret entries that should not be checked due to open bugs
        tmpdir (py._path.local.LocalPath): temporary folder in which the certificates files will reside
        admin_client (DynamicClient): Dynamic client object

    Raises:
        TimeoutExpiredError: raised if certificates renewal did not occur
    """
    wait_timeout = TIMEOUT_2MIN
    polling_interval = 1
    LOGGER.info("Wait for the certificates to be renewed")
    samples = TimeoutSampler(
        wait_timeout=wait_timeout,
        sleep=polling_interval,
        func=get_certificates_validity_period_and_checkend_result,
        hco_namespace_name=hco_namespace.name,
        tmpdir=tmpdir,
        secrets_to_skip=secrets_to_skip,
        admin_client=admin_client,
    )
    sample = None
    try:
        for sample in samples:
            if sample:
                if not [
                    certificate
                    for certificate, certificate_data in initial_certificates_dates.items()
                    if sample[certificate]["not_before"] == certificate_data["not_before"]
                    and sample[certificate]["not_after"] == certificate_data["not_after"]
                ]:
                    LOGGER.info("Certificate renewed, as expected")
                    break
    except TimeoutExpiredError:
        LOGGER.error(
            "Timeout waiting for all certificates to be renewed (to be different from the initial data): "
            f"certificates={sample}"
        )
        raise


def verify_certificates_dates_identical_to_initial_dates(
    hco_namespace: Namespace,
    initial_certificates_dates: dict[str, dict[str, str]],
    secrets_to_skip: tuple,
    tmpdir: py._path.local.LocalPath,
    admin_client: DynamicClient,
) -> None:
    """
    Verifies (in intervals) that the actual certificates dates are identical to the initial dates

    Args:
        hco_namespace (Namespace): HCO namespace
        initial_certificates_dates (dict[str, dict[str, str]]): dict with the initial certificates data
        secrets_to_skip (tuple): names of secret entries that should not be checked due to open bugs
        tmpdir (py._path.local.LocalPath): temporary folder in which the certificates files will reside
        admin_client (DynamicClient): Dynamic client object

    Raises:
        AssertionError: raised if certificates' dates are not identical to the initial dates
    """
    wait_timeout = TIMEOUT_10MIN
    polling_interval = TIMEOUT_20SEC
    LOGGER.info("Verify that the certificates dates were not changed")
    samples = TimeoutSampler(
        wait_timeout=wait_timeout,
        sleep=polling_interval,
        func=get_certificates_validity_period_and_checkend_result,
        hco_namespace_name=hco_namespace.name,
        tmpdir=tmpdir,
        secrets_to_skip=secrets_to_skip,
        admin_client=admin_client,
    )
    try:
        for sample in samples:
            if sample:
                assert sorted(initial_certificates_dates) == sorted(sample), (
                    f"Certificates were renewed: initial_certificates_dates={initial_certificates_dates} "
                    f"current_certificates_dates={sample}"
                )
    except TimeoutExpiredError:
        LOGGER.info("Certificate was not renewed within the expected time frame, as expected")

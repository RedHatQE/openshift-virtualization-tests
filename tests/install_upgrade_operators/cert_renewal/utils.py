import logging
import os
import re
from base64 import b64decode

from ocp_resources.api_service import APIService
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


def get_certificates_validity_period_and_checkend_result(hco_namespace_name, tmpdir, secrets_to_skip, seconds=0):
    """
    Get CNV certificates dates

    Args:
        hco_namespace_name (str): HCO namespace string
        tmpdir (py.path.local): temporary folder in which the certificates files will reside
        secrets_to_skip (tuple): names of secret entries that should not be checked due to open bugs
        seconds (int, default: 0): number of seconds to test whether the certificate will expire or not
            according to openssl -checkend command

    Returns:
        dict: a dict with certificate data: key is the resource name, value is a dict containing the notbefore, notafter
        and the checkend response string
    """
    certificates_to_check = dict(
        {
            os.path.join(tmpdir, secret): get_base64_decoded_certificate(
                certificate_data=Secret(name=secret, namespace=hco_namespace_name).instance.data["tls.crt"]
            )
            for secret in SECRETS
            if secret not in secrets_to_skip
        },
        **{
            os.path.join(tmpdir, api_service): get_base64_decoded_certificate(
                certificate_data=APIService(name=api_service).instance.spec.caBundle
            )
            for api_service in API_SERVICES
        },
    )

    dump_certificates_to_files(certificates_filenames_dict=certificates_to_check)
    certificates_results = {}
    for cert in certificates_to_check:
        command = f"openssl x509 -in {cert} -dates -checkend {seconds}"
        _, out, err = run_command(command=[command], shell=True, check=False)
        stripped_output = out.strip()
        certificates_results[os.path.basename(cert)] = {
            "not_before": re.search("notBefore=(.*)", stripped_output).group(1),
            "not_after": re.search("notAfter=(.*)", stripped_output).group(1),
            "checkend_result": re.search("Certificate will (not )?expire", stripped_output).group(),
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


def dump_certificates_to_files(certificates_filenames_dict):
    """
    Dump the certificates PEM content to file in order to files in order to later on use them in openssl command

    Args:
        certificates_filenames_dict (dict): dict of certificates filenames and data (filename as key, data as value)
    """
    for filename, cert_data in certificates_filenames_dict.items():
        with open(file=filename, mode="w") as file_object:
            file_object.write(cert_data)


def wait_for_certificates_renewal(hco_namespace, initial_certificates_dates, secrets_to_skip, tmpdir):
    """
    Wait for certificate renewal to occur, by practically comparing the actual certificates dates (notBefore/notAfter)
    to the initial certificate data.

    Args:
        hco_namespace (Namespace): HCO namespace
        initial_certificates_dates (dict): dict with the initial certificates data
        secrets_to_skip (tuple): names of secret entries that should not be checked due to open bugs
        tmpdir (py.path.local): temporary folder in which the certificates files will reside

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
    hco_namespace,
    initial_certificates_dates,
    secrets_to_skip,
    tmpdir,
):
    """
    Verifies (in intervals) that the actual certificates dates are identical to the initial dates

    Args:
        hco_namespace (Namespace): HCO namespace
        initial_certificates_dates (dict): dict with the initial certificates data
        secrets_to_skip (tuple): names of secret entries that should not be checked due to open bugs
        tmpdir (py.path.local): temporary folder in which the certificates files will reside

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

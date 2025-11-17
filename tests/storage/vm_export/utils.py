"""
Pytest utils file for CNV VMExport tests
"""

import io
import logging
import shlex
from contextlib import contextmanager
from typing import Generator

import yaml
from kubernetes.dynamic import DynamicClient
from ocp_resources.datavolume import DataVolume
from ocp_resources.virtual_machine import VirtualMachine
from pyhelper_utils.shell import run_command
from pytest_testconfig import config as py_config

from utilities.constants import TIMEOUT_1MIN
from utilities.storage import create_dv

LOGGER = logging.getLogger(__name__)


def get_manifest_from_vmexport(vmexport_cert_file, url, token, kind, namespace_vmexport_target=None):
    cmd = f"curl --cacert {vmexport_cert_file} {url} -H 'x-kubevirt-export-token:{token}' -H 'Accept:application/yaml'"
    out_value = run_command(command=shlex.split(cmd), verify_stderr=False, check=False)[1]
    yaml_file_dict = {}
    for object_dict in yaml.safe_load_all(out_value):
        if object_dict.get("kind") == kind:
            yaml_file_dict = object_dict
            break
    assert yaml_file_dict, f"Manifest for '{kind}' not found"
    if kind == VirtualMachine.kind:
        del yaml_file_dict["metadata"]["namespace"]
        yaml_file_dict["spec"]["dataVolumeTemplates"][0]["metadata"]["namespace"] = namespace_vmexport_target
    return io.StringIO(yaml.dump(yaml_file_dict))


def get_manifest_url(vmexport_external_links, manifest_type):
    url = (
        next(manifest for manifest in vmexport_external_links.get("manifests") if manifest["type"] == manifest_type)
    ).get("url")
    assert url, f"Manifest url '{manifest_type}' in vmexport external links {vmexport_external_links} not found"
    return url


@contextmanager
def create_blank_dv_by_specific_user(
    client: DynamicClient,
    namespace_name: str,
    dv_name: str,
) -> Generator[DataVolume]:
    with create_dv(
        source="blank",
        dv_name=dv_name,
        namespace=namespace_name,
        size="1Gi",
        storage_class=py_config["default_storage_class"],
        consume_wffc=False,
        bind_immediate=True,
        client=client,
    ) as dv:
        dv.wait_for_dv_success(timeout=TIMEOUT_1MIN)
        yield dv

"""
Pytest utils file for CNV VMExport tests
"""

import io
import logging
import shlex

import yaml
from ocp_resources.virtual_machine import VirtualMachine
from pyhelper_utils.shell import run_command

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

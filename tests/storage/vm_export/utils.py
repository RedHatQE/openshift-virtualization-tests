"""
Pytest utils file for CNV VMExport tests
"""

import io
import logging
import shlex

import yaml
from ocp_resources.datavolume import DataVolume
from ocp_resources.persistent_volume_claim import PersistentVolumeClaim
from ocp_resources.storage_profile import StorageProfile
from ocp_resources.virtual_machine import VirtualMachine
from pyhelper_utils.shell import run_command

from utilities.storage import PodWithPVC, get_containers_for_pods_with_pvc

LOGGER = logging.getLogger(__name__)


def get_pvc_sha256sum(pvc_name, pvc_namespace):
    pvc = PersistentVolumeClaim(namespace=pvc_namespace, name=pvc_name)
    volume_mode = StorageProfile(name=pvc.instance.spec.storageClassName).instance.status["claimPropertySets"][0][
        "volumeMode"
    ]
    with PodWithPVC(
        namespace=pvc_namespace,
        name=f"{pvc_name}-pod",
        pvc_name=pvc_name,
        containers=get_containers_for_pods_with_pvc(volume_mode=volume_mode, pvc_name=pvc_name),
    ) as pod:
        pod.wait_for_status(status=pod.Status.RUNNING)
        pvc_disk_img = "/pvc/disk.img"
        checksum = "sha256sum"
        command = (
            f"bash -c 'head -c 1000000 {pvc_disk_img} | {checksum}'"
            if volume_mode == DataVolume.VolumeMode.BLOCK
            else f"{checksum} {pvc_disk_img}"
        )
        return pod.execute(command=shlex.split(command))


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

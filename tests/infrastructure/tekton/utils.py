"""
Tekton Pipeline Use Cases
"""

from __future__ import annotations

import glob
import logging
import os
import re

from kubernetes.dynamic import ResourceInstance
from ocp_resources.pipeline_run import PipelineRun
from ocp_resources.resource import Resource
from timeout_sampler import TimeoutExpiredError, TimeoutSampler

from utilities.constants import (
    TIMEOUT_1MIN,
    TIMEOUT_5SEC,
    TIMEOUT_10SEC,
    TIMEOUT_50MIN,
    WIN_2K22,
    WIN_2K25,
    WIN_10,
    WIN_11,
    Images,
)
from utilities.infra import get_http_image_url

LOGGER = logging.getLogger(__name__)


def win_iso_download_url_for_pipelineref():
    return {
        WIN_10: {
            "winImageDownloadURL": get_http_image_url(
                image_directory=Images.Windows.ISO_WIN10_DIR,
                image_name=Images.Windows.WIN10_ISO_IMG,
            ),
        },
        WIN_11: {
            "winImageDownloadURL": get_http_image_url(
                image_directory=Images.Windows.ISO_WIN11_DIR,
                image_name=Images.Windows.WIN11_ISO_IMG,
            ),
        },
        WIN_2K22: {
            "winImageDownloadURL": get_http_image_url(
                image_directory=Images.Windows.ISO_WIN2022_DIR,
                image_name=Images.Windows.WIN2022_ISO_IMG,
            ),
        },
        WIN_2K25: {
            "winImageDownloadURL": get_http_image_url(
                image_directory=Images.Windows.ISO_WIN2025_DIR,
                image_name=Images.Windows.WIN2025_ISO_IMG,
            ),
        },
    }


def wait_for_tekton_resource_availability(tekton_namespace, tekton_resource_kind, resource_name):
    try:
        for sample in TimeoutSampler(
            wait_timeout=TIMEOUT_10SEC,
            sleep=TIMEOUT_5SEC,
            func=lambda: tekton_resource_kind(namespace=tekton_namespace.name, name=resource_name).exists,
        ):
            if sample:
                return True
    except TimeoutExpiredError:
        LOGGER.error(f"{tekton_resource_kind} {resource_name} doesn't exist")
        raise


def get_component_image_digest(component_name, csv_object):
    for img in csv_object.instance.spec.relatedImages:
        if component_name in img["image"]:
            return img["image"]
    raise ValueError(f"Component image digest for {component_name} not found")


def yaml_files_in_dir(root_dir, sub_dir):
    dir_path = os.path.join(root_dir, sub_dir)
    assert os.path.exists(dir_path), f"Directory '{dir_path}' does not exist"
    return glob.glob(pathname=os.path.join(dir_path, "**", "*.yaml"), recursive=True)


def filter_yaml_files(all_yaml_files, included_patterns):
    filtered_files = [file for file in all_yaml_files if any(pattern in file for pattern in included_patterns)]
    assert filtered_files, "No matching YAML files found after filtering."
    return filtered_files


def update_tekton_resources_yaml_file(file_path, replacements):
    with open(file_path, "r") as file:
        yaml_content = file.read()

    for matched_pattern, replacement_pattern in replacements.items():
        yaml_content = re.sub(matched_pattern, replacement_pattern, yaml_content)

    with open(file_path, "w") as file:
        file.write(yaml_content)


def process_yaml_files(file_paths, replacements, resource_kind, namespace):
    resources = []
    for file_path in file_paths:
        update_tekton_resources_yaml_file(file_path=file_path, replacements=replacements)
        resources.append(resource_kind(yaml_file=file_path, namespace=namespace).create())
    return resources


def wait_for_final_status_pipelinerun(
    pipelinerun: PipelineRun, wait_timeout: int = TIMEOUT_50MIN, sleep_interval: int = TIMEOUT_1MIN
) -> ResourceInstance:
    try:
        for sample in TimeoutSampler(
            wait_timeout=wait_timeout,
            sleep=sleep_interval,
            func=lambda: pipelinerun.instance.status.conditions[0],
        ):
            if sample and sample["status"] != Resource.Condition.Status.UNKNOWN:
                LOGGER.info(f"PipelineRun Condition: {sample}")
                return sample

    except TimeoutExpiredError:
        LOGGER.error(f"Pipelinerun: {pipelinerun.name}, Last available condition: {sample}")
        raise

import logging
import re

from ocp_resources.resource import Resource

from tests.install_upgrade_operators.utils import (
    get_resource_container_env_image_mismatch,
)
from utilities.exceptions import ResourceMismatch

VALID_PRIORITY_CLASS = [
    "openshift-user-critical",
    "system-cluster-critical",
    "system-node-critical",
    "kubevirt-cluster-critical",
]

LOGGER = logging.getLogger(__name__)


def validate_cnv_pods_priority_class_name_exists(pod_list):
    pods_no_priority_class = [pod.name for pod in pod_list if not pod.instance.spec.priorityClassName]
    assert not pods_no_priority_class, (
        f"For the following cnv pods, spec.priorityClassName is missing {pods_no_priority_class}"
    )


def validate_priority_class_value(pod_list):
    pods_invalid_priority_class = {
        pod.name: pod.instance.spec.priorityClassName
        for pod in pod_list
        if pod.instance.spec.priorityClassName and pod.instance.spec.priorityClassName not in VALID_PRIORITY_CLASS
    }
    assert not pods_invalid_priority_class, (
        f"For the following pods, unexpected priority class found: {pods_invalid_priority_class}"
    )


def validate_cnv_pod_resource_request(cnv_pod, request_field):
    containers = cnv_pod.instance.spec.containers

    missing_field_values = [
        container["name"]
        for container in containers
        if not container.get("resources", {}).get("requests", {}).get(request_field)
    ]
    return missing_field_values


def validate_cnv_pod_cpu_min_value(cnv_pod, cpu_min_value):
    containers = cnv_pod.instance.spec.containers
    cpu_values = {
        container["name"]: container.get("resources", {}).get("requests", {}).get("cpu") for container in containers
    }
    LOGGER.info(f"For {cnv_pod.name} cpu_values: {cpu_values}")
    cpu_value_pattern = re.compile(r"^\d+")
    # Get the pods for which resources.requests.cpu value does not meet minimum threshold requirement
    invalid_cpus = {
        key: value
        for key, value in cpu_values.items()
        if not value or (int(cpu_value_pattern.findall(value)[0]) < cpu_min_value)
    }
    return invalid_cpus


def validate_cnv_pods_resource_request(cnv_pods, resource):
    resource_to_check = [*resource][0]
    if resource_to_check == "memory":
        pod_errors = [
            f"For {pod.name}, resources.requests.{resource_to_check} is missing."
            for pod in cnv_pods
            if validate_cnv_pod_resource_request(cnv_pod=pod, request_field=resource_to_check)
        ]
        assert not pod_errors, "\n".join(pod_errors)
    elif resource_to_check == "cpu":
        invalid_cpus = {
            pod.name: validate_cnv_pod_cpu_min_value(cnv_pod=pod, cpu_min_value=resource[resource_to_check])
            for pod in cnv_pods
        }
        cpu_error = {pod_name: invalid_cpu for pod_name, invalid_cpu in invalid_cpus.items() if invalid_cpu}
        assert not cpu_error, f"For following pods invalid cpu values found: {cpu_error}"
    else:
        raise AssertionError(f"Invalid resource: {resource}")


def assert_cnv_pod_container_env_image_not_in_upstream(cnv_pods_by_type):
    cnv_pods_env_with_upstream_image_reference = {
        pod.name: {
            container["name"]: get_resource_container_env_image_mismatch(container=container)
            for container in pod.instance.spec.containers
            if get_resource_container_env_image_mismatch(container=container)
        }
        for pod in cnv_pods_by_type
    }

    validate_image_values(pod_image_dict=cnv_pods_env_with_upstream_image_reference)


def assert_cnv_pod_container_image_not_in_upstream(cnv_pods_by_type):
    cnv_pods_with_upstream_image_reference = {
        pod.name: {
            container["name"]: container["image"]
            for container in pod.instance.spec.containers
            if not container["image"].startswith(Resource.ApiGroup.IMAGE_REGISTRY)
        }
        for pod in cnv_pods_by_type
    }
    validate_image_values(pod_image_dict=cnv_pods_with_upstream_image_reference)


def validate_image_values(pod_image_dict):
    cnv_pods_with_upstream_image_reference = filter_dict_remove_keys_with_empty_value(input_dictionary=pod_image_dict)
    if cnv_pods_with_upstream_image_reference:
        raise ResourceMismatch(
            f"For following pods found upstream image references: {cnv_pods_with_upstream_image_reference}"
        )


def filter_dict_remove_keys_with_empty_value(input_dictionary):
    return {key: value for key, value in input_dictionary.items() if value}

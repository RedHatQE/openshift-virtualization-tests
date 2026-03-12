import logging
import re

from ocp_resources.resource import Resource

from tests.install_upgrade_operators.utils import get_resource_container_env_image_mismatch
from utilities.exceptions import ResourceMismatch

LOGGER = logging.getLogger(__name__)


def validate_daemonset_request_fields(daemonset, cpu_min_value):
    """
    Validates that for a given daemonset object, for each containers: resources.requests contains cpu and memory
    fields. Cpu values can not be less than cpu_min_value

    Args:
        daemonset (Daemonset object): daemonset object to be used for field validation
        cpu_min_value (int): Minimum value of cpu resource request

    Raises:
        AssertionError: if resources.requests does not contains both cpu and memory, or if cpu request value is less
        than cpu_min_value
    """

    field_keys = ["cpu", "memory"]
    containers = daemonset.instance.spec.template.spec.containers
    missing_cpu_memory_values = {
        container["name"]: [
            field_key for field_key in field_keys if not container["resources"]["requests"].get(field_key)
        ]
        for container in containers
    }
    assert not any(missing_cpu_memory_values.values()), (
        f"For daemonset: {daemonset.name}, following resources.requests fields are missing: {missing_cpu_memory_values}"
    )

    cpu_values = {container["name"]: container["resources"]["requests"].get("cpu") for container in containers}
    cpu_value_pattern = re.compile(r"^\d+")

    invalid_cpus = {
        key: value for key, value in cpu_values.items() if int(cpu_value_pattern.findall(value)[0]) < cpu_min_value
    }
    if invalid_cpus:
        raise ResourceMismatch(
            f"For daemonset {daemonset.name} mismatch in cpu values found: {invalid_cpus}, "
            f"expected cpu values < {cpu_min_value}"
        )


def assert_cnv_daemonset_container_image_not_in_upstream(cnv_daemonset):
    cnv_daemonsets_with_upstream_image_reference = {
        container["name"]: container["image"]
        for container in cnv_daemonset.instance.spec.template.spec.containers
        if not container["image"].startswith(Resource.ApiGroup.IMAGE_REGISTRY)
    }

    if cnv_daemonsets_with_upstream_image_reference:
        raise ResourceMismatch(
            f"For following deployments upstream image references found: {cnv_daemonsets_with_upstream_image_reference}"
        )


def assert_cnv_daemonset_container_env_image_not_in_upstream(cnv_daemonset):
    cnv_daemonset_env_with_upstream_image_reference = {}
    for container in cnv_daemonset.instance.spec.template.spec.containers:
        resource_env_image_mismatch = get_resource_container_env_image_mismatch(container=container)
        if resource_env_image_mismatch:
            cnv_daemonset_env_with_upstream_image_reference[container["name"]] = resource_env_image_mismatch

    if cnv_daemonset_env_with_upstream_image_reference:
        raise ResourceMismatch(
            f"For following deployments upstream image references "
            f"found: {cnv_daemonset_env_with_upstream_image_reference}"
        )

import logging
import re

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

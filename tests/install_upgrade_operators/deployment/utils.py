from utilities.exceptions import ResourceMismatch


def validate_liveness_probe_fields(deployment):
    """
    Validates that for a given deployment object values of certain "livenessProbe" fields matches with expected
    values

    Args:
        deployment (Deployment object): Deployment object to be used for field validation

    Raises:
        Asserts on mismatch between expected and actual values of livenessProbe fields
    """
    field_expected_values = {
        "initialDelaySeconds": 30,
        "periodSeconds": 5,
        "failureThreshold": 1,
    }

    containers_with_mismatches = {
        container["name"]: {
            field_name: {
                "expected": field_expected_values[field_name],
                "actual": container["livenessProbe"][field_name],
            }
            for field_name in field_expected_values
            if container["livenessProbe"][field_name] != field_expected_values[field_name]
        }
        for container in deployment.instance.spec.template.spec.containers
    }
    if any(containers_with_mismatches.values()):
        raise ResourceMismatch(
            f"For deployment: {deployment.name}, following livenessProbe fields failed "
            f"validations: {containers_with_mismatches}"
        )

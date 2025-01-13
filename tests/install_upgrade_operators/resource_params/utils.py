def assert_status_condition(conditions, field_dict):
    """
    Validate that expected field is present in all conditions of status.conditions and not expected field does not
    show up there

    Args:
         conditions(list): list of conditions
         field_dict(dict): dictionary containing fields and whether they are expected to be present in conditions

    Raises:
        Asserts if expected field does not show up or unexpected field shows up in hyperconverged resource's
        status.conditions
    """

    for field in field_dict:
        condition_match = [condition for condition in conditions if field in condition.keys()]
        assert bool(condition_match) == field_dict[field], (
            f"Expected key: {field} to be present:{field_dict[field]} in hyperconverged object's status.condition."
            f" Actual result: {condition_match}"
        )
        if field_dict[field]:
            assert len(conditions) == len(condition_match), (
                f" Following conditions {condition_match} for hyperconverged resource contains key: {field}"
            )


def assert_observed_generation(hyperconverged_resource):
    """
    Validate observed generation of hyperconverged resource status.conditions matches with metadata.generation

    Args:
        hyperconverged_resource(Hyperconverged): Hyperconverged object

    Raises:
        Asserts on observedGeneration not matching with metadata.generation

    """
    error_condition = [
        condition
        for condition in hyperconverged_resource.status.conditions
        if condition["observedGeneration"] != hyperconverged_resource.metadata.generation
    ]
    assert not error_condition, (
        f"For following conditions: {error_condition} metadata.generation did not match with "
        f"status.conditions.observedGeneration."
    )

SERVICE_IP_FAMILY_POLICY_SINGLE_STACK = "SingleStack"
SERVICE_IP_FAMILY_POLICY_PREFER_DUAL_STACK = "PreferDualStack"
SERVICE_IP_FAMILY_POLICY_REQUIRE_DUAL_STACK = "RequireDualStack"


def assert_svc_ip_params(
    svc,
    expected_num_families_in_service,
    expected_ip_family_policy,
):
    assert (
        len(svc.instance.spec.ipFamilies) == expected_num_families_in_service
        and svc.instance.spec.ipFamilyPolicy == expected_ip_family_policy
    ), f"{expected_ip_family_policy} service wrongly created."

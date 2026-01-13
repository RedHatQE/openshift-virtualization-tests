from utilities.constants import SSH_PORT_22

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


def basic_expose_command(
    resource_name,
    svc_name,
    resource="vm",
    port="27017",
    target_port=SSH_PORT_22,
    service_type="NodePort",
    protocol="TCP",
):
    return (
        f"expose {resource} {resource_name} --port={port} --target-port="
        f"{target_port} --type={service_type} --name={svc_name} --protocol={protocol}"
    )

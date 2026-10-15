"""WSFC preconfiguration for https://redhat.atlassian.net/browse/CNV-70031."""

from logging import getLogger

from kubernetes.utils.quantity import parse_quantity
from pytest import mark

LOGGER = getLogger(name=__name__)

pytestmark = [mark.amd64, mark.windows, mark.ipv4, mark.tier3, mark.high_resource_vm, mark.special_infra]


def test_environment_ready_for_wsfc(iscsi_pr_environment) -> None:
    """
    Verify that the prepared environment is ready for subsequent WSFC scenarios.

    Jira: https://redhat.atlassian.net/browse/CNV-83048  # <skip-jira-utils-check>

    Preconditions:
        - CI provides three reserved workers, compatible storage and standard images.
        - Fixtures prepare Fedora iSCSI, host multipath, guest routing and AD/DNS.
    Steps:
        1. Verify the DC has 8 GiB, both members have 6 GiB and all have independent private roots.
        2. Verify all guests see the same two shared LUN identities.
        3. Verify one DC and two members belong to the prepared domain.
    Expected:
        - The environment is ready for subsequent WSFC scenarios.
        - Setup has verified both storage paths, actual QEMU consumption and PR configuration.
        - Only installation, promotion and join reboots occur; no WSFC cluster is created.
    """
    environment = iscsi_pr_environment
    vms, roots = environment["vms"], environment["roots"]
    LOGGER.info(
        f"Checking prepared environment: VMs={[vm.name for vm in vms]}, private roots={[root.name for root in roots]}"
    )
    assert len({vm.name for vm in vms}) == len({root.name for root in roots}) == 3, (
        f"Expected three distinct Windows guests and private roots; VMs={[vm.name for vm in vms]}, roots={[root.name for root in roots]}"
    )
    for index, (vm, root) in enumerate(zip(vms, roots, strict=True)):
        expected_memory = "8Gi" if index == 0 else "6Gi"
        assert parse_quantity(vm.vmi.instance.spec.domain.memory.guest) == parse_quantity(expected_memory), (
            f"VM {vm.name}: expected guest memory {expected_memory}, observed {vm.vmi.instance.spec.domain.memory.guest}"
        )
        boot_roots = [
            volume["dataVolume"]["name"]
            for volume in vm.instance.to_dict()["spec"]["template"]["spec"]["volumes"]
            if "dataVolume" in volume
        ]
        assert boot_roots == [root.name], f"VM {vm.name}: expected private root {[root.name]}, observed {boot_roots}"
    assert len(environment["guest_luns"]) == 3 and all(
        len(identities) == 2 and identities == environment["guest_luns"][0] for identities in environment["guest_luns"]
    ), f"Expected the same two LUN identities in all three Windows guests; observed {environment['guest_luns']}"
    assert [member["Role"] for member in environment["members"]] == [5, 3, 3], (
        f"Expected domain roles [5, 3, 3]; observed {[member['Role'] for member in environment['members']]}"
    )
    assert all(member["Domain"].lower() == environment["domain"].name for member in environment["members"]), (
        f"Expected domain {environment['domain'].name} for all guests; observed {[member['Domain'] for member in environment['members']]}"
    )
    LOGGER.info(f"Prepared environment checks passed for domain {environment['domain'].name}")

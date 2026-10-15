"""Shared assertions for policy-hook unit tests."""

from scripts.pre_commit_hooks import check_policy


def _violation_signatures(
    violations: list[check_policy.PolicyViolation],
) -> list[tuple[int | None, str]]:
    return [(violation.line_number, violation.message) for violation in violations]

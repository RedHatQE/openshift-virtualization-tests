"""Pytest test-runner constants.

Exit codes, quarantine marker strings, fixture scope strings, and
unprivileged test credential names used across pytest fixtures and utilities.
"""

DEPENDENCY_SCOPE_SESSION = "session"
QUARANTINED = "quarantined"
SETUP_ERROR = "setup_error"
SANITY_TESTS_FAILURE = 99
UNPRIVILEGED_USER = "unprivileged-user"
UNPRIVILEGED_PASSWORD = "unprivileged-password"

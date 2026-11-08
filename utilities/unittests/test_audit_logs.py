from datetime import UTC, datetime

import pytest

from utilities.audit_logs import (
    ACTIVE_AUDIT_LOG_NAME,
    audit_log_files_per_node,
    relevant_audit_logs,
)


def _naive_utc(*, year: int, month: int, day: int, hour: int = 0, minute: int = 0, second: int = 0) -> datetime:
    """Build a timezone-naive UTC datetime, matching the session fixture and the audit log file names."""
    return datetime(year, month, day, hour, minute, second, tzinfo=UTC).replace(tzinfo=None)


SESSION_START_TIME = _naive_utc(year=2026, month=1, day=2, hour=10)


class TestAuditLogFilesPerNode:
    @pytest.mark.parametrize(
        "command_output, expected_files",
        [
            pytest.param(
                ["node-1 audit.log"],
                {"node-1": [ACTIVE_AUDIT_LOG_NAME]},
                id="active log only",
            ),
            pytest.param(
                ["node-1 audit-2026-01-02T09-59-59.000.log"],
                {
                    "node-1": [
                        (
                            "audit-2026-01-02T09-59-59.000.log",
                            _naive_utc(year=2026, month=1, day=2, hour=9, minute=59, second=59),
                        )
                    ]
                },
                id="rotated log with timestamp",
            ),
            pytest.param(
                ["node-1 audit.log", "node-1 audit-2026-01-02T09-00-00.000.log", "node-2 audit.log"],
                {
                    "node-1": [
                        ACTIVE_AUDIT_LOG_NAME,
                        (
                            "audit-2026-01-02T09-00-00.000.log",
                            _naive_utc(year=2026, month=1, day=2, hour=9),
                        ),
                    ],
                    "node-2": [ACTIVE_AUDIT_LOG_NAME],
                },
                id="multiple nodes and files",
            ),
            pytest.param([], {}, id="empty output"),
        ],
    )
    def test_groups_files_per_node(self, command_output, expected_files):
        assert audit_log_files_per_node(command_output=command_output) == expected_files, (
            f"{command_output} should be grouped as {expected_files}"
        )

    @pytest.mark.parametrize(
        "command_output",
        [
            pytest.param(["only-node"], id="single field"),
            pytest.param(["node-1 audit.log extra"], id="three fields"),
            pytest.param([""], id="empty line"),
        ],
    )
    def test_skips_malformed_lines(self, command_output):
        assert audit_log_files_per_node(command_output=command_output) == {}, (
            f"malformed line {command_output} must not produce an entry"
        )

    def test_skips_non_audit_file_name(self):
        assert audit_log_files_per_node(command_output=["node-1 kube-apiserver.log"]) == {}, (
            "a non-audit file name must not produce an entry"
        )

    def test_skips_rotated_log_with_invalid_timestamp(self):
        assert audit_log_files_per_node(command_output=["node-1 audit-2026-13-45T99-99-99.000.log"]) == {}, (
            "a rotated log with an unparsable timestamp must not produce an entry"
        )


class TestRelevantAuditLogs:
    @pytest.mark.parametrize(
        "log_entries, expected_logs",
        [
            pytest.param([ACTIVE_AUDIT_LOG_NAME], [ACTIVE_AUDIT_LOG_NAME], id="active log kept"),
            pytest.param([], [], id="no entries"),
            pytest.param(
                [
                    (
                        "audit-2026-01-02T09-00-00.000.log",
                        _naive_utc(year=2026, month=1, day=2, hour=9),
                    ),
                    (
                        "audit-2026-01-02T10-00-00.000.log",
                        _naive_utc(year=2026, month=1, day=2, hour=10),
                    ),
                    (
                        "audit-2026-01-02T11-00-00.000.log",
                        _naive_utc(year=2026, month=1, day=2, hour=11),
                    ),
                ],
                [
                    "audit-2026-01-02T09-00-00.000.log",
                    "audit-2026-01-02T10-00-00.000.log",
                    "audit-2026-01-02T11-00-00.000.log",
                ],
                id="all rotated logs around the session start are kept",
            ),
            pytest.param(
                [
                    (
                        "audit-2026-01-02T08-00-00.000.log",
                        _naive_utc(year=2026, month=1, day=2, hour=8),
                    ),
                    (
                        "audit-2026-01-02T09-00-00.000.log",
                        _naive_utc(year=2026, month=1, day=2, hour=9),
                    ),
                    (
                        "audit-2026-01-02T10-00-00.000.log",
                        _naive_utc(year=2026, month=1, day=2, hour=10),
                    ),
                ],
                ["audit-2026-01-02T09-00-00.000.log", "audit-2026-01-02T10-00-00.000.log"],
                id="log preceding the session start is kept, older ones dropped",
            ),
            pytest.param(
                [
                    (
                        "audit-2026-01-02T10-00-00.000.log",
                        _naive_utc(year=2026, month=1, day=2, hour=10),
                    ),
                    (
                        "audit-2026-01-02T11-00-00.000.log",
                        _naive_utc(year=2026, month=1, day=2, hour=11),
                    ),
                ],
                ["audit-2026-01-02T10-00-00.000.log", "audit-2026-01-02T11-00-00.000.log"],
                id="no earlier log available keeps the first one",
            ),
        ],
    )
    def test_selects_session_logs(self, log_entries, expected_logs):
        assert relevant_audit_logs(log_entries=log_entries, session_start_time=SESSION_START_TIME) == expected_logs, (
            f"session logs should be {expected_logs}"
        )

    def test_rotated_logs_are_sorted_and_followed_by_active_logs(self):
        log_entries = [
            (
                "audit-2026-01-02T10-00-00.000.log",
                _naive_utc(year=2026, month=1, day=2, hour=10),
            ),
            ACTIVE_AUDIT_LOG_NAME,
            (
                "audit-2026-01-02T09-00-00.000.log",
                _naive_utc(year=2026, month=1, day=2, hour=9),
            ),
            (
                "audit-2026-01-02T11-00-00.000.log",
                _naive_utc(year=2026, month=1, day=2, hour=11),
            ),
        ]

        assert relevant_audit_logs(log_entries=log_entries, session_start_time=SESSION_START_TIME) == [
            "audit-2026-01-02T09-00-00.000.log",
            "audit-2026-01-02T10-00-00.000.log",
            "audit-2026-01-02T11-00-00.000.log",
            ACTIVE_AUDIT_LOG_NAME,
        ], "rotated logs must be sorted and the active log appended last"

"""Unit tests for CBT restore helper logic."""

from tests.storage.cbt.utils import (
    _checkpoint_timestamp_from_qcow2_path,
    _latest_checkpoint_timestamp,
    _sort_qcow2_files_by_checkpoint,
    _uses_placeholder_qcow2_suffixes,
)


class TestQcow2Discovery:
    def test_checkpoint_timestamp_from_qcow2_path(self):
        path = "/backup/vm/checkpoint/2024-06-01_12-30-45/volume-boot.qcow2"
        assert _checkpoint_timestamp_from_qcow2_path(qcow2_path=path) == "2024-06-01_12-30-45"

    def test_checkpoint_timestamp_missing_returns_empty_string(self):
        assert _checkpoint_timestamp_from_qcow2_path(qcow2_path="/backup/no-timestamp/volume.qcow2") == ""

    def test_sort_qcow2_files_by_checkpoint(self):
        older = "/backup/checkpoint/2024-06-01_10-00-00/disk-boot.qcow2"
        newer = "/backup/checkpoint/2024-06-02_10-00-00/disk-boot.qcow2"
        assert _sort_qcow2_files_by_checkpoint([newer, older]) == [older, newer]

    def test_latest_checkpoint_timestamp(self):
        qcow2_files = [
            "/backup/checkpoint/2024-06-01_10-00-00/disk-boot.qcow2",
            "/backup/checkpoint/2024-06-03_10-00-00/disk-boot.qcow2",
            "/backup/checkpoint/2024-06-02_10-00-00/disk-data.qcow2",
        ]
        assert _latest_checkpoint_timestamp(qcow2_files=qcow2_files) == "2024-06-03_10-00-00"


class TestPlaceholderQcow2Suffixes:
    def test_detects_default_boot_suffix(self):
        assert _uses_placeholder_qcow2_suffixes(qcow2_suffixes=["boot"]) is True

    def test_detects_generated_volume_suffix(self):
        assert _uses_placeholder_qcow2_suffixes(qcow2_suffixes=["volume-1"]) is True

    def test_real_volume_names_are_not_placeholders(self):
        assert _uses_placeholder_qcow2_suffixes(qcow2_suffixes=["disk0", "data-disk-dv"]) is False

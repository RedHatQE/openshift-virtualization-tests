# Co-authored-by: Claude <noreply@anthropic.com>
"""Tests for scripts.manual_tests_reporter.manual_tests_reporter module.

See scripts/manual_tests_reporter/README.md for the tool this module belongs to.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from click import ClickException
from click.testing import CliRunner
from pyhelper_utils.shell import run_command

from scripts.manual_tests_reporter import config as reporter_module_config
from scripts.manual_tests_reporter import manual_tests_reporter as reporter_module
from scripts.manual_tests_reporter.config import CONFIG_KEY_TO_ATTRIBUTE_KEY, load_config
from scripts.manual_tests_reporter.junit_report import ManualTestResult
from scripts.manual_tests_reporter.manual_tests_reporter import (
    _build_run_attributes,
    _load_batch_file,
    _merge_batch_metadata,
    _migrate_legacy_attributes,
    _normalize_tier_value,
    _save_results_for_retry,
    main,
)
from scripts.manual_tests_reporter.tests.utils import (
    MINIMAL_MANUAL_TEST_SOURCE,
    junit_report_path,
    read_junit_properties,
    required_attr_args,
    write_config_file,
    write_manual_tests_dir,
    write_minimal_batch,
    write_minimal_tests_dir,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def isolated_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Run every test from a temporary working directory.

    A regression in the success/cleanup path must never write
    ``manual_results_*.yaml`` into the repository checkout.
    """
    monkeypatch.chdir(path=tmp_path)


class TestBuildRunAttributes:
    def test_explicit_attrs_emit_short_keys(self) -> None:
        """Verify explicit CLI args produce the Jenkins-parity tag keys."""
        result = _build_run_attributes(
            team="NETWORK",
            bundle="v4.22.0",
            overrides={
                "cnv_xy_version": "4.22",
                "ocp_version": "4.22.0",
                "cluster": "bm15a",
                "cluster_domain": "bm15a.example.com",
                "cluster_id": "bm15a-tjxpz",
                "storage_class": "ocs-storagecluster-ceph-rbd",
                "cnv_channel": "candidate",
                "tier": "TIER-2",
                "owner": "tester@redhat.com",
            },
            marker="smoke",
            test_case_name="manual.network",
        )
        attrs_by_key = {attr["key"]: attr["value"] for attr in result}

        assert attrs_by_key["team"] == "NETWORK", "Expected: an explicitly passed team is carried verbatim"
        assert attrs_by_key["tier"] == "2", "Expected: bare-number tier tag"
        assert attrs_by_key["ocp_version"] == "4.22.0", "Expected: Jenkins-parity ocp_version tag"
        assert attrs_by_key["cnv_xy_version"] == "4.22", "Expected: Jenkins-parity cnv_xy_version tag"
        assert attrs_by_key["cluster"] == "bm15a", "Expected: Jenkins-parity cluster tag"
        assert attrs_by_key["cluster_domain"] == "bm15a.example.com", "Expected: cluster_domain tag"
        assert attrs_by_key["cluster_id"] == "bm15a-tjxpz", "Expected: cluster_id tag"
        assert attrs_by_key["storage_class"] == "ocs-storagecluster-ceph-rbd", "Expected: storage_class tag"
        assert attrs_by_key["cnv_channel"] == "candidate", "Expected: Jenkins-parity cnv_channel tag"
        assert attrs_by_key["owner"] == "tester@redhat.com", "Expected: owner tag"
        assert attrs_by_key["marker"] == "smoke", "Expected: marker tag"
        assert attrs_by_key["test_case_name"] == "manual.network", "Expected: test_case_name tag"
        assert "bundle" not in attrs_by_key, "Expected: no bundle tag (Jenkins set has cnv versions)"
        assert "arch" not in attrs_by_key, "Expected: no arch tag (Jenkins set has none)"

    def test_cnv_version_derived_from_bundle(self) -> None:
        """Verify cnv_version/cnv_xy_version are auto-derived from --bundle."""
        result = _build_run_attributes(bundle="v4.22.0.rhel9-102")
        attrs_by_key = {attr["key"]: attr["value"] for attr in result}
        assert attrs_by_key["cnv_version"] == "4.22.0", f"Expected '4.22.0', got {attrs_by_key['cnv_version']!r}"
        assert attrs_by_key["cnv_xy_version"] == "4.22", f"Expected '4.22', got {attrs_by_key['cnv_xy_version']!r}"

    def test_explicit_cnv_version_wins_over_bundle_derivation(self) -> None:
        """Explicit --cnv-version is never silently discarded.

        When both --bundle and --cnv-version are provided, the explicit
        CLI value wins, consistent with every other CLI override.
        """
        result = _build_run_attributes(
            bundle="v4.22.0",
            overrides={"cnv_xy_version": "4.21"},
        )
        attrs_by_key = {attr["key"]: attr["value"] for attr in result}
        assert attrs_by_key["cnv_xy_version"] == "4.21", f"Expected '4.21', got {attrs_by_key['cnv_xy_version']!r}"

    def test_cluster_cnv_version_kept_without_explicit_bundle(self) -> None:
        """Verify cluster-derived cnv versions are kept when bundle is not explicit."""
        result = _build_run_attributes(
            cluster_attrs=[
                {"key": "cnv_version", "value": "4.22.0"},
                {"key": "cnv_xy_version", "value": "4.21"},
            ],
        )
        attrs_by_key = {attr["key"]: attr["value"] for attr in result}
        assert attrs_by_key["cnv_xy_version"] == "4.21", f"Expected '4.21', got {attrs_by_key['cnv_xy_version']!r}"

    def test_cnv_xy_version_derived_from_cluster_cnv_version(self) -> None:
        """Verify cnv_xy_version is derived from a cluster-derived cnv_version."""
        result = _build_run_attributes(
            cluster_attrs=[
                {"key": "cnv_version", "value": "4.22.0"},
            ],
        )
        attrs_by_key = {attr["key"]: attr["value"] for attr in result}
        assert attrs_by_key["cnv_xy_version"] == "4.22", f"Expected '4.22', got {attrs_by_key['cnv_xy_version']!r}"

    def test_cnv_version_not_derived_without_bundle(self) -> None:
        """Verify cnv versions are not set when bundle and cluster attrs are missing."""
        result = _build_run_attributes()
        attrs_by_key = {attr["key"]: attr["value"] for attr in result}
        assert "cnv_version" not in attrs_by_key, "Expected: cnv_version not set without a bundle"
        assert "cnv_xy_version" not in attrs_by_key, "Expected: cnv_xy_version not set without a bundle"

    def test_team_preserved_verbatim(self) -> None:
        """Verify a team value is preserved verbatim, not re-cased.

        A replayed run must reproduce its recorded team attribute exactly, and
        a derived team already carries the Jenkins string as written — so the
        value is never re-cased on its way into the tag.
        """
        result = _build_run_attributes(team="network")
        attrs_by_key = {attr["key"]: attr["value"] for attr in result}
        assert attrs_by_key["team"] == "network", f"Expected 'network', got {attrs_by_key['team']!r}"

    def test_folder_to_team_values_match_jenkins_team_strings(self) -> None:
        """Verify derived teams use the Jenkins JOB_METADATA team vocabulary.

        The CI tag is ``team:${metadata.team}`` verbatim, so a short label
        such as ``NETWORK`` would land manual runs in a facet value no CI run
        ever writes. CHAOS/SCALE are exempt: no Jenkins job carries those
        test folders, so there is no CI value to match.
        """
        jenkins_teams = {
            "CNV Network",
            "Storage Platform",
            "CNV Virtualization",
            "CNV Infrastructure",
            "CNV Install, Upgrade and Operators",
        }
        manual_only = {"CHAOS", "SCALE"}
        unexpected = sorted(
            f"{folder}={team}"
            for folder, team in reporter_module._FOLDER_TO_TEAM.items()
            if team not in jenkins_teams | manual_only
        )
        assert not unexpected, (
            f"Team values outside the Jenkins vocabulary: {unexpected} - "
            "manual runs would be invisible to the CI team facet"
        )

    def test_tier_normalized_to_bare_number(self) -> None:
        """Verify tier labels normalize to the bare number Jenkins tags."""
        for tier_input, expected in (
            ("tier-2", "2"),
            ("TIER-2", "2"),
            ("tier2", "2"),
            ("2", "2"),
            (" 3 ", "3"),
        ):
            result = _build_run_attributes(overrides={"tier": tier_input})
            attrs_by_key = {attr["key"]: attr["value"] for attr in result}
            assert attrs_by_key["tier"] == expected, f"Expected {expected!r} from {tier_input!r}"

    def test_manual_attribute_always_present(self) -> None:
        """Verify the MANUAL run attribute is always emitted as 'true'."""
        result = _build_run_attributes(team="NETWORK")
        attrs_by_key = {attr["key"]: attr["value"] for attr in result}
        assert attrs_by_key["manual"] == "true", f"Expected 'true', got {attrs_by_key['manual']!r}"

        result_without_team = _build_run_attributes()
        attrs_by_key_without_team = {attr["key"]: attr["value"] for attr in result_without_team}
        assert attrs_by_key_without_team["manual"] == "true", "Expected: MANUAL attribute present even without a team"


class TestLoadBatchFile:
    def test_load_batch_file(self, tmp_path: Path) -> None:
        """Verify results and metadata are loaded from a batch YAML file."""
        batch_path = tmp_path / "batch.yaml"
        batch_path.write_text(
            data=(
                "metadata:\n"
                "  bundle: v4.22.0\n"
                "results:\n"
                "  - test: tests/net/test_a.py::TestA::test_one\n"
                "    status: passed\n"
                "  - test: tests/net/test_a.py::TestA::test_two\n"
                "    status: failed\n"
                "    comment: boom\n"
                "    issue_type_label: Product Bug\n"
            ),
            encoding="utf-8",
        )

        results, metadata = _load_batch_file(batch_path=batch_path)

        assert len(results) == 2, f"Expected 2, got {len(results)!r}"
        assert results[0].status == "PASSED", f"Expected 'PASSED', got {results[0].status!r}"
        assert results[1].status == "FAILED", f"Expected 'FAILED', got {results[1].status!r}"
        assert results[1].issue_type_label == "Product Bug", (
            f"Expected 'Product Bug', got {results[1].issue_type_label!r}"
        )
        assert metadata["bundle"] == "v4.22.0", f"Expected 'v4.22.0', got {metadata['bundle']!r}"

    def test_load_batch_file_invalid_status(self, tmp_path: Path) -> None:
        """Verify unknown status values raise a single clean ClickException.

        The message must carry the raw value as typed and the allowed set
        exactly once — not the stacked coerce_status error text.
        """
        batch_path = tmp_path / "batch.yaml"
        batch_path.write_text(
            data=("results:\n  - test: tests/net/test_a.py::TestA::test_one\n    status: maybe\n"),
            encoding="utf-8",
        )

        with pytest.raises(
            expected_exception=ClickException,
            match=(
                r"Invalid status 'maybe' for test 'tests/net/test_a\.py::TestA::test_one' "
                "in batch file .*; expected one of: FAILED, PASSED, SKIPPED"
            ),
        ):
            _load_batch_file(batch_path=batch_path)

    def test_load_batch_file_status_with_trailing_whitespace(self, tmp_path: Path) -> None:
        """Verify a hand-edited status with trailing whitespace is still accepted."""
        batch_path = tmp_path / "batch.yaml"
        batch_path.write_text(
            data=('results:\n  - test: tests/net/test_a.py::TestA::test_one\n    status: "passed "\n'),
            encoding="utf-8",
        )

        results, _metadata = _load_batch_file(batch_path=batch_path)
        assert results[0].status == "PASSED", "Expected: trailing whitespace in status is tolerated"

    def test_load_batch_file_duplicate_status_key_rejected(self, tmp_path: Path) -> None:
        """Verify a duplicated status key in a batch entry is rejected, not last-won."""
        batch_path = tmp_path / "batch.yaml"
        batch_path.write_text(
            data=("results:\n  - test: tests/net/test_a.py::TestA::test_one\n    status: failed\n    status: passed\n"),
            encoding="utf-8",
        )

        with pytest.raises(expected_exception=ClickException, match="Failed to read batch file"):
            _load_batch_file(batch_path=batch_path)

    def test_load_batch_file_invalid_test_type(self, tmp_path: Path) -> None:
        """Verify non-string test values raise a ClickException."""
        batch_path = tmp_path / "batch.yaml"
        batch_path.write_text(
            data=("results:\n  - test: 123\n    status: passed\n"),
            encoding="utf-8",
        )

        with pytest.raises(expected_exception=ClickException, match="Invalid test type"):
            _load_batch_file(batch_path=batch_path)

    def test_load_batch_file_null_comment_coerced(self, tmp_path: Path) -> None:
        """Verify a YAML null comment is coerced to an empty string."""
        batch_path = tmp_path / "batch.yaml"
        batch_path.write_text(
            data=("results:\n  - test: tests/net/test_a.py::TestA::test_one\n    status: passed\n    comment:\n"),
            encoding="utf-8",
        )

        results, _metadata = _load_batch_file(batch_path=batch_path)
        assert results[0].comment == "", "Expected: null comment loads as empty string"

    def test_load_batch_file_null_test_rejected(self, tmp_path: Path) -> None:
        """Verify a YAML null test key is rejected at load time."""
        batch_path = tmp_path / "batch.yaml"
        batch_path.write_text(
            data=("results:\n  - test:\n    status: passed\n"),
            encoding="utf-8",
        )

        with pytest.raises(expected_exception=ClickException, match="missing or null 'test' key"):
            _load_batch_file(batch_path=batch_path)

    def test_load_batch_file_strips_whitespace_from_metadata_and_comment(self, tmp_path: Path) -> None:
        """Verify whitespace-padded hand-edited values are stripped on load.

        A padded ``bundle`` would otherwise produce a Datadog tag with
        embedded spaces (``bundle: v4.22.0 ``) — a different tag.
        """
        batch_path = tmp_path / "batch.yaml"
        batch_path.write_text(
            data=(
                "metadata:\n"
                '  bundle: " v4.22.0 "\n'
                "results:\n"
                "  - test: tests/net/test_a.py::TestA::test_one\n"
                "    status: passed\n"
                '    comment: " flaky on node two "\n'
            ),
            encoding="utf-8",
        )

        results, metadata = _load_batch_file(batch_path=batch_path)

        assert metadata["bundle"] == "v4.22.0", (
            f"Expected 'v4.22.0' with no embedded spaces, got {metadata['bundle']!r}"
        )
        assert results[0].comment == "flaky on node two", f"Expected 'flaky on node two', got {results[0].comment!r}"

    @pytest.mark.parametrize("metadata_key", ["bundle"])
    def test_load_batch_file_non_string_metadata_rejected(self, tmp_path: Path, metadata_key: str) -> None:
        """Verify a non-string bundle metadata value is rejected, not stringified."""
        batch_path = tmp_path / "batch.yaml"
        batch_path.write_text(
            data=(
                f"metadata:\n  {metadata_key}: [NETWORK]\n"
                "results:\n  - test: tests/net/test_a.py::TestA::test_one\n    status: passed\n"
            ),
            encoding="utf-8",
        )

        with pytest.raises(expected_exception=ClickException, match=f"Invalid {metadata_key} type"):
            _load_batch_file(batch_path=batch_path)


class TestMainDryRun:
    def test_dry_run_no_upload(self, tmp_path: Path) -> None:
        """Verify dry-run with a batch file exits without uploading."""
        tests_dir = write_minimal_tests_dir(tmp_path=tmp_path)
        batch_path = tmp_path / "batch.yaml"
        batch_path.write_text(
            data=(
                "metadata:\n"
                "  team: NETWORK\n"
                "  bundle: v4.22.0\n"
                "results:\n"
                "  - test: tests/net/test_a.py::TestA::test_one\n"
                "    status: passed\n"
            ),
            encoding="utf-8",
        )

        runner = CliRunner()
        result = runner.invoke(
            cli=main,
            args=[
                "--tests-dir",
                str(tests_dir),
                "--batch-file",
                str(batch_path),
                "--dry-run",
            ],
        )

        assert result.exit_code == 0, result.output
        assert "No report was written (dry run)." in result.output, (
            "Expected: dry-run with a batch file exits without writing the report"
        )
        assert "team = CNV Network" in result.output, "Expected: dry-run with a batch file resolves the team"


class TestSaveResultsForRetry:
    def test_save_load_round_trip(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify a saved retry file reloads with metadata and results intact."""
        monkeypatch.chdir(path=tmp_path)
        results = [
            ManualTestResult(test="tests/net/test_a.py::TestA::test_one", status="PASSED"),
            ManualTestResult(
                test="tests/net/test_a.py::TestA::test_two",
                status="FAILED",
                comment="boom",
                issue_type_label="Product Bug",
            ),
            ManualTestResult(test="tests/net/test_a.py::TestA::test_three", status="SKIPPED"),
        ]
        attributes = [{"key": "team", "value": "NETWORK"}]

        saved_path = _save_results_for_retry(
            results=results,
            bundle="v4.22.0",
            attributes=attributes,
        )
        assert saved_path is not None, "Expected: retry file is saved for the round trip"
        loaded_results, metadata = _load_batch_file(batch_path=saved_path)

        assert loaded_results == results, "Expected matching values"
        assert metadata["bundle"] == "v4.22.0", f"Expected 'v4.22.0', got {metadata['bundle']!r}"
        assert metadata["attributes"] == attributes, "Expected matching values"


class TestFromClusterImportGuard:
    def test_from_cluster_without_cluster_access(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify --from-cluster fails cleanly when cluster modules did not load."""
        batch_path = tmp_path / "batch.yaml"
        batch_path.write_text(
            data=("results:\n  - test: tests/net/test_a.py::TestA::test_one\n    status: passed\n"),
            encoding="utf-8",
        )

        monkeypatch.setattr(
            target=reporter_module,
            name="_CLUSTER_INFO_IMPORT_ERROR",
            value="Invalid kube-config file. No configuration found.",
        )
        runner = CliRunner()
        result = runner.invoke(
            cli=main,
            args=["--batch-file", str(batch_path), "--from-cluster", "--dry-run"],
        )

        assert result.exit_code != 0, "Expected: --from-cluster fails without cluster access"
        assert "--from-cluster requires cluster access" in result.output, (
            "Expected: clean ClickException guidance when cluster modules did not load"
        )

    def test_from_cluster_zero_attributes_points_at_cluster_access(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify the missing-attributes error hints at cluster access when --from-cluster resolved nothing.

        A user who already passed --from-cluster additionally gets a hint
        pointing at cluster access (KUBECONFIG) when the flag resolved no
        attributes — the generic remedy line stays, the hint supplements it.
        """
        tests_dir, batch_path = write_minimal_batch(tmp_path=tmp_path)
        monkeypatch.setattr(target=reporter_module, name="_CLUSTER_INFO_IMPORT_ERROR", value=None)
        with (
            patch(
                target="scripts.manual_tests_reporter.manual_tests_reporter.get_cluster_attributes",
                return_value=object(),
            ),
            patch(
                target="scripts.manual_tests_reporter.manual_tests_reporter.cluster_attributes_to_run_attrs",
                return_value=[],
            ),
        ):
            result = CliRunner().invoke(
                cli=main,
                args=[
                    "--tests-dir",
                    str(tests_dir),
                    "--batch-file",
                    str(batch_path),
                    "--from-cluster",
                ],
            )

        assert result.exit_code != 0, "Expected: upload validation fails without required attributes"
        assert "Missing required run attributes" in result.output, "Expected: the missing-attributes error is raised"
        assert (
            "--from-cluster resolved no cluster attributes; check cluster access and permissions (KUBECONFIG)"
            in result.output
        ), "Expected: cluster-access hint appended when --from-cluster resolved nothing"

    def test_from_cluster_zero_attributes_hint_survives_partial_replay(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify the cluster-access hint survives a partial retry-file restore.

        The hint is gated on what the cluster itself resolved, not on the
        post-merge attribute list: restoring saved attributes from a retry
        file must not suppress the hint when --from-cluster resolved
        nothing.
        """
        tests_dir, batch_path = write_minimal_batch(tmp_path=tmp_path)
        batch_path.write_text(
            data=(
                "metadata:\n"
                "  attributes:\n"
                "    - key: team\n"
                "      value: NETWORK\n"
                "results:\n"
                "  - test: tests/network/test_manual_minimal.py::test_minimal\n"
                "    status: passed\n"
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(target=reporter_module, name="_CLUSTER_INFO_IMPORT_ERROR", value=None)
        with (
            patch(
                target="scripts.manual_tests_reporter.manual_tests_reporter.get_cluster_attributes",
                return_value=object(),
            ),
            patch(
                target="scripts.manual_tests_reporter.manual_tests_reporter.cluster_attributes_to_run_attrs",
                return_value=[],
            ),
        ):
            result = CliRunner().invoke(
                cli=main,
                args=[
                    "--tests-dir",
                    str(tests_dir),
                    "--batch-file",
                    str(batch_path),
                    "--from-cluster",
                ],
            )

        assert result.exit_code != 0, "Expected: upload validation fails without required attributes"
        assert "--from-cluster resolved no cluster attributes" in result.output, (
            "Expected: hint present even though a partial retry file restored one attribute"
        )

    def test_from_cluster_partial_resolution_no_zero_hint(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify the cluster-access hint stays absent when the cluster resolved something.

        A partial cluster resolution (some attributes, others still missing)
        must not claim the cluster resolved nothing.
        """
        tests_dir, batch_path = write_minimal_batch(tmp_path=tmp_path)
        monkeypatch.setattr(target=reporter_module, name="_CLUSTER_INFO_IMPORT_ERROR", value=None)
        with (
            patch(
                target="scripts.manual_tests_reporter.manual_tests_reporter.get_cluster_attributes",
                return_value=object(),
            ),
            patch(
                target="scripts.manual_tests_reporter.manual_tests_reporter.cluster_attributes_to_run_attrs",
                return_value=[{"key": "cluster", "value": "bm15a"}],
            ),
        ):
            result = CliRunner().invoke(
                cli=main,
                args=[
                    "--tests-dir",
                    str(tests_dir),
                    "--batch-file",
                    str(batch_path),
                    "--from-cluster",
                ],
            )

        assert result.exit_code != 0, "Expected: upload validation fails without required attributes"
        assert "--from-cluster resolved no cluster attributes" not in result.output, (
            "Expected: no zero-resolution hint when the cluster resolved an attribute"
        )

    def test_underivable_bundle_names_the_culprit(self, tmp_path: Path) -> None:
        """Verify a bundle without a major.minor version is named in the error.

        A malformed --bundle must not surface as a bare missing-attribute
        error: the message names the bundle value and asks for an explicit
        --cnv-version.
        """
        tests_dir, batch_path = write_minimal_batch(tmp_path=tmp_path)
        result = CliRunner().invoke(
            cli=main,
            args=[
                "--tests-dir",
                str(tests_dir),
                "--batch-file",
                str(batch_path),
                "--bundle",
                "v4",
                "--ocp-version",
                "4.22.0",
                "--cluster-name",
                "bm15a",
                "--cluster-domain",
                "bm15a.example.com",
                "--sc",
                "ocs",
                "--channel",
                "candidate",
                "--owner",
                "tester@redhat.com",
            ],
        )

        assert result.exit_code != 0, "Expected: upload validation fails for an underivable bundle"
        assert "The bundle 'v4' has no major.minor version; pass --cnv-version explicitly" in result.output, (
            "Expected: the underivable bundle is named as the culprit"
        )

    def test_dry_run_warning_carries_extra_guidance(self, tmp_path: Path) -> None:
        """Verify the dry-run warning carries the same extra guidance as the hard error.

        An underivable bundle must be named in the dry-run warning too —
        dry-run is the documented pre-flight mode, so its prediction must
        match what the real upload error would say.
        """
        tests_dir, batch_path = write_minimal_batch(tmp_path=tmp_path)
        result = CliRunner().invoke(
            cli=main,
            args=[
                "--tests-dir",
                str(tests_dir),
                "--batch-file",
                str(batch_path),
                "--bundle",
                "v4",
                "--dry-run",
            ],
        )

        assert result.exit_code == 0, "Expected: dry-run never fails on missing attributes"
        assert "the report would be incomplete — missing:" in result.stderr, (
            "Expected: warning listing missing attributes"
        )
        assert "The bundle 'v4' has no major.minor version; pass --cnv-version explicitly" in result.stderr, (
            "Expected: underivable-bundle guidance in the dry-run warning"
        )

    def test_dry_run_warning_carries_cluster_access_hint(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify the dry-run warning carries the cluster-access hint on zero resolution.

        Dry-run is the documented pre-flight mode: its prediction must
        match what the real upload error would say when --from-cluster
        resolved nothing.
        """
        tests_dir, batch_path = write_minimal_batch(tmp_path=tmp_path)
        monkeypatch.setattr(target=reporter_module, name="_CLUSTER_INFO_IMPORT_ERROR", value=None)
        with (
            patch(
                target="scripts.manual_tests_reporter.manual_tests_reporter.get_cluster_attributes",
                return_value=object(),
            ),
            patch(
                target="scripts.manual_tests_reporter.manual_tests_reporter.cluster_attributes_to_run_attrs",
                return_value=[],
            ),
        ):
            result = CliRunner().invoke(
                cli=main,
                args=[
                    "--tests-dir",
                    str(tests_dir),
                    "--batch-file",
                    str(batch_path),
                    "--from-cluster",
                    "--dry-run",
                ],
            )

        assert result.exit_code == 0, "Expected: dry-run never fails on missing attributes"
        assert "the report would be incomplete — missing:" in result.stderr, (
            "Expected: warning listing missing attributes"
        )
        assert (
            "--from-cluster resolved no cluster attributes; check cluster access and permissions (KUBECONFIG)"
            in result.stderr
        ), "Expected: cluster-access hint in the dry-run warning"


class TestLoadBatchFileAttributes:
    def test_load_batch_file_invalid_attributes_entry(self, tmp_path: Path) -> None:
        """Verify non-dict or non-string attributes entries are rejected at load time."""
        batch_path = tmp_path / "batch.yaml"
        batch_path.write_text(
            data=(
                "results:\n"
                "  - test: tests/net/test_a.py::TestA::test_one\n"
                "    status: passed\n"
                "metadata:\n"
                "  attributes:\n"
                "    - 1\n"
            ),
            encoding="utf-8",
        )
        with pytest.raises(expected_exception=ClickException, match="Invalid attributes entry"):
            _load_batch_file(batch_path=batch_path)


class TestMergeBatchMetadata:
    def test_batch_attributes_empty_value_rejected(self, tmp_path: Path) -> None:
        """Verify a batch attribute with an empty value fails cleanly."""
        batch_path = tmp_path / "batch.yaml"
        batch_path.write_text(
            data=(
                "results:\n"
                "  - test: tests/net/test_a.py::TestA::test_one\n"
                "    status: passed\n"
                "metadata:\n"
                "  attributes:\n"
                "    - key: team\n"
                "      value: ''\n"
            ),
            encoding="utf-8",
        )
        with pytest.raises(expected_exception=ClickException, match="non-empty string key and value"):
            _load_batch_file(batch_path=batch_path)

    def test_batch_attributes_duplicate_key_rejected(self, tmp_path: Path) -> None:
        """Verify duplicate batch attribute keys fail cleanly."""
        batch_path = tmp_path / "batch.yaml"
        batch_path.write_text(
            data=(
                "results:\n"
                "  - test: tests/net/test_a.py::TestA::test_one\n"
                "    status: passed\n"
                "metadata:\n"
                "  attributes:\n"
                "    - key: team\n"
                "      value: NETWORK\n"
                "    - key: team\n"
                "      value: STORAGE\n"
            ),
            encoding="utf-8",
        )
        with pytest.raises(expected_exception=ClickException, match="Duplicate attribute key"):
            _load_batch_file(batch_path=batch_path)

    def test_batch_attributes_non_list_rejected(self, tmp_path: Path) -> None:
        """Verify a non-list attributes value in batch metadata fails cleanly."""
        batch_path = tmp_path / "batch.yaml"
        batch_path.write_text(
            data=(
                "results:\n"
                "  - test: tests/net/test_a.py::TestA::test_one\n"
                "    status: passed\n"
                "metadata:\n"
                "  attributes:\n"
                "    TEAM: NETWORK\n"
            ),
            encoding="utf-8",
        )
        with pytest.raises(expected_exception=ClickException, match="Invalid attributes type"):
            _load_batch_file(batch_path=batch_path)

    def test_batch_attributes_case_duplicate_rejected(self, tmp_path: Path) -> None:
        """Verify exact duplicate attribute keys fail on load.

        Keys converge to the canonical modern form before the duplicate
        check, so a mixed-case twin (cnv_version + CNV_VERSION) collides
        too — it would otherwise upload two contradictory tags.
        """
        batch_path = tmp_path / "batch.yaml"
        batch_path.write_text(
            data=(
                "results:\n"
                "  - test: tests/net/test_a.py::TestA::test_one\n"
                "    status: passed\n"
                "metadata:\n"
                "  attributes:\n"
                "    - key: team\n"
                "      value: NETWORK\n"
                "    - key: team\n"
                "      value: STORAGE\n"
            ),
            encoding="utf-8",
        )
        with pytest.raises(expected_exception=ClickException, match="Duplicate attribute key"):
            _load_batch_file(batch_path=batch_path)

    def test_marker_replay_keeps_saved_marker_tag(self, tmp_path: Path) -> None:
        """Verify a replay with a different -m filter does not retag the marker.

        The CLI marker is only a live collection filter on a replay; the
        recorded marker attribute stands so the replay reproduces the
        recorded run (the test_case_name treatment).
        """
        attrs_by_key = _build_run_attributes(
            team=None,
            bundle=None,
            marker=None,
            test_case_name=None,
            cluster_attrs=[
                {"key": "team", "value": "NETWORK"},
                {"key": "cnv_version", "value": "4.22.0"},
                {"key": "cnv_xy_version", "value": "4.22"},
                {"key": "ocp_version", "value": "4.22.0"},
                {"key": "cluster", "value": "bm15a"},
                {"key": "cluster_domain", "value": "bm15a.example.com"},
                {"key": "cluster_id", "value": "bm15a-tjxpz"},
                {"key": "storage_class", "value": "ocs"},
                {"key": "cnv_channel", "value": "stable"},
                {"key": "marker", "value": "gating and not tier3"},
                {"key": "test_case_name", "value": "manual.network"},
                {"key": "tier", "value": "2"},
                {"key": "manual", "value": "true"},
            ],
        )

        marker_values = [attr["value"] for attr in attrs_by_key if attr["key"] == "marker"]
        assert marker_values == ["gating and not tier3"], (
            f"Expected the recorded marker to stand on a replay, got {marker_values!r}"
        )

    def test_batch_attributes_keys_replayed_verbatim(self, tmp_path: Path) -> None:
        """Verify unknown attribute keys are preserved verbatim, not re-cased."""
        batch_path = tmp_path / "batch.yaml"
        batch_path.write_text(
            data=(
                "results:\n"
                "  - test: tests/net/test_a.py::TestA::test_one\n"
                "    status: passed\n"
                "metadata:\n"
                "  attributes:\n"
                "    - key: CustomKey\n"
                "      value: NETWORK\n"
                "    - key: another_key\n"
                "      value: STORAGE\n"
            ),
            encoding="utf-8",
        )
        _results, metadata = _load_batch_file(batch_path=batch_path)

        assert metadata["attributes"] == [
            {"key": "CustomKey", "value": "NETWORK"},
            {"key": "another_key", "value": "STORAGE"},
        ], "Expected: unknown keys preserved verbatim for an exact replay"

    def test_batch_attributes_legacy_keys_migrated(self, tmp_path: Path) -> None:
        """Verify legacy upper-case attribute keys migrate to the Jenkins-parity names.

        A retry file saved before the tag rename carries TEAM/OCP/SC keys;
        migrating them on load keeps legacy retries replayable (validation
        and the team-restoration lookup expect the modern names). Keys with
        no modern equivalent (ARCH) stay verbatim.
        """
        batch_path = tmp_path / "batch.yaml"
        batch_path.write_text(
            data=(
                "results:\n"
                "  - test: tests/net/test_a.py::TestA::test_one\n"
                "    status: passed\n"
                "metadata:\n"
                "  attributes:\n"
                "    - key: TEAM\n"
                "      value: NETWORK\n"
                "    - key: OCP\n"
                "      value: 4.22.0\n"
                "    - key: SC\n"
                "      value: ocs\n"
                "    - key: ARCH\n"
                "      value: amd64\n"
            ),
            encoding="utf-8",
        )
        _results, metadata = _load_batch_file(batch_path=batch_path)

        attrs_by_key = {attr["key"]: attr["value"] for attr in metadata["attributes"]}
        assert attrs_by_key == {
            "team": "NETWORK",
            "ocp_version": "4.22.0",
            "storage_class": "ocs",
            "ARCH": "amd64",
        }, f"Expected legacy keys migrated, no-equivalent keys verbatim, got {attrs_by_key!r}"

    def test_unsupported_tier_spelling_rejected(self) -> None:
        """Verify a tier spelling that does not collapse to a number fails fast.

        A value with no digits at all (``prod``) would upload a corrupt tier
        facet; the no-defensive-programming rule prescribes failing at the
        trust boundary instead. Separator-heavy spellings (``tier - 2``)
        still collapse to the bare number.
        """
        assert _normalize_tier_value(tier="tier - 2") == "2", (
            "Expected: separator-heavy spelling collapses to the bare number"
        )
        with pytest.raises(expected_exception=ClickException, match="Unsupported tier spelling"):
            _normalize_tier_value(tier="prod")
        with pytest.raises(expected_exception=ClickException, match="Unsupported tier spelling"):
            _normalize_tier_value(tier="٢")

    def test_legacy_non_numeric_tier_kept_with_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """Verify a recorded non-numeric tier value is kept, not fatal.

        A replay reproduces the recorded run; the value cannot be re-created
        by the user, so it stands with a warning (live CLI input still fails
        fast — see test_unsupported_tier_spelling_rejected).
        """
        with caplog.at_level(level="WARNING"):
            migrated = _migrate_legacy_attributes(attributes=[{"key": "TIER", "value": "TIER-2 (gating)"}])
        assert migrated == [{"key": "tier", "value": "TIER-2 (gating)"}], (
            f"Expected the recorded value kept verbatim, got {migrated!r}"
        )
        assert [record for record in caplog.records if "kept verbatim" in record.getMessage()], (
            "Expected: keeping a non-numeric recorded tier warns"
        )

    def test_explicit_cnv_version_contradiction_warns(self, caplog: pytest.LogCaptureFixture) -> None:
        """Verify an explicit --cnv-version disagreeing with the bundle warns.

        Both values are uploaded as given; the contradiction is surfaced on
        both channels instead of silently shipping inconsistent facets.
        A matching pair stays silent.
        """
        with caplog.at_level(level="WARNING"):
            _build_run_attributes(bundle="v4.22.0.rhel9-102", overrides={"cnv_xy_version": "4.21"})
        contradiction_warnings = [
            record for record in caplog.records if "conflicts with cnv_version" in record.getMessage()
        ]
        assert contradiction_warnings, "Expected: contradiction warning for 4.21 vs bundle 4.22.0"

        caplog.clear()
        with caplog.at_level(level="WARNING"):
            _build_run_attributes(bundle="v4.22.0.rhel9-102", overrides={"cnv_xy_version": "4.22"})
        assert not [record for record in caplog.records if "conflicts with cnv_version" in record.getMessage()], (
            "Expected: matching cnv-version pair stays silent"
        )

    def test_legacy_bundle_derives_cnv_version_and_keeps_recorded_xy(self) -> None:
        """Verify a legacy BUNDLE derives cnv_version next to the recorded XY.

        The migration derives cnv_version from the legacy BUNDLE entry and
        keeps the neighboring legacy CNV_XY_VER verbatim; the resulting
        contradiction (if any) is surfaced by the unified final check in
        _build_run_attributes (see test_restored_contradictory_pair_warns).
        """
        migrated = _migrate_legacy_attributes(
            attributes=[
                {"key": "BUNDLE", "value": "v4.22.0.rhel9-102"},
                {"key": "CNV_XY_VER", "value": "4.21"},
            ]
        )
        attrs_by_key = {attr["key"]: attr["value"] for attr in migrated}
        assert attrs_by_key["cnv_version"] == "4.22.0", "Expected: cnv_version derived from the legacy BUNDLE"
        assert attrs_by_key["cnv_xy_version"] == "4.21", "Expected: recorded legacy XY kept verbatim"

    def test_restored_contradictory_pair_warns(self, caplog: pytest.LogCaptureFixture) -> None:
        """Verify the unified final check fires for restored attribute pairs.

        Legacy retry files and gap-filled batch attributes reach the
        contradiction check through cluster_attrs — a restored pair that
        disagrees must warn, and a matching pair must stay silent.
        """
        contradictory_attrs = [
            {"key": "cnv_version", "value": "4.19.3"},
            {"key": "cnv_xy_version", "value": "4.18"},
        ]
        with caplog.at_level(level="WARNING"):
            _build_run_attributes(cluster_attrs=contradictory_attrs)
        assert [record for record in caplog.records if "conflicts with cnv_version" in record.getMessage()], (
            "Expected: restored contradictory pair warns"
        )

        caplog.clear()
        matching_attrs = [
            {"key": "cnv_version", "value": "4.19.3"},
            {"key": "cnv_xy_version", "value": "4.19"},
        ]
        with caplog.at_level(level="WARNING"):
            _build_run_attributes(cluster_attrs=matching_attrs)
        assert not [record for record in caplog.records if "conflicts with cnv_version" in record.getMessage()], (
            "Expected: matching restored pair stays silent"
        )

    def test_modern_key_case_converges(self) -> None:
        """Verify a hand-edited modern key in non-canonical case converges.

        ``CNV_VERSION`` must map to ``cnv_version`` so the duplicate check
        and the bundle gap-fill see the same key the CLI writes, instead of
        uploading two contradictory lower-cased cnv_version tags.
        """
        migrated = _migrate_legacy_attributes(
            attributes=[
                {"key": "CNV_VERSION", "value": "4.21.0"},
                {"key": "MANUAL", "value": "true"},
                {"key": "CustomKey", "value": "NETWORK"},
            ]
        )
        attrs_by_key = {attr["key"]: attr["value"] for attr in migrated}
        assert attrs_by_key["cnv_version"] == "4.21.0", f"Expected canonical cnv_version, got {attrs_by_key!r}"
        assert attrs_by_key["manual"] == "true", f"Expected canonical manual, got {attrs_by_key!r}"
        assert attrs_by_key["CustomKey"] == "NETWORK", "Expected: unknown keys stay verbatim"

    def test_duplicate_detection_after_case_convergence(self, tmp_path: Path) -> None:
        """Verify a mixed-case duplicate collides after case convergence."""
        batch_path = tmp_path / "batch.yaml"
        batch_path.write_text(
            data=(
                "results:\n"
                "  - test: tests/net/test_a.py::TestA::test_one\n"
                "    status: passed\n"
                "metadata:\n"
                "  attributes:\n"
                "    - key: cnv_version\n"
                "      value: 4.21.0\n"
                "    - key: CNV_VERSION\n"
                "      value: 4.22.0\n"
            ),
            encoding="utf-8",
        )
        with pytest.raises(expected_exception=ClickException, match="Duplicate attribute key"):
            _load_batch_file(batch_path=batch_path)

    def test_legacy_tier_value_normalized(self) -> None:
        """Verify a legacy upper-cased TIER value migrates to a bare number.

        Retry files saved by the previous tool stored ``TIER-2`` values; a
        migrated replay must upload the same ``tier:2`` tag a fresh run
        does, not fragment the tier facet with ``tier:TIER-2``.
        """
        migrated = _migrate_legacy_attributes(attributes=[{"key": "TIER", "value": "TIER-2"}])
        assert migrated == [{"key": "tier", "value": "2"}], f"Expected normalized tier, got {migrated!r}"

    def test_lowercase_bundle_key_migrates(self) -> None:
        """Verify a hand-edited lowercase 'bundle' key migrates, not uploads as a tag."""
        migrated = _migrate_legacy_attributes(
            attributes=[
                {"key": "team", "value": "NETWORK"},
                {"key": "bundle", "value": "v4.22.0.rhel9-102"},
            ]
        )
        attrs_by_key = {attr["key"]: attr["value"] for attr in migrated}
        assert "bundle" not in attrs_by_key, "Expected: no bundle tag survives the migration"
        assert attrs_by_key["cnv_version"] == "4.22.0", f"Expected derived cnv_version, got {attrs_by_key!r}"
        assert attrs_by_key["cnv_xy_version"] == "4.22", f"Expected derived cnv_xy_version, got {attrs_by_key!r}"

    def test_legacy_retry_file_passes_validation(self, tmp_path: Path) -> None:
        """Verify a full legacy retry file replays through modern validation.

        A retry file saved before the Jenkins-parity rename carries only
        upper-case keys and a BUNDLE entry; the migration must derive
        cnv_version from BUNDLE (a replay suppresses the metadata bundle,
        so nothing else produces it) or the report validation hard-fails.
        """
        tests_dir, batch_path = write_minimal_batch(tmp_path=tmp_path)
        batch_path.write_text(
            data=(
                "metadata:\n"
                "  bundle: v4.22.0.rhel9-102\n"
                "  attributes:\n"
                "    - key: TEAM\n"
                "      value: NETWORK\n"
                "    - key: BUNDLE\n"
                "      value: v4.22.0.rhel9-102\n"
                "    - key: CNV_XY_VER\n"
                "      value: '4.22'\n"
                "    - key: ARCH\n"
                "      value: amd64\n"
                "    - key: OCP\n"
                "      value: 4.22.0\n"
                "    - key: CLUSTER_NAME\n"
                "      value: bm15a\n"
                "    - key: CLUSTER_DOMAIN\n"
                "      value: bm15a.example.com\n"
                "    - key: SC\n"
                "      value: ocs\n"
                "    - key: CHANNEL\n"
                "      value: candidate\n"
                "results:\n"
                "  - test: tests/network/test_manual_minimal.py::test_minimal\n"
                "    status: passed\n"
            ),
            encoding="utf-8",
        )
        result = CliRunner().invoke(
            cli=main,
            args=[
                "--tests-dir",
                str(tests_dir),
                "--batch-file",
                str(batch_path),
                # A replay re-derives owner from the current uploader, so pass it
                # explicitly: the suite runs where no git identity exists.
                "--owner",
                "tester@redhat.com",
            ],
        )

        assert result.exit_code == 0, result.output
        assert "Missing required run attributes" not in result.output, (
            "Expected: the migrated legacy attributes satisfy report validation"
        )
        assert (tmp_path / "xunit_results.xml").exists(), (
            "Expected: report written to the default path once validation passes"
        )

    def test_batch_attributes_values_stripped(self, tmp_path: Path) -> None:
        """Verify hand-edited padding in attribute keys and values is stripped."""
        batch_path = tmp_path / "batch.yaml"
        batch_path.write_text(
            data=(
                "results:\n"
                "  - test: tests/net/test_a.py::TestA::test_one\n"
                "    status: passed\n"
                "metadata:\n"
                "  attributes:\n"
                "    - key: ' TEAM '\n"
                "      value: ' NETWORK '\n"
            ),
            encoding="utf-8",
        )
        _results, metadata = _load_batch_file(batch_path=batch_path)

        assert metadata["attributes"] == [{"key": "team", "value": "NETWORK"}], (
            "Expected: padded key and value stripped on load"
        )

    def test_cli_values_not_overridden_by_batch_metadata(self) -> None:
        """Verify CLI-provided bundle/cluster attrs win over batch metadata."""
        cluster_attrs = [{"key": "CLUSTER_NAME", "value": "bm15a"}]
        bundle, merged_attrs, restored = _merge_batch_metadata(
            batch_metadata={
                "bundle": "v4.21.0",
                "attributes": [{"key": "TEAM", "value": "STORAGE"}],
            },
            bundle="v4.22.0",
            cluster_attrs=cluster_attrs,
        )

        assert bundle == "v4.22.0", f"Expected 'v4.22.0', got {bundle!r}"
        assert merged_attrs == cluster_attrs, f"Expected {cluster_attrs!r}, got {merged_attrs!r}"
        assert restored is False, "Expected: cluster attrs present, so nothing restored"

    def test_batch_metadata_fills_missing_cli_values(self) -> None:
        """Verify batch metadata fills bundle when the CLI provided none."""
        bundle, merged_attrs, restored = _merge_batch_metadata(
            batch_metadata={"bundle": "v4.22.0"},
            bundle=None,
            cluster_attrs=None,
        )

        assert bundle == "v4.22.0", f"Expected 'v4.22.0', got {bundle!r}"
        assert merged_attrs is None, f"Expected None, got {merged_attrs!r}"
        assert restored is False, "Expected: no saved attributes to restore"

    def test_restored_attributes_prevent_bundle_override(self) -> None:
        """Verify a restored retry file's saved CNV version is not re-derived from its bundle."""
        # Loader-migrated modern keys — the realistic input to
        # _merge_batch_metadata (a raw legacy list is migrated first).
        saved_attrs = [
            {"key": "cnv_version", "value": "4.21.0"},
            {"key": "cnv_xy_version", "value": "4.21"},
        ]

        bundle, restored_attrs, restored = _merge_batch_metadata(
            batch_metadata={"bundle": "v4.22.0.rhel9-102", "attributes": saved_attrs},
            bundle=None,
            cluster_attrs=None,
        )

        assert bundle is None, (
            "Expected: metadata bundle is not promoted when saved attributes were restored, "
            "so the saved cnv versions are not re-derived"
        )
        assert restored_attrs == saved_attrs, f"Expected {saved_attrs!r}, got {restored_attrs!r}"
        assert restored is True, "Expected: saved attributes restored"

    def test_restored_attributes_not_refilled_with_bundle(self) -> None:
        """Verify a replay does not re-derive versions from batch metadata.

        The saved attributes already carry the recorded cnv versions, so
        the metadata bundle fills nothing on a replay — the recorded run
        is reproduced exactly.
        """
        saved_attrs = [
            {"key": "team", "value": "NETWORK"},
            {"key": "cnv_version", "value": "4.22.0"},
            {"key": "cnv_xy_version", "value": "4.22"},
        ]

        bundle, restored_attrs, restored = _merge_batch_metadata(
            batch_metadata={"bundle": "v4.22.0.rhel9-102", "attributes": saved_attrs},
            bundle=None,
            cluster_attrs=None,
        )

        assert restored is True, "Expected: saved attributes restored"
        assert bundle is None, "Expected: bundle stays unset on a replay (recorded versions stand)"
        assert restored_attrs == saved_attrs, "Expected: restored attributes unchanged"

    def test_restored_partial_attributes_gap_filled_from_bundle(self) -> None:
        """Verify a replay over a partial saved list gap-fills versions from the bundle.

        A hand-written batch file may carry a partial attributes list (e.g.
        only the team) plus a metadata bundle; the missing cnv versions are
        derived from the bundle instead of failing validation — recorded
        values are never overridden.
        """
        saved_attrs = [{"key": "team", "value": "NETWORK"}]

        bundle, restored_attrs, restored = _merge_batch_metadata(
            batch_metadata={"bundle": "v4.22.0.rhel9-102", "attributes": saved_attrs},
            bundle=None,
            cluster_attrs=None,
        )

        assert restored is True, "Expected: saved attributes restored"
        assert bundle is None, "Expected: bundle not re-applied on a replay"
        assert restored_attrs is not None, "Expected: restored attributes list"
        attrs_by_key = {attr["key"]: attr["value"] for attr in restored_attrs}
        assert attrs_by_key["team"] == "NETWORK", "Expected: saved team kept"
        assert attrs_by_key["cnv_version"] == "4.22.0", "Expected: cnv_version gap-filled from the bundle"
        assert attrs_by_key["cnv_xy_version"] == "4.22", "Expected: cnv_xy_version gap-filled from the bundle"

    def test_restored_partial_attributes_gap_fill_per_key(self) -> None:
        """Verify the gap-fill fills only the missing version key.

        A saved list carrying cnv_xy_version but no cnv_version still gets
        cnv_version derived from the bundle (mirroring the fresh-run
        derivation), instead of failing validation over one missing key.
        """
        saved_attrs = [
            {"key": "team", "value": "NETWORK"},
            {"key": "cnv_xy_version", "value": "4.22"},
        ]

        bundle, restored_attrs, restored = _merge_batch_metadata(
            batch_metadata={"bundle": "v4.22.0.rhel9-102", "attributes": saved_attrs},
            bundle=None,
            cluster_attrs=None,
        )

        assert restored is True, "Expected: saved attributes restored"
        assert bundle is None, "Expected: bundle not re-applied on a replay"
        assert restored_attrs is not None, "Expected: restored attributes list"
        attrs_by_key = {attr["key"]: attr["value"] for attr in restored_attrs}
        assert attrs_by_key["cnv_version"] == "4.22.0", "Expected: only the missing key gap-filled"
        assert attrs_by_key["cnv_xy_version"] == "4.22", "Expected: recorded value kept verbatim"
        assert len(restored_attrs) == 3, f"Expected 3 attributes after the gap-fill, got {len(restored_attrs)}"

    def test_saved_attributes_restored_only_without_cluster_attrs(self) -> None:
        """Verify saved attributes are restored only when no cluster attrs were resolved."""
        saved_attrs = [{"key": "TEAM", "value": "NETWORK"}]

        _bundle, restored_attrs, restored = _merge_batch_metadata(
            batch_metadata={"attributes": saved_attrs},
            bundle=None,
            cluster_attrs=None,
        )
        assert restored_attrs == saved_attrs, f"Expected {saved_attrs!r}, got {restored_attrs!r}"
        assert restored is True, "Expected: saved attributes restored"

        cluster_attrs = [{"key": "CLUSTER_NAME", "value": "bm15a"}]
        _bundle, kept_attrs, kept_restored = _merge_batch_metadata(
            batch_metadata={"attributes": saved_attrs},
            bundle=None,
            cluster_attrs=cluster_attrs,
        )
        assert kept_attrs == cluster_attrs, f"Expected {cluster_attrs!r}, got {kept_attrs!r}"
        assert kept_restored is False, "Expected: cluster attrs present, so nothing restored"


class TestBatchUnmatchedWarning:
    def test_batch_unmatched_node_id_warns(self, tmp_path: Path) -> None:
        """Verify batch entries matching no collected test produce a stderr warning."""
        tests_dir = write_minimal_tests_dir(tmp_path=tmp_path)
        batch_path = tmp_path / "batch.yaml"
        batch_path.write_text(
            data=("results:\n  - test: tests/net/test_typo.py::TestA::test_one\n    status: passed\n"),
            encoding="utf-8",
        )
        runner = CliRunner()
        result = runner.invoke(
            cli=main,
            args=["--tests-dir", str(tests_dir), "--batch-file", str(batch_path), "--dry-run"],
        )
        assert result.exit_code == 0, "Expected: unmatched node_id still uploads (warning only)"
        assert "match no collected manual test" in result.stderr, (
            "Expected: stderr warning for batch entries matching no collected test"
        )


class TestInvalidMarkerExpression:
    def test_invalid_marker_expression_with_no_manual_tests(self, tmp_path: Path) -> None:
        """Verify an invalid -m expression fails even when no manual tests are collected."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_automated.py").write_text(
            data=("import pytest\n\n\nclass TestAutomated:\n    def test_one(self):\n        assert True\n"),
            encoding="utf-8",
        )

        result = CliRunner().invoke(
            cli=main,
            args=["--tests-dir", str(tests_dir), "-m", "smoke and (", "--dry-run"],
        )

        assert result.exit_code != 0, "Expected: invalid -m expression fails even with zero manual tests"
        assert "Invalid marker expression" in result.output, (
            "Expected: invalid-expression error instead of a silent empty selection"
        )


class TestUploadPreflight:
    def test_missing_required_attributes_fails_without_dry_run(self, tmp_path: Path) -> None:
        """Verify a non-dry-run missing a required attribute fails before prompting."""
        tests_dir = write_manual_tests_dir(tmp_path=tmp_path, test_count=1)
        all_args = required_attr_args(tests_dir=tests_dir)
        bundle_flag_index = all_args.index("--bundle")
        # Split on a plain index variable: ruff format writes complex slice
        # bounds with a space before ':' (E203), flake8 rejects it.
        after_bundle_index = bundle_flag_index + 2
        incomplete_args = all_args[:bundle_flag_index] + all_args[after_bundle_index:]

        result = CliRunner().invoke(
            cli=main,
            args=incomplete_args,
        )

        assert result.exit_code == 1, f"Expected exit code 1, got {result.exit_code!r}"
        assert "Missing required run attributes" in result.output, "Expected: error listing the missing attributes"
        assert "cnv_version" in result.output, "Expected: error names the missing cnv_version attribute"
        assert "Result (p=pass" not in result.output, "Expected: failure happens before the verdict prompt"


class TestDryRunReadinessWarning:
    def test_dry_run_warns_about_missing_required_attributes(self, tmp_path: Path) -> None:
        """Verify dry-run predicts upload failure when attributes are missing."""
        tests_dir = write_minimal_tests_dir(tmp_path=tmp_path)
        batch_path = tmp_path / "batch.yaml"
        batch_path.write_text(
            data=("results:\n  - test: tests/network/test_manual_minimal.py::test_minimal\n    status: passed\n"),
            encoding="utf-8",
        )

        result = CliRunner().invoke(
            cli=main,
            args=["--tests-dir", str(tests_dir), "--batch-file", str(batch_path), "--dry-run"],
        )

        assert result.exit_code == 0, "Expected: dry-run never fails on missing attributes"
        assert "the report would be incomplete — missing:" in result.stderr, (
            "Expected: warning listing missing attributes"
        )
        assert "No report was written (dry run)." in result.output, (
            "Expected: dry-run still exits without writing the report"
        )


class TestBatchFailureClassificationValidation:
    def test_valid_issue_type_label_accepted(self, tmp_path: Path) -> None:
        """Verify every vocabulary label is accepted from a batch file."""
        tests_dir = write_manual_tests_dir(tmp_path=tmp_path, test_count=1)
        for label in ("Product Bug", "Automation Bug", "System Issue", "To Investigate", "No Defect"):
            batch_path = tmp_path / f"batch_{label.replace(' ', '_')}.yaml"
            batch_path.write_text(
                data=(
                    "metadata:\n  bundle: v4.22.0\n"
                    "results:\n"
                    "  - test: tests/network/test_manual_minimal.py::test_minimal\n"
                    "    status: failed\n"
                    f"    issue_type_label: {label}\n"
                ),
                encoding="utf-8",
            )
            result = CliRunner().invoke(
                cli=main,
                args=[*required_attr_args(tests_dir=tests_dir), "--batch-file", str(batch_path)],
            )
            assert result.exit_code == 0, f"Expected {label!r} accepted, got: {result.output}"

    def test_unknown_issue_type_label_rejected(self, tmp_path: Path) -> None:
        """Verify a label outside the classification vocabulary fails fast.

        Otherwise the typo ships verbatim on <failure type> while
        tfa.classification silently becomes "unknown".
        """
        tests_dir = write_manual_tests_dir(tmp_path=tmp_path, test_count=1)
        batch_path = tmp_path / "batch.yaml"
        batch_path.write_text(
            data=(
                "metadata:\n  bundle: v4.22.0\n"
                "results:\n"
                "  - test: tests/network/test_manual_minimal.py::test_minimal\n"
                "    status: failed\n"
                "    issue_type_label: product bug\n"
            ),
            encoding="utf-8",
        )
        result = CliRunner().invoke(
            cli=main,
            args=[*required_attr_args(tests_dir=tests_dir), "--batch-file", str(batch_path)],
        )

        assert result.exit_code != 0, "Expected an unknown classification label to fail the run"
        assert "Invalid issue_type_label" in result.output, f"Expected a clear label error, got: {result.output}"


class TestInteractiveFlow:
    def test_interactive_verdicts_write_report(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify interactive pass/fail verdicts write the JUnit report."""
        tests_dir = write_manual_tests_dir(tmp_path=tmp_path, test_count=2)
        monkeypatch.chdir(path=tmp_path)
        result = CliRunner().invoke(
            cli=main,
            args=required_attr_args(tests_dir=tests_dir),
            input="p\nf\n1\nboom\n",
        )

        assert result.exit_code == 0, result.output
        assert "Wrote 2 results" in result.output, "Expected: success message after interactive run"
        report_path = junit_report_path(tests_dir=tests_dir)
        assert report_path.exists(), f"Expected the JUnit report at {report_path}"
        props = read_junit_properties(xml_path=report_path)
        assert props["dd_tags[manual]"] == "true", f"Expected manual:true tag, got {props!r}"
        assert props["dd_tags[team]"] == "CNV_Network", f"Expected the sanitized Jenkins team tag, got {props!r}"
        assert not list(tmp_path.glob("manual_results_*.yaml")), "Expected: no retry file on success"

    def test_interactive_skip_verdict_in_summary_and_report(self, tmp_path: Path) -> None:
        """Verify a skip verdict reaches both the summary and the JUnit report."""
        tests_dir = write_manual_tests_dir(tmp_path=tmp_path, test_count=1)
        result = CliRunner().invoke(
            cli=main,
            args=required_attr_args(tests_dir=tests_dir),
            input="s\n",
        )

        assert result.exit_code == 0, result.output
        assert "Skipped: 1" in result.output, "Expected: skip verdict counted in the summary"
        report_path = junit_report_path(tests_dir=tests_dir)
        assert report_path.exists(), f"Expected the JUnit report at {report_path}"
        assert "<skipped" in report_path.read_text(encoding="utf-8"), (
            "Expected: skipped verdict serialized as a <skipped> element"
        )

    def test_interactive_invalid_choice_then_valid(self, tmp_path: Path) -> None:
        """Verify an invalid verdict choice is rejected and re-prompted."""
        tests_dir = write_manual_tests_dir(tmp_path=tmp_path, test_count=1)
        result = CliRunner().invoke(
            cli=main,
            args=required_attr_args(tests_dir=tests_dir),
            input="x\np\n",
        )

        assert result.exit_code == 0, result.output
        assert "Invalid choice" in result.output, "Expected: invalid verdict choice is rejected"

    def test_interactive_invalid_defect_choice_then_valid(self, tmp_path: Path) -> None:
        """Verify an invalid defect-type choice is rejected and re-prompted."""
        tests_dir = write_manual_tests_dir(tmp_path=tmp_path, test_count=1)
        result = CliRunner().invoke(
            cli=main,
            args=required_attr_args(tests_dir=tests_dir),
            input="f\n9\n2\nboom\n",
        )

        assert result.exit_code == 0, result.output
        assert "Invalid choice '9'" in result.output, "Expected: invalid defect-type choice is rejected"

    def test_interactive_quit_saves_partial_results_without_report(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify quitting saves partial results for retry and writes no report."""
        tests_dir = write_manual_tests_dir(tmp_path=tmp_path, test_count=2)
        monkeypatch.chdir(path=tmp_path)
        result = CliRunner().invoke(
            cli=main,
            args=required_attr_args(tests_dir=tests_dir),
            input="p\nq\n",
        )

        assert result.exit_code == 0, result.output
        assert "no report was written" in result.output, "Expected: clear no-report message on quit"
        assert not junit_report_path(tests_dir=tests_dir).exists(), "Expected: no report written after quitting"
        retry_files = list(tmp_path.glob("manual_results_*.yaml"))
        assert len(retry_files) == 1, f"Expected one retry file, got {retry_files!r}"
        loaded_results, metadata = _load_batch_file(batch_path=retry_files[0])
        assert len(loaded_results) == 1, f"Expected 1 partial result, got {len(loaded_results)!r}"
        assert loaded_results[0].status == "PASSED", "Expected: partial result keeps its verdict"
        assert {"key": "team", "value": "CNV Network"} in metadata["attributes"], (
            "Expected: derived team preserved in the saved attributes"
        )

    def test_interactive_eof_saves_partial_results_without_report(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify EOF (Ctrl-D) during the session saves partial results for retry."""
        tests_dir = write_manual_tests_dir(tmp_path=tmp_path, test_count=2)
        monkeypatch.chdir(path=tmp_path)
        # First test gets a verdict; the second prompt hits EOF (Ctrl-D).
        result = CliRunner().invoke(
            cli=main,
            args=required_attr_args(tests_dir=tests_dir),
            input="p\n",
        )

        assert result.exit_code == 0, result.output
        assert "Session interrupted — partial results saved to" in result.output, (
            "Expected: interrupted-session message with the retry path"
        )
        assert "no report was written" in result.output, "Expected: clear no-report message on interrupt"
        assert not junit_report_path(tests_dir=tests_dir).exists(), (
            "Expected: no report written after an interrupted session"
        )
        retry_files = list(tmp_path.glob("manual_results_*.yaml"))
        assert len(retry_files) == 1, f"Expected one retry file, got {retry_files!r}"
        loaded_results, _metadata = _load_batch_file(batch_path=retry_files[0])
        assert len(loaded_results) == 1, f"Expected 1 partial result, got {len(loaded_results)!r}"
        assert loaded_results[0].status == "PASSED", "Expected: verdict collected before EOF is kept"

    def test_interactive_eof_at_first_prompt_reports_interrupt(self, tmp_path: Path) -> None:
        """Verify an interrupt at the very first prompt is reported as an interrupt."""
        tests_dir = write_manual_tests_dir(tmp_path=tmp_path, test_count=1)
        # EOF (Ctrl-D) at the very first prompt: no verdict collected yet.
        result = CliRunner().invoke(
            cli=main,
            args=required_attr_args(tests_dir=tests_dir),
            input="",
        )

        assert result.exit_code == 0, result.output
        assert "Session interrupted before any verdict" in result.output, (
            "Expected: interrupt at the first prompt is reported as an interrupt"
        )
        assert "No results to upload." not in result.output, "Expected: no plain empty-run message on interrupt"
        assert not junit_report_path(tests_dir=tests_dir).exists(), (
            "Expected: no report written after an interrupted session"
        )

    def test_interactive_quit_teamless_round_trip(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify a team-less quit round-trips without fabricating a TEAM attribute."""
        # An unmapped tests directory derives no team, exercising the team-less path.
        tests_dir = tmp_path / "tests" / "unmapped"
        tests_dir.mkdir(parents=True)
        (tests_dir / "test_manual_multi.py").write_text(
            data=(
                "import pytest\n\n\n"
                "@pytest.mark.manual\ndef test_manual_0():\n    pass\n\n\n"
                "@pytest.mark.manual\ndef test_manual_1():\n    pass\n"
            ),
            encoding="utf-8",
        )
        monkeypatch.chdir(path=tmp_path)
        result = CliRunner().invoke(
            cli=main,
            args=required_attr_args(tests_dir=tests_dir),
            input="p\nq\n",
        )

        assert result.exit_code == 0, result.output
        retry_files = list(tmp_path.glob("manual_results_*.yaml"))
        assert len(retry_files) == 1, f"Expected one retry file, got {retry_files!r}"
        loaded_results, metadata = _load_batch_file(batch_path=retry_files[0])
        assert len(loaded_results) == 1, f"Expected 1 partial result, got {len(loaded_results)!r}"
        assert "team" not in metadata, "Expected: team-less session saves no team metadata"
        assert not any(attr["key"] == "TEAM" for attr in metadata["attributes"]), (
            "Expected: team-less session saves no TEAM attribute"
        )

        # Retry the saved file: no TEAM attribute may be fabricated from 'ALL'.
        retry_result = CliRunner().invoke(
            cli=main,
            args=[
                *required_attr_args(tests_dir=tests_dir),
                "--batch-file",
                str(retry_files[0]),
                "--dry-run",
            ],
        )
        assert retry_result.exit_code == 0, retry_result.output
        assert "team = " not in retry_result.output, "Expected: retry of a team-less run stays team-less"

    def test_interactive_quit_save_failure_still_exits_cleanly(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify a failing retry save on the quit path exits 0 with a clear message."""
        tests_dir = write_manual_tests_dir(tmp_path=tmp_path, test_count=2)
        monkeypatch.chdir(path=tmp_path)
        with patch(
            target="scripts.manual_tests_reporter.manual_tests_reporter.yaml.dump",
            side_effect=OSError("disk full"),
        ):
            result = CliRunner().invoke(
                cli=main,
                args=required_attr_args(tests_dir=tests_dir),
                input="p\nq\n",
            )

        assert result.exit_code == 0, f"Expected exit code 0, got {result.exit_code!r}"
        assert "Failed to save partial results" in result.output, (
            "Expected: quit-path save failure is reported without failing the run"
        )
        assert not list(tmp_path.glob("manual_results_*.yaml")), "Expected: no retry file when the save fails"


class TestMalformedKubeconfig:
    def test_batch_dry_run_with_malformed_kubeconfig(self, tmp_path: Path) -> None:
        """Verify a malformed-YAML kubeconfig does not crash import-time flows.

        The import guard must catch the unwrapped YAMLError raised by the
        kubernetes config loader, not only ConfigException.
        """
        kubeconfig_path = tmp_path / "kubeconfig"
        kubeconfig_path.write_text(data="key: [unclosed", encoding="utf-8")
        tests_dir = write_minimal_tests_dir(tmp_path=tmp_path)
        batch_path = tmp_path / "batch.yaml"
        batch_path.write_text(
            data=("results:\n  - test: tests/network/test_manual_minimal.py::test_minimal\n    status: passed\n"),
            encoding="utf-8",
        )
        # Strip the arch env var (set by the test bootstrap) so the child
        # process actually reads the malformed kubeconfig instead of
        # short-circuiting architecture resolution on the env var.
        child_env = {
            key: value for key, value in os.environ.items() if key != "OPENSHIFT_VIRTUALIZATION_TEST_IMAGES_ARCH"
        }
        child_env["KUBECONFIG"] = str(kubeconfig_path)
        base_command = [
            sys.executable,
            "-m",
            "scripts.manual_tests_reporter.manual_tests_reporter",
            "--tests-dir",
            str(tests_dir),
            "--batch-file",
            str(batch_path),
        ]
        result, _, err = run_command(
            command=[*base_command, "--dry-run"],
            env=child_env,
            cwd=REPO_ROOT,
            verify_stderr=False,
            check=False,
        )
        assert result, f"Expected: dry-run succeeds with a malformed kubeconfig; stderr: {err}"
        assert "Traceback" not in err, "Expected: YAMLError caught by the import guard, no raw traceback"

        # Prove the guard fired (rather than the import succeeding):
        # --from-cluster must fail with the cluster-access guidance.
        run_failed, _, fail_err = run_command(
            command=[*base_command, "--from-cluster", "--dry-run"],
            env=child_env,
            cwd=REPO_ROOT,
            verify_stderr=False,
            check=False,
        )
        assert not run_failed, "Expected: --from-cluster fails when the import guard fired"
        assert "--from-cluster requires cluster access" in fail_err, (
            "Expected: guidance message proving the guard caught the import failure"
        )


class TestReportWriteFailure:
    def test_report_write_failure_saves_retry(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify an OSError while writing the report saves a retry file and exits 1."""
        tests_dir, batch_path = write_minimal_batch(tmp_path=tmp_path)
        monkeypatch.chdir(path=tmp_path)
        with patch(
            target="scripts.manual_tests_reporter.manual_tests_reporter.write_junit_report",
            side_effect=OSError("write boom"),
        ):
            result = CliRunner().invoke(
                cli=main,
                args=[
                    *required_attr_args(tests_dir=tests_dir),
                    "--batch-file",
                    str(batch_path),
                ],
            )

        assert result.exit_code == 1, f"Expected exit code 1, got {result.exit_code!r}"
        assert "write boom" in result.output, "Expected: original report-write error is reported"
        assert not junit_report_path(tests_dir=tests_dir).exists(), "Expected: no report file on a write failure"
        retry_files = list(tmp_path.glob("manual_results_*.yaml"))
        assert len(retry_files) == 1, f"Expected one retry file, got {retry_files!r}"

    def test_report_write_failure_retry_save_error_does_not_mask_original(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify a failing retry save does not mask the original report-write error."""
        tests_dir, batch_path = write_minimal_batch(tmp_path=tmp_path)
        monkeypatch.chdir(path=tmp_path)
        with (
            patch(
                target="scripts.manual_tests_reporter.manual_tests_reporter.write_junit_report",
                side_effect=OSError("write boom"),
            ),
            patch(
                target="scripts.manual_tests_reporter.manual_tests_reporter.yaml.dump",
                side_effect=OSError("disk full"),
            ),
        ):
            result = CliRunner().invoke(
                cli=main,
                args=[
                    *required_attr_args(tests_dir=tests_dir),
                    "--batch-file",
                    str(batch_path),
                ],
            )

        assert result.exit_code == 1, f"Expected exit code 1, got {result.exit_code!r}"
        assert "write boom" in result.output, "Expected: original report-write error is still reported"
        assert "Failed to save results for retry" in result.output, (
            "Expected: retry-save failure is reported without masking the original error"
        )
        assert not list(tmp_path.glob("manual_results_*.yaml")), "Expected: no retry file when the save fails"

    def test_keyboard_interrupt_during_report_write_saves_retry(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify Ctrl-C while writing the report saves a retry file without a traceback.

        [NEGATIVE] An interrupt after the verdicts but outside the interactive
        loop must route into the retry-save path, not propagate as a raw
        KeyboardInterrupt traceback with the verdicts lost.
        """
        tests_dir, batch_path = write_minimal_batch(tmp_path=tmp_path)
        monkeypatch.chdir(path=tmp_path)
        with patch(
            target="scripts.manual_tests_reporter.manual_tests_reporter.write_junit_report",
            side_effect=KeyboardInterrupt,
        ):
            result = CliRunner().invoke(
                cli=main,
                args=[
                    *required_attr_args(tests_dir=tests_dir),
                    "--batch-file",
                    str(batch_path),
                ],
            )

        assert result.exit_code == 1, f"Expected exit code 1, got {result.exit_code!r}"
        assert "Session interrupted while writing the report — partial results saved to" in result.output, (
            "Expected: interrupt during the report write saves partial results with a clean message"
        )
        assert "Traceback" not in result.output, "Expected: no raw traceback on interrupt during the report write"
        retry_files = list(tmp_path.glob("manual_results_*.yaml"))
        assert len(retry_files) == 1, f"Expected one retry file, got {retry_files!r}"
        loaded_results, _metadata = _load_batch_file(batch_path=retry_files[0])
        assert loaded_results[0].status == "PASSED", "Expected: verdict collected before the interrupt is kept"


class TestSyntheticAttributes:
    def test_job_name_and_build_number_defaults(self, tmp_path: Path) -> None:
        """Verify synthetic job_name/build_number defaults land in the report."""
        tests_dir, batch_path = write_minimal_batch(tmp_path=tmp_path)
        result = CliRunner().invoke(
            cli=main,
            args=[*required_attr_args(tests_dir=tests_dir), "--batch-file", str(batch_path)],
        )

        assert result.exit_code == 0, result.output
        props = read_junit_properties(xml_path=junit_report_path(tests_dir=tests_dir))
        assert props.get("dd_tags[job_name]") == "manual-tests-cnv_network", (
            f"Expected the team-suffixed job_name, got {props.get('dd_tags[job_name]')!r}"
        )
        build_number = props.get("dd_tags[build_number]")
        assert build_number is not None and build_number.isdigit(), (
            f"Expected an epoch-seconds build_number, got {build_number!r}"
        )

    def test_teamless_job_name_default(self, tmp_path: Path) -> None:
        """Verify a team-less run gets the bare manual-tests job_name."""
        tests_dir = tmp_path / "tests" / "unmapped"
        tests_dir.mkdir(parents=True)
        (tests_dir / "test_unmapped_manual.py").write_text(
            data=MINIMAL_MANUAL_TEST_SOURCE,
            encoding="utf-8",
        )
        batch_path = tmp_path / "batch.yaml"
        batch_path.write_text(
            data=("results:\n  - test: tests/unmapped/test_unmapped_manual.py::test_minimal\n    status: passed\n"),
            encoding="utf-8",
        )
        result = CliRunner().invoke(
            cli=main,
            args=[*required_attr_args(tests_dir=tests_dir), "--batch-file", str(batch_path)],
        )

        assert result.exit_code == 0, result.output
        props = read_junit_properties(xml_path=junit_report_path(tests_dir=tests_dir))
        assert props.get("dd_tags[job_name]") == "manual-tests", (
            f"Expected the bare team-less job_name, got {props.get('dd_tags[job_name]')!r}"
        )
        assert "dd_tags[team]" not in props, "Expected: team-less run carries no team tag"

    def test_replay_preserves_recorded_job_name_and_build_number(self, tmp_path: Path) -> None:
        """Verify a replay keeps its recorded job_name/build_number (setdefault).

        A resumed run must reproduce its recorded build identity instead of
        relabelling it as a new build, so the synthetic attributes never
        overwrite recorded values.
        """
        tests_dir, batch_path = write_minimal_batch(tmp_path=tmp_path)
        saved_attributes = [
            {"key": "team", "value": "NETWORK"},
            {"key": "cnv_version", "value": "4.22.0"},
            {"key": "cnv_xy_version", "value": "4.22"},
            {"key": "ocp_version", "value": "4.22.0"},
            {"key": "cluster", "value": "bm15a"},
            {"key": "cluster_domain", "value": "bm15a.example.com"},
            {"key": "storage_class", "value": "ocs"},
            {"key": "cnv_channel", "value": "candidate"},
            {"key": "job_name", "value": "manual-tests-recorded"},
            {"key": "build_number", "value": "12345"},
        ]
        attributes_yaml = "".join(
            f"    - key: {attr['key']}\n      value: '{attr['value']}'\n" for attr in saved_attributes
        )
        batch_path.write_text(
            data=(
                "metadata:\n"
                f"  attributes:\n{attributes_yaml}"
                "results:\n"
                "  - test: tests/network/test_manual_minimal.py::test_minimal\n"
                "    status: passed\n"
            ),
            encoding="utf-8",
        )
        result = CliRunner().invoke(
            cli=main,
            args=[
                "--tests-dir",
                str(tests_dir),
                "--junit-output",
                str(junit_report_path(tests_dir=tests_dir)),
                "--owner",
                "tester@redhat.com",
                "--batch-file",
                str(batch_path),
            ],
        )

        assert result.exit_code == 0, result.output
        props = read_junit_properties(xml_path=junit_report_path(tests_dir=tests_dir))
        assert props.get("dd_tags[job_name]") == "manual-tests-recorded", (
            f"Expected the recorded job_name kept on replay, got {props.get('dd_tags[job_name]')!r}"
        )
        assert props.get("dd_tags[build_number]") == "12345", (
            f"Expected the recorded build_number kept on replay, got {props.get('dd_tags[build_number]')!r}"
        )


class TestNewTagFlags:
    def test_new_tag_flags_reach_report_properties(self, tmp_path: Path) -> None:
        """Verify --ip-stack/--iib-image/--hco-bundle-version/--rootcoz-url land as report tags."""
        tests_dir, batch_path = write_minimal_batch(tmp_path=tmp_path)
        result = CliRunner().invoke(
            cli=main,
            args=[
                *required_attr_args(tests_dir=tests_dir),
                "--batch-file",
                str(batch_path),
                "--ip-stack",
                "ipv4-ipv6",
                "--iib-image",
                "quay.io/example/iib:422",
                "--hco-bundle-version",
                "v4.22.0.rhel9-102",
                "--rootcoz-url",
                "https://rootcoz.example/run/2",
            ],
        )

        assert result.exit_code == 0, result.output
        props = read_junit_properties(xml_path=junit_report_path(tests_dir=tests_dir))
        expected_tags = {
            "ip_stack": "ipv4-ipv6",
            "iib_image": "quay.io/example/iib:422",
            "hco_bundle_version": "v4.22.0.rhel9-102",
            "rootcoz.url": "https://rootcoz.example/run/2",
        }
        for tag_key, expected_value in expected_tags.items():
            actual_value = props.get(f"dd_tags[{tag_key}]")
            assert actual_value == expected_value, (
                f"Expected dd_tags[{tag_key}]={expected_value!r} in the report, got {actual_value!r}"
            )


class TestJunitOutputOption:
    def test_custom_junit_output_path(self, tmp_path: Path) -> None:
        """Verify --junit-output writes the report at the custom path."""
        tests_dir, batch_path = write_minimal_batch(tmp_path=tmp_path)
        custom_path = tmp_path / "custom_results.xml"
        args = required_attr_args(tests_dir=tests_dir)
        args[args.index("--junit-output") + 1] = str(custom_path)
        result = CliRunner().invoke(
            cli=main,
            args=[*args, "--batch-file", str(batch_path)],
        )

        assert result.exit_code == 0, result.output
        assert f"Wrote 1 results to {custom_path}" in result.output, (
            "Expected: success message names the custom report path"
        )
        assert custom_path.exists(), f"Expected the JUnit report at {custom_path}"
        assert not (tmp_path / "xunit_results.xml").exists(), (
            "Expected: no report at the default path when --junit-output is given"
        )

    def test_missing_parent_directory_is_created(self, tmp_path: Path) -> None:
        """Verify a nested --junit-output path has its parents created."""
        tests_dir, batch_path = write_minimal_batch(tmp_path=tmp_path)
        nested_path = tmp_path / "reports" / "manual" / "xunit_results.xml"
        args = required_attr_args(tests_dir=tests_dir)
        args[args.index("--junit-output") + 1] = str(nested_path)
        result = CliRunner().invoke(cli=main, args=[*args, "--batch-file", str(batch_path)])

        assert result.exit_code == 0, result.output
        assert nested_path.exists(), f"Expected the report at {nested_path}"

    def test_directory_output_path_rejected_before_classifying(self, tmp_path: Path) -> None:
        """Verify a directory --junit-output fails fast with an actionable error."""
        tests_dir, batch_path = write_minimal_batch(tmp_path=tmp_path)
        args = required_attr_args(tests_dir=tests_dir)
        args[args.index("--junit-output") + 1] = str(tmp_path)
        result = CliRunner().invoke(cli=main, args=[*args, "--batch-file", str(batch_path)])

        assert result.exit_code != 0, "Expected: a directory output path fails the run"
        assert "is a directory" in result.output, f"Expected a directory error, got: {result.output}"


class TestRemovedServiceConfigKey:
    def test_service_config_key_rejected_with_removal_hint(self, tmp_path: Path) -> None:
        """Verify the removed 'service' config key is rejected with its removal hint."""
        tests_dir, batch_path = write_minimal_batch(tmp_path=tmp_path)
        config_path = write_config_file(tmp_path=tmp_path, content="service: cnv-qe-tests\n")
        result = CliRunner().invoke(
            cli=main,
            args=[
                "--tests-dir",
                str(tests_dir),
                "--batch-file",
                str(batch_path),
                "--config",
                str(config_path),
                "--dry-run",
            ],
        )

        assert result.exit_code != 0, "Expected: the removed 'service' config key fails the run"
        assert "Unknown config key(s)" in result.output, "Expected: unknown-key error names the service key"
        assert "The 'service' key was removed" in result.output, (
            f"Expected: removal hint names the removed key, got: {result.output}"
        )
        assert "pass --service to datadog-ci at upload time" in result.output, (
            f"Expected: removal hint points at the upload-time flag, got: {result.output}"
        )


class TestTeamDerivation:
    def test_team_derived_from_tests_dir_subfolder(self, tmp_path: Path) -> None:
        """Verify the team is derived from the folder under tests/."""
        tests_dir = tmp_path / "x" / "tests" / "storage"
        tests_dir.mkdir(parents=True)
        (tests_dir / "test_storage_manual.py").write_text(
            data=MINIMAL_MANUAL_TEST_SOURCE,
            encoding="utf-8",
        )
        batch_path = tmp_path / "batch.yaml"
        batch_path.write_text(
            data=("results:\n  - test: tests/storage/test_storage_manual.py::test_minimal\n    status: passed\n"),
            encoding="utf-8",
        )

        result = CliRunner().invoke(
            cli=main,
            args=["--tests-dir", str(tests_dir), "--batch-file", str(batch_path), "--dry-run"],
        )

        assert result.exit_code == 0, result.output
        assert "Derived team: Storage Platform" in result.output, "Expected: team derived from the tests directory"
        assert "team = Storage Platform" in result.output, "Expected: derived team reaches the run attributes"

    def test_team_derived_from_tests_dir_basename(self, tmp_path: Path) -> None:
        """Verify the team is derived from the selected folder's own name."""
        tests_dir = tmp_path / "network"
        tests_dir.mkdir(parents=True)
        (tests_dir / "test_network_manual.py").write_text(
            data=MINIMAL_MANUAL_TEST_SOURCE,
            encoding="utf-8",
        )
        batch_path = tmp_path / "batch.yaml"
        batch_path.write_text(
            data=("results:\n  - test: network/test_network_manual.py::test_minimal\n    status: passed\n"),
            encoding="utf-8",
        )

        result = CliRunner().invoke(
            cli=main,
            args=["--tests-dir", str(tests_dir), "--batch-file", str(batch_path), "--dry-run"],
        )

        assert result.exit_code == 0, result.output
        assert "Derived team: CNV Network" in result.output, "Expected: team derived from the folder name"
        assert "team = CNV Network" in result.output, "Expected: derived team reaches the run attributes"

    def test_team_parent_folder_wins_over_conflicting_basename(self, tmp_path: Path) -> None:
        """Verify a nested dir named after another team derives its parent team.

        tests/observability/storage exists in the repo: its basename maps to
        STORAGE but the folder under tests/ maps to IUO — the parent team
        must win so the run is not misattributed to another team.
        """
        tests_dir = tmp_path / "x" / "tests" / "observability" / "storage"
        tests_dir.mkdir(parents=True)
        (tests_dir / "test_storage_manual.py").write_text(
            data=MINIMAL_MANUAL_TEST_SOURCE,
            encoding="utf-8",
        )
        batch_path = tmp_path / "batch.yaml"
        batch_path.write_text(
            data=(
                "results:\n"
                "  - test: tests/observability/storage/test_storage_manual.py::test_minimal\n"
                "    status: passed\n"
            ),
            encoding="utf-8",
        )

        result = CliRunner().invoke(
            cli=main,
            args=["--tests-dir", str(tests_dir), "--batch-file", str(batch_path), "--dry-run"],
        )

        assert result.exit_code == 0, result.output
        assert "Derived team: CNV Install, Upgrade and Operators" in result.output, (
            "Expected: parent team wins over conflicting basename"
        )
        assert "team = CNV Install, Upgrade and Operators" in result.output, (
            "Expected: parent team reaches the run attributes"
        )
        assert "Derived team: Storage Platform" not in result.output, "Expected: conflicting basename must not win"

    def test_team_derived_from_deep_tests_dir_subfolder(self, tmp_path: Path) -> None:
        """Verify a deep subfolder derives the team from its tests-root parent."""
        tests_dir = tmp_path / "x" / "tests" / "network" / "l2_bridge"
        tests_dir.mkdir(parents=True)
        (tests_dir / "test_l2_manual.py").write_text(
            data=MINIMAL_MANUAL_TEST_SOURCE,
            encoding="utf-8",
        )
        batch_path = tmp_path / "batch.yaml"
        batch_path.write_text(
            data=("results:\n  - test: tests/network/l2_bridge/test_l2_manual.py::test_minimal\n    status: passed\n"),
            encoding="utf-8",
        )

        result = CliRunner().invoke(
            cli=main,
            args=["--tests-dir", str(tests_dir), "--batch-file", str(batch_path), "--dry-run"],
        )

        assert result.exit_code == 0, result.output
        assert "Derived team: CNV Network" in result.output, "Expected: team derived from the tests-root parent"
        assert "team = CNV Network" in result.output, "Expected: derived team reaches the run attributes"

    def test_folder_to_team_covers_all_repo_team_dirs(self) -> None:
        """Verify every top-level tests/ directory maps to a team (drift guard)."""
        tests_root = REPO_ROOT / "tests"
        non_test_dirs = {"fixtures", "__pycache__"}
        unmapped_dirs = sorted(
            entry.name
            for entry in tests_root.iterdir()
            if entry.is_dir() and entry.name not in non_test_dirs and entry.name not in reporter_module._FOLDER_TO_TEAM
        )

        assert not unmapped_dirs, f"New tests directories missing a TEAM mapping in _FOLDER_TO_TEAM: {unmapped_dirs}"

        stale_mappings = sorted(
            set(reporter_module._FOLDER_TO_TEAM) - {entry.name for entry in tests_root.iterdir() if entry.is_dir()}
        )
        assert not stale_mappings, (
            f"_FOLDER_TO_TEAM keys with no tests/ directory (folder renamed or removed?): {stale_mappings}"
        )

    def test_nested_mapped_tests_child_wins_by_design(self, tmp_path: Path) -> None:
        """Verify a mapped nested 'tests' child wins — the deepest mapped candidate is authoritative.

        For a path like tests/network/tests/storage the deepest 'tests' child
        (storage) maps to a team, so it wins over the outer tests child
        (network). This pins the documented deepest-mapped-wins invariant.
        """
        tests_dir = tmp_path / "x" / "tests" / "network" / "tests" / "storage"
        tests_dir.mkdir(parents=True)
        (tests_dir / "test_nested_storage_manual.py").write_text(
            data=MINIMAL_MANUAL_TEST_SOURCE,
            encoding="utf-8",
        )
        batch_path = tmp_path / "batch.yaml"
        batch_path.write_text(
            data=(
                "results:\n"
                "  - test: tests/network/tests/storage/test_nested_storage_manual.py::test_minimal\n"
                "    status: passed\n"
            ),
            encoding="utf-8",
        )

        result = CliRunner().invoke(
            cli=main,
            args=["--tests-dir", str(tests_dir), "--batch-file", str(batch_path), "--dry-run"],
        )

        assert result.exit_code == 0, result.output
        assert "Derived team: Storage Platform" in result.output, "Expected: deepest mapped tests child wins by design"
        assert "team = Storage Platform" in result.output, "Expected: derived team reaches the run attributes"

    def test_nested_tests_dir_does_not_shadow_team_folder(self, tmp_path: Path) -> None:
        """Verify an unmapped nested 'tests' child falls through to the outer tests child.

        The deepest "tests" child is authoritative; when it maps to no team
        (here: the unmapped leaf under a nested 'tests' directory), the next
        candidate — the outer tests-root child — derives the team.
        """
        tests_dir = tmp_path / "x" / "tests" / "network" / "tests" / "manual"
        tests_dir.mkdir(parents=True)
        (tests_dir / "test_nested_manual.py").write_text(
            data=MINIMAL_MANUAL_TEST_SOURCE,
            encoding="utf-8",
        )
        batch_path = tmp_path / "batch.yaml"
        batch_path.write_text(
            data=(
                "results:\n"
                "  - test: tests/network/tests/manual/test_nested_manual.py::test_minimal\n"
                "    status: passed\n"
            ),
            encoding="utf-8",
        )

        result = CliRunner().invoke(
            cli=main,
            args=["--tests-dir", str(tests_dir), "--batch-file", str(batch_path), "--dry-run"],
        )

        assert result.exit_code == 0, result.output
        assert "Derived team: CNV Network" in result.output, "Expected: outer tests root wins over nested tests dir"
        assert "team = CNV Network" in result.output, "Expected: derived team reaches the run attributes"

    def test_unmapped_tests_dir_omits_team(self, tmp_path: Path) -> None:
        """Verify an unmapped tests directory uploads without a TEAM attribute."""
        tests_dir = tmp_path / "x" / "tests" / "unmapped"
        tests_dir.mkdir(parents=True)
        (tests_dir / "test_unmapped_manual.py").write_text(
            data=MINIMAL_MANUAL_TEST_SOURCE,
            encoding="utf-8",
        )
        batch_path = tmp_path / "batch.yaml"
        batch_path.write_text(
            data=("results:\n  - test: tests/unmapped/test_unmapped_manual.py::test_minimal\n    status: passed\n"),
            encoding="utf-8",
        )

        result = CliRunner().invoke(
            cli=main,
            args=["--tests-dir", str(tests_dir), "--batch-file", str(batch_path), "--dry-run"],
        )

        assert result.exit_code == 0, result.output
        assert "TEAM =" not in result.output, "Expected: unmapped directory derives no TEAM"
        assert "Derived team" not in result.output, "Expected: unmapped directory derives no team"
        assert "maps to no team" in result.output, "Expected: unmapped directory warns the tester"


class TestConfigFileIntegration:
    def test_all_attribute_config_keys_reach_run_attributes(self, tmp_path: Path) -> None:
        """Verify every config-wired attribute config key has CLI wiring (drift guard)."""
        tests_dir, batch_path = write_minimal_batch(tmp_path=tmp_path)
        # Generate the config and expectations from the full config-key map so
        # a new CONFIG_KEY_TO_ATTRIBUTE_KEY entry fails this test until it is
        # wired through main() and reaches the run attributes.
        config_lines = []
        expected_lines = []
        for config_key in sorted(CONFIG_KEY_TO_ATTRIBUTE_KEY):
            attr_key = CONFIG_KEY_TO_ATTRIBUTE_KEY[config_key]
            # TIER normalizes to the bare number; every other key passes
            # its config value through unchanged.
            if attr_key == "tier":
                config_lines.append(f"{config_key}: tier-2")
                expected_lines.append("tier = 2")
                continue
            value = f"val-{config_key}"
            config_lines.append(f"{config_key}: {value}")
            expected_lines.append(f"{attr_key} = {value}")
        config_path = write_config_file(
            tmp_path=tmp_path,
            content="\n".join(config_lines) + "\n",
        )

        result = CliRunner().invoke(
            cli=main,
            args=[
                "--tests-dir",
                str(tests_dir),
                "--config",
                str(config_path),
                "--batch-file",
                str(batch_path),
                "--dry-run",
            ],
        )

        assert result.exit_code == 0, result.output
        for expected in expected_lines:
            assert expected in result.output, f"Expected: {expected!r} in the dry-run output"

    def test_all_attribute_config_keys_reach_replay_gap_fill(self, tmp_path: Path) -> None:
        """Verify every config-wired attribute key has replay gap-fill wiring (drift guard)."""
        tests_dir, batch_path = write_minimal_batch(tmp_path=tmp_path)
        # A partial saved list (team only): the replay branch must gap-fill
        # every other wired attribute key from the generated config.
        batch_path.write_text(
            data=(
                "metadata:\n"
                "  attributes:\n"
                "    - key: team\n"
                "      value: NETWORK\n"
                "results:\n"
                "  - test: tests/network/test_manual_minimal.py::test_minimal\n"
                "    status: passed\n"
            ),
            encoding="utf-8",
        )
        config_lines = []
        expected_lines = []
        for config_key in sorted(CONFIG_KEY_TO_ATTRIBUTE_KEY):
            attr_key = CONFIG_KEY_TO_ATTRIBUTE_KEY[config_key]
            # TIER normalizes to the bare number; every other key passes
            # its config value through unchanged.
            if attr_key == "tier":
                config_lines.append(f"{config_key}: tier-2")
                expected_lines.append("tier = 2")
                continue
            value = f"val-{config_key}"
            config_lines.append(f"{config_key}: {value}")
            expected_lines.append(f"{attr_key} = {value}")
        config_path = write_config_file(
            tmp_path=tmp_path,
            content="\n".join(config_lines) + "\n",
        )

        result = CliRunner().invoke(
            cli=main,
            args=[
                "--tests-dir",
                str(tests_dir),
                "--config",
                str(config_path),
                "--batch-file",
                str(batch_path),
                "--dry-run",
            ],
        )

        assert result.exit_code == 0, result.output
        assert "team = NETWORK" in result.output, "Expected: saved team stands over the config team"
        for expected in expected_lines:
            assert expected in result.output, f"Expected: {expected!r} in the dry-run output"

    def test_config_supplies_required_attributes(self, tmp_path: Path) -> None:
        """Verify a config file supplies every required attribute without CLI flags."""
        tests_dir, batch_path = write_minimal_batch(tmp_path=tmp_path)
        config_path = write_config_file(
            tmp_path=tmp_path,
            content=(
                "bundle: v4.22.0\n"
                "ocp-version: 4.22.0\n"
                "cnv-version: '4.22'\n"
                "owner: tester@redhat.com\n"
                "cluster-name: bm15a\n"
                "cluster-domain: bm15a.example.com\n"
                "sc: ocs-storagecluster-ceph-rbd\n"
                "channel: candidate\n"
            ),
        )
        result = CliRunner().invoke(
            cli=main,
            args=[
                "--tests-dir",
                str(tests_dir),
                "--config",
                str(config_path),
                "--batch-file",
                str(batch_path),
                "--dry-run",
            ],
        )

        assert result.exit_code == 0, result.output
        assert "Loaded config defaults from" in result.output, "Expected: config source is reported"
        assert "team = CNV Network" in result.output, "Expected: derived team reaches the run attributes"
        assert "Missing required run attributes" not in result.output, (
            "Expected: config file supplies every required attribute"
        )

    def test_cli_flag_overrides_config(self, tmp_path: Path) -> None:
        """Verify an explicit CLI flag wins over the config-file value."""
        tests_dir, batch_path = write_minimal_batch(tmp_path=tmp_path)
        config_path = write_config_file(tmp_path=tmp_path, content="ocp-version: 4.21.0\n")
        result = CliRunner().invoke(
            cli=main,
            args=[
                *required_attr_args(tests_dir=tests_dir),
                "--config",
                str(config_path),
                "--batch-file",
                str(batch_path),
                "--dry-run",
            ],
        )

        assert result.exit_code == 0, result.output
        assert "ocp_version = 4.22.0" in result.output, "Expected: CLI flag wins over the config value"

    def test_retry_replay_ignores_config_attributes(self, tmp_path: Path) -> None:
        """Verify a retry file's saved attributes are not disturbed by config defaults."""
        tests_dir, batch_path = write_minimal_batch(tmp_path=tmp_path)
        # Simulate a retry file: saved attributes + the same values as metadata.
        batch_path.write_text(
            data=(
                "metadata:\n"
                "  bundle: v4.22.0\n"
                "  attributes:\n"
                "    - key: team\n"
                "      value: NETWORK\n"
                "    - key: cnv_xy_version\n"
                "      value: '4.21'\n"
                "    - key: ocp_version\n"
                "      value: 4.22.0\n"
                "    - key: cluster\n"
                "      value: bm15a\n"
                "    - key: cluster_domain\n"
                "      value: bm15a.example.com\n"
                "    - key: storage_class\n"
                "      value: ocs-storagecluster-ceph-rbd\n"
                "    - key: cnv_channel\n"
                "      value: candidate\n"
                "results:\n"
                "  - test: tests/network/test_manual_minimal.py::test_minimal\n"
                "    status: passed\n"
            ),
            encoding="utf-8",
        )
        config_path = write_config_file(tmp_path=tmp_path, content="cnv-version: '4.23'\n")
        result = CliRunner().invoke(
            cli=main,
            args=[
                "--tests-dir",
                str(tests_dir),
                "--config",
                str(config_path),
                "--batch-file",
                str(batch_path),
                "--dry-run",
            ],
        )

        assert result.exit_code == 0, result.output
        assert "config defaults for cnv-version are ignored" in result.output, (
            "Expected: config keys saved in the retry file are reported as ignored"
        )
        assert "team = NETWORK" in result.output, "Expected: saved team is replayed, not the config team"
        assert "cnv_xy_version = 4.21" in result.output, "Expected: saved CNV version is replayed, not re-derived"

    def test_retry_replay_fills_gaps_from_config(self, tmp_path: Path) -> None:
        """Verify a partially-filled saved attribute list gets config gap-fills."""
        tests_dir, batch_path = write_minimal_batch(tmp_path=tmp_path)
        # Hand-written batch carrying only team in its attributes list.
        batch_path.write_text(
            data=(
                "metadata:\n"
                "  attributes:\n"
                "    - key: team\n"
                "      value: NETWORK\n"
                "results:\n"
                "  - test: tests/network/test_manual_minimal.py::test_minimal\n"
                "    status: passed\n"
            ),
            encoding="utf-8",
        )
        config_path = write_config_file(
            tmp_path=tmp_path,
            content=(
                "bundle: v4.22.0\n"
                "cnv-version: '4.22'\n"
                "owner: tester@redhat.com\n"
                "ocp-version: 4.22.0\n"
                "cluster-name: bm15a\n"
                "cluster-domain: bm15a.example.com\n"
                "sc: ocs-storagecluster-ceph-rbd\n"
                "channel: candidate\n"
            ),
        )

        result = CliRunner().invoke(
            cli=main,
            args=[
                "--tests-dir",
                str(tests_dir),
                "--config",
                str(config_path),
                "--batch-file",
                str(batch_path),
                "--dry-run",
            ],
        )

        assert result.exit_code == 0, result.output
        assert "team = NETWORK" in result.output, "Expected: saved TEAM stands over the config team"
        assert "config defaults for team are ignored" not in result.output, (
            "Expected: team is no longer a config key, so no replay note for it"
        )
        # Assert the effective attributes so the test fails when a gap is
        # silently left: attribute keys gap-fill from the config file…
        for expected_line in ("ocp_version = 4.22.0", "owner = tester@redhat.com"):
            assert expected_line in result.output, f"Expected {expected_line!r} in the effective attributes"
        # …but the config bundle does not (a replay keeps its recorded run;
        # only a batch-file metadata bundle gap-fills) — surfaced as a
        # dry-run warning naming the one missing key.
        assert "missing: cnv_version" in result.output, (
            "Expected: the un-fillable cnv_version gap is surfaced as a warning"
        )
        assert "Missing required run attributes" not in result.output, (
            "Expected: dry-run reports the gap as a warning, not an error"
        )

    def test_retry_replay_ignores_config_bundle(self, tmp_path: Path) -> None:
        """Verify a replay never re-derives versions from a config bundle.

        The saved attributes carry the recorded run; the config bundle is a
        derivation input for fresh runs only, so a replay keeps its saved
        cnv versions exactly.
        """
        tests_dir, batch_path = write_minimal_batch(tmp_path=tmp_path)
        # Saved attributes carry the recorded CNV version but no bundle.
        batch_path.write_text(
            data=(
                "metadata:\n"
                "  attributes:\n"
                "    - key: team\n"
                "      value: NETWORK\n"
                "    - key: cnv_xy_version\n"
                "      value: '4.21'\n"
                "results:\n"
                "  - test: tests/network/test_manual_minimal.py::test_minimal\n"
                "    status: passed\n"
            ),
            encoding="utf-8",
        )
        config_path = write_config_file(
            tmp_path=tmp_path,
            content=(
                "bundle: v4.23.0\n"
                "owner: tester@redhat.com\n"
                "ocp-version: 4.22.0\n"
                "cluster-name: bm15a\n"
                "cluster-domain: bm15a.example.com\n"
                "sc: ocs-storagecluster-ceph-rbd\n"
                "channel: candidate\n"
            ),
        )

        result = CliRunner().invoke(
            cli=main,
            args=[
                "--tests-dir",
                str(tests_dir),
                "--config",
                str(config_path),
                "--batch-file",
                str(batch_path),
                "--dry-run",
            ],
        )

        assert result.exit_code == 0, result.output
        assert "cnv_xy_version = 4.21" in result.output, (
            "Expected: saved CNV version stands, not re-derived from the config bundle"
        )
        assert "cnv_xy_version = 4.23" not in result.output, "Expected: config bundle never re-derives on a replay"
        assert "cnv_version = " not in result.output, "Expected: no cnv_version derived from the config bundle"

    def test_restored_team_attribute_prevents_no_team_warning(self, tmp_path: Path) -> None:
        """Verify a restored team attribute counts as the run team (no false warning).

        Saved attributes carry team plus every required attribute, but
        metadata.team is absent. Run without --dry-run so the warning check
        (skipped in dry runs) is actually reached; a successful report write
        proves the run passed the team warning check and validation.
        """
        tests_dir, batch_path = write_minimal_batch(tmp_path=tmp_path)
        saved_attributes = [
            {"key": "team", "value": "NETWORK"},
            {"key": "cnv_version", "value": "4.22.0"},
            {"key": "cnv_xy_version", "value": "4.22"},
            {"key": "ocp_version", "value": "4.22.0"},
            {"key": "cluster", "value": "bm15a"},
            {"key": "cluster_domain", "value": "bm15a.example.com"},
            {"key": "storage_class", "value": "ocs-storagecluster-ceph-rbd"},
            {"key": "cnv_channel", "value": "candidate"},
            {"key": "owner", "value": "tester@redhat.com"},
        ]
        attributes_yaml = "".join(
            f"    - key: {attr['key']}\n      value: '{attr['value']}'\n" for attr in saved_attributes
        )
        batch_path.write_text(
            data=(
                "metadata:\n"
                f"  attributes:\n{attributes_yaml}"
                "results:\n"
                "  - test: tests/network/test_manual_minimal.py::test_minimal\n"
                "    status: passed\n"
            ),
            encoding="utf-8",
        )
        result = CliRunner().invoke(
            cli=main,
            args=[
                "--tests-dir",
                str(tests_dir),
                "--batch-file",
                str(batch_path),
                # A replay drops the saved owner and re-derives it from the
                # current uploader; the suite has no git identity, so pass one.
                "--owner",
                "tester@redhat.com",
            ],
        )

        assert result.exit_code == 0, result.output
        assert "Using team from restored attributes: NETWORK" in result.output, (
            "Expected: restored team used as the run team"
        )
        assert "maps to no team" not in result.output, "Expected: no false team warning with a restored team"
        assert (tmp_path / "xunit_results.xml").exists(), (
            "Expected: report written once the restored attributes pass validation"
        )

    def test_saved_team_attribute_beats_metadata_team(self, tmp_path: Path) -> None:
        """Verify a restored TEAM attribute wins over the batch file's metadata team."""
        tests_dir, batch_path = write_minimal_batch(tmp_path=tmp_path)
        # A hand-edited retry file whose metadata team conflicts with the
        # saved TEAM attribute: the replay must keep the recorded value.
        batch_path.write_text(
            data=(
                "metadata:\n"
                "  team: STORAGE\n"
                "  attributes:\n"
                "    - key: team\n"
                "      value: NETWORK\n"
                "results:\n"
                "  - test: tests/network/test_manual_minimal.py::test_minimal\n"
                "    status: passed\n"
            ),
            encoding="utf-8",
        )

        result = CliRunner().invoke(
            cli=main,
            args=["--tests-dir", str(tests_dir), "--batch-file", str(batch_path), "--dry-run"],
        )

        assert result.exit_code == 0, result.output
        assert "team = NETWORK" in result.output, (
            "Expected: saved TEAM stands over the metadata team — replay semantics"
        )
        assert "Using team from batch file" not in result.output, (
            "Expected: metadata team not applied when a TEAM attribute is restored"
        )

    def test_metadata_team_is_ignored(self, tmp_path: Path) -> None:
        """Verify batch metadata team is ignored; TEAM comes from the saved run only."""
        tests_dir, batch_path = write_minimal_batch(tmp_path=tmp_path)
        # Hand-written batch carrying only BUNDLE in its attributes list plus
        # a stale metadata team: the replay keeps the recorded (team-less) run.
        batch_path.write_text(
            data=(
                "metadata:\n"
                "  team: STORAGE\n"
                "  bundle: v4.22.0\n"
                "  attributes:\n"
                "    - key: cnv_xy_version\n"
                "      value: '4.22'\n"
                "results:\n"
                "  - test: tests/network/test_manual_minimal.py::test_minimal\n"
                "    status: passed\n"
            ),
            encoding="utf-8",
        )

        result = CliRunner().invoke(
            cli=main,
            args=["--tests-dir", str(tests_dir), "--batch-file", str(batch_path), "--dry-run"],
        )

        assert result.exit_code == 0, result.output
        assert "Using team from batch file" not in result.output, "Expected: metadata team is never applied"
        assert "team = " not in result.output, "Expected: replay without saved TEAM stays team-less"

    def test_retry_replay_without_config_attribute_keys_prints_no_note(self, tmp_path: Path) -> None:
        """Verify no replay note when the config carries no attribute keys."""
        tests_dir, batch_path = write_minimal_batch(tmp_path=tmp_path)
        batch_path.write_text(
            data=(
                "metadata:\n"
                "  attributes:\n"
                "    - key: team\n"
                "      value: NETWORK\n"
                "results:\n"
                "  - test: tests/network/test_manual_minimal.py::test_minimal\n"
                "    status: passed\n"
            ),
            encoding="utf-8",
        )
        config_path = write_config_file(tmp_path=tmp_path, content="bundle: v4.22.0\n")

        result = CliRunner().invoke(
            cli=main,
            args=[
                "--tests-dir",
                str(tests_dir),
                "--config",
                str(config_path),
                "--batch-file",
                str(batch_path),
                "--dry-run",
            ],
        )

        assert result.exit_code == 0, result.output
        assert "are ignored" not in result.output, "Expected: no replay note without config attribute keys"
        assert f"Loaded config defaults from {config_path}" in result.output, (
            "Expected: non-attribute config keys still load"
        )

    def test_auto_discovered_config_used_by_main(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify a config at the default path is auto-discovered by main."""
        tests_dir, batch_path = write_minimal_batch(tmp_path=tmp_path)
        default_config = tmp_path / "discovered.yaml"
        default_config.write_text(data=f"tests-dir: {tests_dir}\n", encoding="utf-8")
        monkeypatch.setattr(
            target=reporter_module_config,
            name="DEFAULT_CONFIG_PATH",
            value=default_config,
        )

        result = CliRunner().invoke(
            cli=main,
            args=["--batch-file", str(batch_path), "--dry-run"],
        )

        assert result.exit_code == 0, result.output
        assert f"Loaded config defaults from {default_config}" in result.output, (
            "Expected: the default-path config is picked up and its source reported"
        )
        assert "Derived team: CNV Network" in result.output, (
            "Expected: discovered config tests-dir drives the team derivation"
        )

    def test_tests_dir_from_config(self, tmp_path: Path) -> None:
        """Verify the scan directory comes from the config when --tests-dir is absent."""
        tests_dir = write_minimal_tests_dir(tmp_path=tmp_path)
        config_path = write_config_file(tmp_path=tmp_path, content=f"tests-dir: {tests_dir}\n")

        result = CliRunner().invoke(
            cli=main,
            args=["--config", str(config_path), "--dry-run"],
        )

        assert f"Scanning {tests_dir}" in result.output, "Expected: config tests-dir is used for the scan"

    def test_config_tests_dir_must_exist(self, tmp_path: Path) -> None:
        """Verify a config tests-dir pointing nowhere fails cleanly."""
        config_path = write_config_file(
            tmp_path=tmp_path,
            content=f"tests-dir: {tmp_path / 'does-not-exist'}\n",
        )

        result = CliRunner().invoke(cli=main, args=["--config", str(config_path), "--dry-run"])

        assert result.exit_code != 0, "Expected: nonexistent config tests-dir fails"
        assert "is not an existing directory" in result.output, "Expected: clean error naming the bad path"

    def test_config_tests_dir_unresolvable_home_fails_cleanly(self, tmp_path: Path) -> None:
        """Verify a config tests-dir with an unknown ~user fails cleanly, not a traceback."""
        config_path = write_config_file(
            tmp_path=tmp_path,
            content="tests-dir: ~no-such-user-xyz/manual-tests\n",
        )

        result = CliRunner().invoke(cli=main, args=["--config", str(config_path), "--dry-run"])

        assert result.exit_code != 0, "Expected: unresolvable ~user tests-dir fails"
        assert "could not be resolved" in result.output, "Expected: clean error naming the raw value"
        assert result.exception.__class__.__name__ != "RuntimeError", (
            "Expected: RuntimeError converted to a ClickException"
        )

    def test_derived_team_reaches_attributes_with_config(self, tmp_path: Path) -> None:
        """Verify the tests-dir team applies even when a config file is present."""
        tests_dir = tmp_path / "x" / "tests" / "network"
        tests_dir.mkdir(parents=True)
        (tests_dir / "test_network_manual.py").write_text(
            data=MINIMAL_MANUAL_TEST_SOURCE,
            encoding="utf-8",
        )
        batch_path = tmp_path / "batch.yaml"
        batch_path.write_text(
            data=("results:\n  - test: tests/network/test_network_manual.py::test_minimal\n    status: passed\n"),
            encoding="utf-8",
        )
        config_path = write_config_file(tmp_path=tmp_path, content="bundle: v4.22.0\n")

        result = CliRunner().invoke(
            cli=main,
            args=[
                "--tests-dir",
                str(tests_dir),
                "--config",
                str(config_path),
                "--batch-file",
                str(batch_path),
                "--dry-run",
            ],
        )

        assert result.exit_code == 0, result.output
        assert "Derived team: CNV Network" in result.output, "Expected: team derived from the tests directory"
        assert "team = CNV Network" in result.output, "Expected: derived team reaches the attributes"

    def test_from_cluster_with_retry_file_still_gets_config_defaults(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify --from-cluster over a retry file is not a replay: config defaults apply."""
        tests_dir, batch_path = write_minimal_batch(tmp_path=tmp_path)
        # A retry file with saved attributes that will NOT be restored because
        # --from-cluster resolves cluster attributes instead.
        batch_path.write_text(
            data=(
                "metadata:\n"
                "  attributes:\n"
                "    - key: team\n"
                "      value: NETWORK\n"
                "results:\n"
                "  - test: tests/network/test_manual_minimal.py::test_minimal\n"
                "    status: passed\n"
            ),
            encoding="utf-8",
        )
        config_path = write_config_file(tmp_path=tmp_path, content="ocp-version: 4.22.0\n")
        monkeypatch.setattr(target=reporter_module, name="_CLUSTER_INFO_IMPORT_ERROR", value=None)
        cluster_attrs = [
            {"key": "ocp_version", "value": "4.21.0"},
            {"key": "cluster", "value": "bm15a"},
        ]
        with (
            patch(
                target="scripts.manual_tests_reporter.manual_tests_reporter.get_cluster_attributes",
                return_value=cluster_attrs,
            ),
            patch(
                target="scripts.manual_tests_reporter.manual_tests_reporter.cluster_attributes_to_run_attrs",
                side_effect=lambda cluster_attrs: cluster_attrs,
            ),
        ):
            result = CliRunner().invoke(
                cli=main,
                args=[
                    "--tests-dir",
                    str(tests_dir),
                    "--config",
                    str(config_path),
                    "--batch-file",
                    str(batch_path),
                    "--from-cluster",
                    "--dry-run",
                ],
            )

        assert result.exit_code == 0, result.output
        assert "config defaults for" not in result.output, (
            "Expected: no false replay note — saved attributes were not restored"
        )
        assert "1 saved attributes from the batch file are ignored" in result.output, (
            "Expected: skipped saved attributes are reported, not silently discarded"
        )
        assert "ocp_version = 4.22.0" in result.output, "Expected: config defaults apply to the from-cluster run"

    def test_explicit_cnv_version_drops_contradicting_cluster_cnv_version(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify an explicit --cnv-version contradicting cluster values drops the derived full version.

        CLI-over-cluster precedence must be complete: keeping the
        cluster-derived full cnv_version next to an explicit X.Y override
        would ship a self-contradictory facet pair. The derived full value
        is dropped; the X.Y override stands.
        """
        tests_dir, batch_path = write_minimal_batch(tmp_path=tmp_path)
        monkeypatch.setattr(target=reporter_module, name="_CLUSTER_INFO_IMPORT_ERROR", value=None)
        with (
            patch(
                target="scripts.manual_tests_reporter.manual_tests_reporter.get_cluster_attributes",
                return_value=object(),
            ),
            patch(
                target="scripts.manual_tests_reporter.manual_tests_reporter.cluster_attributes_to_run_attrs",
                return_value=[
                    {"key": "cnv_version", "value": "4.22.0"},
                    {"key": "cluster", "value": "test-cluster"},
                ],
            ),
        ):
            result = CliRunner().invoke(
                cli=main,
                args=[
                    "--tests-dir",
                    str(tests_dir),
                    "--batch-file",
                    str(batch_path),
                    "--from-cluster",
                    "--cnv-version",
                    "4.21",
                    "--dry-run",
                ],
            )

        assert result.exit_code == 0, result.output
        assert "Dropping cluster-derived cnv_version 4.22.0" in result.output, (
            "Expected: the contradicting cluster-derived cnv_version is dropped"
        )
        assert "cnv_version = 4.22.0" not in result.output, (
            "Expected: the dropped full version must not appear in the attribute list"
        )
        assert "cnv_xy_version = 4.21" in result.output, "Expected: the explicit X.Y override stands"

    def test_from_cluster_with_no_cluster_attributes_replays_saved_run(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify --from-cluster yielding zero attributes still replays the saved run."""
        tests_dir, batch_path = write_minimal_batch(tmp_path=tmp_path)
        # A retry file whose saved attributes WILL be restored: --from-cluster
        # resolved no cluster attributes, so the run is a replay after all.
        batch_path.write_text(
            data=(
                "metadata:\n"
                "  attributes:\n"
                "    - key: team\n"
                "      value: NETWORK\n"
                "    - key: ocp_version\n"
                "      value: 4.21.0\n"
                "results:\n"
                "  - test: tests/network/test_manual_minimal.py::test_minimal\n"
                "    status: passed\n"
            ),
            encoding="utf-8",
        )
        config_path = write_config_file(tmp_path=tmp_path, content="ocp-version: 4.22.0\n")
        monkeypatch.setattr(target=reporter_module, name="_CLUSTER_INFO_IMPORT_ERROR", value=None)
        with (
            patch(
                target="scripts.manual_tests_reporter.manual_tests_reporter.get_cluster_attributes",
                return_value=object(),
            ),
            patch(
                target="scripts.manual_tests_reporter.manual_tests_reporter.cluster_attributes_to_run_attrs",
                return_value=[],
            ),
        ):
            result = CliRunner().invoke(
                cli=main,
                args=[
                    "--tests-dir",
                    str(tests_dir),
                    "--config",
                    str(config_path),
                    "--batch-file",
                    str(batch_path),
                    "--from-cluster",
                    "--dry-run",
                ],
            )

        assert result.exit_code == 0, result.output
        assert "Restored 2 attributes from batch file." in result.output, (
            "Expected: saved attributes restored because no cluster attributes were resolved"
        )
        assert "config defaults for ocp-version are ignored" in result.output, (
            "Expected: replay note — the empty from-cluster result does not turn the run fresh"
        )
        assert "team = NETWORK" in result.output, "Expected: saved team stands over the config team"
        assert "ocp_version = 4.21.0" in result.output, "Expected: saved ocp_version stands over the config value"

    def test_batch_metadata_team_ignored_for_fresh_run(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """Verify non-replay batch-file metadata team is ignored; the derived team wins."""
        tests_dir, batch_path = write_minimal_batch(tmp_path=tmp_path)
        batch_path.write_text(
            data=(
                "metadata:\n"
                "  team: STORAGE\n"
                "results:\n"
                "  - test: tests/network/test_manual_minimal.py::test_minimal\n"
                "    status: passed\n"
            ),
            encoding="utf-8",
        )
        config_path = write_config_file(tmp_path=tmp_path, content="bundle: v4.22.0\n")

        with caplog.at_level(level="WARNING"):
            result = CliRunner().invoke(
                cli=main,
                args=[
                    "--tests-dir",
                    str(tests_dir),
                    "--config",
                    str(config_path),
                    "--batch-file",
                    str(batch_path),
                    "--dry-run",
                ],
            )

        assert result.exit_code == 0, result.output
        assert "Using team from batch file" not in result.output, "Expected: metadata team is never applied"
        assert "team = CNV Network" in result.output, "Expected: derived team wins over the metadata team"
        ignored_team_warnings = [record for record in caplog.records if "declares metadata.team" in record.getMessage()]
        assert ignored_team_warnings, "Expected: ignored metadata.team surfaces a warning, not silence"

    def test_batch_metadata_null_team_does_not_warn(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """Verify a legacy `team: null` retry file does not trigger the ignored-team warning.

        Older releases serialized `metadata.team: null` for team-less runs; a
        null value declares nothing and must not warn on replay or fresh runs.
        """
        tests_dir, batch_path = write_minimal_batch(tmp_path=tmp_path)
        batch_path.write_text(
            data=(
                "metadata:\n"
                "  team: null\n"
                "  bundle: v4.22.0\n"
                "results:\n"
                "  - test: tests/network/test_manual_minimal.py::test_minimal\n"
                "    status: passed\n"
            ),
            encoding="utf-8",
        )

        with caplog.at_level(level="WARNING"):
            result = CliRunner().invoke(
                cli=main,
                args=[
                    "--tests-dir",
                    str(tests_dir),
                    "--batch-file",
                    str(batch_path),
                    "--dry-run",
                ],
            )

        assert result.exit_code == 0, result.output
        ignored_team_warnings = [record for record in caplog.records if "declares metadata.team" in record.getMessage()]
        assert not ignored_team_warnings, "Expected: null metadata.team declares nothing and does not warn"

    def test_config_value_beats_cluster_attribute(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify a config-file attribute overrides a cluster-derived value."""
        tests_dir, batch_path = write_minimal_batch(tmp_path=tmp_path)
        config_path = write_config_file(tmp_path=tmp_path, content="ocp-version: 4.22.0\n")
        monkeypatch.setattr(target=reporter_module, name="_CLUSTER_INFO_IMPORT_ERROR", value=None)
        cluster_attrs = [
            {"key": "ocp_version", "value": "4.21.0"},
            {"key": "cluster", "value": "bm15a"},
        ]
        with (
            patch(
                target="scripts.manual_tests_reporter.manual_tests_reporter.get_cluster_attributes",
                return_value=cluster_attrs,
            ),
            patch(
                target="scripts.manual_tests_reporter.manual_tests_reporter.cluster_attributes_to_run_attrs",
                side_effect=lambda cluster_attrs: cluster_attrs,
            ),
        ):
            result = CliRunner().invoke(
                cli=main,
                args=[
                    "--tests-dir",
                    str(tests_dir),
                    "--config",
                    str(config_path),
                    "--batch-file",
                    str(batch_path),
                    "--from-cluster",
                    "--dry-run",
                ],
            )

        assert result.exit_code == 0, result.output
        assert "ocp_version = 4.22.0" in result.output, "Expected: config ocp_version beats the cluster-derived one"
        assert "ocp_version = 4.21.0" not in result.output, "Expected: cluster ocp_version is overridden"

    def test_config_values_are_stripped(self, tmp_path: Path) -> None:
        """Verify whitespace-padded config values are stripped on load."""
        config_path = write_config_file(tmp_path=tmp_path, content='tier: "  TIER-2  "\n')

        config, _source = load_config(config_path=config_path)

        assert config["tier"] == "TIER-2", f"Expected stripped value, got {config['tier']!r}"


class TestBatchUpload:
    def test_batch_upload_keeps_polarion_linkage(self, tmp_path: Path) -> None:
        """Verify a batch run writes the collected Polarion ID into the JUnit XML."""
        tests_dir = tmp_path / "tests" / "network"
        tests_dir.mkdir(parents=True)
        (tests_dir / "test_polarion_manual.py").write_text(
            data=(
                "import pytest\n\n\n"
                "@pytest.mark.manual\n"
                '@pytest.mark.polarion("MOCK-4321")\n'
                "def test_polarion_linked():\n    pass\n"
            ),
            encoding="utf-8",
        )
        batch_path = tmp_path / "batch.yaml"
        batch_path.write_text(
            data=(
                "results:\n  - test: tests/network/test_polarion_manual.py::test_polarion_linked\n    status: passed\n"
            ),
            encoding="utf-8",
        )
        result = CliRunner().invoke(
            cli=main,
            args=[*required_attr_args(tests_dir=tests_dir), "--batch-file", str(batch_path)],
        )

        assert result.exit_code == 0, result.output
        report_path = junit_report_path(tests_dir=tests_dir)
        assert report_path.exists(), f"Expected the JUnit report at {report_path}"
        props = read_junit_properties(xml_path=report_path)
        assert props["dd_tags[polarion-testcase-id]"] == "MOCK-4321", (
            f"Expected the collected Polarion ID in the report, got {props!r}"
        )


class TestJenkinsParityTags:
    def test_report_carries_jenkins_parity_tags(self, tmp_path: Path) -> None:
        """Verify the written report carries the Jenkins parity tags as dd_tags properties.

        The tag names and suite/file names mirror the Jenkins
        datadog-upload-results pipeline so both run types land on the same
        Datadog tests; MANUAL is the only intentional difference.
        """
        tests_dir, batch_path = write_minimal_batch(tmp_path=tmp_path)
        result = CliRunner().invoke(
            cli=main,
            args=[
                *required_attr_args(tests_dir=tests_dir),
                "--batch-file",
                str(batch_path),
                "--tier",
                "tier-2",
                "--marker",
                "manual",
                "--rootcoz-url",
                "https://rootcoz.example/run/1",
            ],
        )

        assert result.exit_code == 0, result.output
        report_path = junit_report_path(tests_dir=tests_dir)
        assert report_path.name == "xunit_results.xml", (
            f"Expected the Jenkins upload file name, got {report_path.name!r}"
        )
        assert report_path.exists(), f"Expected the JUnit report at {report_path}"
        props = read_junit_properties(xml_path=report_path)
        expected_tags = {
            "manual": "true",
            "team": "CNV_Network",
            "tier": "2",
            "cnv_version": "4.22.0",
            "cnv_xy_version": "4.22",
            "ocp_version": "4.22.0",
            "cluster": "bm15a",
            "cluster_domain": "example.com",
            "storage_class": "ocs",
            "cnv_channel": "candidate",
            "owner": "tester@redhat.com",
            "marker": "manual",
            "test_case_name": "manual.network",
            "job_name": "manual-tests-cnv_network",
            "rootcoz.url": "https://rootcoz.example/run/1",
        }
        for tag_key, expected_value in expected_tags.items():
            actual_value = props.get(f"dd_tags[{tag_key}]")
            assert actual_value == expected_value, (
                f"Expected dd_tags[{tag_key}]={expected_value!r} in the report, got {actual_value!r}"
            )
        build_number = props.get("dd_tags[build_number]")
        assert build_number is not None and build_number.isdigit(), (
            f"Expected a numeric dd_tags[build_number] in the report, got {build_number!r}"
        )
        assert not any(name.startswith(("dd_tags[arch]", "dd_tags[bundle]")) for name in props), (
            f"Expected: no arch/bundle tags in the Jenkins-parity set, got {sorted(props)!r}"
        )
        assert 'name="pytest"' in report_path.read_text(encoding="utf-8"), (
            "Expected: suite name matches the Jenkins uploads"
        )

    def test_owner_derived_from_git_when_not_overridden(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify the owner tag defaults to the tests checkout's git identity."""
        tests_dir, batch_path = write_minimal_batch(tmp_path=tmp_path)
        monkeypatch.setattr(
            target=reporter_module,
            name="_get_git_user_email",
            value=lambda tests_dir: "git-derived@redhat.com",
        )
        result = CliRunner().invoke(
            cli=main,
            args=[
                "--tests-dir",
                str(tests_dir),
                "--batch-file",
                str(batch_path),
                "--dry-run",
            ],
        )

        assert result.exit_code == 0, result.output
        assert "Derived owner from git: git-derived@redhat.com" in result.output, (
            "Expected: git identity becomes the owner attribute"
        )

    def test_replay_drops_saved_owner_for_current_uploader(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify a replay tags the current uploader, not the saved one."""
        tests_dir, batch_path = write_minimal_batch(tmp_path=tmp_path)
        batch_path.write_text(
            data=(
                "metadata:\n"
                "  attributes:\n"
                "    - key: team\n"
                "      value: NETWORK\n"
                "    - key: owner\n"
                "      value: original-runner@redhat.com\n"
                "results:\n"
                "  - test: tests/network/test_manual_minimal.py::test_minimal\n"
                "    status: passed\n"
            ),
            encoding="utf-8",
        )
        result = CliRunner().invoke(
            cli=main,
            args=[
                "--tests-dir",
                str(tests_dir),
                "--batch-file",
                str(batch_path),
                "--owner",
                "replayer@redhat.com",
                "--dry-run",
            ],
        )

        assert result.exit_code == 0, result.output
        assert "Dropping saved owner original-runner@redhat.com" in result.output, (
            "Expected: saved owner reported as dropped"
        )
        assert "owner = replayer@redhat.com" in result.output, "Expected: the current uploader's owner stands"

    def test_get_git_user_email_reads_tests_checkout(self, tmp_path: Path) -> None:
        """Verify the git identity is read from the scanned tests directory."""
        with patch(
            target="scripts.manual_tests_reporter.manual_tests_reporter.run_command",
            return_value=(True, "tester@redhat.com\n", ""),
        ) as mock_run:
            email = reporter_module._get_git_user_email(tests_dir=tmp_path)

        assert email == "tester@redhat.com", f"Expected the git e-mail, got {email!r}"
        assert mock_run.call_args_list[0].kwargs["command"][:4] == ["git", "-C", str(tmp_path), "config"], (
            "Expected: git runs against the tests directory"
        )

    def test_get_git_user_email_unavailable_returns_none(self, tmp_path: Path) -> None:
        """Verify a missing git identity returns None instead of raising."""
        with patch(
            target="scripts.manual_tests_reporter.manual_tests_reporter.run_command",
            return_value=(False, "", "not a git repository"),
        ):
            email = reporter_module._get_git_user_email(tests_dir=tmp_path)

        assert email is None, "Expected: unavailable git identity yields None"

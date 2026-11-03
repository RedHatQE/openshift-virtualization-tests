#!/usr/bin/env -S uv run python
# Co-authored-by: Claude <noreply@anthropic.com>
"""Manual Test Reporter for Datadog Test Visibility.

Interactive CLI that collects tests marked with ``@pytest.mark.manual``,
shows full test context (docstrings, markers, preconditions) one-by-one,
lets the tester mark each as pass/fail/skip, and pushes results to
Datadog Test Optimization as a JUnit XML upload via ``datadog-ci``.

Supports batch mode via YAML file for non-interactive use and failure retry.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import click
import yaml
from kubernetes.client.exceptions import ApiException
from kubernetes.config import ConfigException
from simple_logger.logger import get_logger
from urllib3.exceptions import HTTPError
from yaml import YAMLError

from scripts.manual_tests_reporter.collector import (
    ManualTestDetail,
    collect_manual_tests,
)
from scripts.manual_tests_reporter.config import (
    ATTRIBUTE_CONFIG_KEYS,
    CONFIG_KEY_TO_ATTRIBUTE_KEY,
    UniqueKeySafeLoader,
    load_config,
)
from scripts.manual_tests_reporter.junit_report import (
    VALID_STATUSES,
    DatadogUploadError,
    ManualTestResult,
    attributes_to_tags,
    build_junit_xml,
    coerce_status,
    upload_junit_report,
    write_junit_report,
)
from scripts.manual_tests_reporter.versions import cnv_xy_version_from_version_string
from utilities.exceptions import UnsupportedCPUArchitectureError

# The cluster_info import transitively pulls the utilities.* chain, which
# resolves cluster architecture (and thus connects to the cluster) at import
# time. Defer that failure to --from-cluster — the only consumer — so plain
# scan, batch, and dry-run flows work on hosts without a kubeconfig.
_CLUSTER_INFO_IMPORT_ERROR: str | None = None
try:
    from scripts.manual_tests_reporter.cluster_info import (
        cluster_attributes_to_run_attrs,
        get_cluster_attributes,
    )
except (
    ApiException,  # reachable API server, expired credentials (401) or RBAC denial (403)
    ConfigException,  # missing or invalid kubeconfig
    HTTPError,  # connection-level failure (unreachable/black-holed server address)
    UnsupportedCPUArchitectureError,  # reachable cluster, no arch-labeled nodes
    YAMLError,  # malformed YAML in the kubeconfig itself
) as exc:
    _CLUSTER_INFO_IMPORT_ERROR = str(exc)

LOGGER = get_logger(name=__name__)


TERMINAL_WIDTH = 80

_DEFECT_TYPES: dict[str, str] = {
    "1": "Product Bug",
    "2": "Automation Bug",
    "3": "System Issue",
    "4": "To Investigate",
    "5": "No Defect",
}

_DEFAULT_SERVICE = "cnv-manual-tests"

# Tests-directory folder (directly under ``tests/``) → Datadog TEAM attribute.
# TEAM is derived from the scanned directory, never hand-specified: the
# ``--team`` flag was dropped because the tests directory is the single
# source of truth — a hand-specified team could contradict the folder that
# produced the run.
#
# This mapping deliberately DIFFERS from the pytest-side TEAM_MARKERS in the
# root conftest.py: TEAM_MARKERS is a marker taxonomy (several folders carry
# multiple team markers), while this maps each folder to its single Datadog
# reporting owner. Known divergences from the marker taxonomy:
# data_protection reports under STORAGE, observability under IUO, and the
# multi-marker folders (deprecated_api, post_test_alerts) plus the marker-less
# folder after_cluster_deploy_sanity report under IUO, while the marker-less
# folder scale reports under SCALE. A drift-guard
# test keeps every new tests/ folder mapped.
_FOLDER_TO_TEAM = {
    "network": "NETWORK",
    "storage": "STORAGE",
    "data_protection": "STORAGE",
    "virt": "VIRT",
    "observability": "IUO",
    "infrastructure": "INFRASTRUCTURE",
    "install_upgrade_operators": "IUO",
    "chaos": "CHAOS",
    "after_cluster_deploy_sanity": "IUO",
    "deprecated_api": "IUO",
    "post_test_alerts": "IUO",
    "scale": "SCALE",
}


def _build_run_attributes(
    team: str | None = None,
    bundle: str | None = None,
    cnv_version: str | None = None,
    ocp_version: str | None = None,
    cluster_name: str | None = None,
    cluster_domain: str | None = None,
    storage_class: str | None = None,
    channel: str | None = None,
    tier: str | None = None,
    cluster_attrs: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    """Build run attribute list from CLI args and optional cluster attributes.

    Cluster-derived attributes serve as defaults; explicit CLI values
    override them.  ``MANUAL`` is always present; ``TEAM`` is present when
    derived from the tests directory, or restored from a replayed run's
    saved attributes.

    Args:
        team: Team name (e.g. ``NETWORK``).
        bundle: Bundle version string.
        cnv_version: CNV X.Y version override.
        ocp_version: OCP version override.
        cluster_name: Cluster name override.
        cluster_domain: Cluster domain override.
        storage_class: Storage-class label override.
        channel: Channel override.
        tier: Tier label (e.g. ``TIER-2``).
        cluster_attrs: Attributes auto-populated from ``--from-cluster``.

    Returns:
        Final list of ``{"key": ..., "value": ...}`` dicts.
    """
    # Start from cluster attrs (as a mutable copy) or empty list
    attrs_by_key: dict[str, str] = {}
    if cluster_attrs:
        for attr in cluster_attrs:
            attrs_by_key[attr["key"]] = attr["value"]

    # Map explicit CLI overrides to their attribute keys
    overrides: dict[str, str | None] = {
        "BUNDLE": bundle,
        "CNV_XY_VER": cnv_version,
        "OCP": ocp_version,
        "CLUSTER_NAME": cluster_name,
        "CLUSTER_DOMAIN": cluster_domain,
        "SC": storage_class,
        "CHANNEL": channel,
    }

    for key, value in overrides.items():
        if value is not None:
            attrs_by_key[key] = value

    # Auto-derive CNV_XY_VER from BUNDLE
    # Explicit --cnv-version always wins (never silently discarded).
    # An explicit --bundle overrides cluster-derived CNV_XY_VER; a cluster-derived
    # bundle only fills CNV_XY_VER when it is missing.
    if cnv_version is None and "BUNDLE" in attrs_by_key and (bundle is not None or "CNV_XY_VER" not in attrs_by_key):
        derived_xy = cnv_xy_version_from_version_string(version_string=attrs_by_key["BUNDLE"])
        if derived_xy is not None:
            attrs_by_key["CNV_XY_VER"] = derived_xy

    # Mandatory attributes
    # Run-type tag (Datadog: manual:true), mirroring the always-emitted
    # MANUAL attribute of the previous ReportPortal manual reporter.
    attrs_by_key["MANUAL"] = "true"

    if team:
        # Preserved verbatim: a derived team is already upper-case (every
        # _FOLDER_TO_TEAM value is), while a replayed run must reproduce its
        # recorded TEAM attribute exactly — re-casing here would make the
        # "Using team from restored attributes" echo disagree with the
        # uploaded tag. The suite-name label normalizes for display instead.
        attrs_by_key["TEAM"] = team

    if tier is not None:
        attrs_by_key["TIER"] = tier.upper()

    return [{"key": key, "value": value} for key, value in attrs_by_key.items()]


def _display_test_detail(test: ManualTestDetail, index: int, total: int) -> None:
    """Display a single test's full context to stdout.

    Renders the test header, markers, fixtures, docstrings, and
    separator lines using a fixed-width terminal format.

    Args:
        test: Manual test detail to display.
        index: 1-based index of the current test.
        total: Total number of tests.
    """
    header_line = "═" * TERMINAL_WIDTH
    separator_line = "─" * TERMINAL_WIDTH

    # Header block
    click.echo(message=f"\n{header_line}")
    if test.class_name:
        click.echo(message=f"[{index}/{total}] {test.file_path}")
        click.echo(message=f"       {test.class_name}::{test.method_name}")
    else:
        click.echo(message=f"[{index}/{total}] {test.file_path}")
        click.echo(message=f"       {test.method_name}")
    click.echo(message=header_line)
    click.echo()

    # Module markers
    if test.module_markers:
        formatted_markers = ", ".join(f"@{marker}" for marker in test.module_markers)
        click.echo(message=f"Module markers: {formatted_markers}")

    # Class info
    if test.class_name:
        click.echo(message=f"Class:          {test.class_name}")

    # Class fixtures
    if test.class_fixtures:
        formatted_fixtures = ", ".join(f'"{fixture}"' for fixture in test.class_fixtures)
        click.echo(message=f"Class fixtures: @usefixtures({formatted_fixtures})")

    # Class markers
    if test.class_markers:
        formatted_class_markers = ", ".join(f"@{marker}" for marker in test.class_markers)
        click.echo(message=f"Class markers:  {formatted_class_markers}")

    # Test markers
    if test.test_markers:
        formatted_test_markers = ", ".join(f"@{marker}" for marker in test.test_markers)
        click.echo(message=f"Test markers:   {formatted_test_markers}")

    # Polarion ID
    if test.polarion_id:
        click.echo(message=f"Polarion:       {test.polarion_id}")

    # Module docstring (STP / preconditions)
    if test.module_docstring and test.module_docstring.strip():
        click.echo()
        click.echo(message="Module:")
        for line in test.module_docstring.strip().splitlines():
            click.echo(message=f"  {line}")

    # Class docstring
    if test.class_docstring and test.class_docstring.strip():
        click.echo()
        click.echo(message="Class docs:")
        for line in test.class_docstring.strip().splitlines():
            click.echo(message=f"  {line}")

    # Test docstring
    if test.test_docstring and test.test_docstring.strip():
        click.echo()
        click.echo(message="Description:")
        for line in test.test_docstring.strip().splitlines():
            click.echo(message=f"  {line}")

    click.echo()
    click.echo(message=separator_line)


def _run_interactive_mode(tests: list[ManualTestDetail]) -> tuple[list[ManualTestResult], int, bool, bool]:
    """Run interactive test result collection.

    Presents each manual test one-by-one and collects a verdict
    from the tester via the terminal.

    Args:
        tests: List of manual tests to present.

    Returns:
        Tuple of (results list, skipped count, quit_early flag, interrupted
        flag). Results contain PASSED/FAILED/SKIPPED entries collected before
        a quit or interruption; quit_early is True when the session ended
        before the last test; interrupted is True when that end was caused
        by Ctrl-C / Ctrl-D rather than an explicit 'q'.
    """
    results: list[ManualTestResult] = []
    skipped_count = 0
    total = len(tests)

    try:
        for index, test in enumerate(tests, start=1):
            _display_test_detail(test=test, index=index, total=total)

            while True:
                choice = (
                    click
                    .prompt(
                        text="Result (p=pass, f=fail, s=skip, q=quit)",
                        type=str,
                    )
                    .strip()
                    .lower()
                )

                if choice == "p":
                    results.append(ManualTestResult(test=test.node_id, status="PASSED"))
                    break
                elif choice == "f":
                    while True:
                        click.echo(message="Defect type:")
                        for key, label in _DEFECT_TYPES.items():
                            click.echo(message=f"  {key}. {label}")
                        defect_choice = click.prompt(
                            text="Choose (1-5, default=4)",
                            type=str,
                            default="4",
                            show_default=False,
                        ).strip()
                        if defect_choice in _DEFECT_TYPES:
                            break
                        click.echo(message=f"Invalid choice '{defect_choice}'. Use 1-5.")
                    issue_type_label = _DEFECT_TYPES[defect_choice]
                    comment = click.prompt(text="Comment (optional)", default="", show_default=False)
                    results.append(
                        ManualTestResult(
                            test=test.node_id,
                            status="FAILED",
                            comment=comment,
                            issue_type_label=issue_type_label,
                        )
                    )
                    break
                elif choice == "s":
                    results.append(ManualTestResult(test=test.node_id, status="SKIPPED"))
                    skipped_count += 1
                    break
                elif choice == "q":
                    click.echo(message="Quitting — returning results collected so far.")
                    return results, skipped_count, True, False
                else:
                    click.echo(message="Invalid choice. Use p/f/s/q.")
    except click.Abort, KeyboardInterrupt:
        # Ctrl-C / Ctrl-D: keep the verdicts collected so far and route
        # into the same partial-results save path as an explicit 'q'.
        return results, skipped_count, True, True

    return results, skipped_count, False, False


def _load_batch_file(batch_path: Path) -> tuple[list[ManualTestResult], dict[str, Any]]:
    """Load test results and metadata from a batch YAML file.

    Expected format::

        metadata:
            bundle: v4.22.0
        results:
          - test: "tests/foo/test_bar.py::TestClass::test_method"
            status: passed
            comment: "optional"

    Args:
        batch_path: Path to the YAML file.

    Returns:
        Tuple of (results list, metadata dict). Metadata may contain
        ``bundle`` and ``attributes`` from a previous session's saved
        file. A ``team`` metadata key is ignored — TEAM is derived from
        the tests directory.

    Raises:
        click.ClickException: If the file format is invalid, a status
            value is unrecognised, an entry field has an invalid type, a
            metadata attributes entry is not a dict with non-empty string
            ``key``/``value`` fields, an attribute key is duplicated, or
            ``attributes`` is not a list.
    """
    try:
        raw = yaml.load(stream=batch_path.read_text(encoding="utf-8"), Loader=UniqueKeySafeLoader)
    except UnicodeDecodeError as exc:
        raise click.ClickException(f"Batch file {batch_path} is not valid UTF-8: {exc}") from exc
    except (OSError, YAMLError) as exc:
        raise click.ClickException(f"Failed to read batch file {batch_path}: {exc}") from exc

    if not isinstance(raw, dict) or "results" not in raw:
        raise click.ClickException(f"Batch file {batch_path} must contain a top-level 'results' key")

    raw_results = raw["results"]
    if not isinstance(raw_results, list):
        raise click.ClickException(
            f"Batch file {batch_path}: 'results' must be a list, got {type(raw_results).__name__}"
        )

    results: list[ManualTestResult] = []
    for entry in raw_results:
        if not isinstance(entry, dict):
            raise click.ClickException(f"Batch result entry must be a dict, got: {type(entry).__name__}")
        raw_test = entry.get("test")
        if raw_test is None:
            raise click.ClickException(f"Batch entry has a missing or null 'test' key: {entry}")
        if not isinstance(raw_test, str):
            raise click.ClickException(
                f"Invalid test type for test '{raw_test}': expected string, got {type(raw_test).__name__}"
            )
        for field_name in ("comment", "issue_type_label"):
            field_value = entry.get(field_name)
            if field_value is not None and not isinstance(field_value, str):
                raise click.ClickException(
                    f"Invalid {field_name} type for test '{raw_test}': "
                    f"expected string, got {type(field_value).__name__}"
                )
        raw_status = entry.get("status", "")
        if not isinstance(raw_status, str):
            raise click.ClickException(
                f"Invalid status type for test '{entry.get('test')}': expected string, got {type(raw_status).__name__}"
            )
        try:
            status = coerce_status(value=raw_status.strip().upper())
        except ValueError:
            # Single clean message: the raw value as typed plus the allowed
            # set — chaining coerce_status's ValueError would repeat both.
            raise click.ClickException(
                f"Invalid status {raw_status!r} for test '{raw_test}' in batch file {batch_path}; "
                f"expected one of: {', '.join(sorted(VALID_STATUSES))}"
            ) from None
        results.append(
            ManualTestResult(
                test=raw_test,
                status=status,
                # YAML `comment:` with no value yields None — coerce to empty string;
                # strip so hand-edited padding cannot reach the report verbatim.
                comment=(entry.get("comment") or "").strip(),
                issue_type_label=entry.get("issue_type_label"),
            )
        )

    metadata: dict[str, Any] = {}  # values can be str or list[dict]
    raw_metadata = raw.get("metadata", {})
    if isinstance(raw_metadata, dict):
        # A legacy batch/retry file may still declare metadata.team (older
        # runs wrote it unconditionally, including `team: null` for team-less
        # sessions). Surface a real declaration instead of silently diverging
        # from it; a null value declares nothing and does not warn.
        declared_team = raw_metadata.get("team")
        if declared_team:
            LOGGER.warning(
                f"Batch file {batch_path} declares metadata.team {declared_team!r} - it is ignored; "
                "TEAM is derived from the tests directory (a replayed retry uses its saved TEAM "
                "attribute; add a TEAM entry to metadata.attributes to restore one)"
            )
        raw_bundle = raw_metadata.get("bundle")
        if raw_bundle is not None:
            if not isinstance(raw_bundle, str):
                raise click.ClickException(
                    f"Invalid bundle type in batch metadata: expected string, got {type(raw_bundle).__name__}"
                )
            stripped_bundle = raw_bundle.strip()
            if stripped_bundle:
                # Strip so hand-edited padding (e.g. `bundle: " v4.22 "`)
                # cannot produce a padded Datadog tag value.
                metadata["bundle"] = stripped_bundle
        saved_attrs = raw_metadata.get("attributes")
        if saved_attrs is not None and not isinstance(saved_attrs, list):
            raise click.ClickException(
                f"Invalid attributes type in batch metadata: expected list, got {type(saved_attrs).__name__}"
            )
        if isinstance(saved_attrs, list):
            seen_keys: set[str] = set()
            normalized_attrs: list[dict[str, str]] = []
            for attr in saved_attrs:
                attr_key = attr.get("key") if isinstance(attr, dict) else None
                attr_value = attr.get("value") if isinstance(attr, dict) else None
                if (
                    not isinstance(attr, dict)
                    or not isinstance(attr_key, str)
                    or not isinstance(attr_value, str)
                    or not attr_key.strip()
                    or not attr_value.strip()
                ):
                    raise click.ClickException(
                        f"Invalid attributes entry in batch metadata (non-empty string key and value required): {attr}"
                    )
                assert isinstance(attr_key, str) and isinstance(attr_value, str), (
                    "validated above; keeps type-checkers honest"
                )
                # Attribute keys are upper-case identifiers — normalize on load
                # so hand-edited lowercase keys reach every consumer correctly.
                normalized_key = attr_key.strip().upper()
                if normalized_key in seen_keys:
                    raise click.ClickException(f"Duplicate attribute key in batch metadata: {normalized_key}")
                seen_keys.add(normalized_key)
                # Strip so hand-edited padding cannot reach the Datadog tags.
                normalized_attrs.append({"key": normalized_key, "value": attr_value.strip()})
            metadata["attributes"] = normalized_attrs

    LOGGER.info(f"Loaded {len(results)} results from batch file {batch_path}")
    return results, metadata


def _merge_batch_metadata(
    batch_metadata: dict[str, Any],
    bundle: str | None,
    cluster_attrs: list[dict[str, str]] | None,
) -> tuple[str | None, list[dict[str, str]] | None, bool]:
    """Fill missing bundle and restore saved cluster attributes from batch metadata.

    CLI-provided values win; batch-file metadata fills the gaps; saved
    run attributes from a retry file are restored only when no cluster
    attributes were resolved. TEAM is never taken from metadata — it is
    derived from the tests directory (or restored with the saved run).

    Args:
        batch_metadata: Metadata loaded from the batch YAML file.
        bundle: Bundle version from CLI, if any.
        cluster_attrs: Cluster-derived attributes, if any.

    Returns:
        Tuple of (bundle, cluster_attrs, restored) with metadata merged
        in; ``restored`` is True when the batch file's saved run attributes
        were restored into ``cluster_attrs`` (i.e. the run is a replay).
    """
    saved_attrs = batch_metadata.get("attributes")
    restored = False
    if isinstance(saved_attrs, list) and saved_attrs and not cluster_attrs:
        # Copy on restore: later appends (missing BUNDLE fill, config bundle
        # gap-fill) must not mutate the parsed batch-file metadata.
        cluster_attrs = [dict(attr) for attr in saved_attrs]
        restored = True
        click.echo(message=f"Restored {len(saved_attrs)} attributes from batch file.")
    elif isinstance(saved_attrs, list) and saved_attrs:
        click.echo(
            message=f"Note: {len(saved_attrs)} saved attributes from the batch file are ignored — "
            "cluster-derived attributes take precedence."
        )
    batch_bundle = batch_metadata.get("bundle")
    if batch_bundle and not bundle:
        if restored:
            # Saved attributes carry the recorded run; do NOT promote the metadata
            # bundle to an explicit override — that would re-derive CNV_XY_VER and
            # discard the saved value. Fill BUNDLE only when the saved list lacks it
            # (e.g. a hand-written batch file with only TEAM).
            assert cluster_attrs is not None, "Restored attributes must be a list when restored is set"
            if not any(attr["key"] == "BUNDLE" for attr in cluster_attrs):
                cluster_attrs.append({"key": "BUNDLE", "value": batch_bundle})
                click.echo(message=f"Filled missing BUNDLE attribute from batch file: {batch_bundle}")
        else:
            bundle = batch_bundle
            click.echo(message=f"Using bundle from batch file: {bundle}")
    return bundle, cluster_attrs, restored


def _save_results_for_retry(
    results: list[ManualTestResult],
    bundle: str | None,
    attributes: list[dict[str, str]] | None = None,
) -> Path | None:
    """Save test results to a YAML file for later retry.

    The file is written to the current directory with a timestamped
    name so that multiple retry files can coexist. Save failures are
    logged and swallowed so a failure here never masks the original
    error when called from an exception handler.

    Args:
        results: List of ``ManualTestResult`` objects to save.
        bundle: Bundle version.
        attributes: Run attributes to preserve for retry. The TEAM
            attribute, when present, preserves the team for the retry.

    Returns:
        Path to the saved YAML file, or None when saving failed.
    """
    # Microsecond resolution: second-resolution stamps collide when two
    # saves happen in the same cwd within one second, silently truncating
    # the earlier file via write_text.
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%d_%H%M%S_%f")
    filename = f"manual_results_{timestamp}.yaml"
    output_path = Path.cwd() / filename

    payload: dict[str, Any] = {
        "metadata": {
            "bundle": bundle,
            "attributes": attributes or [],
            "saved_at": datetime.now(tz=UTC).isoformat(),
        },
        "results": [asdict(result) for result in results],
    }

    try:
        yaml_content = yaml.dump(data=payload, default_flow_style=False, sort_keys=False)
        output_path.write_text(data=yaml_content, encoding="utf-8")
    except (OSError, YAMLError) as exc:
        LOGGER.error(f"Failed to save retry file {output_path}: {exc}")
        return None
    LOGGER.info(f"Saved {len(results)} results to {output_path}")
    return output_path


@click.command(
    help="Manual Test Reporter for Datadog Test Visibility",
    epilog="Collects manual test results for @pytest.mark.manual tests and "
    "uploads them to Datadog Test Optimization via `datadog-ci junit upload`.",
)
@click.option("--bundle", type=str, default=None, help="Bundle version prefix (e.g., v4.22.0.rhel9-102)")
@click.option("--tier", type=str, default=None, help="Tier label (e.g., TIER-2)")
@click.option(
    "--tests-dir",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Tests directory to scan (e.g., tests/network/); defaults to the config file's "
    "tests-dir when set, otherwise this repository's tests directory",
)
@click.option(
    "-m", "--marker", type=str, default=None, help="Pytest marker expression (e.g., 'gating', 'smoke and not tier3')"
)
@click.option(
    "-k", "--keyword", type=str, default=None, help="Keyword filter on test node IDs (e.g., 'test_connectivity')"
)
@click.option("--from-cluster", is_flag=True, default=False, help="Auto-fill attributes from connected cluster")
@click.option("--ocp-version", type=str, default=None, help="Override OCP version")
@click.option("--cnv-version", type=str, default=None, help="Override CNV X.Y version")
@click.option("--cluster-name", type=str, default=None, help="Override cluster name")
@click.option("--cluster-domain", type=str, default=None, help="Override cluster domain")
@click.option("--sc", "storage_class", type=str, default=None, help="Override storage class label")
@click.option("--channel", type=str, default=None, help="Override channel")
@click.option(
    "--service",
    type=str,
    default=None,
    help=f"Datadog service name for uploaded results (default: {_DEFAULT_SERVICE})",
)
@click.option(
    "--batch-file",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Batch YAML file with pre-filled results",
)
@click.option("--dry-run", is_flag=True, default=False, help="Show what would be uploaded without uploading")
@click.option(
    "--config",
    "config_file",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="YAML config file with default run attributes; defaults to "
    "~/.config/manual_tests_reporter/config.yaml when that file exists",
)
def main(
    bundle: str | None,
    tier: str | None,
    tests_dir: Path | None,
    marker: str | None,
    keyword: str | None,
    from_cluster: bool,
    ocp_version: str | None,
    cnv_version: str | None,
    cluster_name: str | None,
    cluster_domain: str | None,
    storage_class: str | None,
    channel: str | None,
    service: str | None,
    batch_file: Path | None,
    dry_run: bool,
    config_file: Path | None,
) -> None:
    """Collect manual test results and upload them to Datadog.

    In interactive mode, each manual test is shown with full
    context and the tester marks it pass/fail/skip.  In batch mode a
    YAML file supplies pre-filled verdicts.
    """
    # ── 0a. Load config-file defaults. The config behaves like pre-set CLI
    # flags: a CLI flag always wins over it, and it overrides cluster-derived
    # values. Saved batch-file attributes (retries) are exempt — see step 3a. ──
    config, config_source = load_config(config_path=config_file)
    if config:
        click.echo(message=f"Loaded config defaults from {config_source}")

    def _config_default(cli_value: str | None, config_key: str) -> str | None:
        """Return the config-file value only when the CLI flag was not given."""
        return cli_value if cli_value is not None else config.get(config_key)

    service = _config_default(cli_value=service, config_key="service") or _DEFAULT_SERVICE
    if tests_dir is None:
        config_tests_dir = config.get("tests-dir")
        if config_tests_dir:
            try:
                tests_dir = Path(config_tests_dir).expanduser()
            except (RuntimeError, OSError) as expand_error:
                raise click.ClickException(
                    f"Config tests-dir '{config_tests_dir}' could not be resolved: {expand_error}"
                ) from expand_error
            if not tests_dir.is_dir():
                raise click.ClickException(
                    f"Config tests-dir '{config_tests_dir}' is not an existing directory "
                    f"(resolved to {tests_dir.resolve()}; relative paths resolve against the "
                    "launch directory)"
                )
    if tests_dir is None:
        tests_dir = Path(__file__).resolve().parents[2] / "tests"

    # Team inference from the tests directory runs LAST (step 2c, after
    # batch metadata and config defaults) so it cannot outrank explicit
    # sources — and never runs for a replayed retry, whose saved TEAM stands.

    # ── 1. Resolve cluster attributes ──
    cluster_attrs: list[dict[str, str]] | None = None
    # Immutable count of what --from-cluster actually resolved: the list
    # itself is later filled by restored batch attributes and config
    # gap-fills, so it cannot tell "the cluster resolved nothing" at
    # validation time — this count can.
    cluster_attr_count = 0
    if from_cluster:
        if _CLUSTER_INFO_IMPORT_ERROR is not None:
            raise click.ClickException(
                f"--from-cluster requires cluster access, but the cluster modules "
                f"failed to load: {_CLUSTER_INFO_IMPORT_ERROR}\n"
                "Provide a kubeconfig."
            )
        raw_cluster = get_cluster_attributes()
        cluster_attrs = cluster_attributes_to_run_attrs(cluster_attrs=raw_cluster)
        cluster_attr_count = len(cluster_attrs)
        click.echo(message=f"Loaded {len(cluster_attrs)} attributes from connected cluster.")

    # ── 2. Collect results ──
    collected_tests: list[ManualTestDetail] = []
    skipped_count = 0
    batch_metadata: dict[str, Any] = {}
    # Whether the batch file's saved attributes were restored — i.e. the run
    # is a replay of its recorded attributes. _merge_batch_metadata owns the
    # restore decision (only when no cluster attributes were resolved), so a
    # from-cluster run over a retry file is NOT a replay.
    replaying_saved_run = False
    # Team is never a CLI/config input: it is restored with a replayed run
    # or derived from the scanned tests directory (step 2c below).
    team: str | None = None

    if batch_file:
        results, batch_metadata = _load_batch_file(batch_path=batch_file)
        skipped_count = sum(1 for result in results if result.status == "SKIPPED")
        collected_count = len(results)
        bundle, cluster_attrs, replaying_saved_run = _merge_batch_metadata(
            batch_metadata=batch_metadata,
            bundle=bundle,
            cluster_attrs=cluster_attrs,
        )
        if replaying_saved_run and cluster_attrs:
            # A replay reproduces the recorded run: keep its TEAM, if any.
            team = next((attr["value"] for attr in cluster_attrs if attr["key"] == "TEAM"), None)
            if team:
                click.echo(message=f"Using team from restored attributes: {team}")
        # Re-collect manual tests to rebuild the node_id → Polarion ID
        # lookup so retried reports keep their Polarion linkage.
        collected_tests = collect_manual_tests(
            tests_dir=tests_dir,
            marker_filter=marker,
            keyword_filter=keyword,
        )
        # Batch node_ids that match no collected test (e.g. a typo in a
        # hand-edited file) upload without Polarion linkage — surface that.
        collected_node_ids = {test.node_id for test in collected_tests}
        unmatched_tests = [result.test for result in results if result.test not in collected_node_ids]
        if unmatched_tests:
            LOGGER.warning(f"Batch results matching no collected manual test: {unmatched_tests}")
            click.echo(message=f"Warning: {len(unmatched_tests)} result(s) match no collected manual test.", err=True)
    else:
        filter_parts = []
        if marker:
            filter_parts.append(f"-m '{marker}'")
        if keyword:
            filter_parts.append(f"-k '{keyword}'")
        filter_msg = f" (filters: {', '.join(filter_parts)})" if filter_parts else ""
        click.echo(message=f"Scanning {tests_dir} for manual tests{filter_msg}...")
        collected_tests = collect_manual_tests(
            tests_dir=tests_dir,
            marker_filter=marker,
            keyword_filter=keyword,
        )

        if not collected_tests:
            click.echo(message="No manual tests found.")
            sys.exit(0)

        collected_count = len(collected_tests)
        click.echo(message=f"Found {collected_count} manual tests.\n")

    # ── 2b. Apply config-file defaults for still-unset run attributes ──
    # On a replayed retry the saved attributes stand; config defaults only
    # fill gaps the saved list leaves (e.g. a hand-written batch with only
    # TEAM), so a partial saved list does not disable the whole config.
    # Bundle is special: filling it as an explicit override would re-derive
    # CNV_XY_VER and discard a saved value, so on a replay it is appended to
    # the restored attributes (mirroring the batch-metadata fill) instead.
    if replaying_saved_run:
        assert cluster_attrs is not None, "replay requires saved cluster attributes"
        saved_attr_keys = {attr["key"] for attr in cluster_attrs}
        skipped_config_keys = sorted(
            config_key
            for config_key in ATTRIBUTE_CONFIG_KEYS
            if config_key in config and CONFIG_KEY_TO_ATTRIBUTE_KEY[config_key] in saved_attr_keys
        )
        if skipped_config_keys:
            click.echo(
                message=f"Note: config defaults for {', '.join(skipped_config_keys)} are ignored — "
                "a higher-precedence source supplies those run attributes."
            )
        if "BUNDLE" not in saved_attr_keys and "bundle" in config:
            cluster_attrs.append({"key": "BUNDLE", "value": config["bundle"]})

        def _replay_config_default(cli_value: str | None, config_key: str) -> str | None:
            """Fill from config only when the saved attributes lack the key."""
            if cli_value is not None or CONFIG_KEY_TO_ATTRIBUTE_KEY[config_key] in saved_attr_keys:
                return cli_value
            return config.get(config_key)

        tier = _replay_config_default(cli_value=tier, config_key="tier")
        cnv_version = _replay_config_default(cli_value=cnv_version, config_key="cnv-version")
        ocp_version = _replay_config_default(cli_value=ocp_version, config_key="ocp-version")
        cluster_name = _replay_config_default(cli_value=cluster_name, config_key="cluster-name")
        cluster_domain = _replay_config_default(cli_value=cluster_domain, config_key="cluster-domain")
        storage_class = _replay_config_default(cli_value=storage_class, config_key="sc")
        channel = _replay_config_default(cli_value=channel, config_key="channel")
    else:
        tier = _config_default(cli_value=tier, config_key="tier")
        bundle = _config_default(cli_value=bundle, config_key="bundle")
        cnv_version = _config_default(cli_value=cnv_version, config_key="cnv-version")
        ocp_version = _config_default(cli_value=ocp_version, config_key="ocp-version")
        cluster_name = _config_default(cli_value=cluster_name, config_key="cluster-name")
        cluster_domain = _config_default(cli_value=cluster_domain, config_key="cluster-domain")
        storage_class = _config_default(cli_value=storage_class, config_key="sc")
        channel = _config_default(cli_value=channel, config_key="channel")

    # ── 2c. Derive team from the scanned tests directory ──
    if not team and not replaying_saved_run:
        resolved = tests_dir.resolve()
        parts = resolved.parts
        # Candidate folders, most-authoritative first: the folder directly
        # under each "tests" path component, deepest (last) first — the
        # deepest "tests" child wins, so a checkout path containing an
        # earlier "tests" component still derives from the real tests
        # directory. A nested "tests" dir whose own child is a mapped folder
        # (e.g. tests/network/tests/storage) therefore DOES win over the outer
        # folder: the deepest child is authoritative by design. Unmapped
        # deepest children fall through to the shallower "tests" children,
        # then to the selected folder itself (e.g. a standalone
        # --tests-dir network). Checking the tests-root children before the
        # basename keeps a nested leaf whose basename matches another team
        # (e.g. tests/observability/storage) attributed to its parent team.
        tests_child_candidates = [parts[index + 1] for index in range(len(parts) - 1) if parts[index] == "tests"]
        candidate_folders = [*reversed(tests_child_candidates), resolved.name]
        for folder in candidate_folders:
            team = _FOLDER_TO_TEAM.get(folder)
            if team:
                click.echo(message=f"Derived team: {team} (from {tests_dir})")
                break
        else:
            LOGGER.warning(f"Tests directory {tests_dir} maps to no team - TEAM attribute will be omitted")
            click.echo(
                message=f"Warning: {tests_dir} maps to no team - the run will not be team-filterable.",
                err=True,
            )

    # ── 3. Build run attributes ──
    attributes = _build_run_attributes(
        team=team,
        bundle=bundle,
        cnv_version=cnv_version,
        ocp_version=ocp_version,
        cluster_name=cluster_name,
        cluster_domain=cluster_domain,
        storage_class=storage_class,
        channel=channel,
        tier=tier,
        cluster_attrs=cluster_attrs,
    )

    # If bundle wasn't provided via CLI, extract from built attributes (may come from cluster)
    if not bundle:
        for attr in attributes:
            if attr["key"] == "BUNDLE":
                bundle = attr["value"]
                break

    # ── 4. Validate upload readiness ──
    required_attr_keys = {
        "BUNDLE": "--bundle",
        "OCP": "--ocp-version",
        "CNV_XY_VER": "--cnv-version",
        "CLUSTER_NAME": "--cluster-name",
        "CLUSTER_DOMAIN": "--cluster-domain",
        "SC": "--sc",
        "CHANNEL": "--channel",
    }
    present_keys = {attr["key"] for attr in attributes}
    missing = {key: flag for key, flag in required_attr_keys.items() if key not in present_keys}
    # Extra guidance appended to both the hard error and the dry-run
    # warning when the generic remedy line would mislead.
    extra_guidance = ""
    if from_cluster and not cluster_attr_count:
        # --from-cluster resolved nothing, so the "or --from-cluster"
        # advice below would mislead a user who already passed the flag:
        # point at cluster access instead. Restored retry-file attributes
        # do NOT suppress this — the count reflects only what the cluster
        # itself resolved.
        extra_guidance = (
            "\n--from-cluster resolved no cluster attributes; check cluster access and permissions (KUBECONFIG)."
        )
    if "CNV_XY_VER" in missing and cnv_version is None and bundle:
        # A bundle was supplied (CLI, config, cluster, batch metadata, or a
        # restored retry file — the step-3 backfill above normalizes them
        # all into `bundle`) but its X.Y version was underivable — name the
        # culprit instead of a bare missing-attribute error.
        extra_guidance += f"\nThe bundle '{bundle}' has no major.minor version; pass --cnv-version explicitly."
    if not dry_run:
        if missing:
            missing_names = ", ".join(sorted(missing.keys()))
            missing_flags = ", ".join(sorted(missing.values()))
            raise click.ClickException(
                f"Missing required run attributes: {missing_names}\n"
                f"Provide them via CLI flags ({missing_flags}), the config file, or --from-cluster."
                f"{extra_guidance}"
            )
        # Preflight upload prerequisites before the tester spends time on
        # verdicts; dry-run skips these since nothing is uploaded.
        if not (os.environ.get("DATADOG_API_KEY") or os.environ.get("DD_API_KEY")):
            raise click.ClickException("DATADOG_API_KEY (or DD_API_KEY) env var required for upload.")
        if shutil.which("datadog-ci") is None:
            raise click.ClickException(
                "datadog-ci not found on PATH. Install it with: npm install -g @datadog/datadog-ci"
            )
    elif missing:
        # Dry-run should predict upload readiness, not skip validation.
        missing_names = ", ".join(sorted(missing.keys()))
        click.echo(
            message=f"WARNING: upload would fail — missing: {missing_names}{extra_guidance}",
            err=True,
        )

    quit_early = False
    interrupted = False
    if not batch_file:
        results, skipped_count, quit_early, interrupted = _run_interactive_mode(tests=collected_tests)

    # ── 5. Print summary ──
    pass_count = sum(1 for result in results if result.status == "PASSED")
    failed_results = [result for result in results if result.status == "FAILED"]
    fail_count = len(failed_results)
    click.echo(message="\n── Summary ──")
    click.echo(message=f"Collected: {collected_count} tests")
    click.echo(message=f"  PASSED:  {pass_count}")
    click.echo(message=f"  FAILED:  {fail_count}")
    if failed_results:
        defect_counts: dict[str, int] = {}
        for result in failed_results:
            label = result.issue_type_label or "Unclassified"
            defect_counts[label] = defect_counts.get(label, 0) + 1
        for label, count in sorted(defect_counts.items()):
            click.echo(message=f"    {label}: {count}")
    click.echo(message=f"  Skipped: {skipped_count}")

    if not results:
        if interrupted:
            click.echo(message="\nSession interrupted before any verdict; nothing to save.")
        else:
            click.echo(message="\nNo results to upload.")
        sys.exit(0)

    # ── 6. Dry-run summary ──
    if dry_run:
        click.echo(message="\nAttributes:")
        for attr in attributes:
            click.echo(message=f"  {attr['key']} = {attr['value']}")
        click.echo(message=f"\nDatadog service: {service}")
        click.echo(message="No data was uploaded to Datadog.")
        sys.exit(0)

    # ── 7. Quit early: keep partial results, upload nothing ──
    team_label = team.upper() if team else "ALL"
    if quit_early:
        # The saved TEAM attribute (when present) keeps the team for the
        # retry; a team-less session saves no TEAM and stays team-less.
        saved_path = _save_results_for_retry(
            results=results,
            bundle=bundle,
            attributes=attributes,
        )
        if saved_path is not None:
            if interrupted:
                click.echo(
                    message=f"Session interrupted — partial results saved to {saved_path}; nothing was uploaded."
                )
            else:
                click.echo(message=f"Partial results saved to {saved_path}; nothing was uploaded.")
            click.echo(message=f"  Resume with: --batch-file {saved_path}")
        else:
            click.echo(message="Failed to save partial results; nothing was uploaded.", err=True)
        sys.exit(0)

    # ── 8. Build and upload JUnit report ──
    suite_name = f"Manual - {team_label}"
    if bundle:
        suite_name = f"{suite_name} - {bundle}"

    polarion_lookup: dict[str, str] = {}
    for test in collected_tests:
        if test.polarion_id:
            polarion_lookup[test.node_id] = test.polarion_id

    timestamp = datetime.now(tz=UTC).strftime("%Y%m%d_%H%M%S")
    # Write the report to a temp directory: successful uploads leave nothing
    # behind in the working directory; the file is only kept on failure.
    # Created inside the try so an OSError from mkdtemp (e.g. a full or
    # read-only TMPDIR) reaches the same retry-save path as upload failures.
    xml_dir: Path | None = None
    xml_path: Path | None = None
    try:
        xml_dir = Path(tempfile.mkdtemp(prefix="manual_tests_reporter_"))
        xml_path = xml_dir / f"manual_tests_report_{timestamp}.xml"
        xml_content = build_junit_xml(
            results=results,
            suite_name=suite_name,
            attributes=attributes,
            polarion_lookup=polarion_lookup,
            description=f"Manual test results for {team_label}",
        )
        write_junit_report(xml_path=xml_path, xml_content=xml_content)
        upload_junit_report(
            xml_path=xml_path,
            service=service,
            tags=attributes_to_tags(attributes=attributes),
        )
        click.echo(message=f"\n✓ Uploaded {len(results)} results to Datadog (service: {service})")
        click.echo(message="  View results in Datadog Test Optimization (CI Test Runs).")
        # Cleanup: remove the temp report after a successful upload.
        try:
            xml_path.unlink()
            xml_dir.rmdir()
        except OSError as exc:
            LOGGER.warning(f"Failed to clean up temporary report directory {xml_dir}: {exc}")

    except (DatadogUploadError, OSError) as exc:
        LOGGER.error(str(exc))
        saved_path = _save_results_for_retry(
            results=results,
            bundle=bundle,
            attributes=attributes,
        )
        click.echo(message=f"\n✗ Report generation or upload failed: {exc}", err=True)
        if saved_path is not None:
            click.echo(message=f"  Results saved to: {saved_path}", err=True)
            click.echo(message=f"  Retry with: --batch-file {saved_path}", err=True)
        else:
            click.echo(message="  Failed to save results for retry — see log output.", err=True)
        if xml_path is not None and xml_path.exists():
            click.echo(message=f"  JUnit report kept at: {xml_path}", err=True)
        sys.exit(1)

    except KeyboardInterrupt:
        # Ctrl-C during report build/upload (after the verdicts, outside the
        # interactive loop): keep the verdicts via the same retry-save path
        # the upload-failure handler uses, instead of exiting with a traceback.
        saved_path = _save_results_for_retry(
            results=results,
            bundle=bundle,
            attributes=attributes,
        )
        if saved_path is not None:
            click.echo(
                message=f"Session interrupted during upload — partial results saved to {saved_path}.",
                err=True,
            )
        else:
            click.echo(
                message="Session interrupted during upload — failed to save partial results.",
                err=True,
            )
        if xml_path is not None and xml_path.exists():
            click.echo(message=f"  JUnit report kept at: {xml_path}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

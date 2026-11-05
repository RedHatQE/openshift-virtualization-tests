#!/usr/bin/env -S uv run python
# Co-authored-by: Claude <noreply@anthropic.com>
"""Manual Test Reporter for Datadog Test Visibility.

Interactive CLI that collects tests marked with ``@pytest.mark.manual``,
shows full test context (docstrings, markers, preconditions) one-by-one,
lets the tester mark each as pass/fail/skip, and writes the results as a
JUnit XML report that carries every Datadog run tag — so it can be uploaded
later (``datadog-ci junit upload``) without this tool pushing to Datadog.

Supports batch mode via YAML file for non-interactive use and failure retry.
"""

from __future__ import annotations

import os
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import click
import yaml
from kubernetes.client.exceptions import ApiException
from kubernetes.config import ConfigException
from pyhelper_utils.shell import run_command
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
    CLASSIFICATION_BY_DEFECT_LABEL,
    DEFECT_LABELS,
    UNCLASSIFIED_LABEL,
    VALID_STATUSES,
    ManualTestResult,
    build_junit_xml,
    coerce_status,
    write_junit_report,
)
from scripts.manual_tests_reporter.versions import cnv_versions_from_version_string
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

# Interactive defect choices. The label text is the single source of the
# classification vocabulary: junit_report maps these exact strings to the
# tfa.classification tag, so a new choice must be added there too (a drift
# test asserts the two stay in sync).
# Interactive chooser: numeric key -> defect label. The labels themselves live
# in junit_report.DEFECT_LABELS (next to the classification map) so the
# vocabulary has one home.
_DEFECT_TYPES: dict[str, str] = {str(index): label for index, label in enumerate(DEFECT_LABELS, start=1)}

# Choice preselected on an empty answer; "To Investigate" is the honest
# default for an unclassified failure.
_DEFAULT_DEFECT_CHOICE = str(DEFECT_LABELS.index("To Investigate") + 1)

# Suite name used by Jenkins uploads (datadog-ci derives @test.full_name from
# the suite name); manual reports reuse it so the same test node ID resolves
# to the same Datadog test, instead of creating a parallel "Manual - X"
# test universe.
_DEFAULT_SUITE_NAME = "pytest"

# XML file name used by Jenkins uploads (**/xunit_results.xml filter); reusing
# it aligns the @test.module / @test.bundle facets too. This tool only writes
# the file — uploading it is a separate, later step.
_JUNIT_FILE_NAME = "xunit_results.xml"

# Job-name prefix for the synthetic ``job_name`` tag. Manual runs have no
# Jenkins job, but the tag is mandatory for the Datadog Builds facet, so a
# stable, filterable name is emitted instead of leaving it out.
_JOB_NAME_PREFIX = "manual-tests"

# Tests-directory folder (directly under ``tests/``) → Datadog ``team`` tag.
# The team is derived from the scanned directory, never hand-specified: the
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
# Values are the Jenkins JOB_METADATA ``team`` strings verbatim (verified
# against src/resources/test-jobs-metadata in contra), because the CI tag is
# ``team:${metadata.team}`` unchanged. A short upper-case label would put
# manual runs in a facet value no CI run ever writes — invisible to every
# team filter. Datadog converts spaces and commas to underscores server-side
# for every uploader (tagging docs: "all other characters ... are converted
# to underscores"), so "CNV Network" lands on CNV_Network for CI and for a
# manual run alike.
#
# tests/chaos and tests/scale have no Jenkins counterpart job at all, so
# they keep their own values: there is no CI facet to align with.
_FOLDER_TO_TEAM = {
    "network": "CNV Network",
    "storage": "Storage Platform",
    "data_protection": "Storage Platform",
    "virt": "CNV Virtualization",
    "observability": "CNV Install, Upgrade and Operators",
    "infrastructure": "CNV Infrastructure",
    "install_upgrade_operators": "CNV Install, Upgrade and Operators",
    "chaos": "CHAOS",
    "after_cluster_deploy_sanity": "CNV Install, Upgrade and Operators",
    "deprecated_api": "CNV Install, Upgrade and Operators",
    "post_test_alerts": "CNV Install, Upgrade and Operators",
    "scale": "SCALE",
}


def _warn_cnv_version_contradiction(full_version: str, xy_version: str, source: str) -> None:
    """Warn when a full and an X.Y CNV version describe different releases.

    Args:
        full_version: Full CNV version (e.g. ``4.22.0``).
        xy_version: X.Y CNV version (e.g. ``4.21``).
        source: Where the values came from, for the warning message.
    """
    _full_version_xy, derived_xy = cnv_versions_from_version_string(version_string=full_version)
    if derived_xy is not None and derived_xy != xy_version:
        message = f"{source} {xy_version} conflicts with cnv_version {full_version} - both are uploaded as given"
        LOGGER.warning(message)
        # The logger may be routed away from the terminal; mirror the
        # established dual-channel pattern so the tester sees it too.
        click.echo(message=f"Warning: {message}", err=True)


def _normalize_tier_value(tier: str) -> str:
    """Normalize a tier label to the bare tier number Jenkins tags.

    Args:
        tier: Tier label in any accepted spelling (``2``, ``TIER-2``,
            ``tier2``, ``tier 2``).

    Returns:
        The bare tier number (e.g. ``2``).

    Raises:
        click.ClickException: When the spelling does not collapse to a bare
            number — a mangled value would fragment the tier facet.
    """
    normalized = tier.strip().lower().removeprefix("tier").strip().lstrip("-_").strip()
    # isascii: str.isdigit accepts non-ASCII digits (e.g. ``٢``) that
    # Jenkins never tags — they would fragment the tier facet.
    if not (normalized.isascii() and normalized.isdigit()):
        raise click.ClickException(f"Unsupported tier spelling: {tier!r} - expected e.g. 2, TIER-2, tier2")
    return normalized


def _prepare_junit_output_path(junit_path: Path) -> None:
    """Validate the JUnit output path and create its parent directory.

    Runs before the tester starts classifying, so an unusable path fails
    fast instead of discarding a finished session.

    Args:
        junit_path: Destination file path from ``--junit-output``.

    Raises:
        click.ClickException: The path is a directory, its parent cannot be
            created, or the destination is not writable.
    """
    if junit_path.is_dir():
        raise click.ClickException(f"--junit-output {junit_path} is a directory; pass a file path.")
    if junit_path.is_symlink():
        raise click.ClickException(
            f"--junit-output {junit_path} is a symlink; pass a regular file path (writing through a "
            "link would overwrite its target)."
        )
    try:
        junit_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise click.ClickException(f"Cannot create the directory for --junit-output {junit_path}: {exc}") from exc
    if junit_path.exists() and not os.access(junit_path, os.W_OK):
        raise click.ClickException(f"--junit-output {junit_path} is not writable.")
    if not os.access(junit_path.parent, os.W_OK):
        raise click.ClickException(f"The directory for --junit-output {junit_path} is not writable.")


def _config_value(
    cli_value: str | None,
    config_key: str,
    config: dict[str, str],
    skip_attribute_keys: frozenset[str] = frozenset(),
) -> str | None:
    """Return a run-attribute value, falling back to its config-file default.

    Args:
        cli_value: Value from the matching CLI flag (``None`` when unset).
        config_key: Config-file key supplying the default.
        config: Validated config-file mapping.
        skip_attribute_keys: Run-attribute keys a higher-precedence source
            already supplies (a replayed run's saved attributes); their
            config default is ignored.

    Returns:
        ``cli_value`` when given, else the config-file default, else None.
    """
    if cli_value is not None:
        return cli_value
    # .get: non-attribute keys (bundle) map to no attribute and are never
    # skipped — the caller decides whether they apply at all.
    if CONFIG_KEY_TO_ATTRIBUTE_KEY.get(config_key) in skip_attribute_keys:
        return None
    return config.get(config_key)


def _build_run_attributes(
    team: str | None = None,
    bundle: str | None = None,
    overrides: dict[str, str | None] | None = None,
    marker: str | None = None,
    test_case_name: str | None = None,
    cluster_attrs: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    """Build run attribute list from CLI args and optional cluster attributes.

    Attribute keys mirror the tag names the Jenkins ``datadog-upload-results``
    pipeline emits for CI runs (``team``, ``tier``, ``cnv_xy_version``,
    ``cnv_version``, ``ocp_version``, ``cluster``, ``cluster_domain``,
    ``cluster_id``, ``storage_class``, ``cnv_channel``, ``owner``,
    ``test_case_name``, ``marker``), so a manual run is tagged exactly like a
    Jenkins run — with ``manual`` as the only intentional difference.

    Cluster-derived attributes serve as defaults; explicit CLI values
    override them.  ``manual`` is always present; ``team`` is present when
    derived from the tests directory, or restored from a replayed run's
    saved attributes.

    Args:
        team: Team name from the Jenkins vocabulary (e.g. ``CNV Network``).
        bundle: Bundle version string (derives ``cnv_version``/``cnv_xy_version``).
        overrides: Explicit attribute values keyed by the attribute key they
            set (``cnv_xy_version``, ``ocp_version``, ``cluster``,
            ``cluster_domain``, ``cluster_id``, ``storage_class``,
            ``cnv_channel``, ``owner``, ``tier``, ``ip_stack``,
            ``iib_image``, ``hco_bundle_version``, and ``rootcoz.url`` — the
            Jenkins tag name, which contains a dot).
        marker: Pytest marker expression used to filter the run.
        test_case_name: Run label (e.g. ``manual.network``).
        cluster_attrs: Attributes auto-populated from ``--from-cluster``.

    Returns:
        Final list of ``{"key": ..., "value": ...}`` dicts.
    """
    # Start from cluster attrs (as a mutable copy) or empty list
    attrs_by_key: dict[str, str] = {}
    if cluster_attrs:
        for attr in cluster_attrs:
            attrs_by_key[attr["key"]] = attr["value"]

    explicit_overrides = dict(overrides or {})
    # Tier is stored normalized below, so it never joins the verbatim merge.
    tier = explicit_overrides.pop("tier", None)
    # Only an explicit (CLI/config) X.Y version blocks the bundle derivation
    # below: a cluster-derived or replayed value is not explicit.
    explicit_cnv_xy_version = explicit_overrides.get("cnv_xy_version")

    # Map explicit CLI overrides to their attribute keys
    overrides_by_key: dict[str, str | None] = {
        **explicit_overrides,
        "marker": marker,
        "test_case_name": test_case_name,
    }

    for key, value in overrides_by_key.items():
        if value is not None:
            attrs_by_key[key] = value

    # Auto-derive CNV versions from the bundle. Explicit --cnv-version always
    # wins (never silently discarded). An explicit --bundle overrides
    # cluster-derived versions; a cluster-derived set only fills gaps.
    if bundle is not None:
        derived_cnv_version, derived_cnv_xy_version = cnv_versions_from_version_string(version_string=bundle)
        if derived_cnv_version is not None:
            attrs_by_key["cnv_version"] = derived_cnv_version
        if explicit_cnv_xy_version is None and derived_cnv_xy_version is not None:
            attrs_by_key["cnv_xy_version"] = derived_cnv_xy_version
    elif explicit_cnv_xy_version is None and "cnv_version" in attrs_by_key and "cnv_xy_version" not in attrs_by_key:
        _derived_full, derived_xy = cnv_versions_from_version_string(version_string=attrs_by_key["cnv_version"])
        if derived_xy is not None:
            attrs_by_key["cnv_xy_version"] = derived_xy

    # Final consistency check: however the pair was assembled (explicit CLI
    # values, cluster derivation, replayed attributes, bundle gap-fill),
    # mutually inconsistent CNV version facets are surfaced instead of
    # silently uploaded.
    if "cnv_version" in attrs_by_key and "cnv_xy_version" in attrs_by_key:
        _warn_cnv_version_contradiction(
            full_version=attrs_by_key["cnv_version"],
            xy_version=attrs_by_key["cnv_xy_version"],
            source="cnv_xy_version",
        )

    # Mandatory attributes
    # Run-type tag (Datadog: manual:true), mirroring the always-emitted
    # MANUAL attribute of the previous ReportPortal manual reporter.
    attrs_by_key["manual"] = "true"

    if team:
        # Preserved verbatim: a replayed run must reproduce its recorded team
        # attribute exactly, and a derived team already carries the Jenkins
        # string as written — re-casing here would make the "Using team from
        # restored attributes" echo disagree with the uploaded tag.
        attrs_by_key["team"] = team

    if tier is not None:
        # Jenkins tags the bare tier number (e.g. ``2``); accept ``2``,
        # ``TIER-2`` and the hyphen-less ``tier2`` spellings.
        attrs_by_key["tier"] = _normalize_tier_value(tier=tier)

    # Synthetic job identity. A manual run has no Jenkins job, but
    # job_name/build_number are mandatory for the Datadog Builds facet.
    # setdefault keeps a replayed run's recorded identity instead of
    # relabelling a resumed run as a new build.
    attrs_by_key.setdefault(
        "job_name",
        f"{_JOB_NAME_PREFIX}-{team.lower()}" if team else _JOB_NAME_PREFIX,
    )
    attrs_by_key.setdefault("build_number", str(int(datetime.now(tz=UTC).timestamp())))

    return [{"key": key, "value": value} for key, value in attrs_by_key.items()]


def _git_query_output(tests_dir: Path, git_args: list[str]) -> str | None:
    """Run a git query in the tests checkout and return its stripped stdout.

    Args:
        tests_dir: The scanned tests directory (a git checkout).
        git_args: Git arguments after the ``-C <tests_dir>`` prefix.

    Returns:
        The stripped stdout, or None when the query failed or printed
        nothing (e.g. the directory is not a git checkout).
    """
    try:
        success, stdout, _ = run_command(
            command=["git", "-C", str(tests_dir), *git_args],
            check=False,
            verify_stderr=False,
            capture_output=True,
            log_errors=False,
        )
    except OSError as exc:
        # A host without git on PATH degrades like a non-git checkout, but
        # the degradation must be visible: without this warning a missing
        # git binary surfaces only as a generic "missing required run
        # attributes" error far from the cause.
        LOGGER.warning(f"git {' '.join(git_args)} could not run in {tests_dir}: {exc}")
        return None
    stripped_output = stdout.strip()
    if not success or not stripped_output:
        LOGGER.warning(f"git {' '.join(git_args)} returned no usable output in {tests_dir}")
        return None
    return stripped_output


def _get_git_user_email(tests_dir: Path) -> str | None:
    """Read the uploader's git e-mail from the scanned tests checkout.

    Jenkins tags every uploaded run with ``owner``; for manual runs the
    uploader is the tester running this tool, so the git identity of the
    scanned checkout is the equivalent.

    Args:
        tests_dir: The scanned tests directory (a git checkout).

    Returns:
        The configured ``user.email``, or None when unavailable.
    """
    return _git_query_output(tests_dir=tests_dir, git_args=["config", "user.email"])


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


def _run_interactive_mode(tests: list[ManualTestDetail]) -> tuple[list[ManualTestResult], bool, bool]:
    """Run interactive test result collection.

    Presents each manual test one-by-one and collects a verdict
    from the tester via the terminal.

    Args:
        tests: List of manual tests to present.

    Returns:
        Tuple of (results list, quit_early flag, interrupted flag). The skip
        count is derived from the results by the caller, so the two paths
        cannot disagree. Results contain PASSED/FAILED/SKIPPED entries collected before
        a quit or interruption; quit_early is True when the session ended
        before the last test; interrupted is True when that end was caused
        by Ctrl-C / Ctrl-D rather than an explicit 'q'.
    """
    results: list[ManualTestResult] = []
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
                            text=f"Choose (1-{len(_DEFECT_TYPES)}, default={_DEFAULT_DEFECT_CHOICE})",
                            type=str,
                            default=_DEFAULT_DEFECT_CHOICE,
                            show_default=False,
                        ).strip()
                        if defect_choice in _DEFECT_TYPES:
                            break
                        click.echo(message=f"Invalid choice '{defect_choice}'. Use 1-{len(_DEFECT_TYPES)}.")
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
                    break
                elif choice == "q":
                    click.echo(message="Quitting — returning results collected so far.")
                    return results, True, False
                else:
                    click.echo(message="Invalid choice. Use p/f/s/q.")
    except click.Abort, KeyboardInterrupt:
        # Ctrl-C / Ctrl-D: keep the verdicts collected so far and route
        # into the same partial-results save path as an explicit 'q'.
        return results, True, True

    return results, False, False


# Legacy retry files (saved before the Jenkins-parity tag rename) carry the
# old upper-case attribute keys. Migrate them on load so a legacy retry
# replays cleanly through validation and the team-restoration lookup.
# A legacy BUNDLE entry converts to the cnv_version/cnv_xy_version it would
# derive on a fresh run (a replay suppresses the metadata bundle, so nothing
# else could produce them). Keys with no modern equivalent (ARCH) and
# unknown keys stay verbatim — a replay reproduces the recorded run.
# Modern attribute keys in their canonical form. A hand-edited key in
# non-canonical case (``CNV_VERSION``) converges to the canonical form so
# the duplicate check and the bundle gap-fill see the same key the CLI
# writes; unknown keys stay verbatim.
_MODERN_KEY_BY_LOWER = {
    modern_key.lower(): modern_key
    for modern_key in (
        "team",
        "tier",
        "cnv_version",
        "cnv_xy_version",
        "ocp_version",
        "cluster",
        "cluster_domain",
        "cluster_id",
        "storage_class",
        "cnv_channel",
        "owner",
        "marker",
        "test_case_name",
        "ip_stack",
        "iib_image",
        "hco_bundle_version",
        "rootcoz.url",
        "cni",
        "job_name",
        "build_number",
        "manual",
    )
}

# Legacy keys whose lower-case form is already a modern key (TEAM, TIER,
# CLUSTER_DOMAIN) converge via _MODERN_KEY_BY_LOWER in the migration
# lookup — only keys with no modern lower-case twin need an explicit entry.
_LEGACY_ATTRIBUTE_KEY_MAP = {
    "CNV_XY_VER": "cnv_xy_version",
    "OCP": "ocp_version",
    "CLUSTER_NAME": "cluster",
    "SC": "storage_class",
    "CHANNEL": "cnv_channel",
}


def _migrate_legacy_attributes(attributes: list[dict[str, str]]) -> list[dict[str, str]]:
    """Migrate legacy attribute entries to the Jenkins-parity key names.

    Args:
        attributes: Normalized attribute entries from a batch file.

    Returns:
        The attribute list with legacy keys renamed, a legacy BUNDLE entry
        converted to its derived cnv_version/cnv_xy_version entries, and
        entries without a modern equivalent left verbatim.
    """
    migrated = [
        {
            "key": _MODERN_KEY_BY_LOWER.get(
                attr["key"].lower(),
                _LEGACY_ATTRIBUTE_KEY_MAP.get(attr["key"].upper(), attr["key"]),
            ),
            "value": attr["value"],
        }
        for attr in attributes
    ]
    # A legacy TIER entry carries the old upper-cased value (``TIER-2``);
    # normalize it so a legacy replay uploads the same bare-number tag a
    # fresh run does. A recorded value that does not collapse to a number is
    # kept with a warning — a replay reproduces the recorded run instead of
    # hard-failing on data the user cannot re-create (live CLI/config input
    # still fails fast).
    for attr in migrated:
        if attr["key"] == "tier":
            try:
                attr["value"] = _normalize_tier_value(tier=attr["value"])
            except click.ClickException:
                # Purpose-built message: the fail-fast remediation text does
                # not apply here (the recorded value is uploaded as-is).
                message = (
                    f"Recorded tier value {attr['value']!r} is not a bare number - kept verbatim "
                    "for the replay (live --tier input would be rejected)"
                )
                LOGGER.warning(message)
                click.echo(message=f"Warning: {message}", err=True)
    bundle_entry = next((attr for attr in migrated if attr["key"].upper() == "BUNDLE"), None)
    if bundle_entry is not None:
        migrated = [attr for attr in migrated if attr["key"].upper() != "BUNDLE"]
        cnv_version, cnv_xy_version = cnv_versions_from_version_string(version_string=bundle_entry["value"])
        migrated_keys = {attr["key"] for attr in migrated}
        if cnv_version is not None and "cnv_version" not in migrated_keys:
            migrated.append({"key": "cnv_version", "value": cnv_version})
        if cnv_xy_version is not None and "cnv_xy_version" not in migrated_keys:
            migrated.append({"key": "cnv_xy_version", "value": cnv_xy_version})
        # A derived-versus-recorded contradiction (legacy BUNDLE vs the
        # neighboring CNV_XY_VER, or vice versa) is surfaced by the final
        # consistency check in _build_run_attributes once both keys exist.
    return migrated


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
        file. A ``team`` metadata key is ignored — the team is derived from
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
        raw_issue_type = entry.get("issue_type_label")
        if raw_issue_type is not None and raw_issue_type not in CLASSIFICATION_BY_DEFECT_LABEL:
            # A typo'd label would ship verbatim on <failure type> while the
            # tfa.classification tag silently became "unknown", mislabelling a
            # failure the tester did classify.
            raise click.ClickException(
                f"Invalid issue_type_label {raw_issue_type!r} for test '{raw_test}' in batch file {batch_path}; "
                f"expected one of: {', '.join(CLASSIFICATION_BY_DEFECT_LABEL)}"
            )
        results.append(
            ManualTestResult(
                test=raw_test,
                status=status,
                # YAML `comment:` with no value yields None — coerce to empty string;
                # strip so hand-edited padding cannot reach the report verbatim.
                comment=(entry.get("comment") or "").strip(),
                issue_type_label=raw_issue_type,
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
                "the team is derived from the tests directory (a replayed retry uses its saved team "
                "attribute; add a team entry to metadata.attributes to restore one)"
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
                # The checks above guarantee both are strings; cast-free
                # narrowing that survives ``python -O`` (an assert would not).
                attr_key = str(attr_key)
                attr_value = str(attr_value)
                # Strip so hand-edited padding cannot reach the Datadog tags;
                # the legacy migration then renames old keys to their modern
                # equivalents (see _migrate_legacy_attributes).
                normalized_attrs.append({"key": attr_key.strip(), "value": attr_value.strip()})
            migrated_attrs = _migrate_legacy_attributes(attributes=normalized_attrs)
            # Duplicate detection runs on the FINAL keys: a legacy file can
            # carry TEAM alongside a hand-added team, colliding only after
            # the migration renames them. The lowercased form collides too —
            # build_junit_xml lowercases attribute keys into dd_tags[...], so
            # CustomKey + customkey would land two values under one tag name.
            final_keys = [attr["key"] for attr in migrated_attrs]
            duplicated_keys = {key for key in final_keys if final_keys.count(key) > 1}
            if not duplicated_keys:
                lowered_keys = [key.lower() for key in final_keys]
                duplicated_keys = {
                    original for original, lowered in zip(final_keys, lowered_keys) if lowered_keys.count(lowered) > 1
                }
            if duplicated_keys:
                raise click.ClickException(
                    f"Duplicate attribute key in batch metadata: {', '.join(sorted(duplicated_keys))}"
                )
            metadata["attributes"] = migrated_attrs

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
    attributes were resolved. The team is never taken from metadata — it is
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
    # The restored list itself is the "was restored" signal, so the
    # narrowing survives ``python -O`` (an assert for it would not).
    restored_attrs: list[dict[str, str]] | None = None
    if isinstance(saved_attrs, list) and saved_attrs and not cluster_attrs:
        # Copy on restore: later mutations must not affect the parsed
        # batch-file metadata.
        cluster_attrs = [dict(attr) for attr in saved_attrs]
        restored_attrs = cluster_attrs
        click.echo(message=f"Restored {len(saved_attrs)} attributes from batch file.")
    elif isinstance(saved_attrs, list) and saved_attrs:
        click.echo(
            message=f"Note: {len(saved_attrs)} saved attributes from the batch file are ignored — "
            "cluster-derived attributes take precedence."
        )
    batch_bundle = batch_metadata.get("bundle")
    if batch_bundle and not bundle:
        if restored_attrs is not None:
            # A real retry file carries its recorded cnv versions, so the
            # metadata bundle is not re-applied (the recorded run stands).
            # Gap-fill only: a hand-written batch with a partial saved list
            # derives any CNV version it lacks from the bundle instead of
            # failing validation — recorded values are never overridden.
            saved_keys = {attr["key"] for attr in restored_attrs}
            if "cnv_version" not in saved_keys or "cnv_xy_version" not in saved_keys:
                derived_cnv_version, derived_cnv_xy_version = cnv_versions_from_version_string(
                    version_string=batch_bundle
                )
                gap_filled_keys = []
                if "cnv_version" not in saved_keys and derived_cnv_version is not None:
                    restored_attrs.append({"key": "cnv_version", "value": derived_cnv_version})
                    gap_filled_keys.append("cnv_version")
                if "cnv_xy_version" not in saved_keys and derived_cnv_xy_version is not None:
                    restored_attrs.append({"key": "cnv_xy_version", "value": derived_cnv_xy_version})
                    gap_filled_keys.append("cnv_xy_version")
                if gap_filled_keys:
                    click.echo(message=f"Derived {', '.join(gap_filled_keys)} from batch file bundle: {batch_bundle}")
        else:
            bundle = batch_bundle
            click.echo(message=f"Using bundle from batch file: {bundle}")
    return bundle, cluster_attrs, restored_attrs is not None


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
        attributes: Run attributes to preserve for retry. The team
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
    epilog="Collects manual test results for @pytest.mark.manual tests and writes them to a "
    "JUnit XML report whose dd_tags[...] properties carry the Jenkins tag set; "
    "upload it later with `datadog-ci junit upload`.",
)
@click.option(
    "--bundle",
    type=str,
    default=None,
    help="Bundle version prefix (e.g., v4.22.0.rhel9-102); derives the CNV version tags",
)
@click.option("--tier", type=str, default=None, help="Tier number (e.g., 2 or tier-2)")
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
@click.option(
    "--cluster-id",
    type=str,
    default=None,
    help="Cluster ID (CLUSTER_NAME-HASH, e.g. infd-vrf-412t0-n47k6); with --from-cluster it is "
    "derived from the cluster's node names",
)
@click.option(
    "--owner",
    type=str,
    default=None,
    help="Uploader e-mail for the owner tag; defaults to the git user.email of the tests checkout",
)
@click.option("--sc", "storage_class", type=str, default=None, help="Override storage class label")
@click.option("--channel", type=str, default=None, help="Override channel")
@click.option(
    "--junit-output",
    "junit_output",
    type=click.Path(path_type=Path),
    default=None,
    help=f"Path for the generated JUnit XML report (default: ./{_JUNIT_FILE_NAME})",
)
@click.option("--ip-stack", type=str, default=None, help="Override the ip_stack tag (e.g. ipv4, ipv6, ipv4-ipv6)")
@click.option("--iib-image", type=str, default=None, help="Override the iib_image tag (CI index image)")
@click.option(
    "--hco-bundle-version",
    "hco_bundle_version",
    type=str,
    default=None,
    help="Override the hco_bundle_version tag (HCO bundle, distinct from cnv_version)",
)
@click.option(
    "--rootcoz-url",
    "rootcoz_url",
    type=str,
    default=None,
    help="Override the rootcoz.url tag (analysis report for this run)",
)
@click.option(
    "--batch-file",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Batch YAML file with pre-filled results",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Show the resolved run attributes and report path without writing the report",
)
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
    cluster_id: str | None,
    owner: str | None,
    storage_class: str | None,
    channel: str | None,
    junit_output: Path | None,
    ip_stack: str | None,
    iib_image: str | None,
    hco_bundle_version: str | None,
    rootcoz_url: str | None,
    batch_file: Path | None,
    dry_run: bool,
    config_file: Path | None,
) -> None:
    """Collect manual test results and write them as a JUnit XML report.

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

    effective_junit_path = junit_output if junit_output is not None else Path.cwd() / _JUNIT_FILE_NAME
    # Validate the output path BEFORE the tester classifies tests: a bad path
    # discovered at write time would discard a whole interactive session into
    # a retry file.
    _prepare_junit_output_path(junit_path=effective_junit_path)

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
    # sources — and never runs for a replayed retry, whose saved team stands.

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
        collected_count = len(results)
        bundle, cluster_attrs, replaying_saved_run = _merge_batch_metadata(
            batch_metadata=batch_metadata,
            bundle=bundle,
            cluster_attrs=cluster_attrs,
        )
        if replaying_saved_run and cluster_attrs:
            # A replay reproduces the recorded run: keep its team, if any.
            # owner is the one exception — it always reflects the user
            # pushing THIS run, so a saved owner never survives a replay.
            team = next((attr["value"] for attr in cluster_attrs if attr["key"] == "team"), None)
            if team:
                click.echo(message=f"Using team from restored attributes: {team}")
            saved_owner = next((attr["value"] for attr in cluster_attrs if attr["key"] == "owner"), None)
            if saved_owner:
                cluster_attrs = [attr for attr in cluster_attrs if attr["key"] != "owner"]
                click.echo(message=f"Dropping saved owner {saved_owner} - the current uploader is tagged instead.")
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
    # team), so a partial saved list does not disable the whole config.
    # The config bundle is never applied on a replay: deriving versions
    # from it would discard the saved, recorded values.
    saved_attr_keys: frozenset[str] = frozenset()
    if replaying_saved_run:
        if cluster_attrs is None:
            # _merge_batch_metadata only reports a replay after restoring a
            # list; an explicit raise keeps that invariant under ``python -O``.
            raise click.ClickException("Internal error: a replayed run restored no attributes.")
        saved_attr_keys = frozenset(attr["key"] for attr in cluster_attrs)
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
    else:
        # The bundle is a derivation input, not an attribute: it applies on a
        # fresh run only, never on a replay (deriving versions from it would
        # discard the saved, recorded values).
        bundle = _config_value(cli_value=bundle, config_key="bundle", config=config)

    # CLI flag values keyed by the run attribute each one sets, so the config
    # defaults apply in ONE pass over CONFIG_KEY_TO_ATTRIBUTE_KEY instead of
    # one wiring statement per key (and a new key needs no edit here beyond
    # its CLI flag).
    cli_attribute_values: dict[str, str | None] = {
        "tier": tier,
        "cnv_xy_version": cnv_version,
        "ocp_version": ocp_version,
        "cluster": cluster_name,
        "cluster_domain": cluster_domain,
        "cluster_id": cluster_id,
        "storage_class": storage_class,
        "cnv_channel": channel,
        "owner": owner,
        "ip_stack": ip_stack,
        "iib_image": iib_image,
        "hco_bundle_version": hco_bundle_version,
        "rootcoz.url": rootcoz_url,
    }
    attribute_values: dict[str, str | None] = {
        attribute_key: _config_value(
            cli_value=cli_attribute_values[attribute_key],
            config_key=config_key,
            config=config,
            skip_attribute_keys=saved_attr_keys,
        )
        for config_key, attribute_key in CONFIG_KEY_TO_ATTRIBUTE_KEY.items()
    }

    # Kept as a local: steps 3 and 4 compare the explicit X.Y version against
    # cluster-derived values and name --cnv-version in the remedies.
    cnv_version = attribute_values["cnv_xy_version"]

    # Owner always reflects the user pushing THIS run: CLI/config override,
    # else the git identity of the scanned checkout.
    if attribute_values["owner"] is None:
        owner_from_git = _get_git_user_email(tests_dir=tests_dir)
        if owner_from_git:
            attribute_values["owner"] = owner_from_git
            click.echo(message=f"Derived owner from git: {owner_from_git}")

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
            LOGGER.warning(f"Tests directory {tests_dir} maps to no team - team attribute will be omitted")
            click.echo(
                message=f"Warning: {tests_dir} maps to no team - the run will not be team-filterable.",
                err=True,
            )

    # ── 3. Build run attributes ──
    # test_case_name labels the run the way Jenkins jobs do (tier + job
    # name); the manual analog is the scanned tests directory. A replay
    # restores the recorded value from its saved attributes — likewise the
    # marker tag: the CLI -m is only a live collection filter there, and the
    # recorded marker stands so the replay cannot retag the run.
    test_case_name = None if replaying_saved_run else f"manual.{tests_dir.resolve().name}"
    marker_tag = None if replaying_saved_run else marker
    attributes = _build_run_attributes(
        team=team,
        bundle=bundle,
        overrides=attribute_values,
        marker=marker_tag,
        test_case_name=test_case_name,
        cluster_attrs=cluster_attrs,
    )

    # An explicit --cnv-version overrides cluster-derived values outright (the
    # CLI-over-cluster precedence rule): when it disagrees with the
    # cluster-derived full cnv_version, the derived value is dropped so the
    # pair never ships contradictory facets — validation then asks for
    # --bundle if the full version is required. A replay keeps its recorded
    # values (the recorded run stands), and an explicit --bundle pair is
    # surfaced by the warning in _build_run_attributes instead.
    if cnv_version is not None and not replaying_saved_run and bundle is None:
        recorded_cnv_version = next((attr["value"] for attr in attributes if attr["key"] == "cnv_version"), None)
        if recorded_cnv_version is not None:
            _derived_full, derived_xy = cnv_versions_from_version_string(version_string=recorded_cnv_version)
            if derived_xy is not None and derived_xy != cnv_version:
                attributes = [attr for attr in attributes if attr["key"] != "cnv_version"]
                click.echo(
                    message=f"Dropping cluster-derived cnv_version {recorded_cnv_version} - "
                    f"it contradicts the explicit --cnv-version {cnv_version}"
                )

    # ── 4. Validate report completeness ──
    # Jenkins-parity tag set: every tag a Jenkins upload always carries.
    required_attr_keys = {
        "cnv_version": "--bundle",
        "cnv_xy_version": "--cnv-version",
        "ocp_version": "--ocp-version",
        "cluster": "--cluster-name",
        "cluster_domain": "--cluster-domain",
        "storage_class": "--sc",
        "cnv_channel": "--channel",
        "owner": "--owner (or git user.email in the tests checkout)",
    }
    present_keys = {attr["key"] for attr in attributes}
    missing = {key: flag for key, flag in required_attr_keys.items() if key not in present_keys}
    # Extra guidance appended to both the hard error and the dry-run
    # warning when the generic remedy line would mislead.
    extra_guidance = ""
    if from_cluster and not cluster_attr_count:
        # --from-cluster resolved nothing, so the remedy line would mislead
        # a user who already passed the flag: point at cluster access
        # instead. Restored retry-file attributes do NOT suppress this —
        # the count reflects only what the cluster itself resolved.
        extra_guidance = (
            "\n--from-cluster resolved no cluster attributes; check cluster access and permissions (KUBECONFIG)."
        )
    if ("cnv_version" in missing or "cnv_xy_version" in missing) and cnv_version is None and bundle:
        # A bundle was supplied (CLI, config, or batch metadata — the
        # derivation inputs) but its versions were underivable — name the
        # culprit instead of a bare missing-attribute error.
        extra_guidance += f"\nThe bundle '{bundle}' has no major.minor version; pass --cnv-version explicitly."
    if not dry_run:
        if missing:
            missing_names = ", ".join(sorted(missing.keys()))
            missing_flags = ", ".join(sorted(missing.values()))
            # The remedy list differs on a replay: recorded attributes
            # stand, config-file defaults fill only attribute-key gaps the
            # saved list leaves, and the config bundle (a derivation input)
            # is not applied — only a batch-file metadata bundle fills
            # missing CNV versions.
            replay_note = (
                "Provide them via CLI flags ({flags}) or --from-cluster."
                if not replaying_saved_run
                else "Provide them via CLI flags ({flags}) or by adding the missing "
                "key to the config file — a replay keeps its recorded attributes; "
                "config defaults fill only keys the saved list lacks, and the "
                "config bundle is not applied (only a batch-file metadata bundle "
                "fills missing CNV versions)."
            )
            raise click.ClickException(
                f"Missing required run attributes: {missing_names}\n"
                + replay_note.format(flags=missing_flags)
                + extra_guidance
            )
    elif missing:
        # Dry-run should predict upload readiness, not skip validation.
        missing_names = ", ".join(sorted(missing.keys()))
        click.echo(
            message=f"WARNING: the report would be incomplete — missing: {missing_names}{extra_guidance}",
            err=True,
        )

    quit_early = False
    interrupted = False
    if not batch_file:
        results, quit_early, interrupted = _run_interactive_mode(tests=collected_tests)
    skipped_count = sum(1 for result in results if result.status == "SKIPPED")

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
            label = result.issue_type_label or UNCLASSIFIED_LABEL
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
        click.echo(message=f"\nJUnit report: {effective_junit_path}")
        click.echo(message="No report was written (dry run).")
        sys.exit(0)

    # ── 7. Quit early: keep partial results, upload nothing ──
    team_label = team.upper() if team else "ALL"
    if quit_early:
        # The saved team attribute (when present) keeps the team for the
        # retry; a team-less session saves no team and stays team-less.
        saved_path = _save_results_for_retry(
            results=results,
            bundle=bundle,
            attributes=attributes,
        )
        if saved_path is not None:
            if interrupted:
                click.echo(
                    message=f"Session interrupted — partial results saved to {saved_path}; no report was written."
                )
            else:
                click.echo(message=f"Partial results saved to {saved_path}; no report was written.")
            click.echo(message=f"  Resume with: --batch-file {saved_path}")
        else:
            click.echo(message="Failed to save partial results; no report was written.", err=True)
        sys.exit(0)

    # ── 8. Build and write the JUnit report ──
    # Suite name and file name mirror the Jenkins uploads exactly so the
    # same test node ID resolves to the same Datadog test (@test.full_name,
    # @test.module) instead of creating a parallel "Manual - X" universe.
    suite_name = _DEFAULT_SUITE_NAME

    polarion_lookup: dict[str, str] = {}
    for test in collected_tests:
        if test.polarion_id:
            polarion_lookup[test.node_id] = test.polarion_id

    xml_path = effective_junit_path
    try:
        xml_content = build_junit_xml(
            results=results,
            suite_name=suite_name,
            attributes=attributes,
            polarion_lookup=polarion_lookup,
            description=f"Manual test results for {team_label}",
        )
        write_junit_report(xml_path=xml_path, xml_content=xml_content)
        click.echo(message=f"\n✓ Wrote {len(results)} results to {xml_path}")
        click.echo(message="  Upload it with: datadog-ci junit upload --service cnv-qe-tests <file>")

    except (OSError, ValueError) as exc:
        # ValueError covers UnicodeEncodeError from a value that survived
        # sanitisation with an unencodable code point.
        LOGGER.error(f"Failed to write the JUnit report to {xml_path}: {exc}")
        saved_path = _save_results_for_retry(
            results=results,
            bundle=bundle,
            attributes=attributes,
        )
        click.echo(message=f"\n✗ Report generation failed: {exc}", err=True)
        if saved_path is not None:
            click.echo(message=f"  Results saved to: {saved_path}", err=True)
            click.echo(message=f"  Retry with: --batch-file {saved_path}", err=True)
        else:
            click.echo(message="  Failed to save results for retry — see log output.", err=True)
        sys.exit(1)

    except KeyboardInterrupt:
        # Ctrl-C while writing the report (after the verdicts, outside the
        # interactive loop): keep the verdicts via the same retry-save path
        # the failure handler uses, instead of exiting with a traceback.
        saved_path = _save_results_for_retry(
            results=results,
            bundle=bundle,
            attributes=attributes,
        )
        if saved_path is not None:
            click.echo(
                message=f"Session interrupted while writing the report — partial results saved to {saved_path}.",
                err=True,
            )
        else:
            click.echo(
                message="Session interrupted while writing the report — failed to save partial results.",
                err=True,
            )
        if xml_path.exists():
            click.echo(message=f"  JUnit report kept at: {xml_path}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

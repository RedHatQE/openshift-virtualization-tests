# Co-authored-by: Claude <noreply@anthropic.com>
"""Manual Test Reporter for ReportPortal.

Interactive CLI that collects __test__ = False placeholder tests,
shows full test context (docstrings, markers, preconditions) one-by-one,
lets the tester mark each as pass/fail/skip, and pushes results to
ReportPortal as a new launch.

Supports batch mode via YAML file for non-interactive use and failure retry.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import click
import requests
import yaml
from simple_logger.logger import get_logger

from scripts.reportportal.rp_manual_reporter.cluster_info import (
    cluster_attributes_to_launch_attrs,
    get_cluster_attributes,
)
from scripts.reportportal.rp_manual_reporter.collector import (
    PlaceholderTestDetail,
    collect_placeholder_details,
)
from scripts.reportportal.rp_utils.naming import node_id_to_rp_name
from scripts.reportportal.rp_utils.rp_client import RPClient

LOGGER = get_logger(name=__name__)


TERMINAL_WIDTH = 80

_VALID_STATUSES = {"PASSED", "FAILED", "SKIPPED"}


class PartialPushError(Exception):
    """Raised when a push to ReportPortal fails after some items were already pushed.

    Attributes:
        pushed_count: Number of items successfully pushed before the failure.
        launch_uuid: UUID of the partially-filled launch.
    """

    def __init__(self, message: str, pushed_count: int, launch_uuid: str) -> None:
        super().__init__(message)
        self.pushed_count = pushed_count
        self.launch_uuid = launch_uuid


_DEFECT_TYPES: dict[str, tuple[str, str]] = {
    "1": ("pb001", "Product Bug"),
    "2": ("ab001", "Automation Bug"),
    "3": ("si001", "System Issue"),
    "4": ("ti001", "To Investigate"),
    "5": ("nd001", "No Defect"),
}


def _build_launch_attributes(
    team: str | None = None,
    bundle: str | None = None,
    cnv_version: str | None = None,
    arch: str | None = None,
    ocp_version: str | None = None,
    cluster_name: str | None = None,
    cluster_domain: str | None = None,
    storage_class: str | None = None,
    channel: str | None = None,
    tier: str | None = None,
    cluster_attrs: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    """Build launch attribute list from CLI args and optional cluster attributes.

    Cluster-derived attributes serve as defaults; explicit CLI values
    override them.  ``TEAM`` and ``MANUAL`` are always present.

    Args:
        team: Team name (e.g. ``NETWORK``).
        bundle: Bundle version string.
        cnv_version: CNV X.Y version override.
        arch: Architecture override.
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

    # Map explicit CLI overrides to their RP attribute keys
    overrides: dict[str, str | None] = {
        "BUNDLE": bundle,
        "CNV_XY_VER": cnv_version,
        "ARCH": arch,
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
    # When bundle is explicitly provided (CLI arg), always override cluster-derived CNV_XY_VER
    # When bundle comes from cluster only, derive if CNV_XY_VER is missing
    if "BUNDLE" in attrs_by_key and (bundle is not None or "CNV_XY_VER" not in attrs_by_key):
        bundle_val = attrs_by_key["BUNDLE"].lstrip("v")
        parts = bundle_val.split(".")
        if len(parts) >= 2:
            attrs_by_key["CNV_XY_VER"] = f"{parts[0]}.{parts[1]}"

    # Mandatory attributes
    if team:
        attrs_by_key["TEAM"] = team.upper()
    attrs_by_key["MANUAL"] = "true"

    if tier is not None:
        attrs_by_key["TIER"] = tier.upper()

    return [{"key": key, "value": value} for key, value in attrs_by_key.items()]


def _display_test_detail(test: PlaceholderTestDetail, index: int, total: int) -> None:
    """Display a single test's full context to stdout.

    Renders the test header, markers, fixtures, docstrings, and
    separator lines using a fixed-width terminal format.

    Args:
        test: Placeholder test detail to display.
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


def _run_interactive_mode(tests: list[PlaceholderTestDetail]) -> tuple[list[dict[str, Any]], int]:
    """Run interactive test result collection.

    Presents each placeholder test one-by-one and collects a verdict
    from the tester via the terminal.

    Args:
        tests: List of placeholder tests to present.

    Returns:
        Tuple of (results list, skipped count). Results contain only
        PASSED/FAILED entries; skipped tests are counted but not recorded.
    """
    results: list[dict[str, Any]] = []
    skipped_count = 0
    total = len(tests)

    for index, test in enumerate(tests, start=1):
        _display_test_detail(test=test, index=index, total=total)

        while True:
            choice = (
                click
                .prompt(
                    "Result (p=pass, f=fail, s=skip, q=quit)",
                    type=str,
                )
                .strip()
                .lower()
            )

            if choice == "p":
                results.append({"test": test.node_id, "status": "PASSED", "comment": ""})
                break
            elif choice == "f":
                while True:
                    click.echo(message="Defect type:")
                    for key, (_, label) in _DEFECT_TYPES.items():
                        click.echo(message=f"  {key}. {label}")
                    defect_choice = click.prompt(
                        "Choose (1-5, default=4)",
                        type=str,
                        default="4",
                        show_default=False,
                    ).strip()
                    if defect_choice in _DEFECT_TYPES:
                        break
                    click.echo(message=f"Invalid choice '{defect_choice}'. Use 1-5.")
                issue_type, issue_type_label = _DEFECT_TYPES[defect_choice]
                comment = click.prompt("Comment (optional)", default="", show_default=False)
                results.append({
                    "test": test.node_id,
                    "status": "FAILED",
                    "comment": comment,
                    "issue_type": issue_type,
                    "issue_type_label": issue_type_label,
                })
                break
            elif choice == "s":
                skipped_count += 1
                break
            elif choice == "q":
                click.echo(message="Quitting — returning results collected so far.")
                return results, skipped_count
            else:
                click.echo(message="Invalid choice. Use p/f/s/q.")

    return results, skipped_count


def _load_batch_file(batch_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Load test results and metadata from a batch YAML file.

    Expected format::

        metadata:
            team: NETWORK
            bundle: v4.22.0
        results:
          - test: "tests/foo/test_bar.py::TestClass::test_method"
            status: passed
            comment: "optional"

    Args:
        batch_path: Path to the YAML file.

    Returns:
        Tuple of (results list, metadata dict). Metadata may contain
        ``team``, ``bundle``, and ``attributes`` from a previous
        session's saved file.

    Raises:
        click.ClickException: If the file format is invalid or a status
            value is unrecognised.
    """
    try:
        raw = yaml.safe_load(batch_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise click.ClickException(f"Failed to read batch file {batch_path}: {exc}") from exc

    if not isinstance(raw, dict) or "results" not in raw:
        raise click.ClickException(f"Batch file {batch_path} must contain a top-level 'results' key")

    raw_results = raw["results"]
    if not isinstance(raw_results, list):
        raise click.ClickException(
            f"Batch file {batch_path}: 'results' must be a list, got {type(raw_results).__name__}"
        )

    results: list[dict[str, Any]] = []
    for entry in raw_results:
        if not isinstance(entry, dict):
            raise click.ClickException(f"Batch result entry must be a dict, got: {type(entry).__name__}")
        if "test" not in entry:
            raise click.ClickException(f"Batch entry missing required 'test' key: {entry}")
        raw_status = entry.get("status", "")
        if not isinstance(raw_status, str):
            raise click.ClickException(
                f"Invalid status type for test '{entry.get('test')}': expected string, got {type(raw_status).__name__}"
            )
        status = raw_status.upper()
        if status not in _VALID_STATUSES:
            raise click.ClickException(
                f"Invalid status '{entry.get('status')}' for test '{entry.get('test')}'. "
                f"Must be one of: {', '.join(sorted(_VALID_STATUSES))}"
            )
        result_entry: dict[str, Any] = {
            "test": entry["test"],
            "status": status,
            "comment": entry.get("comment", ""),
        }
        if entry.get("issue_type"):
            result_entry["issue_type"] = entry["issue_type"]
            result_entry["issue_type_label"] = entry.get("issue_type_label", "")
        results.append(result_entry)

    metadata: dict[str, Any] = {}  # values can be str or list[dict]
    raw_metadata = raw.get("metadata", {})
    if isinstance(raw_metadata, dict):
        for key in ("team", "bundle"):
            if raw_metadata.get(key):
                metadata[key] = str(raw_metadata[key])
        saved_attrs = raw_metadata.get("attributes")
        if isinstance(saved_attrs, list):
            metadata["attributes"] = saved_attrs

    LOGGER.info(f"Loaded {len(results)} results from batch file {batch_path}")
    return results, metadata


def _save_results_for_retry(
    results: list[dict[str, Any]],
    team: str,
    bundle: str | None,
    attributes: list[dict[str, str]] | None = None,
) -> Path:
    """Save test results to a YAML file for later retry.

    The file is written to the current directory with a timestamped
    name so that multiple retry files can coexist.

    Args:
        results: List of result dicts to save.
        team: Team name.
        bundle: Bundle version.
        attributes: Launch attributes to preserve for retry.

    Returns:
        Path to the saved YAML file.
    """
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%d_%H%M%S")
    filename = f"manual_results_{timestamp}.yaml"
    output_path = Path.cwd() / filename

    payload: dict[str, Any] = {
        "metadata": {
            "team": team,
            "bundle": bundle,
            "attributes": attributes or [],
            "saved_at": datetime.now(tz=UTC).isoformat(),
        },
        "results": results,
    }

    yaml_content = yaml.dump(data=payload, default_flow_style=False, sort_keys=False)
    output_path.write_text(data=yaml_content, encoding="utf-8")
    LOGGER.info(f"Saved {len(results)} results to {output_path}")
    return output_path


def _push_results_to_rp(
    rp_client: RPClient,
    results: list[dict[str, Any]],
    launch_name: str,
    attributes: list[dict[str, str]],
    tests: list[PlaceholderTestDetail] | None = None,
    description: str = "",
) -> str:
    """Push test results to ReportPortal.

    Creates a launch, populates it with test items (one per result),
    and finishes the launch.

    Args:
        rp_client: Authenticated RPClient instance.
        results: List of result dicts with test, status, comment.
        launch_name: Name for the RP launch.
        attributes: Launch attributes.
        tests: Optional list of placeholder test details for Polarion ID
            lookup. When provided, matching tests get a
            ``polarion-testcase-id`` attribute on their RP item.
        description: Launch description.

    Returns:
        The launch UUID.
    """
    # Build a node_id → polarion_id lookup from collected tests
    polarion_lookup: dict[str, str] = {}
    if tests:
        for test in tests:
            if test.polarion_id:
                polarion_lookup[test.node_id] = test.polarion_id

    launch_uuid = rp_client.create_launch(name=launch_name, attributes=attributes, description=description)

    pushed_count = 0
    try:
        for result in results:
            item_name = node_id_to_rp_name(node_id=result["test"])
            item_attrs: list[dict[str, str]] | None = None

            polarion_id = polarion_lookup.get(result["test"])
            if polarion_id:
                item_attrs = [{"key": "polarion-testcase-id", "value": polarion_id}]

            item_uuid = rp_client.start_test_item(
                launch_uuid=launch_uuid,
                name=item_name,
                description=result.get("comment", ""),
                attributes=item_attrs,
            )
            issue: dict[str, str] | None = None
            if result.get("issue_type"):
                issue = {"issueType": result["issue_type"], "comment": result.get("comment", "")}
            rp_client.finish_test_item(item_uuid=item_uuid, status=result["status"], issue=issue)
            pushed_count += 1
    except requests.RequestException as exc:
        raise PartialPushError(
            f"Failed after pushing {pushed_count}/{len(results)} items: {exc}",
            pushed_count=pushed_count,
            launch_uuid=launch_uuid,
        ) from exc

    try:
        rp_client.finish_launch(launch_uuid=launch_uuid)
    except requests.RequestException as exc:
        raise PartialPushError(
            f"All {len(results)} items pushed but finish_launch failed: {exc}",
            pushed_count=len(results),
            launch_uuid=launch_uuid,
        ) from exc
    LOGGER.info(f"Pushed {len(results)} results to launch {launch_uuid}")
    return launch_uuid


@click.command(
    help="Manual Test Reporter for ReportPortal",
    epilog="Collects manual test results for __test__ = False STD placeholder tests and pushes to ReportPortal.",
)
@click.option("--bundle", type=str, default=None, help="Bundle version prefix (e.g., v4.22.0.rhel9-102)")
@click.option(
    "--team",
    type=str,
    default=None,
    help="Team name (e.g., NETWORK, STORAGE, VIRT). Auto-inferred from --tests-dir if not set.",
)
@click.option("--tier", type=str, default=None, help="Tier label (e.g., TIER-2)")
@click.option(
    "--tests-dir",
    type=click.Path(exists=True, path_type=Path),
    default=Path("tests"),
    help="Tests directory to scan (e.g., tests/network/)",
)
@click.option(
    "-m", "--marker", type=str, default=None, help="Pytest marker expression (e.g., 'gating', 'smoke and not tier3')"
)
@click.option(
    "-k", "--keyword", type=str, default=None, help="Keyword filter on test node IDs (e.g., 'test_connectivity')"
)
@click.option("--from-cluster", is_flag=True, default=False, help="Auto-fill attributes from connected cluster")
@click.option("--arch", type=str, default=None, help="Override architecture")
@click.option("--ocp-version", type=str, default=None, help="Override OCP version")
@click.option("--cnv-version", type=str, default=None, help="Override CNV X.Y version")
@click.option("--cluster-name", type=str, default=None, help="Override cluster name")
@click.option("--cluster-domain", type=str, default=None, help="Override cluster domain")
@click.option("--sc", type=str, default=None, help="Override storage class label")
@click.option("--channel", type=str, default=None, help="Override channel")
@click.option(
    "--rp-url", type=str, envvar="REPORT_PORTAL_URL", default=None, help="ReportPortal URL (env: REPORT_PORTAL_URL)"
)
@click.option(
    "--rp-project",
    type=str,
    envvar="REPORT_PORTAL_PROJECT",
    default=None,
    help="RP project name (env: REPORT_PORTAL_PROJECT)",
)
@click.option("--rp-token", type=str, envvar="REPORT_PORTAL_TOKEN", default=None, help="RP API token")
@click.option(
    "--batch-file",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Batch YAML file with pre-filled results",
)
@click.option("--dry-run", is_flag=True, default=False, help="Show what would be pushed without pushing")
def main(
    bundle: str | None,
    team: str | None,
    tier: str | None,
    tests_dir: Path,
    marker: str | None,
    keyword: str | None,
    from_cluster: bool,
    arch: str | None,
    ocp_version: str | None,
    cnv_version: str | None,
    cluster_name: str | None,
    cluster_domain: str | None,
    sc: str | None,
    channel: str | None,
    rp_url: str | None,
    rp_project: str | None,
    rp_token: str | None,
    batch_file: Path | None,
    dry_run: bool,
) -> None:
    """Collect manual test results and push to ReportPortal.

    In interactive mode, each placeholder test is shown with full
    context and the tester marks it pass/fail/skip.  In batch mode a
    YAML file supplies pre-filled verdicts.
    """
    # ── 0. Infer team from tests_dir if not provided ──
    if not team:
        resolved_parts = tests_dir.resolve().parts
        try:
            tests_index = list(resolved_parts).index("tests")
            if tests_index + 1 < len(resolved_parts):
                team = resolved_parts[tests_index + 1].upper()
                click.echo(message=f"Inferred team: {team} (from {tests_dir})")
        except ValueError:
            pass  # "tests" not found in path — no inference possible

    # ── 1. Resolve cluster attributes ──
    cluster_attrs: list[dict[str, str]] | None = None
    if from_cluster:
        raw_cluster = get_cluster_attributes()
        cluster_attrs = cluster_attributes_to_launch_attrs(cluster_attrs=raw_cluster)
        click.echo(message=f"Loaded {len(cluster_attrs)} attributes from connected cluster.")

    # ── 2. Build launch attributes ──
    attributes = _build_launch_attributes(
        team=team,
        bundle=bundle,
        cnv_version=cnv_version,
        arch=arch,
        ocp_version=ocp_version,
        cluster_name=cluster_name,
        cluster_domain=cluster_domain,
        storage_class=sc,
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

    # ── 3. Collect results ──
    collected_tests: list[PlaceholderTestDetail] | None = None
    collected_count = 0
    skipped_count = 0

    if batch_file:
        results, batch_metadata = _load_batch_file(batch_path=batch_file)
        skipped_count = sum(1 for entry in results if entry["status"] == "SKIPPED")
        results = [entry for entry in results if entry["status"] != "SKIPPED"]
        collected_count = len(results) + skipped_count
        # Fill team/bundle from batch metadata if not provided via CLI
        batch_team = batch_metadata.get("team")
        batch_bundle = batch_metadata.get("bundle")
        if not team and batch_team:
            team = batch_team
            click.echo(message=f"Using team from batch file: {team}")
        if not bundle and batch_bundle:
            bundle = batch_bundle
            click.echo(message=f"Using bundle from batch file: {bundle}")
        # Use saved attributes from retry file as base (if present)
        saved_attrs = batch_metadata.get("attributes")
        if isinstance(saved_attrs, list) and not cluster_attrs:
            cluster_attrs = saved_attrs
            click.echo(message=f"Restored {len(saved_attrs)} attributes from batch file.")
        # Rebuild attributes with batch metadata merged in
        attributes = _build_launch_attributes(
            team=team,
            bundle=bundle,
            cnv_version=cnv_version,
            arch=arch,
            ocp_version=ocp_version,
            cluster_name=cluster_name,
            cluster_domain=cluster_domain,
            storage_class=sc,
            channel=channel,
            tier=tier,
            cluster_attrs=cluster_attrs,
        )
    else:
        filter_parts = []
        if marker:
            filter_parts.append(f"-m '{marker}'")
        if keyword:
            filter_parts.append(f"-k '{keyword}'")
        filter_msg = f" (filters: {', '.join(filter_parts)})" if filter_parts else ""
        click.echo(message=f"Scanning {tests_dir} for placeholder tests{filter_msg}...")
        collected_tests = collect_placeholder_details(
            tests_dir=tests_dir,
            marker_filter=marker,
            keyword_filter=keyword,
        )

        if not collected_tests:
            click.echo(message="No placeholder tests found.")
            sys.exit(0)

        collected_count = len(collected_tests)
        click.echo(message=f"Found {collected_count} placeholder tests.\n")

    # ── 4. Validate required launch attributes (skip in dry-run) ──
    required_attr_keys = {
        "BUNDLE": "--bundle",
        "OCP": "--ocp-version",
        "CNV_XY_VER": "--cnv-version",
        "ARCH": "--arch",
        "CLUSTER_NAME": "--cluster-name",
        "CLUSTER_DOMAIN": "--cluster-domain",
        "SC": "--sc",
        "CHANNEL": "--channel",
    }
    if not dry_run:
        present_keys = {attr["key"] for attr in attributes}
        missing = {key: flag for key, flag in required_attr_keys.items() if key not in present_keys}
        if missing:
            missing_names = ", ".join(sorted(missing.keys()))
            missing_flags = ", ".join(sorted(missing.values()))
            raise click.ClickException(
                f"Missing required launch attributes: {missing_names}\n"
                f"Provide them via CLI flags ({missing_flags}) or use --from-cluster."
            )

    if not batch_file:
        assert collected_tests is not None, "collected_tests must be set when not using batch file"
        results, skipped_count = _run_interactive_mode(tests=collected_tests)

    # ── 5. Print summary ──
    pass_count = sum(1 for result in results if result["status"] == "PASSED")
    failed_results = [result for result in results if result["status"] == "FAILED"]
    fail_count = len(failed_results)
    click.echo(message="\n── Summary ──")
    click.echo(message=f"Collected: {collected_count} tests")
    click.echo(message=f"  PASSED:  {pass_count}")
    click.echo(message=f"  FAILED:  {fail_count}")
    if failed_results:
        defect_counts: dict[str, int] = {}
        for result in failed_results:
            label = result.get("issue_type_label", "Unclassified")
            defect_counts[label] = defect_counts.get(label, 0) + 1
        for label, count in sorted(defect_counts.items()):
            click.echo(message=f"    {label}: {count}")
    click.echo(message=f"  Skipped: {skipped_count}")

    if not results:
        click.echo(message="\nNo results to push.")
        sys.exit(0)

    # ── 6. Dry-run summary ──
    if dry_run:
        click.echo(message="\nAttributes:")
        for attr in attributes:
            click.echo(message=f"  {attr['key']} = {attr['value']}")
        click.echo(message="\nNo data was pushed to ReportPortal.")
        sys.exit(0)

    # ── 7. Validate RP connection settings ──
    if not rp_url:
        raise click.ClickException("REPORT_PORTAL_URL env var or --rp-url required.")
    if not rp_project:
        raise click.ClickException("REPORT_PORTAL_PROJECT env var or --rp-project required.")
    if not rp_token:
        raise click.ClickException("REPORT_PORTAL_TOKEN env var or --rp-token required.")

    # ── 8. Push to ReportPortal ──
    team_label = team.upper() if team else "ALL"
    launch_name = f"Manual - {team_label}"
    if bundle:
        launch_name = f"{launch_name} - {bundle}"

    try:
        client = RPClient(base_url=rp_url, project=rp_project, token=rp_token)
        launch_uuid = _push_results_to_rp(
            rp_client=client,
            results=results,
            launch_name=launch_name,
            attributes=attributes,
            tests=collected_tests,
            description=f"Manual test results for {team_label}",
        )
        click.echo(message=f"\n✓ Launch created successfully (UUID: {launch_uuid})")
        click.echo(message=f"  View in ReportPortal: {rp_url}/ui/#{rp_project}/launches/all")

    except PartialPushError as exc:
        LOGGER.error(str(exc))
        unpushed_start = exc.pushed_count
        remaining = results[unpushed_start:]
        click.echo(message=f"\n✗ Push failed after {exc.pushed_count}/{len(results)} items.", err=True)
        if remaining:
            saved_path = _save_results_for_retry(
                results=remaining,
                team=team_label,
                bundle=bundle,
                attributes=attributes,
            )
            click.echo(message=f"  {len(remaining)} unpushed results saved to: {saved_path}", err=True)
            click.echo(message=f"  Retry with: --batch-file {saved_path}", err=True)
        else:
            click.echo(
                message=f"  All items pushed but launch not finished. Launch UUID: {exc.launch_uuid}",
                err=True,
            )
            click.echo(
                message="  The launch may need manual finishing in ReportPortal.",
                err=True,
            )
        sys.exit(1)

    except requests.RequestException as exc:
        LOGGER.error(f"Failed to push results to ReportPortal: {exc}")
        saved_path = _save_results_for_retry(
            results=results,
            team=team_label,
            bundle=bundle,
            attributes=attributes,
        )
        click.echo(message=f"\n✗ Push failed: {exc}", err=True)
        click.echo(message=f"  Results saved to: {saved_path}", err=True)
        click.echo(message=f"  Retry with: --batch-file {saved_path}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

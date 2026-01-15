"""Generated using Claude cli

Tier2 Quarantine Status Dashboard Generator

Scans OpenShift Virtualization test repositories for quarantined tests
and generates an HTML dashboard or JSON output with statistics per version and team.

Repositories:
    - RedHatQE/openshift-virtualization-tests
    - RedHatQE/cnv-tests

Output:
    - CLI: Summary tables showing quarantine stats by version and team
    - HTML: Interactive dashboard at scripts/quarantine_stats/dashboard.html (default)
    - JSON: Machine-readable output at scripts/quarantine_stats/dashboard.json (--json flag)
"""

from __future__ import annotations

from argparse import ArgumentParser, Namespace, RawDescriptionHelpFormatter
from ast import AST, ClassDef, FunctionDef, parse, walk
from collections import defaultdict
from datetime import UTC, datetime
from html import escape as html_escape
from json import dumps as json_dumps
from os import environ
from pathlib import Path
from re import DOTALL, MULTILINE, Pattern
from re import compile as re_compile
from re import search as re_search
from shutil import rmtree
from tempfile import gettempdir
from typing import ClassVar, NamedTuple

from pyhelper_utils.shell import run_command
from simple_logger.logger import get_logger

LOGGER = get_logger(name=__name__)

# Pattern to match valid CNV version branches (e.g., cnv-4.15, cnv-5.0)
CNV_BRANCH_PATTERN: Pattern[str] = re_compile(pattern=r"^cnv-\d+\.\d+$")

# Repositories to scan (hardcoded)
REPOS = [
    "RedHatQE/openshift-virtualization-tests",
    "RedHatQE/cnv-tests",
]

# Minimum branch versions per repo (exclusive - branches before this are filtered out)
REPO_MIN_VERSIONS: dict[str, tuple[int, int]] = {
    "RedHatQE/cnv-tests": (4, 14),  # Only show cnv-4.14 and higher
}

# Repo-specific folder exclusions (folders to exclude from report)
REPO_EXCLUDED_FOLDERS: dict[str, set[str]] = {
    "RedHatQE/cnv-tests": {"ansible-module", "ci", "ci_tests", "csv", "security", "vmimport"},
}

# Repo-specific folder mappings (source -> target team)
REPO_FOLDER_MAPPINGS: dict[str, dict[str, str]] = {
    "RedHatQE/cnv-tests": {
        "must-gather": "install_upgrade_operators",
        "must_gather": "install_upgrade_operators",
        "product_uninstall": "install_upgrade_operators",
        "product_upgrade": "install_upgrade_operators",
    },
}

# Working directory for cloned repos (hardcoded)
WORKDIR = Path(gettempdir()) / "quarantine-stats"


def is_valid_branch(branch: str) -> bool:
    """Check if branch is main or matches cnv-X.Y pattern.

    Args:
        branch: The branch name to validate.

    Returns:
        True if the branch is 'main' or matches the cnv-X.Y pattern,
        False otherwise.

    """
    if branch == "main":
        return True
    return CNV_BRANCH_PATTERN.match(string=branch) is not None


def filter_branches_for_repo(repo: str, branches: list[str]) -> list[str]:
    """Filter branches based on repo-specific minimum version requirements.

    For repositories defined in REPO_MIN_VERSIONS, filters out branches
    with versions below the minimum. The 'main' branch is always kept.

    Args:
        repo: Repository name in "owner/name" format.
        branches: List of branch names to filter.

    Returns:
        Filtered list of branch names. If repo has no minimum version
        requirement, returns the original list unchanged.

    """
    min_version = REPO_MIN_VERSIONS.get(repo)
    if not min_version:
        return branches  # No filtering for this repo

    filtered: list[str] = []
    for branch in branches:
        if branch == "main":
            filtered.append(branch)
        elif branch.startswith("cnv-"):
            # Parse version: cnv-4.14 -> (4, 14)
            version_str = branch[4:]  # Remove "cnv-"
            parts = version_str.split(".")
            if len(parts) == 2:
                try:
                    version = (int(parts[0]), int(parts[1]))
                    if version >= min_version:
                        filtered.append(branch)
                except ValueError:
                    LOGGER.warning("Invalid version format in branch '%s', skipping", branch)
    return filtered


def get_valid_branches(cwd: Path | None = None) -> list[str]:
    """Get all branches matching main or cnv-X.Y pattern.

    Fetches remote branches and filters for valid patterns.
    Returns branches sorted with main first, then cnv versions by
    version number descending.

    Args:
        cwd: Working directory for git command. Defaults to current directory.

    Returns:
        List of valid branch names (e.g., ["main", "cnv-4.18", "cnv-4.17"]).

    Raises:
        RuntimeError: If git command fails.

    """
    success, stdout, stderr = run_command(
        command=["git", "branch", "-r", "--list", "origin/main", "origin/cnv-*"],
        check=False,
        verify_stderr=False,
        cwd=cwd,
    )
    if not success:
        raise RuntimeError(f"Failed to get remote branches: {stderr}")

    branches: list[str] = []
    for line in stdout.strip().split("\n"):
        stripped_line = line.strip()
        if not stripped_line:
            continue
        # Remove 'origin/' prefix
        branch = stripped_line.replace("origin/", "").strip()
        if is_valid_branch(branch=branch):
            branches.append(branch)

    return sort_branches(branches=branches)


def sort_branches(branches: list[str]) -> list[str]:
    """Sort branches: main first, then cnv versions by version number descending.

    Args:
        branches: List of branch names to sort.

    Returns:
        Sorted list of branch names.

    """

    def sort_key(branch_name: str) -> tuple[int, int, int]:
        if branch_name == "main":
            return (0, 0, 0)
        # Extract version number for cnv-X.Y branches
        match = CNV_BRANCH_PATTERN.match(string=branch_name)
        if match:
            version_str = branch_name.replace("cnv-", "")
            parts = version_str.split(".")
            if len(parts) == 2:
                try:
                    major, minor = int(parts[0]), int(parts[1])
                    return (1, -major, -minor)  # Negative for descending order
                except ValueError:
                    return (2, 0, 0)
        return (2, 0, 0)

    return sorted(branches, key=sort_key)


def get_display_path(file_path: Path) -> str:
    """Get a display-friendly path for a test file.

    In local mode, returns path relative to cwd.
    In multi-repo mode (files under /tmp/), extracts path from 'tests/' onwards.

    Args:
        file_path: Absolute path to the test file.

    Returns:
        A relative or shortened path suitable for display.

    """
    try:
        return str(file_path.relative_to(Path.cwd()))
    except ValueError:
        # Multi-repo mode: file is not under cwd
        # Try to extract path from 'tests/' onwards
        path_parts = file_path.parts
        if "tests" in path_parts:
            tests_index = path_parts.index("tests")
            return str(Path(*path_parts[tests_index:]))
        # Fallback to just the filename
        return file_path.name


def checkout_branch(branch: str, cwd: Path | None = None) -> None:
    """Checkout a specific branch.

    Args:
        branch: The branch name to checkout.
        cwd: Working directory for git command. Defaults to current directory.

    Raises:
        RuntimeError: If checkout fails.

    """
    success, _, stderr = run_command(
        command=["git", "checkout", branch],
        check=False,
        verify_stderr=False,
        cwd=cwd,
    )
    if not success:
        raise RuntimeError(f"Failed to checkout branch '{branch}': {stderr}")


def scan_branch(
    branch: str,
    tests_dir: Path,
    original_branch: str | None = None,
    cwd: Path | None = None,
    repo: str | None = None,
) -> DashboardStats | None:
    """Checkout branch and scan its tests.

    Args:
        branch: The branch to scan.
        tests_dir: Path to the tests/ directory.
        original_branch: The original branch to restore after scanning.
            If None, does not restore to original branch after scanning.
        cwd: Working directory for git commands. Defaults to current directory.
        repo: Repository name in "owner/name" format for repo-specific configs.

    Returns:
        DashboardStats for the branch, or None if scanning failed.

    """
    try:
        checkout_branch(branch=branch, cwd=cwd)
        scanner = TestScanner(tests_dir=tests_dir, repo=repo)
        stats = scanner.scan_all_tests()
        return stats
    except RuntimeError as error:
        LOGGER.warning("Failed to scan branch '%s': %s", branch, error)
        return None
    finally:
        # Return to original branch if specified
        if original_branch:
            try:
                checkout_branch(branch=original_branch, cwd=cwd)
            except RuntimeError as error:
                LOGGER.warning("Failed to restore branch '%s': %s", original_branch, error)


def format_unified_version_table(repo_stats: dict[str, list[VersionStats]]) -> str:
    """Format unified version stats for all repositories as a single ASCII table for CLI output.

    Creates a single table with a Repository column that shows the short repo name
    for the first row of each repo, then empty for subsequent versions.

    Args:
        repo_stats: Dict mapping repository names to list of VersionStats for each branch.

    Returns:
        Formatted ASCII table as a string.

    """
    if not repo_stats:
        return ""

    # Define column widths
    col_repo = 32
    col_version = 12
    col_total = 7
    col_active = 8
    col_quarantined = 13
    col_health = 8

    # Create separator line
    separator = "+" + "-" * col_repo + "+" + "-" * col_version + "+" + "-" * col_total + "+"
    separator += "-" * col_active + "+" + "-" * col_quarantined + "+" + "-" * col_health + "+"

    # Create header
    header = f"| {'Repository':<{col_repo - 2}} | {'Version':<{col_version - 2}} |"
    header += f" {'Total':>{col_total - 2}} | {'Active':>{col_active - 2}} |"
    header += f" {'Quarantined':>{col_quarantined - 2}} | {'Health':>{col_health - 2}} |"

    lines = [
        "",
        "Version Summary:",
        separator,
        header,
        separator,
    ]

    for repo, version_stats_list in repo_stats.items():
        # Extract short repo name (last part after /)
        short_repo = repo.rsplit("/", maxsplit=1)[-1]

        for idx, version_stat in enumerate(version_stats_list):
            total = version_stat.stats.total_tests
            active = version_stat.stats.active_tests
            quarantined = version_stat.stats.quarantined_tests
            health_pct = (active / total * 100) if total > 0 else 0

            # Show repo name only for first row of each repo
            repo_display = short_repo if idx == 0 else ""

            row = f"| {repo_display:<{col_repo - 2}} | {version_stat.branch:<{col_version - 2}} |"
            row += f" {total:>{col_total - 2},} | {active:>{col_active - 2},} |"
            row += f" {quarantined:>{col_quarantined - 2},} | {health_pct:>{col_health - 3}.1f}% |"
            lines.append(row)

    lines.append(separator)

    return "\n".join(lines)


def format_team_breakdown_by_version(repo_stats: dict[str, list[VersionStats]]) -> str:
    """Format unified team breakdown with all repos/versions as columns for CLI output.

    Creates a single table with teams as rows and all repo/version combinations as columns,
    showing quarantined counts in each cell.

    Args:
        repo_stats: Dict mapping repository names to list of VersionStats for each branch.

    Returns:
        Formatted ASCII table as a string.

    """
    if not repo_stats:
        return ""

    # Collect all unique teams across all repos and branches
    all_teams: set[str] = set()
    for version_stats_list in repo_stats.values():
        for version_stat in version_stats_list:
            all_teams.update(version_stat.stats.category_breakdown.keys())

    if not all_teams:
        return ""

    # Sort teams alphabetically
    sorted_teams = sorted(all_teams)

    # Build list of (repo, version_stat) pairs for columns - flatten the structure
    repo_version_pairs: list[RepoVersionStats] = []
    for repo, version_stats_list in repo_stats.items():
        for version_stat in version_stats_list:
            repo_version_pairs.append(RepoVersionStats(repo=repo, branch=version_stat.branch, stats=version_stat.stats))

    # Calculate column widths - use formatted team names for width calculation
    formatted_team_names = [team.replace("_", " ").title() for team in sorted_teams]
    col_team = max(27, max(len(name) for name in formatted_team_names) + 2)
    col_branch = 10  # Width for each branch column

    # Build separator line
    separator = "+" + "-" * col_team
    for _ in repo_version_pairs:
        separator += "+" + "-" * col_branch
    separator += "+"

    # Build header with version names only
    header = f"| {'Team':<{col_team - 2}} "
    for rvs in repo_version_pairs:
        branch_display = rvs.branch[: col_branch - 2] if len(rvs.branch) > col_branch - 2 else rvs.branch
        header += f"| {branch_display:^{col_branch - 2}} "
    header += "|"

    # Build repo name row (showing which columns belong to which repo)
    repo_row = f"| {'':<{col_team - 2}} "
    prev_repo = None
    for rvs in repo_version_pairs:
        if rvs.repo != prev_repo:
            # Extract short repo name (last part after /)
            short_repo = rvs.repo.rsplit("/", maxsplit=1)[-1][: col_branch - 2]
            repo_row += f"| {short_repo:^{col_branch - 2}} "
            prev_repo = rvs.repo
        else:
            repo_row += f"| {'':<{col_branch - 2}} "
    repo_row += "|"

    # Add blank line before header and make it more prominent
    lines = [
        "",
        "Team Breakdown (Quarantined by Version):",
        separator,
        repo_row,
        header,
        separator,
    ]

    # Build data rows
    for team in sorted_teams:
        team_display = team.replace("_", " ").title()
        if len(team_display) > col_team - 2:
            team_display = team_display[: col_team - 5] + "..."

        row = f"| {team_display:<{col_team - 2}} "

        for rvs in repo_version_pairs:
            category_data = rvs.stats.category_breakdown.get(team)
            if category_data is None:
                # Team doesn't exist in this repo/version
                row += f"| {'-':^{col_branch - 2}} "
            else:
                quarantined = category_data.get("quarantined", 0)
                row += f"| {quarantined:^{col_branch - 2}} "

        row += "|"
        lines.append(row)

    lines.append(separator)

    return "\n".join(lines)


def clone_or_update_repo(repo: str, base_dir: Path, github_token: str | None = None) -> Path:
    """Clone repository or update existing clone.

    Args:
        repo: Repository in format "owner/name" (e.g., "RedHatQE/openshift-virtualization-tests").
        base_dir: Base directory to clone repos into.
        github_token: Optional GitHub personal access token for cloning private repos.

    Returns:
        Path to the cloned repository.

    Raises:
        RuntimeError: If git clone/fetch fails.

    """
    # Extract repo name from full path
    repo_name = repo.rsplit("/", maxsplit=1)[-1]
    repo_dir = base_dir / repo_name

    if repo_dir.exists():
        # Update existing repo
        LOGGER.info("Updating existing clone: %s", repo_dir)
        success, _, stderr = run_command(
            command=["git", "fetch", "--all", "--prune"],
            check=False,
            verify_stderr=False,
            cwd=repo_dir,
        )
        if not success:
            raise RuntimeError(f"Failed to fetch updates for '{repo}': {stderr}")
        return repo_dir

    # Clone new repo - use token if provided for private repos
    if github_token:
        repo_url = f"https://{github_token}@github.com/{repo}.git"
        # Log without exposing the token
        LOGGER.info("Cloning: https://***@github.com/%s.git (with token)", repo)
    else:
        repo_url = f"https://github.com/{repo}.git"
        LOGGER.info("Cloning: %s", repo_url)

    base_dir.mkdir(parents=True, exist_ok=True)

    success, _, stderr = run_command(
        command=["git", "clone", repo_url, str(repo_dir)],
        check=False,
        verify_stderr=False,
    )
    if not success:
        raise RuntimeError(f"Failed to clone '{repo}': {stderr}")
    return repo_dir


def get_repo_branches(repo_dir: Path) -> list[str]:
    """Get all valid branches from repository.

    Fetches remote branches and filters for main/cnv-X.Y patterns.

    Args:
        repo_dir: Path to the cloned repository.

    Returns:
        List of valid branch names sorted (main first, then cnv versions descending).

    Raises:
        RuntimeError: If git command fails.

    """
    return get_valid_branches(cwd=repo_dir)


def scan_repo_branch(repo_dir: Path, branch: str, repo: str | None = None) -> DashboardStats | None:
    """Checkout branch in repository and scan its tests.

    Args:
        repo_dir: Path to the cloned repository.
        branch: Branch name to checkout and scan.
        repo: Repository name in "owner/name" format for repo-specific configs.

    Returns:
        DashboardStats for the branch, or None if scanning failed.

    """
    tests_dir = repo_dir / "tests"
    if not tests_dir.exists():
        LOGGER.warning("tests/ directory not found in %s", repo_dir)
        return None

    return scan_branch(branch=branch, tests_dir=tests_dir, cwd=repo_dir, repo=repo)


def scan_all_repos(
    repos: list[str],
    workdir: Path,
    branch_filter: str | None = None,
    github_token: str | None = None,
) -> dict[str, list[VersionStats]]:
    """Scan all repositories and branches, returning per-version stats.

    Args:
        repos: List of repository names in "owner/name" format.
        workdir: Working directory to clone repos into.
        branch_filter: If specified, only scan this specific branch.
        github_token: Optional GitHub personal access token for cloning private repos.

    Returns:
        Dict mapping repository name to list of VersionStats for each branch.

    """
    results: dict[str, list[VersionStats]] = {}

    for repo in repos:
        LOGGER.info("Processing repository: %s", repo)
        repo_stats: list[VersionStats] = []

        try:
            repo_dir = clone_or_update_repo(repo=repo, base_dir=workdir, github_token=github_token)
        except RuntimeError as error:
            LOGGER.error("Error processing repository '%s': %s", repo, error)
            LOGGER.info("Skipping repository: %s", repo)
            continue

        # Get branches to scan
        if branch_filter:
            branches = [branch_filter] if is_valid_branch(branch=branch_filter) else []
            if not branches:
                LOGGER.warning("Branch '%s' is not a valid pattern", branch_filter)
                branches = [branch_filter]  # Try anyway
        else:
            try:
                branches = get_repo_branches(repo_dir=repo_dir)
            except RuntimeError as error:
                LOGGER.error("Error getting branches: %s", error)
                continue

        # Apply repo-specific branch filtering (e.g., minimum version requirements)
        branches = filter_branches_for_repo(repo=repo, branches=branches)

        if not branches:
            LOGGER.info("No valid branches found in %s", repo)
            continue

        LOGGER.info("Found %d branches: %s", len(branches), ", ".join(branches))

        for branch in branches:
            LOGGER.info("Scanning branch: %s...", branch)
            stats = scan_repo_branch(repo_dir=repo_dir, branch=branch, repo=repo)
            if stats:
                repo_stats.append(VersionStats(branch=branch, stats=stats))
                LOGGER.info("  -> %d tests, %d quarantined", stats.total_tests, stats.quarantined_tests)
            else:
                LOGGER.warning("  -> Failed to scan")

        if repo_stats:
            results[repo] = repo_stats

    return results


def cleanup_workdir(workdir: Path) -> None:
    """Remove the working directory and all cloned repos.

    Args:
        workdir: Working directory to remove.

    Raises:
        OSError: If removal fails.

    """
    if workdir.exists():
        LOGGER.info("Cleaning up working directory: %s", workdir)
        try:
            rmtree(path=workdir)
        except OSError as error:
            LOGGER.error("Failed to remove %s: %s", workdir, error)
            raise


class TestInfo(NamedTuple):
    """Information about a single test function.

    Attributes:
        name: The test function name (e.g., "test_vm_creation").
        file_path: Absolute path to the test file.
        line_number: Line number where the test function is defined.
        category: Team/category derived from top-level folder under tests/.
        is_quarantined: Whether the test is marked as quarantined.
        quarantine_reason: Reason for quarantine if applicable.
        jira_ticket: Associated Jira ticket (e.g., "CNV-12345") if found.

    """

    name: str
    file_path: Path
    line_number: int
    category: str
    is_quarantined: bool
    quarantine_reason: str = ""
    jira_ticket: str = ""


class DashboardStats(NamedTuple):
    """Aggregated statistics for the test dashboard.

    Attributes:
        total_tests: Total number of test functions found.
        active_tests: Number of non-quarantined tests.
        quarantined_tests: Number of quarantined tests.
        category_breakdown: Dict mapping category name to counts
            ({"total": N, "active": N, "quarantined": N}).
        quarantined_list: List of TestInfo for all quarantined tests.

    """

    total_tests: int
    active_tests: int
    quarantined_tests: int
    category_breakdown: dict[str, dict[str, int]]
    quarantined_list: list[TestInfo]


class VersionStats(NamedTuple):
    """Statistics for a specific branch/version.

    Attributes:
        branch: The branch name (e.g., "main", "cnv-4.18").
        stats: DashboardStats for this branch.

    """

    branch: str
    stats: DashboardStats


class RepoVersionStats(NamedTuple):
    """Statistics for a specific repository and branch/version.

    Attributes:
        repo: The repository name (e.g., "RedHatQE/openshift-virtualization-tests").
        branch: The branch name (e.g., "main", "cnv-4.18").
        stats: DashboardStats for this repo+branch combination.

    """

    repo: str
    branch: str
    stats: DashboardStats


class TestScanner:
    """Scanner for Python test files to detect quarantined tests.

    Scans test files using AST parsing to find test functions and detects
    quarantine markers using regex patterns on decorator blocks.

    Attributes:
        DEFAULT_EXCLUDED_FOLDERS: Set of folder names to exclude from scanning.
        DEFAULT_FOLDER_MAPPINGS: Dict mapping source folders to target team names.

    """

    # Default folders to exclude from the report (for openshift-virtualization-tests)
    DEFAULT_EXCLUDED_FOLDERS: ClassVar[set[str]] = {"after_cluster_deploy_sanity", "deprecated_api"}

    # Default folder mappings (source -> target) for combining quarantine_stats
    DEFAULT_FOLDER_MAPPINGS: ClassVar[dict[str, str]] = {
        "compute": "virt",
        "data_protection": "storage",
        "cross_cluster_live_migration": "storage",
    }

    # Maximum number of lines to search backwards for decorators
    MAX_DECORATOR_SEARCH_LINES: ClassVar[int] = 50

    def __init__(self, tests_dir: Path, repo: str | None = None) -> None:
        """Initialize the scanner.

        Args:
            tests_dir: Path to the tests/ directory to scan.
            repo: Repository name in "owner/name" format. Used for repo-specific
                configurations. If None, uses default configurations.

        """
        self.tests_dir = tests_dir
        self.repo = repo

        # Merge default and repo-specific configurations
        self.excluded_folders = self.DEFAULT_EXCLUDED_FOLDERS.copy()
        if repo and repo in REPO_EXCLUDED_FOLDERS:
            self.excluded_folders = self.excluded_folders | REPO_EXCLUDED_FOLDERS[repo]

        self.folder_mappings = self.DEFAULT_FOLDER_MAPPINGS.copy()
        if repo and repo in REPO_FOLDER_MAPPINGS:
            self.folder_mappings = {**self.folder_mappings, **REPO_FOLDER_MAPPINGS[repo]}
        # Multiple patterns to catch all quarantine variations:
        # 1. reason=(f"{QUARANTINED}: ...") - with parentheses around f-string
        # 2. reason=f"{QUARANTINED}: ..." - without parentheses
        # 3. Various whitespace and formatting variations
        # Regex patterns for quarantine detection
        _paren_pattern = (
            r'@pytest\.mark\.xfail\s*\(\s*reason\s*=\s*\(\s*f["\'].*?'
            r'QUARANTINED.*?:([^"\']+)["\'].*?\)\s*,\s*run\s*=\s*False'
        )
        _no_paren_pattern = (
            r'@pytest\.mark\.xfail\s*\(\s*reason\s*=\s*f["\'].*?'
            r'QUARANTINED.*?:([^"\']+)["\'].*?,\s*run\s*=\s*False'
        )
        _simple_pattern = r"@pytest\.mark\.xfail\s*\([^)]*QUARANTINED[^)]*run\s*=\s*False"

        self.quarantine_patterns: list[Pattern[str]] = [
            re_compile(pattern=_paren_pattern, flags=MULTILINE | DOTALL),
            re_compile(pattern=_no_paren_pattern, flags=MULTILINE | DOTALL),
            re_compile(pattern=_simple_pattern, flags=MULTILINE | DOTALL),
        ]
        self.jira_pattern: Pattern[str] = re_compile(pattern=r"CNV-\d+")

    def scan_all_tests(self) -> DashboardStats:
        """Scan all test files and return aggregated statistics.

        Recursively finds all test_*.py files under the tests directory,
        parses each file to extract test functions, and identifies
        quarantined tests.

        Returns:
            DashboardStats containing total counts, category breakdown,
            and list of quarantined tests.

        """
        all_tests: list[TestInfo] = []

        test_files = list(self.tests_dir.rglob("test_*.py"))

        for test_file in test_files:
            try:
                tests = self._scan_file(file_path=test_file)
                all_tests.extend(tests)
            except (SyntaxError, OSError, UnicodeDecodeError) as error:
                LOGGER.warning("Error scanning %s: %s", test_file, error)

        return self._calculate_stats(all_tests=all_tests)

    def _scan_file(self, file_path: Path) -> list[TestInfo]:
        """Scan a single test file for test functions.

        Uses Python AST to parse the file and find all functions starting
        with "test_". Checks both function-level and class-level quarantine
        decorators.

        Args:
            file_path: Path to the Python test file to scan.

        Returns:
            List of TestInfo objects for each test function found.
            Returns empty list if file cannot be parsed.

        """
        tests: list[TestInfo] = []

        try:
            content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError as error:
            LOGGER.warning("Unicode decode error reading %s: %s", file_path, error)
            return tests

        # Determine category from file path
        category = self._get_category(file_path=file_path)

        # Skip excluded categories
        if category is None:
            return tests

        try:
            tree = parse(source=content, filename=str(file_path))
        except SyntaxError as error:
            LOGGER.warning("Syntax error parsing %s: %s", file_path, error)
            return tests

        quarantined_classes: dict[str, tuple[str, str]] = {}

        # First pass: identify quarantined classes
        for node in walk(tree):
            if isinstance(node, ClassDef):
                is_quarantined, reason, jira = self._check_quarantine(content=content, line_number=node.lineno)
                if is_quarantined:
                    quarantined_classes[node.name] = (reason, jira)

        # Second pass: find all test functions
        for node in walk(tree):
            if isinstance(node, FunctionDef) and node.name.startswith("test_"):
                # Check if test is quarantined (either directly or via parent class)
                is_quarantined, reason, jira = self._check_quarantine(content=content, line_number=node.lineno)

                # If not directly quarantined, check if parent class is quarantined
                if not is_quarantined:
                    parent_class = self._get_parent_class(tree=tree, func_node=node)
                    if parent_class and parent_class in quarantined_classes:
                        is_quarantined = True
                        reason, jira = quarantined_classes[parent_class]

                test_info = TestInfo(
                    name=node.name,
                    file_path=file_path,
                    line_number=node.lineno,
                    category=category,
                    is_quarantined=is_quarantined,
                    quarantine_reason=reason,
                    jira_ticket=jira,
                )
                tests.append(test_info)

        return tests

    def _get_parent_class(self, tree: AST, func_node: FunctionDef) -> str | None:
        """Find the parent class of a function node, if any.

        Args:
            tree: The AST tree of the parsed file.
            func_node: The function node to find the parent class for.

        Returns:
            The class name if the function is inside a class, None otherwise.

        """
        for node in walk(tree):
            if isinstance(node, ClassDef):
                for child in walk(node):
                    if child is func_node:
                        return node.name
        return None

    def _get_category(self, file_path: Path) -> str | None:
        """Extract category (team) from file path.

        The category is the first directory component after tests/.
        Applies folder mappings and exclusions.

        Args:
            file_path: Path to the test file.

        Returns:
            Category name, or None if the file should be excluded.

        Example:
            tests/network/bgp/test_foo.py -> "network"
            tests/data_protection/test_bar.py -> "storage" (mapped)

        """
        parts = file_path.relative_to(self.tests_dir).parts
        if parts:
            category = parts[0]

            if category in self.excluded_folders:
                return None

            category = self.folder_mappings.get(category, category)

            return category
        return "uncategorized"

    def _check_quarantine(self, content: str, line_number: int) -> tuple[bool, str, str]:
        """Check if a test function or class is quarantined.

        Looks for decorators above the given line number that match the
        quarantine pattern: @pytest.mark.xfail with QUARANTINED in reason
        and run=False.

        Args:
            content: Full file content as string.
            line_number: Line number of the function/class definition.

        Returns:
            Tuple of (is_quarantined, reason, jira_ticket).
            If not quarantined, returns (False, "", "").

        """
        # Extract lines before the function definition (decorators area)
        # Only look at contiguous decorator block (stop at blank lines or non-decorator/non-continuation lines)
        lines = content.split("\n")
        decorator_lines: list[str] = []

        # Walk backwards from the function definition to find its decorators
        for line_idx in range(line_number - 2, max(0, line_number - self.MAX_DECORATOR_SEARCH_LINES) - 1, -1):
            line = lines[line_idx].strip()
            if not line:
                # Blank line - stop searching (decorators must be contiguous)
                break
            if line.startswith(("@", "def ", "class ")):
                # Part of decorator block or we hit the function/class def
                decorator_lines.insert(0, lines[line_idx])
            elif line.startswith((")", "(")) or line.endswith((",", "(")):
                # Continuation of multi-line decorator
                decorator_lines.insert(0, lines[line_idx])
            elif "pytest.param" in line or "marks=" in line or "indirect=" in line:
                # Part of parametrize
                decorator_lines.insert(0, lines[line_idx])
            elif line.startswith(('"', "'", 'f"', "f'")):
                # String continuation
                decorator_lines.insert(0, lines[line_idx])
            elif "{" in line or "}" in line or "[" in line or "]" in line:
                # Dict/list in decorator
                decorator_lines.insert(0, lines[line_idx])
            elif line.startswith("#"):
                # Comment - skip but continue
                continue
            else:
                # Some other code - stop searching
                break

        decorator_section = "\n".join(decorator_lines)

        # Check if QUARANTINED appears in the decorator section with xfail and run=False
        if "QUARANTINED" not in decorator_section:
            return False, "", ""

        if "@pytest.mark.xfail" not in decorator_section:
            return False, "", ""

        if "run=False" not in decorator_section and "run = False" not in decorator_section:
            return False, "", ""

        # Extract the reason from the decorator section
        # Look for the full reason text
        reason = ""
        for pattern in self.quarantine_patterns:
            match = pattern.search(string=decorator_section)
            if match:
                if match.lastindex and match.lastindex >= 1:
                    reason = match.group(1).strip()
                break

        # If no reason captured, extract it manually
        if not reason:
            # Find the reason text between QUARANTINED and the closing quote/paren
            reason_match = re_search(pattern=r'QUARANTINED[}"\']?:\s*([^"\']+)', string=decorator_section)
            if reason_match:
                reason = reason_match.group(1).strip().rstrip('",)')

        # Extract Jira ticket from the reason text specifically (not from @polarion markers)
        # Find the xfail decorator section only
        xfail_start = decorator_section.find("@pytest.mark.xfail")
        if xfail_start != -1:
            # Find where this decorator ends (next decorator or function def)
            xfail_section = decorator_section[xfail_start:]
            # Look for run=False to ensure we're in the right section
            if "run=False" in xfail_section or "run = False" in xfail_section:
                jira_match = self.jira_pattern.search(string=xfail_section)
                jira_ticket = jira_match.group(0) if jira_match else ""
            else:
                jira_ticket = ""
        else:
            jira_ticket = ""

        return True, reason, jira_ticket

    def _calculate_stats(self, all_tests: list[TestInfo]) -> DashboardStats:
        """Calculate aggregated statistics from list of tests.

        Groups tests by category and counts active vs quarantined tests.

        Args:
            all_tests: List of all TestInfo objects from scanning.

        Returns:
            DashboardStats with totals, breakdowns, and quarantined list.

        """
        total_tests = len(all_tests)
        quarantined_tests = [test for test in all_tests if test.is_quarantined]
        active_tests = total_tests - len(quarantined_tests)

        # Category breakdown
        category_breakdown: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "active": 0, "quarantined": 0})
        for test in all_tests:
            category_breakdown[test.category]["total"] += 1
            if test.is_quarantined:
                category_breakdown[test.category]["quarantined"] += 1
            else:
                category_breakdown[test.category]["active"] += 1

        return DashboardStats(
            total_tests=total_tests,
            active_tests=active_tests,
            quarantined_tests=len(quarantined_tests),
            category_breakdown=dict(category_breakdown),
            quarantined_list=sorted(quarantined_tests, key=lambda test: test.category),
        )


class DashboardGenerator:
    """Generator for HTML dashboard output.

    Creates a styled HTML page with summary cards, progress bar,
    team breakdown table, and detailed quarantined tests section.
    Optionally includes version comparison when multi-version stats are provided.
    Supports multi-repository mode with per-repo, per-version breakdown.
    """

    def __init__(
        self,
        stats: DashboardStats,
        branch: str,
        version_stats_list: list[VersionStats] | None = None,
        repo_stats: dict[str, list[VersionStats]] | None = None,
    ) -> None:
        """Initialize the generator.

        Args:
            stats: DashboardStats containing all test statistics for current branch.
            branch: The current git branch name for version display.
            version_stats_list: Optional list of VersionStats for multi-version display (single repo mode).
            repo_stats: Optional dict mapping repo names to VersionStats lists (multi-repo mode).

        """
        self.stats = stats
        self.branch = branch
        self.version_stats_list = version_stats_list or []
        self.repo_stats = repo_stats or {}

    def generate(self) -> str:
        """Generate the complete HTML dashboard.

        Creates a self-contained HTML page with embedded CSS styling.
        Includes version summary tables, team breakdown tables,
        and detailed quarantined tests section.

        Returns:
            Complete HTML document as a string.

        """
        timestamp = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

        # Build quarantined details section based on mode
        if self.repo_stats:
            quarantined_details = self._generate_quarantined_details_by_version()
        else:
            quarantined_details = f"""        <div class="section">
            <h2>Quarantined Tests Details</h2>
{self._generate_quarantined_html()}
        </div>"""

        # Assemble all sections
        parts = [
            self._render_header(),
            self._generate_version_comparison_section(),
            quarantined_details,
            self._render_footer(timestamp=timestamp),
        ]

        return "".join(parts)

    def _render_css(self) -> str:
        """Render the embedded CSS styles for the dashboard.

        Returns:
            HTML style block containing all CSS rules.

        """
        return """    <style>
        :root {
            --green: #22c55e;
            --yellow: #eab308;
            --red: #ef4444;
            --blue: #3b82f6;
            --gray: #6b7280;
            --light-gray: #f3f4f6;
            --dark: #1f2937;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: var(--light-gray);
            color: var(--dark);
            line-height: 1.6;
            padding: 2rem;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        h1 {
            text-align: center;
            margin-bottom: 2rem;
            color: var(--dark);
        }
        .section {
            background: white;
            border-radius: 8px;
            padding: 1.5rem;
            margin-bottom: 2rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }
        .section h2 { margin-bottom: 1rem; color: var(--dark); }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 0.75rem; text-align: left; border-bottom: 1px solid var(--light-gray); }
        th { background: var(--light-gray); font-weight: 600; }
        tr:hover { background: #f9fafb; }
        .health { font-weight: bold; }
        .health.green { color: var(--green); }
        .health.yellow { color: var(--yellow); }
        .health.red { color: var(--red); }
        .team-header {
            background: var(--light-gray);
            padding: 0.75rem 1rem;
            margin: 1rem 0 0.5rem;
            border-radius: 4px;
            font-weight: 600;
        }
        .test-item {
            padding: 0.75rem 1rem;
            border-left: 3px solid var(--red);
            margin-bottom: 0.5rem;
            background: #fef2f2;
        }
        .test-item code { background: #fee2e2; padding: 0.125rem 0.375rem; border-radius: 4px; font-size: 0.875rem; }
        .test-item a { color: var(--blue); text-decoration: none; }
        .test-item a:hover { text-decoration: underline; }
        .test-item .meta { color: var(--gray); font-size: 0.875rem; margin-top: 0.25rem; }
        .note {
            background: #eff6ff;
            border-left: 3px solid var(--blue);
            padding: 0.75rem 1rem;
            margin-top: 1rem;
            font-size: 0.875rem;
            color: var(--gray);
        }
        .tabs {
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem;
            margin-bottom: 1rem;
            border-bottom: 2px solid var(--light-gray);
            padding-bottom: 0.5rem;
        }
        .tab-btn {
            padding: 0.5rem 1rem;
            border: none;
            background: var(--light-gray);
            cursor: pointer;
            border-radius: 4px 4px 0 0;
            font-size: 0.875rem;
        }
        .tab-btn.active {
            background: var(--blue);
            color: white;
        }
        .tab-btn:hover:not(.active) {
            background: #e5e7eb;
        }
        .tab-separator {
            display: flex;
            align-items: center;
            padding: 0 0.25rem;
            color: var(--gray);
            font-weight: bold;
        }
        .tab-content {
            display: none;
        }
        .tab-content.active {
            display: block;
        }
        .footer {
            text-align: center;
            color: var(--gray);
            font-size: 0.875rem;
            margin-top: 2rem;
        }
    </style>"""

    def _render_header(self) -> str:
        """Render the HTML header section including doctype, head, and opening body/container.

        Returns:
            HTML string from doctype through the opening of the main container
            and page title.

        """
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Tier2 Quarantine Status</title>
{self._render_css()}
</head>
<body>
    <div class="container">
        <h1>Tier2 Quarantine Status</h1>

"""

    def _render_footer(self, timestamp: str) -> str:
        """Render the HTML footer section with timestamp and closing tags.

        Args:
            timestamp: Formatted timestamp string for the "Last updated" display.

        Returns:
            HTML string containing footer content, JavaScript, and closing tags.

        """
        return f"""        <div class="footer">
            Last updated: {timestamp}<br>
            Generated by generate_dashboard.py
        </div>
    </div>
    <script>
        document.querySelectorAll('.tab-btn').forEach(btn => {{
            btn.addEventListener('click', () => {{
                const tabId = btn.dataset.tab;
                const section = btn.closest('.section');

                // Deactivate all tabs in this section
                section.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
                section.querySelectorAll('.tab-content').forEach(c => {{
                    c.classList.remove('active');
                    c.style.display = 'none';
                }});

                // Activate clicked tab
                btn.classList.add('active');
                const content = section.querySelector('#' + tabId);
                content.classList.add('active');
                content.style.display = 'block';
            }});
        }});
    </script>
</body>
</html>"""

    def _generate_version_comparison_section(self) -> str:
        """Generate HTML section for version comparison.

        Creates tables showing statistics for each repository and version/branch.
        Supports both single-repo (version_stats_list) and multi-repo (repo_stats) modes.

        Returns:
            HTML string containing the version comparison section,
            or empty string if no multi-version data available.

        """
        # Multi-repo mode
        if self.repo_stats:
            return self._generate_multi_repo_section()

        # Single-repo mode (legacy)
        if not self.version_stats_list:
            return ""

        rows = []
        for version_stat in self.version_stats_list:
            total = version_stat.stats.total_tests
            active = version_stat.stats.active_tests
            quarantined = version_stat.stats.quarantined_tests
            health_pct = (active / total * 100) if total > 0 else 0

            if health_pct == 100:
                health_class = "green"
                health_text = "100%"
            elif health_pct >= 95:
                health_class = "yellow"
                health_text = f"{health_pct:.1f}%"
            else:
                health_class = "red"
                health_text = f"{health_pct:.1f}%"

            rows.append(f"""                    <tr>
                        <td>{version_stat.branch}</td>
                        <td>{total:,}</td>
                        <td>{active:,}</td>
                        <td>{quarantined:,}</td>
                        <td><span class="health {health_class}">{health_text}</span></td>
                    </tr>""")

        rows_html = "\n".join(rows)
        return f"""        <div class="section">
            <h2>Version Comparison</h2>
            <table>
                <thead>
                    <tr>
                        <th>Version</th>
                        <th>Total</th>
                        <th>Active</th>
                        <th>Quarantined</th>
                        <th>Health</th>
                    </tr>
                </thead>
                <tbody>
{rows_html}
                </tbody>
            </table>
            <div class="note">
                Statistics shown for each branch scanned. Health percentage indicates
                proportion of active (non-quarantined) tests.
            </div>
        </div>

"""

    def _generate_multi_repo_section(self) -> str:
        """Generate HTML section for multi-repository version comparison.

        Creates a single unified table for all repositories with per-version breakdown
        and a unified team breakdown table showing quarantined counts by team
        across all repos and versions.

        Returns:
            HTML string containing the multi-repo comparison section.

        """
        sections = []

        # Generate unified version summary section (single table for all repos)
        rows: list[str] = []
        for repo, version_stats_list in self.repo_stats.items():
            # Extract short repo name (last part after /)
            short_repo = repo.rsplit("/", maxsplit=1)[-1]

            for idx, version_stat in enumerate(version_stats_list):
                total = version_stat.stats.total_tests
                active = version_stat.stats.active_tests
                quarantined = version_stat.stats.quarantined_tests
                health_pct = (active / total * 100) if total > 0 else 0

                if health_pct == 100:
                    health_class = "green"
                    health_text = "100%"
                elif health_pct >= 95:
                    health_class = "yellow"
                    health_text = f"{health_pct:.1f}%"
                else:
                    health_class = "red"
                    health_text = f"{health_pct:.1f}%"

                # Show repo name only for first row of each repo
                repo_display = short_repo if idx == 0 else ""

                rows.append(f"""                    <tr>
                        <td>{repo_display}</td>
                        <td>{version_stat.branch}</td>
                        <td>{total:,}</td>
                        <td>{active:,}</td>
                        <td>{quarantined:,}</td>
                        <td><span class="health {health_class}">{health_text}</span></td>
                    </tr>""")

        rows_html = "\n".join(rows)

        # Unified version summary section
        sections.append(f"""        <div class="section">
            <h2>Version Summary</h2>
            <table>
                <thead>
                    <tr>
                        <th>Repository</th>
                        <th>Version</th>
                        <th>Total</th>
                        <th>Active</th>
                        <th>Quarantined</th>
                        <th>Health</th>
                    </tr>
                </thead>
                <tbody>
{rows_html}
                </tbody>
            </table>
        </div>

""")

        # Generate unified team breakdown table (across all repos)
        team_breakdown_html = self._generate_unified_team_breakdown_by_version()
        if team_breakdown_html:
            sections.append(f"""        <div class="section">
            <h2>Team Breakdown (Quarantined by Version)</h2>
{team_breakdown_html}
        </div>

""")

        return "\n".join(sections)

    def _generate_unified_team_breakdown_by_version(self) -> str:
        """Generate HTML table for unified team breakdown across all repos with versions as columns.

        Creates a single table with teams as rows and all repo/version combinations as columns,
        showing quarantined counts in each cell. Teams that don't exist in a particular
        repo/version show "-".

        Returns:
            HTML string containing the unified team breakdown table.

        """
        if not self.repo_stats:
            return ""

        # Collect all unique teams across all repos and branches
        all_teams: set[str] = set()
        for version_stats_list in self.repo_stats.values():
            for version_stat in version_stats_list:
                all_teams.update(version_stat.stats.category_breakdown.keys())

        if not all_teams:
            return ""

        # Sort teams alphabetically
        sorted_teams = sorted(all_teams)

        # Build list of (repo, version_stat) pairs for columns - flatten the structure
        repo_version_pairs: list[RepoVersionStats] = []
        for repo, version_stats_list in self.repo_stats.items():
            for version_stat in version_stats_list:
                repo_version_pairs.append(
                    RepoVersionStats(repo=repo, branch=version_stat.branch, stats=version_stat.stats),
                )

        # Build header row with repo name sub-header and version columns
        # First row: repo names (spanning their respective columns)
        repo_header_cells = ["<th rowspan='2'>Team</th>"]
        prev_repo = None
        repo_colspan = 0
        for rvs in repo_version_pairs:
            if rvs.repo != prev_repo:
                if prev_repo is not None:
                    # Extract short repo name
                    short_repo = prev_repo.rsplit("/", maxsplit=1)[-1]
                    repo_header_cells.append(f"<th colspan='{repo_colspan}'>{short_repo}</th>")
                prev_repo = rvs.repo
                repo_colspan = 1
            else:
                repo_colspan += 1
        # Add the last repo
        if prev_repo is not None:
            short_repo = prev_repo.rsplit("/", maxsplit=1)[-1]
            repo_header_cells.append(f"<th colspan='{repo_colspan}'>{short_repo}</th>")

        repo_header_row = "\n                        ".join(repo_header_cells)

        # Second row: version names
        version_header_cells = []
        for rvs in repo_version_pairs:
            version_header_cells.append(f"<th>{rvs.branch}</th>")
        version_header_row = "\n                        ".join(version_header_cells)

        # Build data rows
        data_rows = []
        for team in sorted_teams:
            team_display = team.replace("_", " ").title()
            cells = [f"<td>{team_display}</td>"]

            for rvs in repo_version_pairs:
                category_data = rvs.stats.category_breakdown.get(team)

                if category_data is None:
                    # Team doesn't exist in this repo/version
                    cells.append('<td><span class="health">-</span></td>')
                else:
                    quarantined = category_data.get("quarantined", 0)

                    # Color-code based on quarantine count
                    if quarantined == 0:
                        cell_class = "health green"
                    elif quarantined <= 5:
                        cell_class = "health yellow"
                    else:
                        cell_class = "health red"

                    cells.append(f'<td><span class="{cell_class}">{quarantined}</span></td>')

            row_cells = "\n                        ".join(cells)
            data_rows.append(f"""                    <tr>
                        {row_cells}
                    </tr>""")

        rows_html = "\n".join(data_rows)

        return f"""            <table>
                <thead>
                    <tr>
                        {repo_header_row}
                    </tr>
                    <tr>
                        {version_header_row}
                    </tr>
                </thead>
                <tbody>
{rows_html}
                </tbody>
            </table>
            <div class="note">
                Shows quarantined test count per team for each repository and branch/version.
                "-" indicates the team does not exist in that repository/version.
            </div>"""

    def _get_display_path(self, file_path: Path) -> str:
        """Get a display-friendly path for a test file.

        Delegates to the module-level get_display_path function.

        Args:
            file_path: Absolute path to the test file.

        Returns:
            A relative or shortened path suitable for display.

        """
        return get_display_path(file_path=file_path)

    def _generate_quarantined_html(self) -> str:
        """Generate HTML for quarantined tests section.

        Groups quarantined tests by team/category and generates styled
        HTML blocks for each test with Jira links and file locations.

        Returns:
            HTML string containing the quarantined tests section.
            Returns success message if no tests are quarantined.

        """
        if not self.stats.quarantined_list:
            return '            <p style="color: var(--green);">✅ No tests are currently quarantined!</p>'

        total_count = len(self.stats.quarantined_list)
        lines = [f"            <p>Total: <strong>{total_count}</strong> test functions currently quarantined</p>"]

        by_category: dict[str, list[TestInfo]] = defaultdict(list)
        for test in self.stats.quarantined_list:
            by_category[test.category].append(test)

        for category in sorted(by_category.keys()):
            tests = by_category[category]
            category_display = category.replace("_", " ").title()
            test_count = len(tests)
            plural = "s" if test_count > 1 else ""
            lines.append(
                f'            <div class="team-header">📁 {category_display} ({test_count} test{plural})</div>',
            )

            for test in sorted(tests, key=lambda test_item: test_item.name):
                rel_path = html_escape(s=self._get_display_path(file_path=test.file_path))
                escaped_name = html_escape(s=test.name)
                escaped_reason = html_escape(s=test.quarantine_reason) if test.quarantine_reason else ""
                jira_link = f"https://issues.redhat.com/browse/{test.jira_ticket}"
                jira_html = (
                    f' <a href="{jira_link}" target="_blank">[{test.jira_ticket}]</a>'
                    if test.jira_ticket
                    else ' <span style="color: var(--yellow);">⚠️ No Jira ticket</span>'
                )
                reason_html = (
                    f'<br><span class="meta">Reason: {escaped_reason}</span>' if test.quarantine_reason else ""
                )

                lines.append(f"""            <div class="test-item">
                <code>{escaped_name}</code>{jira_html}
                <div class="meta">File: {rel_path}:{test.line_number}</div>{reason_html}
            </div>""")

        return "\n".join(lines)

    def _generate_quarantined_details_by_version(self) -> str:
        """Generate HTML section for quarantined tests details organized by version with tabs.

        Creates a single unified tabbed interface combining all repositories and versions.
        Each tab shows version name with quarantine count.

        Returns:
            HTML string containing the unified quarantined tests details section
            with tabbed interface, or empty string if no multi-repo data available.

        """
        if not self.repo_stats:
            return ""

        # Collect all tab buttons and contents across all repos
        all_tab_buttons: list[str] = []
        all_tab_contents: list[str] = []
        first_tab = True
        repo_index = 0

        for _, version_stats_list in self.repo_stats.items():
            repo_index += 1
            repo_id = f"repo{repo_index}"

            for version_stat in version_stats_list:
                quarantined_list = version_stat.stats.quarantined_list
                quarantined_count = len(quarantined_list)

                # Create safe tab ID from repo and branch name
                tab_id = f"{repo_id}-{version_stat.branch.replace('.', '-')}"
                active_class = " active" if first_tab else ""
                display_style = "" if first_tab else ' style="display:none;"'

                # Tab button with version and quarantine count
                tab_label = f"{version_stat.branch} ({quarantined_count})"
                all_tab_buttons.append(
                    f'            <button class="tab-btn{active_class}" data-tab="{tab_id}">{tab_label}</button>',
                )

                # Tab content
                content_parts = []

                if quarantined_count == 0:
                    content_parts.append(
                        '                <p style="color: var(--green);">No tests are currently quarantined!</p>',
                    )
                else:
                    # Group by team/category
                    by_category: dict[str, list[TestInfo]] = defaultdict(list)
                    for test in quarantined_list:
                        by_category[test.category].append(test)

                    # Generate test items for each category
                    for category in sorted(by_category.keys()):
                        tests = by_category[category]
                        category_display = category.replace("_", " ").title()
                        test_count = len(tests)
                        plural = "s" if test_count > 1 else ""
                        header_html = (
                            f'                <div class="team-header">'
                            f"{category_display} ({test_count} test{plural})</div>"
                        )
                        content_parts.append(header_html)

                        for test in sorted(tests, key=lambda test_item: test_item.name):
                            rel_path = html_escape(s=self._get_display_path(file_path=test.file_path))
                            escaped_name = html_escape(s=test.name)
                            escaped_reason = html_escape(s=test.quarantine_reason) if test.quarantine_reason else ""
                            jira_link = f"https://issues.redhat.com/browse/{test.jira_ticket}"
                            jira_html = (
                                f' <a href="{jira_link}" target="_blank">[{test.jira_ticket}]</a>'
                                if test.jira_ticket
                                else ' <span style="color: var(--yellow);">No Jira ticket</span>'
                            )
                            reason_html = (
                                f'<br><span class="meta">Reason: {escaped_reason}</span>'
                                if test.quarantine_reason
                                else ""
                            )

                            content_parts.append(f"""                <div class="test-item">
                    <code>{escaped_name}</code>{jira_html}
                    <div class="meta">File: {rel_path}:{test.line_number}</div>{reason_html}
                </div>""")

                all_tab_contents.append(
                    f'            <div class="tab-content{active_class}" id="{tab_id}"{display_style}>\n'
                    + "\n".join(content_parts)
                    + "\n            </div>",
                )

                first_tab = False

        # Build the single unified section
        buttons_html = "\n".join(all_tab_buttons)
        contents_html = "\n".join(all_tab_contents)

        return f"""        <div class="section">
            <h2>Quarantined Tests Details</h2>

            <div class="tabs">
{buttons_html}
            </div>

{contents_html}
        </div>

"""


def generate_json_output(repo_stats: dict[str, list[VersionStats]]) -> str:
    """Generate JSON output with all quarantine statistics.

    Args:
        repo_stats: Dict mapping repository names to list of VersionStats for each branch.

    Returns:
        JSON string with complete quarantine statistics.

    """
    output: dict = {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "repositories": {},
    }

    for repo, version_stats_list in repo_stats.items():
        repo_data: dict = {"versions": {}}

        for version_stat in version_stats_list:
            stats = version_stat.stats
            total = stats.total_tests
            active = stats.active_tests
            quarantined = stats.quarantined_tests
            health_percent = round((active / total * 100), 1) if total > 0 else 0.0

            # Build teams breakdown
            teams_data: dict[str, dict[str, int]] = {}
            for team, counts in stats.category_breakdown.items():
                teams_data[team.replace("_", " ").title()] = {
                    "total": counts["total"],
                    "active": counts["active"],
                    "quarantined": counts["quarantined"],
                }

            # Build quarantined tests list
            quarantined_tests: list[dict] = []
            for test in stats.quarantined_list:
                quarantined_tests.append({
                    "name": test.name,
                    "file": get_display_path(file_path=test.file_path),
                    "line": test.line_number,
                    "team": test.category.replace("_", " ").title(),
                    "jira": test.jira_ticket,
                    "reason": test.quarantine_reason,
                })

            repo_data["versions"][version_stat.branch] = {
                "total": total,
                "active": active,
                "quarantined": quarantined,
                "health_percent": health_percent,
                "teams": teams_data,
                "quarantined_tests": quarantined_tests,
            }

        output["repositories"][repo] = repo_data

    return json_dumps(obj=output, indent=2)


def parse_args() -> Namespace:
    """Parse command line arguments.

    Returns:
        Parsed arguments namespace.

    """
    parser = ArgumentParser(
        description="Tier2 Quarantine Status Dashboard Generator",
        formatter_class=RawDescriptionHelpFormatter,
        epilog="""
Scans both repositories (RedHatQE/openshift-virtualization-tests, RedHatQE/cnv-tests)
across all valid branches (main and cnv-X.Y versions).

Examples:
    # Scan both repos, all versions (default behavior)
    python generate_dashboard.py

    # Keep cloned repos after completion
    python generate_dashboard.py --keep-clones

    # Output as JSON instead of HTML
    python generate_dashboard.py --json

    # Use custom directories
    python generate_dashboard.py --workdir /path/to/clones --output-dir /path/to/output

    # Run from container (using entry point defined in pyproject.toml)
    podman run --rm -e GITHUB_TOKEN="${GITHUB_TOKEN}" \\
        -v $(pwd)/output:/openshift-virtualization-tests/output:Z \\
        cnv-tests:latest uv run quarantine-dashboard --output-dir /openshift-virtualization-tests/output
        """,
    )
    parser.add_argument(
        "--keep-clones",
        action="store_true",
        help="Keep cloned repositories after completion (default: cleanup)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output JSON instead of HTML dashboard",
    )
    parser.add_argument(
        "--workdir",
        type=Path,
        default=WORKDIR,
        help=f"Directory to clone repos into (default: {WORKDIR})",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory to save output files (default: script directory)",
    )
    parser.add_argument(
        "--github-token",
        type=str,
        default=None,
        help="GitHub personal access token for cloning private repositories. "
        "If not provided, falls back to GITHUB_TOKEN environment variable.",
    )
    return parser.parse_args()


def run_multi_repo_mode(
    *,
    keep_clones: bool,
    output_file: Path,
    json_output: bool = False,
    workdir: Path = WORKDIR,
    github_token: str | None = None,
) -> int:
    """Run dashboard generator in multi-repository mode.

    Clones repositories, scans all branches, and generates a combined dashboard or JSON output.

    Args:
        keep_clones: Whether to keep cloned repositories after completion.
        output_file: Path to write the dashboard HTML file (ignored if json_output is True).
        json_output: If True, output JSON to stdout instead of generating HTML dashboard.
        workdir: Directory to clone repos into.
        github_token: Optional GitHub personal access token for cloning private repos.

    Returns:
        Exit code: 0 on success, 1 on error.

    """
    LOGGER.info("Mode: Multi-Repository (all versions)")
    LOGGER.info("Repositories: %s", ", ".join(REPOS))
    LOGGER.info("Working directory: %s", workdir)

    # Scan all repos and all branches
    repo_stats = scan_all_repos(repos=REPOS, workdir=workdir, branch_filter=None, github_token=github_token)

    if not repo_stats:
        LOGGER.error("No repositories could be scanned.")
        return 1

    # Handle JSON output mode
    if json_output:
        json_content = generate_json_output(repo_stats=repo_stats)
        output_file.write_text(data=json_content, encoding="utf-8")
        LOGGER.info("JSON output generated: %s", output_file)

        # Cleanup unless --keep-clones was specified
        if not keep_clones:
            cleanup_workdir(workdir=workdir)
        else:
            LOGGER.info("Cloned repositories preserved at: %s", workdir)

        return 0

    # Display CLI output with unified version summary table
    LOGGER.info("=" * 60)
    LOGGER.info("Summary by Repository and Version")
    LOGGER.info("=" * 60)

    # Print unified version summary table (single table for all repos)
    version_summary = format_unified_version_table(repo_stats=repo_stats)
    LOGGER.info("%s", version_summary)

    # Print unified team breakdown with all repos/versions as columns
    LOGGER.info("=" * 60)
    team_breakdown = format_team_breakdown_by_version(repo_stats=repo_stats)
    LOGGER.info("%s", team_breakdown)

    # Determine primary stats for dashboard header (first repo, first branch)
    first_repo = next(iter(repo_stats))
    first_version_stats = repo_stats[first_repo][0]
    primary_stats = first_version_stats.stats
    primary_branch = first_version_stats.branch

    # Generate dashboard
    LOGGER.info("Generating dashboard...")
    generator = DashboardGenerator(
        stats=primary_stats,
        branch=primary_branch,
        repo_stats=repo_stats,
    )
    dashboard_content = generator.generate()

    # Write output
    output_file.write_text(data=dashboard_content, encoding="utf-8")
    LOGGER.info("Dashboard generated: %s", output_file)

    # Cleanup unless --keep-clones was specified
    if not keep_clones:
        cleanup_workdir(workdir=workdir)
    else:
        LOGGER.info("Cloned repositories preserved at: %s", workdir)

    return 0


def main() -> int:
    """Main entry point for the dashboard generator.

    Scans both repositories across all valid branches (main and cnv-X.Y),
    generates an HTML dashboard or JSON output, and writes to the output directory.

    Returns:
        Exit code: 0 on success, 1 on error.

    """
    args = parse_args()

    # Determine output file path based on format
    output_dir = args.output_dir or Path(__file__).parent
    if args.json_output:
        output_file = output_dir / "dashboard.json"
    else:
        output_file = output_dir / "dashboard.html"

    # Resolve GitHub token: CLI argument takes precedence over environment variable
    github_token = args.github_token or environ.get("GITHUB_TOKEN")

    LOGGER.info("Tier2 Quarantine Status Dashboard Generator")
    LOGGER.info("=" * 60)

    return run_multi_repo_mode(
        keep_clones=args.keep_clones,
        output_file=output_file,
        json_output=args.json_output,
        workdir=args.workdir,
        github_token=github_token,
    )


if __name__ == "__main__":
    raise SystemExit(main())

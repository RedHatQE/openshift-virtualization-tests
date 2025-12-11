"""
*This document was created with the assistance of Claude (Anthropic).*

OpenShift Virtualization Test Dashboard Generator

Scans the tests/ directory for Python test files, counts test functions,
identifies quarantined tests, and generates an HTML dashboard.

Usage:
    python stats/generate_dashboard.py

Output:
    Generates stats/dashboard.html with test statistics.

Configuration:
    - EXCLUDED_FOLDERS: Folders to exclude from the report
    - FOLDER_MAPPINGS: Map folder names to team names (e.g., data_protection -> storage)
"""

import ast
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, NamedTuple


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
    category_breakdown: Dict[str, Dict[str, int]]
    quarantined_list: List[TestInfo]


class TestScanner:
    """Scanner for Python test files to detect quarantined tests.

    Scans test files using AST parsing to find test functions and detects
    quarantine markers using regex patterns on decorator blocks.

    Attributes:
        EXCLUDED_FOLDERS: Set of folder names to exclude from scanning.
        FOLDER_MAPPINGS: Dict mapping source folders to target team names.
    """

    # Folders to exclude from the report
    EXCLUDED_FOLDERS = {"after_cluster_deploy_sanity", "deprecated_api"}

    # Folder mappings (source -> target) for combining stats
    FOLDER_MAPPINGS = {"data_protection": "storage", "cross_cluster_live_migration": "storage"}

    def __init__(self, tests_dir: Path):
        """Initialize the scanner.

        Args:
            tests_dir: Path to the tests/ directory to scan.
        """
        self.tests_dir = tests_dir
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

        self.quarantine_patterns = [
            re.compile(pattern=_paren_pattern, flags=re.MULTILINE | re.DOTALL),
            re.compile(pattern=_no_paren_pattern, flags=re.MULTILINE | re.DOTALL),
            re.compile(pattern=_simple_pattern, flags=re.MULTILINE | re.DOTALL),
        ]
        self.jira_pattern = re.compile(r"CNV-\d+")

    def scan_all_tests(self) -> DashboardStats:
        """Scan all test files and return aggregated statistics.

        Recursively finds all test_*.py files under the tests directory,
        parses each file to extract test functions, and identifies
        quarantined tests.

        Returns:
            DashboardStats containing total counts, category breakdown,
            and list of quarantined tests.
        """
        all_tests: List[TestInfo] = []

        test_files = list(self.tests_dir.rglob("test_*.py"))

        for test_file in test_files:
            try:
                tests = self._scan_file(file_path=test_file)
                all_tests.extend(tests)
            except Exception as e:
                print(f"Warning: Error scanning {test_file}: {e}")

        return self._calculate_stats(all_tests=all_tests)

    def _scan_file(self, file_path: Path) -> List[TestInfo]:
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
        tests: List[TestInfo] = []

        try:
            content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return tests

        # Determine category from file path
        category = self._get_category(file_path=file_path)

        # Skip excluded categories
        if category is None:
            return tests

        try:
            tree = ast.parse(source=content, filename=str(file_path))
        except SyntaxError:
            return tests

        quarantined_classes: Dict[str, tuple[str, str]] = {}

        # First pass: identify quarantined classes
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                is_quarantined, reason, jira = self._check_quarantine(content=content, line_number=node.lineno)
                if is_quarantined:
                    quarantined_classes[node.name] = (reason, jira)

        # Second pass: find all test functions
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
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

    def _get_parent_class(self, tree: ast.AST, func_node: ast.FunctionDef) -> str | None:
        """Find the parent class of a function node, if any.

        Args:
            tree: The AST tree of the parsed file.
            func_node: The function node to find the parent class for.

        Returns:
            The class name if the function is inside a class, None otherwise.
        """
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for child in ast.walk(node):
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
        parts = file_path.relative_to(self.tests_dir).parts  # noqa: FCN001
        if len(parts) > 0:
            category = parts[0]

            if category in self.EXCLUDED_FOLDERS:
                return None

            category = self.FOLDER_MAPPINGS.get(category, category)

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
        for i in range(line_number - 2, max(0, line_number - 50) - 1, -1):
            line = lines[i].strip()
            if not line:
                # Blank line - stop searching (decorators must be contiguous)
                break
            if line.startswith("@") or line.startswith("def ") or line.startswith("class "):
                # Part of decorator block or we hit the function/class def
                decorator_lines.insert(0, lines[i])
            elif line.startswith(")") or line.startswith("(") or line.endswith(",") or line.endswith("("):
                # Continuation of multi-line decorator
                decorator_lines.insert(0, lines[i])
            elif "pytest.param" in line or "marks=" in line or "indirect=" in line:
                # Part of parametrize
                decorator_lines.insert(0, lines[i])
            elif line.startswith('"') or line.startswith("'") or line.startswith('f"') or line.startswith("f'"):
                # String continuation
                decorator_lines.insert(0, lines[i])
            elif "{" in line or "}" in line or "[" in line or "]" in line:
                # Dict/list in decorator
                decorator_lines.insert(0, lines[i])
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
            reason_match = re.search(r'QUARANTINED[}"\']?:\s*([^"\']+)', decorator_section)
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

    def _calculate_stats(self, all_tests: List[TestInfo]) -> DashboardStats:
        """Calculate aggregated statistics from list of tests.

        Groups tests by category and counts active vs quarantined tests.

        Args:
            all_tests: List of all TestInfo objects from scanning.

        Returns:
            DashboardStats with totals, breakdowns, and quarantined list.
        """
        total_tests = len(all_tests)
        quarantined_tests = [t for t in all_tests if t.is_quarantined]
        active_tests = total_tests - len(quarantined_tests)

        # Category breakdown
        category_breakdown: Dict[str, Dict[str, int]] = defaultdict(lambda: {"total": 0, "active": 0, "quarantined": 0})
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
            quarantined_list=sorted(quarantined_tests, key=lambda t: t.category),
        )


class DashboardGenerator:
    """Generator for HTML dashboard output.

    Creates a styled HTML page with summary cards, progress bar,
    team breakdown table, and detailed quarantined tests section.
    """

    def __init__(self, stats: DashboardStats):
        """Initialize the generator.

        Args:
            stats: DashboardStats containing all test statistics.
        """
        self.stats = stats

    def generate(self) -> str:
        """Generate the complete HTML dashboard.

        Creates a self-contained HTML page with embedded CSS styling.
        Includes summary statistics, visual progress bar, team breakdown
        table, and detailed quarantined tests section.

        Returns:
            Complete HTML document as a string.
        """
        active_pct = (self.stats.active_tests / self.stats.total_tests * 100) if self.stats.total_tests > 0 else 0
        quarantined_pct = (
            (self.stats.quarantined_tests / self.stats.total_tests * 100) if self.stats.total_tests > 0 else 0
        )
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OpenShift Virtualization Test Dashboard</title>
    <style>
        :root {{
            --green: #22c55e;
            --yellow: #eab308;
            --red: #ef4444;
            --blue: #3b82f6;
            --gray: #6b7280;
            --light-gray: #f3f4f6;
            --dark: #1f2937;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: var(--light-gray);
            color: var(--dark);
            line-height: 1.6;
            padding: 2rem;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        h1 {{
            text-align: center;
            margin-bottom: 2rem;
            color: var(--dark);
        }}
        .cards {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }}
        .card {{
            background: white;
            border-radius: 8px;
            padding: 1.5rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            text-align: center;
        }}
        .card h3 {{ color: var(--gray); font-size: 0.875rem; text-transform: uppercase; }}
        .card .value {{ font-size: 2.5rem; font-weight: bold; margin: 0.5rem 0; }}
        .card .percent {{ color: var(--gray); }}
        .card.total .value {{ color: var(--blue); }}
        .card.active .value {{ color: var(--green); }}
        .card.quarantined .value {{ color: var(--red); }}
        .progress-container {{
            background: white;
            border-radius: 8px;
            padding: 1.5rem;
            margin-bottom: 2rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        .progress-bar {{
            height: 24px;
            background: var(--light-gray);
            border-radius: 12px;
            overflow: hidden;
            display: flex;
        }}
        .progress-bar .active {{ background: var(--green); }}
        .progress-bar .quarantined {{ background: var(--red); }}
        .section {{
            background: white;
            border-radius: 8px;
            padding: 1.5rem;
            margin-bottom: 2rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        .section h2 {{ margin-bottom: 1rem; color: var(--dark); }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 0.75rem; text-align: left; border-bottom: 1px solid var(--light-gray); }}
        th {{ background: var(--light-gray); font-weight: 600; }}
        tr:hover {{ background: #f9fafb; }}
        .health {{ font-weight: bold; }}
        .health.green {{ color: var(--green); }}
        .health.yellow {{ color: var(--yellow); }}
        .health.red {{ color: var(--red); }}
        .team-header {{
            background: var(--light-gray);
            padding: 0.75rem 1rem;
            margin: 1rem 0 0.5rem;
            border-radius: 4px;
            font-weight: 600;
        }}
        .test-item {{
            padding: 0.75rem 1rem;
            border-left: 3px solid var(--red);
            margin-bottom: 0.5rem;
            background: #fef2f2;
        }}
        .test-item code {{ background: #fee2e2; padding: 0.125rem 0.375rem; border-radius: 4px; font-size: 0.875rem; }}
        .test-item a {{ color: var(--blue); text-decoration: none; }}
        .test-item a:hover {{ text-decoration: underline; }}
        .test-item .meta {{ color: var(--gray); font-size: 0.875rem; margin-top: 0.25rem; }}
        .note {{
            background: #eff6ff;
            border-left: 3px solid var(--blue);
            padding: 0.75rem 1rem;
            margin-top: 1rem;
            font-size: 0.875rem;
            color: var(--gray);
        }}
        .footer {{
            text-align: center;
            color: var(--gray);
            font-size: 0.875rem;
            margin-top: 2rem;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>OpenShift Virtualization Test Dashboard</h1>

        <div class="cards">
            <div class="card total">
                <h3>Total Tests</h3>
                <div class="value">{self.stats.total_tests:,}</div>
                <div class="percent">100%</div>
            </div>
            <div class="card active">
                <h3>Active Tests</h3>
                <div class="value">{self.stats.active_tests:,}</div>
                <div class="percent">{active_pct:.1f}%</div>
            </div>
            <div class="card quarantined">
                <h3>Quarantined Tests</h3>
                <div class="value">{self.stats.quarantined_tests:,}</div>
                <div class="percent">{quarantined_pct:.1f}%</div>
            </div>
        </div>

        <div class="progress-container">
            <h3 style="margin-bottom: 0.5rem;">Test Health</h3>
            <div class="progress-bar">
                <div class="active" style="width: {active_pct}%;"></div>
                <div class="quarantined" style="width: {quarantined_pct}%;"></div>
            </div>
        </div>

        <div class="section">
            <h2>Breakdown by Team</h2>
            <table>
                <thead>
                    <tr>
                        <th>Team</th>
                        <th>Total</th>
                        <th>Active</th>
                        <th>Quarantined</th>
                        <th>Health</th>
                    </tr>
                </thead>
                <tbody>
{self._generate_team_rows()}
                </tbody>
            </table>
            <div class="note">
                Team is determined by the top-level folder under <code>tests/</code>.
                Counts are based on test functions; parametrized tests are counted as single functions.
            </div>
        </div>

        <div class="section">
            <h2>Quarantined Tests Details</h2>
{self._generate_quarantined_html()}
        </div>

        <div class="footer">
            Last updated: {timestamp}<br>
            Generated by generate_dashboard.py
        </div>
    </div>
</body>
</html>"""

    def _generate_team_rows(self) -> str:
        """Generate HTML table rows for team breakdown.

        Creates table rows sorted by total test count (descending).
        Each row includes team name, counts, and health indicator
        (green=100%, yellow>=95%, red<95%).

        Returns:
            HTML string containing all <tr> elements.
        """
        rows = []
        sorted_categories = sorted(self.stats.category_breakdown.items(), key=lambda x: x[1]["total"], reverse=True)

        for category, counts in sorted_categories:
            total = counts["total"]
            active = counts["active"]
            quarantined = counts["quarantined"]
            active_pct = (active / total * 100) if total > 0 else 0
            category_display = category.replace("_", " ").title()

            if active_pct == 100:
                health_class = "green"
                health_text = "100%"
            elif active_pct >= 95:
                health_class = "yellow"
                health_text = f"{active_pct:.1f}%"
            else:
                health_class = "red"
                health_text = f"{active_pct:.1f}%"

            rows.append(f"""                    <tr>
                        <td>{category_display}</td>
                        <td>{total:,}</td>
                        <td>{active:,}</td>
                        <td>{quarantined:,}</td>
                        <td><span class="health {health_class}">{health_text}</span></td>
                    </tr>""")

        return "\n".join(rows)

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

        by_category: Dict[str, List[TestInfo]] = defaultdict(list)
        for test in self.stats.quarantined_list:
            by_category[test.category].append(test)

        for category in sorted(by_category.keys()):
            tests = by_category[category]
            category_display = category.replace("_", " ").title()
            test_count = len(tests)
            plural = "s" if test_count > 1 else ""
            lines.append(
                f'            <div class="team-header">📁 {category_display} ({test_count} test{plural})</div>'
            )

            for test in sorted(tests, key=lambda t: t.name):
                rel_path = test.file_path.relative_to(Path.cwd())  # noqa: FCN001
                jira_link = f"https://issues.redhat.com/browse/{test.jira_ticket}"
                jira_html = (
                    f' <a href="{jira_link}" target="_blank">[{test.jira_ticket}]</a>'
                    if test.jira_ticket
                    else ' <span style="color: var(--yellow);">⚠️ No Jira ticket</span>'
                )
                reason_html = (
                    f'<br><span class="meta">Reason: {test.quarantine_reason}</span>' if test.quarantine_reason else ""
                )

                lines.append(f"""            <div class="test-item">
                <code>{test.name}</code>{jira_html}
                <div class="meta">File: {rel_path}:{test.line_number}</div>{reason_html}
            </div>""")

        return "\n".join(lines)


def main() -> int:
    """Main entry point for the dashboard generator.

    Scans the tests/ directory, calculates statistics, generates
    an HTML dashboard, and writes it to stats/dashboard.html.

    Returns:
        Exit code: 0 on success, 1 if tests directory not found.
    """
    # Determine paths
    script_dir = Path(__file__).parent  # noqa: FCN001
    project_root = script_dir.parent
    tests_dir = project_root / "tests"
    output_file = script_dir / "dashboard.html"

    print("OpenShift Virtualization Test Dashboard Generator")
    print("=" * 60)
    print(f"Tests directory: {tests_dir}")
    print(f"Output file: {output_file}")
    print()

    # Validate paths
    if not tests_dir.exists():
        print(f"Error: Tests directory not found: {tests_dir}")
        return 1

    # Scan tests
    print("Scanning test files...")
    scanner = TestScanner(tests_dir=tests_dir)
    stats = scanner.scan_all_tests()

    # Display summary
    print()
    print(f"Total tests found: {stats.total_tests:,}")
    print(f"Active tests: {stats.active_tests:,}")
    print(f"Quarantined tests: {stats.quarantined_tests:,}")
    print(f"Categories: {len(stats.category_breakdown)}")
    print()

    # Generate dashboard
    print("Generating dashboard...")
    generator = DashboardGenerator(stats=stats)
    dashboard_content = generator.generate()

    # Write output
    output_file.write_text(data=dashboard_content, encoding="utf-8")
    print(f"✅ Dashboard generated: {output_file}")
    print()

    return 0


if __name__ == "__main__":
    exit(main())

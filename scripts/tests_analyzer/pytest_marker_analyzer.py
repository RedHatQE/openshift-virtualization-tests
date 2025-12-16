#!/usr/bin/env -S uv run python

# Generated using Claude cli

# flake8: noqa: N802

"""
Pytest Marker Analyzer

Analyzes PR changes to determine if tests with specific markers should run
based on static dependency analysis.

For full documentation, see README.md in this directory.

Quick usage:
    uv run python scripts/test_analyzer/pytest_marker_analyzer.py --help
"""

from __future__ import annotations

import argparse
import ast
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from simple_logger.logger import get_logger

# Configure logging
logger = get_logger(name=__name__, level=logging.INFO)

# Constants
GITHUB_API_MAX_PER_PAGE = 100
GITHUB_API_TIMEOUT_SECONDS = 30
MAX_RESPONSE_SIZE = 10 * 1024 * 1024  # 10MB
PYTEST_COLLECTION_TIMEOUT_SECONDS = 300  # 5 minutes instead of 60
MAX_TRANSITIVE_IMPORT_DEPTH = 2
MAX_CONFTEST_SEARCH_ITERATIONS = 100
REPORT_TIMEOUT_SECONDS = 10
MAX_FILES_PER_PR = 10000

# Parallelization settings
MAX_WORKERS = min(32, (os.cpu_count() or 1) + 4)


def validate_repo_name(repo: str) -> None:
    """Validate GitHub repo name format strictly.

    Args:
        repo: Repository in owner/repo format

    Raises:
        ValueError: If repo format is invalid or contains dangerous characters
    """
    if "/" not in repo or repo.count("/") != 1:
        raise ValueError(f"Invalid repo format: {repo}. Expected 'owner/repo'")

    # Check for valid characters only (alphanumeric, dash, underscore, dot)
    if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*/[a-zA-Z0-9][a-zA-Z0-9._-]*$", repo):
        raise ValueError(f"Invalid repo format: {repo}. Contains invalid characters")

    # Reject shell metacharacters that could enable command injection
    dangerous_chars = ["`", "$", "|", "&", ";", "\n", "\r", "\\", '"', "'", "<", ">", "(", ")"]
    if any(char in repo for char in dangerous_chars):
        raise ValueError(f"Invalid characters in repo name: {repo}")


def cleanup_temp_dir(temp_dir: str | None) -> None:
    """Clean up temporary directory if it exists."""
    if temp_dir:
        try:
            shutil.rmtree(path=temp_dir)
            logger.info(msg="Cleaned up temporary directory", extra={"temp_dir": temp_dir})
        except OSError as e:
            logger.warning(msg="Failed to clean up temporary directory", extra={"temp_dir": temp_dir, "error": str(e)})


def _handle_github_api_error(e: urllib.error.HTTPError, context: str = "") -> None:
    """Handle common GitHub API errors with appropriate messages."""
    error_body = ""
    try:
        error_body = e.read().decode()
    except (OSError, UnicodeDecodeError):  # fmt: skip
        logger.info(msg="Failed to read GitHub API error body")

    if e.code == 401:
        raise RuntimeError(
            "GitHub API authentication failed. Please provide a valid token via "
            "--github-token or GITHUB_TOKEN environment variable"
        ) from e
    elif e.code == 403:
        if "rate limit" in error_body.lower():
            raise RuntimeError(
                "GitHub API rate limit exceeded. Please provide authentication token via "
                "--github-token or GITHUB_TOKEN environment variable to increase rate limits"
            ) from e
        raise RuntimeError(f"GitHub API forbidden (403): {error_body}") from e
    elif e.code == 404:
        raise RuntimeError(f"{context} not found (404): {error_body}") from e
    else:
        raise RuntimeError(f"GitHub API error: {e.code} {e.reason}\n{error_body}") from e


def get_pr_info(repo: str, pr_number: int, token: str | None = None) -> dict[str, Any]:
    """Get PR information including base branch.

    Args:
        repo: Repository in owner/repo format
        pr_number: PR number
        token: Optional GitHub token for authentication

    Returns:
        Dictionary with PR info including 'base_ref' field

    Raises:
        ValueError: If repo format is invalid or PR number is invalid
        RuntimeError: If GitHub API request fails
    """
    validate_repo_name(repo=repo)

    if pr_number <= 0:
        raise ValueError(f"Invalid PR number: {pr_number}. Must be positive integer")

    url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}"

    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "pytest-marker-analyzer",
    }
    if token:
        headers["Authorization"] = f"token {token}"

    request = urllib.request.Request(url, headers=headers)

    try:
        logger.info(msg="Fetching PR info")
        with urllib.request.urlopen(request, timeout=GITHUB_API_TIMEOUT_SECONDS) as response:
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > MAX_RESPONSE_SIZE:
                raise RuntimeError(f"Response too large: {content_length} bytes (max: {MAX_RESPONSE_SIZE})")

            data = json.loads(response.read().decode())
            return {
                "base_ref": data["base"]["ref"],
                "head_ref": data["head"]["ref"],
                "number": data["number"],
            }

    except urllib.error.HTTPError as e:
        _handle_github_api_error(e=e, context=f"PR {repo}#{pr_number}")

    except urllib.error.URLError as e:
        raise RuntimeError(f"Failed to connect to GitHub API: {e}") from e
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse GitHub API response: {e}") from e


def get_pr_changed_files(repo: str, pr_number: int, token: str | None = None) -> list[str]:
    """Get list of changed files from a GitHub PR (handles pagination).

    Args:
        repo: Repository in owner/repo format
        pr_number: PR number
        token: Optional GitHub token for authentication

    Returns:
        List of file paths changed in the PR

    Raises:
        ValueError: If repo format is invalid or PR number is invalid
        RuntimeError: If GitHub API request fails
    """
    # Validate inputs
    validate_repo_name(repo=repo)

    # Validate PR number
    if pr_number <= 0:
        raise ValueError(f"Invalid PR number: {pr_number}. Must be positive integer")

    files = []
    page = 1
    per_page = GITHUB_API_MAX_PER_PAGE

    while True:
        url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}/files?per_page={per_page}&page={page}"

        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "pytest-marker-analyzer",
        }
        if token:
            headers["Authorization"] = f"token {token}"

        request = urllib.request.Request(url, headers=headers)

        try:
            logger.info(msg="Fetching PR files page", extra={"page": page})
            with urllib.request.urlopen(request, timeout=GITHUB_API_TIMEOUT_SECONDS) as response:
                # Check response size to prevent memory exhaustion
                content_length = response.headers.get("Content-Length")
                if content_length and int(content_length) > MAX_RESPONSE_SIZE:
                    raise RuntimeError(f"Response too large: {content_length} bytes (max: {MAX_RESPONSE_SIZE})")

                data = json.loads(response.read().decode())
                page_files = [file["filename"] for file in data]
                files.extend(page_files)

                if len(files) >= MAX_FILES_PER_PR:
                    logger.warning(msg="PR has many files, truncating for safety", extra={"file_count": len(files)})
                    break

                logger.info(msg="Fetched PR files page", extra={"page": page, "file_count": len(page_files)})

                # Check if we've fetched all pages
                if len(page_files) < per_page:
                    break

                page += 1

        except urllib.error.HTTPError as e:
            _handle_github_api_error(e=e, context=f"PR {repo}#{pr_number} files")

        except urllib.error.URLError as e:
            raise RuntimeError(f"Failed to connect to GitHub API: {e}") from e
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Failed to parse GitHub API response: {e}") from e

    logger.info(msg="Fetched changed files from PR", extra={"file_count": len(files), "pr_number": pr_number})
    return files


def get_pr_file_diff(repo: str, pr_number: int, file_path: str, token: str | None = None) -> str:
    """Get the diff content for a specific file in a PR from GitHub API.

    Args:
        repo: Repository in owner/repo format
        pr_number: PR number
        file_path: Path to the file to get diff for
        token: Optional GitHub token

    Returns:
        The unified diff content as a string (patch field from GitHub API)
    """
    validate_repo_name(repo=repo)
    if pr_number <= 0:
        raise ValueError(f"Invalid PR number: {pr_number}. Must be positive integer")

    url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}/files"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "pytest-marker-analyzer",
    }
    if token:
        headers["Authorization"] = f"token {token}"

    # Note: This function fetches all files but only returns diff for requested file.
    # For better efficiency with many files, could implement caching at caller level.
    page = 1
    per_page = GITHUB_API_MAX_PER_PAGE

    while True:
        paginated_url = f"{url}?per_page={per_page}&page={page}"
        request = urllib.request.Request(paginated_url, headers=headers)

        try:
            with urllib.request.urlopen(request, timeout=GITHUB_API_TIMEOUT_SECONDS) as response:
                content_length = response.headers.get("Content-Length")
                if content_length and int(content_length) > MAX_RESPONSE_SIZE:
                    raise RuntimeError(f"Response too large: {content_length} bytes")

                files = json.loads(response.read().decode())

                for file in files:
                    if file["filename"] == file_path:
                        # GitHub provides patch content in the 'patch' field
                        return file.get("patch", "")

                # Check if we've fetched all pages
                if len(files) < per_page:
                    break

                page += 1

        except urllib.error.HTTPError as e:
            logger.warning(msg="Failed to get PR diff for file", extra={"file_path": file_path, "http_code": e.code})
            return ""
        except (urllib.error.URLError, json.JSONDecodeError, OSError) as e:  # fmt: skip
            logger.warning(msg="Failed to get PR diff for file", extra={"file_path": file_path, "error": str(e)})
            return ""

    return ""


def checkout_pr(repo: str, pr_number: int, workdir: Path, token: str | None = None) -> bool:
    """Clone repository and checkout PR head.

    Args:
        repo: Repository in owner/repo format
        pr_number: PR number
        workdir: Directory to clone into
        token: Optional GitHub token for authentication

    Returns:
        True if checkout successful

    Raises:
        RuntimeError: If git operations fail
    """
    validate_repo_name(repo=repo)
    logger.info(msg="Checking out PR from repository", extra={"pr_number": pr_number, "repo": repo})

    # Construct clone URL with authentication
    env = os.environ.copy()
    if token:
        # Embed token in URL for authentication
        clone_url = f"https://x-access-token:{token}@github.com/{repo}.git"
        env["GIT_TERMINAL_PROMPT"] = "0"
    else:
        clone_url = f"https://github.com/{repo}.git"

    try:
        # Clone repository with depth=1 for speed
        logger.info(msg="Cloning repository", extra={"repo": repo, "workdir": str(workdir)})
        subprocess.run(
            ["git", "clone", "--depth=1", clone_url, str(workdir)],
            capture_output=True,
            text=True,
            check=True,
            timeout=300,  # 5 minute timeout
            env=env,
        )

        # Fetch PR head
        logger.info(msg="Fetching PR head", extra={"pr_number": pr_number})
        subprocess.run(
            ["git", "-C", str(workdir), "fetch", "origin", f"pull/{pr_number}/head:pr-{pr_number}"],
            capture_output=True,
            text=True,
            check=True,
            timeout=120,
            env=env,
        )

        # Checkout PR branch
        logger.info(msg="Checking out PR branch...")
        subprocess.run(
            ["git", "-C", str(workdir), "checkout", f"pr-{pr_number}"],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
            env=env,
        )

        logger.info(msg="Checkout successful")
        return True

    except subprocess.CalledProcessError as e:
        stderr = e.stderr if hasattr(e, "stderr") else ""
        # Sanitize any token from error message
        stderr = re.sub(r"://[^@]*@", "://<redacted>@", stderr)
        raise RuntimeError(f"Git operation failed: {e}\n{stderr}") from e
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"Git operation timed out: {e}") from e


def extract_marker_names(marker_expression: str) -> set[str]:
    """Extract marker names from a pytest marker expression.

    Args:
        marker_expression: Pytest marker expression (e.g., "smoke and not slow")

    Returns:
        Set of marker names found in the expression

    Examples:
        >>> extract_marker_names("smoke")
        {'smoke'}
        >>> extract_marker_names("smoke and sanity")
        {'smoke', 'sanity'}
        >>> extract_marker_names("smoke and not slow")
        {'smoke', 'slow'}
        >>> extract_marker_names("(smoke or sanity) and not slow")
        {'smoke', 'sanity', 'slow'}
    """
    # Remove parentheses and split by operators
    # Extract word tokens that could be markers (exclude: and, or, not)
    tokens = re.findall(pattern=r"\b\w+\b", string=marker_expression)
    # Filter out boolean operators
    operators = {"and", "or", "not"}
    return {token for token in tokens if token not in operators}


def is_marker(decorator: ast.AST, marker_names: set[str]) -> bool:
    """Check if decorator is pytest.mark.<marker> for any of the specified marker names.

    Args:
        decorator: AST node representing a decorator
        marker_names: Set of marker names to check for (extracted from marker expression)

    Returns:
        True if decorator matches any of the specified marker names
    """
    if isinstance(decorator, ast.Attribute):
        if isinstance(decorator.value, ast.Attribute):
            return (
                isinstance(decorator.value.value, ast.Name)
                and decorator.value.value.id == "pytest"
                and decorator.value.attr == "mark"
                and decorator.attr in marker_names
            )
    elif isinstance(decorator, ast.Call):
        return is_marker(decorator=decorator.func, marker_names=marker_names)
    return False


def check_pytestmark_assignment(node: ast.Assign, marker_names: set[str]) -> bool:
    """Check if an assignment is pytestmark with one of the specified markers.

    Handles both single marker and list of markers:
        pytestmark = pytest.mark.smoke
        pytestmark = [pytest.mark.smoke, pytest.mark.gating]

    Args:
        node: AST assignment node
        marker_names: Set of marker names to check for

    Returns:
        True if assignment is pytestmark with any of the specified markers
    """
    # Check if this is a pytestmark assignment
    if not (len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)):
        return False

    if node.targets[0].id != "pytestmark":
        return False

    # Check the value being assigned
    value = node.value

    # Case 1: pytestmark = pytest.mark.smoke
    if is_marker(decorator=value, marker_names=marker_names):
        return True

    # Case 2: pytestmark = [pytest.mark.smoke, pytest.mark.gating, ...]
    if isinstance(value, ast.List):
        for element in value.elts:
            if is_marker(decorator=element, marker_names=marker_names):
                return True

    return False


def check_parametrize_marks(decorator: ast.AST, marker_names: set[str]) -> bool:
    """Check if a parametrize decorator has any pytest.param() with the specified markers.

    Handles pattern: @pytest.mark.parametrize(..., [pytest.param(..., marks=pytest.mark.smoke())])

    Args:
        decorator: AST decorator node (should be parametrize call)
        marker_names: Set of marker names to check for

    Returns:
        True if any pytest.param has the specified marker in its marks
    """
    # Check if this is @pytest.mark.parametrize
    if not isinstance(decorator, ast.Call):
        return False

    func = decorator.func
    if not isinstance(func, ast.Attribute):
        return False

    # Verify it's pytest.mark.parametrize
    if not (
        isinstance(func.value, ast.Attribute)
        and isinstance(func.value.value, ast.Name)
        and func.value.value.id == "pytest"
        and func.value.attr == "mark"
        and func.attr == "parametrize"
    ):
        return False

    # Check the arguments - typically (param_names, param_values)
    # param_values can be a list containing pytest.param() calls
    if len(decorator.args) < 2:
        return False

    param_values = decorator.args[1]

    # param_values should be a list or tuple
    if not isinstance(param_values, (ast.List, ast.Tuple)):
        return False

    # Check each element in the list for pytest.param(..., marks=...)
    for element in param_values.elts:
        if has_marker_in_param(node=element, marker_names=marker_names):
            return True

    return False


def has_marker_in_param(node: ast.AST, marker_names: set[str]) -> bool:
    """Check if a pytest.param() call has the specified marker in its marks argument.

    Args:
        node: AST node (should be pytest.param() call)
        marker_names: Set of marker names to check for

    Returns:
        True if pytest.param has the marker in marks
    """
    # Check if this is a pytest.param() call
    if not isinstance(node, ast.Call):
        return False

    func = node.func
    if not (
        isinstance(func, ast.Attribute)
        and isinstance(func.value, ast.Name)
        and func.value.id == "pytest"
        and func.attr == "param"
    ):
        return False

    # Look for marks keyword argument
    for keyword in node.keywords:
        if keyword.arg is not None and keyword.arg == "marks":
            # marks can be a single marker or a tuple of markers
            marks_value = keyword.value

            # Case 1: marks=pytest.mark.smoke()
            if is_marker(decorator=marks_value, marker_names=marker_names):
                return True

            # Case 2: marks=(pytest.mark.polarion(...), pytest.mark.smoke())
            if isinstance(marks_value, ast.Tuple):
                for mark in marks_value.elts:
                    if is_marker(decorator=mark, marker_names=marker_names):
                        return True

    return False


def extract_usefixtures_from_decorator(decorator: ast.AST) -> set[str]:
    """Extract fixture names from @pytest.mark.usefixtures decorator."""
    fixtures = set()

    # Check for @pytest.mark.usefixtures("fixture_name") pattern
    if isinstance(decorator, ast.Call):
        func = decorator.func
        if isinstance(func, ast.Attribute):
            if (
                isinstance(func.value, ast.Attribute)
                and isinstance(func.value.value, ast.Name)
                and func.value.value.id == "pytest"
                and func.value.attr == "mark"
                and func.attr == "usefixtures"
            ):
                # Extract fixture names from arguments
                for arg in decorator.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        fixtures.add(arg.value)

    return fixtures


@dataclass
class MarkedTest:
    """Represents a test with specified markers and its dependencies."""

    file_path: Path
    test_name: str
    node_id: str
    dependencies: set[Path] = field(default_factory=set)
    fixtures: set[str] = field(default_factory=set)


@dataclass
class AnalysisResult:
    """Results of marked test analysis."""

    should_run_tests: bool
    reason: str
    marker_expression: str
    affected_tests: list[dict[str, Any]]
    changed_files: list[str]
    total_tests: int


@dataclass
class Fixture:
    """Represents a fixture with its dependencies."""

    name: str
    file_path: Path
    fixture_deps: set[str] = field(default_factory=set)  # Other fixtures it uses
    function_calls: set[str] = field(default_factory=set)  # Functions it calls


class ImportVisitor(ast.NodeVisitor):
    """AST visitor to extract import statements from Python files."""

    def __init__(self) -> None:
        self.imports: set[str] = set()

    def visit_Import(self, node: ast.Import) -> None:
        """Visit import statements (import x)."""
        for alias in node.names:
            self.imports.add(alias.name.split(".")[0])

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Visit from-import statements (from x import y)."""
        if node.module:
            self.imports.add(node.module.split(".")[0])


class FixtureVisitor(ast.NodeVisitor):
    """AST visitor to extract fixture usage from test functions."""

    def __init__(self, marker_names: set[str]) -> None:
        self.fixtures: set[str] = set()
        self.marker_names = marker_names

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Visit function definitions to extract fixture parameters."""
        # Check for pytest.mark.<marker> decorator
        has_marker = False
        for decorator in node.decorator_list:
            if is_marker(decorator=decorator, marker_names=self.marker_names):
                has_marker = True
            # Extract fixtures from @pytest.mark.usefixtures decorator
            self.fixtures.update(extract_usefixtures_from_decorator(decorator=decorator))

        if has_marker or node.name.startswith("test_"):
            # Extract function parameters (fixtures)
            for arg in node.args.args:
                if arg.arg != "self":
                    self.fixtures.add(arg.arg)

        self.generic_visit(node=node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Visit class definitions to extract fixtures from class-level decorators."""
        # Check for class-level @pytest.mark.usefixtures decorator
        for decorator in node.decorator_list:
            self.fixtures.update(extract_usefixtures_from_decorator(decorator=decorator))

        self.generic_visit(node=node)


class FunctionCallVisitor(ast.NodeVisitor):
    """AST visitor to extract function calls from fixture bodies."""

    def __init__(self) -> None:
        self.function_calls: set[str] = set()

    def visit_Call(self, node: ast.Call) -> None:
        """Visit function calls."""
        # Extract function name
        if isinstance(node.func, ast.Name):
            self.function_calls.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            # For method calls like obj.method(), we track the method name
            self.function_calls.add(node.func.attr)

        self.generic_visit(node=node)


class FixtureDefinitionVisitor(ast.NodeVisitor):
    """AST visitor to extract fixture definitions and their dependencies."""

    def __init__(self) -> None:
        self.fixtures: dict[str, Fixture] = {}
        self.file_path: Path | None = None

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Visit function definitions to find fixtures."""
        # Check if function has @pytest.fixture decorator
        is_fixture = False
        for decorator in node.decorator_list:
            if self._is_fixture_decorator(decorator=decorator):
                is_fixture = True
                break

        if is_fixture:
            # Extract fixture dependencies (parameters)
            fixture_deps = set()
            for arg in node.args.args:
                if arg.arg not in ("self", "request"):
                    fixture_deps.add(arg.arg)

            # Extract function calls within fixture body
            call_visitor = FunctionCallVisitor()
            for stmt in node.body:
                call_visitor.visit(node=stmt)

            fixture = Fixture(
                name=node.name,
                file_path=self.file_path,
                fixture_deps=fixture_deps,
                function_calls=call_visitor.function_calls,
            )
            self.fixtures[node.name] = fixture

        self.generic_visit(node=node)

    def _is_fixture_decorator(self, decorator: ast.AST) -> bool:
        """Check if decorator is @pytest.fixture."""
        if isinstance(decorator, ast.Name):
            return decorator.id == "fixture"
        elif isinstance(decorator, ast.Attribute):
            return (
                isinstance(decorator.value, ast.Name) and decorator.value.id == "pytest" and decorator.attr == "fixture"
            )
        elif isinstance(decorator, ast.Call):
            return self._is_fixture_decorator(decorator=decorator.func)
        return False


def _process_test_file_for_markers(
    test_file: Path, marker_names: set[str], repo_root: Path
) -> list[tuple[str, str, Path]]:
    """Process a single test file to extract marked tests.

    Args:
        test_file: Path to test file
        marker_names: Set of marker names to look for
        repo_root: Repository root path

    Returns:
        List of tuples (node_id, test_name, file_path)
    """
    results = []
    try:
        source = test_file.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(test_file))

        # Check for module-level pytestmark assignment
        module_has_marker = False
        for node in tree.body:
            if isinstance(node, ast.Assign) and check_pytestmark_assignment(node=node, marker_names=marker_names):
                module_has_marker = True
                break

        tests = []
        if module_has_marker:
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.name.startswith("test_"):
                        tests.append(node.name)
                elif isinstance(node, ast.ClassDef):
                    for item in node.body:
                        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            if item.name.startswith("test_"):
                                tests.append(f"{node.name}::{item.name}")
        else:
            # Check class-level and method-level markers
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.name.startswith("test_"):
                        for decorator in node.decorator_list:
                            if is_marker(decorator=decorator, marker_names=marker_names):
                                tests.append(node.name)
                                break
                            elif check_parametrize_marks(decorator=decorator, marker_names=marker_names):
                                tests.append(node.name)
                                break
                elif isinstance(node, ast.ClassDef):
                    class_has_marker = False
                    for decorator in node.decorator_list:
                        if is_marker(decorator=decorator, marker_names=marker_names):
                            class_has_marker = True
                            break
                    if class_has_marker:
                        for item in node.body:
                            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                                if item.name.startswith("test_"):
                                    tests.append(f"{node.name}::{item.name}")
                    else:
                        for item in node.body:
                            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                                if item.name.startswith("test_"):
                                    for decorator in item.decorator_list:
                                        if is_marker(decorator=decorator, marker_names=marker_names):
                                            tests.append(f"{node.name}::{item.name}")
                                            break
                                        elif check_parametrize_marks(decorator=decorator, marker_names=marker_names):
                                            tests.append(f"{node.name}::{item.name}")
                                            break

        for test_name in tests:
            try:
                rel_path = test_file.relative_to(other=repo_root)
                node_id = f"{rel_path}::{test_name}"
                results.append((node_id, test_name, test_file))
            except ValueError:
                logger.info(msg="File path outside repository root", extra={"file": str(test_file)})

    except (SyntaxError, UnicodeDecodeError, OSError) as e:  # fmt: skip
        logger.info(msg="Skipping file due to parsing error", extra={"file": str(test_file), "error": str(e)})

    return results


def _process_conftest_file(conftest: Path) -> dict[str, Fixture]:
    """Process a single conftest file to extract fixtures.

    Args:
        conftest: Path to conftest.py file

    Returns:
        Dictionary of fixture name to Fixture object
    """
    fixtures = {}
    try:
        source = conftest.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(conftest))

        visitor = FixtureDefinitionVisitor()
        visitor.file_path = conftest
        visitor.visit(node=tree)
        fixtures = visitor.fixtures

    except (SyntaxError, UnicodeDecodeError, OSError) as e:  # fmt: skip
        logger.info(msg="Skipping conftest file due to parsing error", extra={"file": str(conftest), "error": str(e)})

    return fixtures


def _extract_imports_from_file(file_path: Path) -> set[str]:
    """Extract import statements from a Python file.

    Args:
        file_path: Path to Python file

    Returns:
        Set of imported module names
    """
    imports = set()
    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))
        visitor = ImportVisitor()
        visitor.visit(node=tree)
        imports = visitor.imports
    except (SyntaxError, UnicodeDecodeError, OSError) as e:  # fmt: skip
        logger.info(msg="Error extracting imports from file", extra={"file": str(file_path), "error": str(e)})
    return imports


def _extract_fixtures_from_file(file_path: Path, marker_names: set[str]) -> set[str]:
    """Extract fixture names used in test file.

    Args:
        file_path: Path to test file
        marker_names: Set of marker names

    Returns:
        Set of fixture names
    """
    fixtures = set()
    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))
        visitor = FixtureVisitor(marker_names=marker_names)
        visitor.visit(node=tree)
        fixtures = visitor.fixtures
    except (SyntaxError, UnicodeDecodeError, OSError) as e:  # fmt: skip
        logger.info(msg="Error extracting fixtures from file", extra={"file": str(file_path), "error": str(e)})
    return fixtures


def _resolve_imports_helper(imports: set[str], repo_root: Path) -> set[Path]:
    """Resolve import module names to file paths.

    Args:
        imports: Set of module names
        repo_root: Repository root path

    Returns:
        Set of resolved file paths
    """
    resolved = set()

    for module in imports:
        # Try to resolve relative to repo root
        module_path = repo_root / module.replace(".", "/")

        # Check for Python package
        if (module_path / "__init__.py").exists():
            resolved.add(module_path / "__init__.py")
        # Check for Python module
        elif module_path.with_suffix(".py").exists():
            resolved.add(module_path.with_suffix(".py"))
        # Check in tests directory
        else:
            tests_module_path = repo_root / "tests" / module.replace(".", "/")
            if (tests_module_path / "__init__.py").exists():
                resolved.add(tests_module_path / "__init__.py")
            elif tests_module_path.with_suffix(".py").exists():
                resolved.add(tests_module_path.with_suffix(".py"))

    return resolved


def _find_relevant_conftests_helper(test_file: Path, repo_root: Path) -> set[Path]:
    """Find conftest.py files in the test's directory hierarchy.

    Args:
        test_file: Test file path
        repo_root: Repository root path

    Returns:
        Set of conftest.py file paths
    """
    relevant = set()
    current = test_file.parent.resolve()
    repo_root_resolved = repo_root.resolve()

    # Safety limit to prevent infinite loops
    max_iterations = MAX_CONFTEST_SEARCH_ITERATIONS
    iteration = 0

    while iteration < max_iterations:
        iteration += 1
        conftest = current / "conftest.py"
        if conftest.exists():
            relevant.add(conftest)

        if current == repo_root_resolved:
            break

        # Safety check to prevent infinite loop
        parent = current.parent.resolve()
        if parent == current:  # Reached filesystem root
            break
        current = parent

    return relevant


def _analyze_single_test_dependencies(
    marked_test: MarkedTest, repo_root: Path, marker_names: set[str]
) -> tuple[set[Path], set[str]]:
    """Analyze dependencies for a single marked test (static method for parallel execution).

    Args:
        marked_test: Test to analyze
        repo_root: Repository root path
        marker_names: Set of marker names

    Returns:
        Tuple of (dependencies, fixtures)
    """
    dependencies = set()
    fixtures = set()

    try:
        # Add the test file itself as a dependency
        dependencies.add(marked_test.file_path)

        # Extract direct imports from test file
        imports = _extract_imports_from_file(file_path=marked_test.file_path)
        dependencies.update(_resolve_imports_helper(imports=imports, repo_root=repo_root))

        # Extract fixtures used by the test
        fixtures = _extract_fixtures_from_file(file_path=marked_test.file_path, marker_names=marker_names)

        # Add conftest files in the test's directory hierarchy
        conftest_deps = _find_relevant_conftests_helper(test_file=marked_test.file_path, repo_root=repo_root)
        dependencies.update(conftest_deps)

        # Analyze transitive imports (1-2 levels deep)
        visited = set()
        to_visit = list(dependencies)
        current_depth = 0
        max_depth = MAX_TRANSITIVE_IMPORT_DEPTH

        while to_visit and current_depth < max_depth:
            current_level = to_visit[:]
            to_visit = []

            for dep_file in current_level:
                if dep_file in visited or not dep_file.suffix == ".py":
                    continue

                visited.add(dep_file)
                dep_imports = _extract_imports_from_file(file_path=dep_file)
                resolved = _resolve_imports_helper(imports=dep_imports, repo_root=repo_root)

                for resolved_file in resolved:
                    if resolved_file not in dependencies:
                        dependencies.add(resolved_file)
                        to_visit.append(resolved_file)

            current_depth += 1

    except (SyntaxError, UnicodeDecodeError, OSError) as e:  # fmt: skip
        logger.info(
            msg="Error analyzing test dependencies", extra={"file": str(marked_test.file_path), "error": str(e)}
        )

    return dependencies, fixtures


def _check_test_impact(
    node_id: str,
    marked_test: MarkedTest,
    changed_set: set[Path],
    repo_root: Path,
    fixtures_dict: dict[str, Fixture],
    base_branch: str,
    github_pr_info: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Check if a single test is affected by changed files (for parallel execution).

    Args:
        node_id: Test node ID
        marked_test: Test to check
        changed_set: Set of changed file paths
        repo_root: Repository root path
        fixtures_dict: Dictionary of all fixtures
        base_branch: Base branch name
        github_pr_info: GitHub PR info for API calls

    Returns:
        Dictionary with test info if affected, None otherwise
    """
    test_affected = False
    matching_deps = []

    for changed_file in changed_set:
        # Special handling for conftest.py: use fixture-level analysis
        if changed_file.name == "conftest.py" and changed_file in marked_test.dependencies:
            modified_fixtures, modified_functions = _extract_modified_items_from_conftest(
                changed_file=changed_file, base_branch=base_branch, repo_root=repo_root, github_pr_info=github_pr_info
            )

            # Get all transitively affected fixtures
            affected_fixtures = _get_affected_fixtures_helper(
                modified_fixtures=modified_fixtures, modified_functions=modified_functions, fixtures_dict=fixtures_dict
            )

            # Check if test uses any affected fixture
            test_fixtures = marked_test.fixtures
            common_fixtures = test_fixtures & affected_fixtures

            if common_fixtures:
                test_affected = True
                fixtures_str = ", ".join(sorted(common_fixtures))
                matching_deps.append(f"{changed_file.relative_to(repo_root)} (fixtures: {fixtures_str})")

        # Direct dependency check for non-conftest files
        elif changed_file in marked_test.dependencies and changed_file.name != "conftest.py":
            test_affected = True
            matching_deps.append(str(changed_file.relative_to(repo_root)))

    if test_affected:
        return {
            "node_id": node_id,
            "test_name": marked_test.test_name,
            "test_file": str(marked_test.file_path.relative_to(repo_root)),
            "dependencies": matching_deps,
        }
    return None


def _get_affected_fixtures_helper(
    modified_fixtures: set[str], modified_functions: set[str], fixtures_dict: dict[str, Fixture]
) -> set[str]:
    """Get all fixtures affected by modifications (transitive) - helper for parallelization.

    Args:
        modified_fixtures: Set of directly modified fixture names
        modified_functions: Set of directly modified function names
        fixtures_dict: Dictionary of all fixtures

    Returns:
        Set of all fixture names that are affected
    """
    affected = modified_fixtures.copy()
    to_check = list(modified_fixtures)

    # Also check fixtures that call modified functions
    for fixture_name, fixture in fixtures_dict.items():
        if fixture.function_calls & modified_functions:
            affected.add(fixture_name)
            to_check.append(fixture_name)

    # Transitive closure
    visited = set()
    while to_check:
        fixture_name = to_check.pop()
        if fixture_name in visited:
            continue
        visited.add(fixture_name)

        # Find fixtures that depend on this one
        for other_name, other_fixture in fixtures_dict.items():
            if fixture_name in other_fixture.fixture_deps and other_name not in affected:
                affected.add(other_name)
                to_check.append(other_name)

    return affected


def _extract_modified_items_from_conftest(
    changed_file: Path, base_branch: str, repo_root: Path, github_pr_info: dict[str, Any] | None
) -> tuple[set[str], set[str]]:
    """Extract modified fixtures and functions from conftest.py.

    Args:
        changed_file: Path to conftest.py
        base_branch: Base branch name
        repo_root: Repository root
        github_pr_info: GitHub PR info for API calls

    Returns:
        Tuple of (modified_fixtures, modified_functions)
    """
    modified_fixtures = set()
    modified_functions = set()

    try:
        # Get all fixtures in the file
        all_fixtures = set()
        try:
            source = changed_file.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(changed_file))

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    for decorator in node.decorator_list:
                        if _is_fixture_decorator_helper(decorator=decorator):
                            all_fixtures.add(node.name)
                            break
        except (SyntaxError, UnicodeDecodeError, OSError) as e:  # fmt: skip
            logger.info(msg="Error parsing conftest for fixtures", extra={"file": str(changed_file), "error": str(e)})

        # Get modified function names
        modified_function_names = _get_modified_function_names_helper(
            file_path=changed_file, base_branch=base_branch, repo_root=repo_root, github_pr_info=github_pr_info
        )

        # Classify
        for func_name in modified_function_names:
            if func_name in all_fixtures:
                modified_fixtures.add(func_name)
            else:
                modified_functions.add(func_name)

        # Fallback
        if not modified_function_names and changed_file.exists():
            return all_fixtures, set()

    except (SyntaxError, UnicodeDecodeError, OSError, subprocess.SubprocessError) as e:  # fmt: skip
        logger.info(
            msg="Error extracting modified items from conftest", extra={"file": str(changed_file), "error": str(e)}
        )

    return modified_fixtures, modified_functions


def _is_fixture_decorator_helper(decorator: ast.AST) -> bool:
    """Check if decorator is @pytest.fixture - helper for parallelization."""
    if isinstance(decorator, ast.Name):
        return decorator.id == "fixture"
    elif isinstance(decorator, ast.Attribute):
        return isinstance(decorator.value, ast.Name) and decorator.value.id == "pytest" and decorator.attr == "fixture"
    elif isinstance(decorator, ast.Call):
        return _is_fixture_decorator_helper(decorator=decorator.func)
    return False


def _get_modified_function_names_helper(
    file_path: Path, base_branch: str, repo_root: Path, github_pr_info: dict[str, Any] | None
) -> set[str]:
    """Get modified function names - helper for parallelization."""
    modified = set()

    # Use GitHub API if available
    if github_pr_info:
        repo = github_pr_info["repo"]
        pr_number = github_pr_info["pr_number"]
        token = github_pr_info.get("token")

        try:
            relative_path = file_path.relative_to(other=repo_root)
        except ValueError:
            relative_path = file_path

        diff_content = get_pr_file_diff(repo=repo, pr_number=pr_number, file_path=str(relative_path), token=token)
        if diff_content:
            modified = _parse_diff_for_functions_helper(diff_content=diff_content)
        return modified

    # Use local git
    try:
        result = subprocess.run(
            ["git", "diff", "-U3", f"{base_branch}...HEAD", "--", str(file_path)],
            capture_output=True,
            text=True,
            cwd=repo_root,
            timeout=10,
        )
        if result.returncode == 0:
            modified = _parse_diff_for_functions_helper(diff_content=result.stdout)
    except (subprocess.SubprocessError, OSError) as e:  # fmt: skip
        logger.info(msg="Error getting modified function names", extra={"file": str(file_path), "error": str(e)})

    return modified


def _parse_diff_for_functions_helper(diff_content: str) -> set[str]:
    """Parse diff to extract modified functions - helper for parallelization."""
    modified = set()
    current_function = None
    has_changes_in_function = False

    for line in diff_content.splitlines():
        if line.startswith("@@"):
            if current_function and has_changes_in_function:
                modified.add(current_function)

            match = re.search(pattern=r"@@.*@@\s*(?:async\s+)?def\s+(\w+)", string=line)
            if match:
                current_function = match.group(1)
                has_changes_in_function = False
            else:
                current_function = None
            continue

        if line.startswith(("+", "-")) and not line.startswith(("+++", "---", "@@")):
            stripped = line[1:].strip()
            if stripped and not stripped.startswith("#"):
                has_changes_in_function = True

    if current_function and has_changes_in_function:
        modified.add(current_function)

    return modified


class MarkerTestAnalyzer:
    """Analyzes tests with specific markers and their dependencies to determine if tests should run."""

    def __init__(
        self,
        marker_expression: str,
        repo_root: Path | None = None,
        base_branch: str = "main",
        github_pr_info: dict[str, Any] | None = None,
    ) -> None:
        self.marker_expression = marker_expression
        self.marker_names = extract_marker_names(marker_expression=marker_expression)
        self.repo_root = repo_root or Path.cwd()
        self.base_branch = base_branch
        self.github_pr_info = github_pr_info  # Contains repo, pr_number, token for GitHub API calls
        self.marked_tests: dict[str, MarkedTest] = {}
        self.conftest_files: list[Path] = []
        self.fixtures: dict[str, Fixture] = {}  # name -> Fixture
        self.fixture_usage: dict[str, set[str]] = {}  # test_node_id -> set of fixture names
        self.infrastructure_dirs = {
            self.repo_root / "utilities",
            self.repo_root / "libs",
        }

    def _run_pytest_command(self, args: list[str]) -> subprocess.CompletedProcess | None:
        """Run pytest with different command strategies.

        Tries pytest commands in this order:
        1. Direct 'pytest' (if in venv or system PATH)
        2. 'uv run pytest' (if uv is available)

        Returns:
            CompletedProcess if successful, None if all attempts failed
        """
        # Validate arguments to prevent command injection
        for arg in args:
            if not isinstance(arg, str):
                logger.error(msg="Invalid argument type", extra={"arg_type": str(type(arg))})
                return None
            # Reject shell metacharacters that could enable command injection
            if any(char in arg for char in [";", "|", "&", "`", "$", "\n", "\r"]):
                logger.warning(msg="Suspicious argument rejected", extra={"arg": arg})
                return None

        # Verify repository root exists
        if not self.repo_root.exists():
            logger.error(msg="Repository root does not exist", extra={"repo_root": str(self.repo_root)})
            return None

        # Get current environment and add the required variable
        env = os.environ.copy()
        env["OPENSHIFT_VIRTUALIZATION_TEST_IMAGES_ARCH"] = "amd64"

        logger.info(msg="Executing pytest command", extra={"cmd_args": " ".join(args)})

        # Try direct pytest first (works in containers with venv)
        try:
            result = subprocess.run(
                ["pytest"] + args,
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                timeout=PYTEST_COLLECTION_TIMEOUT_SECONDS,
                env=env,
            )
            # If pytest ran (even with errors), return the result
            logger.info(msg="pytest completed", extra={"exit_code": result.returncode})
            return result
        except FileNotFoundError:
            logger.info(msg="Direct 'pytest' not found, trying 'uv run pytest'")
        except subprocess.TimeoutExpired:
            logger.warning(
                msg="Command timed out",
                extra={"timeout_seconds": PYTEST_COLLECTION_TIMEOUT_SECONDS, "command": f"pytest {' '.join(args)}"},
            )
            return None

        # Try uv run pytest as fallback
        try:
            result = subprocess.run(
                ["uv", "run", "pytest"] + args,
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                timeout=PYTEST_COLLECTION_TIMEOUT_SECONDS,
                env=env,
            )
            logger.info(msg="pytest completed", extra={"exit_code": result.returncode})
            return result
        except FileNotFoundError:
            logger.info(msg="'uv run pytest' not found")
            return None
        except subprocess.TimeoutExpired:
            logger.warning(
                msg="Command timed out",
                extra={
                    "timeout_seconds": PYTEST_COLLECTION_TIMEOUT_SECONDS,
                    "command": f"uv run pytest {' '.join(args)}",
                },
            )
            return None

    def discover_marked_tests(self) -> None:
        """Discover all tests with specified marker expression using pytest collection."""
        logger.info(msg="Discovering tests with marker expression", extra={"marker_expression": self.marker_expression})

        # Use pytest --collect-only to discover ALL tests with the marker
        result = self._run_pytest_command(args=["--collect-only", "-q", "-m", self.marker_expression])

        if result is None:
            # No pytest available, use AST fallback
            logger.info(msg="pytest not available, using AST-based fallback")
            self._fallback_discover_marked_tests()
            logger.info(
                msg="Found tests with marker expression",
                extra={"test_count": len(self.marked_tests), "marker_expression": self.marker_expression},
            )
            return

        if result.returncode not in (0, 5):  # 5 = no tests collected
            logger.warning(msg="pytest collection had issues", extra={"return_code": result.returncode})
            logger.info(msg="pytest stderr output", extra={"stderr": result.stderr})

        # Parse pytest output to extract test node IDs
        for line in result.stdout.splitlines():
            line = line.strip()
            if "::" in line and not line.startswith(" "):
                # Format: tests/path/to/test_file.py::TestClass::test_method
                node_id = line
                parts = node_id.split("::")
                file_path = self.repo_root / parts[0]

                if file_path.exists():
                    test_name = parts[-1] if len(parts) > 1 else "unknown"
                    marked_test = MarkedTest(
                        file_path=file_path,
                        test_name=test_name,
                        node_id=node_id,
                    )
                    self.marked_tests[node_id] = marked_test

        if not self.marked_tests:
            logger.info(
                msg="Pytest collection found no tests, expected in offline environments, using fallback",
                extra={"marker_expression": self.marker_expression},
            )
            # Fallback: scan known test files directly
            self._fallback_discover_marked_tests()

        logger.info(
            msg="Found tests with marker expression",
            extra={"test_count": len(self.marked_tests), "marker_expression": self.marker_expression},
        )

        # After discovering all tests, try to get fixture usage with --setup-plan
        # This is optional and will add fixture information if available
        self._try_pytest_setup_plan()

    def _try_pytest_setup_plan(self) -> bool:
        """Try to use pytest --setup-plan to get fixture usage for already-discovered tests.

        This is called AFTER discover_marked_tests() to add fixture information.
        It does NOT discover tests - only adds fixture metadata to existing tests.

        Returns:
            True if successful, False if pytest not available or failed
        """
        result = self._run_pytest_command(args=["--setup-plan", "-m", self.marker_expression, "-q"])

        if result is None or result.returncode not in (0, 5):
            if result:
                logger.info(msg="pytest --setup-plan failed", extra={"return_code": result.returncode})
            return False

        # Parse output to extract fixture usage for already-discovered tests
        # Note: SETUP lines appear BEFORE the test line, so we collect them first
        current_fixtures = set()
        fixture_count = 0

        for line in result.stdout.splitlines():
            line = line.strip()

            # Fixture setup line (SETUP F fixture_name) - collect before test
            if line.startswith("SETUP"):
                match = re.search(pattern=r"SETUP\s+[FSM]\s+(\w+)", string=line)
                if match:
                    fixture_name = match.group(1)
                    current_fixtures.add(fixture_name)

            # WARNING lines from pytest-dependency (tests with @pytest.mark.dependency)
            elif line.startswith("WARNING:") and "::" in line:
                # Extract test ID from "WARNING: cannot execute test relative to others: tests/..."
                match = re.search(pattern=r":\s+(tests/[^\s]+::[^\s]+)", string=line)
                if match:
                    node_id = match.group(1)
                    # Only add fixture info if test was already discovered
                    if node_id in self.marked_tests:
                        self.fixture_usage[node_id] = current_fixtures.copy()
                        fixture_count += 1
                    # Reset fixture collection for next test
                    current_fixtures = set()

            # Test node ID line - assign collected fixtures
            elif "::" in line and not line.startswith(" "):
                # Extract node_id (remove any trailing info like "(fixtures used: ...)")
                node_id = line.split("(")[0].strip()
                # Only add fixture info if test was already discovered
                if node_id in self.marked_tests:
                    self.fixture_usage[node_id] = current_fixtures.copy()
                    fixture_count += 1
                # Reset fixture collection for next test
                current_fixtures = set()

        logger.info(msg="Added fixture information via --setup-plan", extra={"test_count": fixture_count})
        return fixture_count > 0

    def _fallback_discover_marked_tests(self) -> None:
        """Fallback method to discover marked tests by scanning all test files (parallelized)."""
        logger.info(msg="Using AST-based fallback discovery (normal for containerized/offline environments)...")

        # Scan tests directory for test files
        tests_dir = self.repo_root / "tests"
        if not tests_dir.exists():
            logger.warning(msg="Tests directory not found", extra={"tests_dir": str(tests_dir)})
            return

        # Collect all test files to process
        test_files = []
        # Scan test_*.py pattern
        test_files.extend(tests_dir.rglob("test_*.py"))
        # Also scan *_test.py pattern
        test_files.extend(tests_dir.rglob("*_test.py"))
        # Remove duplicates
        test_files = list(set(test_files))

        logger.info(msg="Found test files to scan", extra={"file_count": len(test_files)})

        # Process files in parallel using ThreadPoolExecutor (I/O-bound: file reading and AST parsing)
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            # Submit all tasks
            future_to_file = {
                executor.submit(
                    _process_test_file_for_markers,
                    test_file=test_file,
                    marker_names=self.marker_names,
                    repo_root=self.repo_root,
                ): test_file
                for test_file in test_files
            }

            # Collect results as they complete
            for future in as_completed(future_to_file):
                test_file = future_to_file[future]
                try:
                    results = future.result()
                    for node_id, test_name, file_path in results:
                        if node_id not in self.marked_tests:  # Avoid duplicates
                            self.marked_tests[node_id] = MarkedTest(
                                file_path=file_path,
                                test_name=test_name,
                                node_id=node_id,
                            )
                except (SyntaxError, UnicodeDecodeError, OSError) as e:  # fmt: skip
                    logger.info(msg="Error processing test file", extra={"file": str(test_file), "error": str(e)})

        logger.info(
            msg="Fallback discovered tests with marker expression",
            extra={"test_count": len(self.marked_tests), "marker_expression": self.marker_expression},
        )

    def _extract_marked_tests_from_file(self, file_path: Path) -> list[str]:
        """Extract test names with specified markers from a file.

        Checks for markers in this priority:
        1. Module-level pytestmark - if present, ALL tests in file match
        2. Class-level decorators - if present, ALL test methods in class match
        3. Individual function/method decorators - only marked tests match
        """
        tests = []
        try:
            source = file_path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(file_path))

            # STEP 1: Check for module-level pytestmark assignment
            # If found, ALL test functions/methods in the file should be included
            module_has_marker = False
            for node in tree.body:
                if isinstance(node, ast.Assign) and check_pytestmark_assignment(
                    node=node, marker_names=self.marker_names
                ):
                    module_has_marker = True
                    logger.info(msg="Module-level marker found", extra={"file_path": str(file_path)})
                    break

            if module_has_marker:
                # Use proper tree traversal, not ast.walk() which loses context
                for node in tree.body:
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if node.name.startswith("test_"):
                            tests.append(node.name)
                    elif isinstance(node, ast.ClassDef):
                        for item in node.body:
                            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                                if item.name.startswith("test_"):
                                    tests.append(f"{node.name}::{item.name}")
                return tests

            # STEP 2: No module-level marker, check class-level and method-level markers
            # Iterate through module body to properly handle classes vs functions
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    # Module-level function with marker
                    if node.name.startswith("test_"):
                        for decorator in node.decorator_list:
                            if is_marker(decorator=decorator, marker_names=self.marker_names):
                                tests.append(node.name)
                                break
                            # Also check for markers in parametrize pytest.param(..., marks=...)
                            elif check_parametrize_marks(decorator=decorator, marker_names=self.marker_names):
                                tests.append(node.name)
                                break

                elif isinstance(node, ast.ClassDef):
                    # Check if class has marker (applies to all test methods)
                    class_has_marker = False
                    for decorator in node.decorator_list:
                        if is_marker(decorator=decorator, marker_names=self.marker_names):
                            class_has_marker = True
                            break

                    if class_has_marker:
                        # Class-level marker: add ALL test methods
                        for item in node.body:
                            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                                if item.name.startswith("test_"):
                                    tests.append(f"{node.name}::{item.name}")
                    else:
                        # No class-level marker: check individual methods
                        for item in node.body:
                            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                                if item.name.startswith("test_"):
                                    # Check method-level markers
                                    for decorator in item.decorator_list:
                                        if is_marker(decorator=decorator, marker_names=self.marker_names):
                                            tests.append(f"{node.name}::{item.name}")
                                            break
                                        # Also check parametrize marks
                                        elif check_parametrize_marks(
                                            decorator=decorator, marker_names=self.marker_names
                                        ):
                                            tests.append(f"{node.name}::{item.name}")
                                            break

        except SyntaxError as e:
            logger.warning(msg="Syntax error in file", extra={"file_path": str(file_path), "error": str(e)})
        except UnicodeDecodeError as e:
            logger.warning(msg="Encoding error in file", extra={"file_path": str(file_path), "error": str(e)})
        except OSError as e:
            logger.info(msg="Unexpected error parsing file", extra={"file_path": str(file_path), "error": str(e)})

        return tests

    def build_fixture_dependency_graph(self) -> None:
        """Build a graph of fixture dependencies from all conftest files (parallelized)."""
        logger.info(msg="Building fixture dependency graph...")

        # Process conftest files in parallel using ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            # Submit all tasks
            future_to_conftest = {
                executor.submit(_process_conftest_file, conftest=conftest): conftest for conftest in self.conftest_files
            }

            # Collect results first, then merge after parallel execution completes
            all_fixtures = []
            for future in as_completed(future_to_conftest):
                conftest = future_to_conftest[future]
                try:
                    fixtures = future.result()
                    all_fixtures.append(fixtures)
                except (SyntaxError, UnicodeDecodeError, OSError) as e:  # fmt: skip
                    logger.info(msg="Error processing conftest", extra={"file": str(conftest), "error": str(e)})

            # Merge after parallel execution completes (thread-safe)
            for fixtures in all_fixtures:
                self.fixtures.update(fixtures)

        logger.info(
            msg="Found fixtures across conftest files",
            extra={"fixture_count": len(self.fixtures), "conftest_count": len(self.conftest_files)},
        )

    def get_affected_fixtures(self, modified_fixtures: set[str], modified_functions: set[str]) -> set[str]:
        """Get all fixtures affected by modifications (transitive).

        Args:
            modified_fixtures: Set of directly modified fixture names
            modified_functions: Set of directly modified function names

        Returns:
            Set of all fixture names that are affected (directly or transitively)
        """
        affected = modified_fixtures.copy()
        to_check = list(modified_fixtures)

        # Also check fixtures that call modified functions
        for fixture_name, fixture in self.fixtures.items():
            if fixture.function_calls & modified_functions:
                affected.add(fixture_name)
                to_check.append(fixture_name)

        # Transitive closure: find all fixtures that depend on affected fixtures
        visited = set()
        while to_check:
            fixture_name = to_check.pop()
            if fixture_name in visited:
                continue
            visited.add(fixture_name)

            # Find fixtures that depend on this one
            for other_name, other_fixture in self.fixtures.items():
                if fixture_name in other_fixture.fixture_deps and other_name not in affected:
                    affected.add(other_name)
                    to_check.append(other_name)

        return affected

    def extract_modified_items(self, changed_file: Path) -> tuple[set[str], set[str]]:
        """Extract modified fixtures and functions from a conftest.py file using git diff.

        This method uses a two-phase approach:
        1. Parse the file to identify which functions are fixtures
        2. Use git diff to identify which functions were actually modified
        3. Classify modified functions as fixtures or regular functions

        This prevents triggering all tests when only unrelated fixtures/functions
        were modified in a conftest.py file.

        Args:
            changed_file: Path to the modified conftest.py

        Returns:
            Tuple of (modified_fixture_names, modified_function_names)
        """
        modified_fixtures = set()
        modified_functions = set()

        try:
            # Phase 1: Get all fixtures in the current file
            all_fixtures = self._get_all_fixtures_in_file(file_path=changed_file)
            logger.info(
                msg="Found fixtures in file", extra={"fixture_count": len(all_fixtures), "file": changed_file.name}
            )

            # Phase 2: Get modified function names from git diff
            modified_function_names = self._get_modified_function_names(file_path=changed_file)
            logger.info(
                msg="Found modified functions",
                extra={"function_count": len(modified_function_names), "file": changed_file.name},
            )

            # Phase 3: Classify modified functions
            for func_name in modified_function_names:
                if func_name in all_fixtures:
                    modified_fixtures.add(func_name)
                else:
                    modified_functions.add(func_name)

            # Log results
            if modified_fixtures:
                logger.info(
                    msg="Modified fixtures in file",
                    extra={"file": changed_file.name, "fixtures": sorted(modified_fixtures)},
                )
            if modified_functions:
                logger.info(
                    msg="Modified functions in file",
                    extra={"file": changed_file.name, "functions": sorted(modified_functions)},
                )

            # Fallback: If git diff failed or file is new, conservatively assume all are modified
            if not modified_function_names and changed_file.exists():
                logger.warning(
                    msg="Could not determine specific modifications, using conservative fallback",
                    extra={"file": str(changed_file)},
                )
                # Return all fixtures as modified (conservative)
                return all_fixtures, set()

        except (SyntaxError, UnicodeDecodeError, OSError, subprocess.SubprocessError) as e:  # fmt: skip
            logger.info(
                msg="Error extracting modifications from file", extra={"file": str(changed_file), "error": str(e)}
            )
            # Fallback to conservative behavior
            try:
                all_fixtures = self._get_all_fixtures_in_file(file_path=changed_file)
                logger.warning(
                    msg="Error during smart analysis, using conservative fallback", extra={"file": str(changed_file)}
                )
                return all_fixtures, set()
            except (SyntaxError, UnicodeDecodeError, OSError) as e:  # fmt: skip
                logger.info(msg="Error during fallback analysis", extra={"file": str(changed_file), "error": str(e)})

        return modified_fixtures, modified_functions

    def _get_all_fixtures_in_file(self, file_path: Path) -> set[str]:
        """Get all fixture names in a file using AST parsing.

        Args:
            file_path: Path to Python file

        Returns:
            Set of fixture names
        """
        fixtures = set()

        try:
            source = file_path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(file_path))

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    # Check decorators for @pytest.fixture or @fixture
                    for decorator in node.decorator_list:
                        if self._is_fixture_decorator(decorator=decorator):
                            fixtures.add(node.name)
                            break

        except (SyntaxError, UnicodeDecodeError, OSError) as e:  # fmt: skip
            logger.info(msg="Error parsing file for fixtures", extra={"file": str(file_path), "error": str(e)})

        return fixtures

    def _get_modified_function_names(self, file_path: Path) -> set[str]:
        """Get names of functions that were modified using git diff or GitHub API.

        Args:
            file_path: Path to file

        Returns:
            Set of modified function names
        """
        modified = set()

        # If we have GitHub PR info, use API instead of local git
        if self.github_pr_info:
            repo = self.github_pr_info["repo"]
            pr_number = self.github_pr_info["pr_number"]
            token = self.github_pr_info.get("token")

            # Get relative path for API call
            try:
                relative_path = file_path.relative_to(other=self.repo_root)
            except ValueError:
                relative_path = file_path

            logger.info(msg="Fetching PR diff from GitHub API", extra={"file": str(relative_path)})
            diff_content = get_pr_file_diff(repo=repo, pr_number=pr_number, file_path=str(relative_path), token=token)

            if diff_content:
                modified = self._parse_diff_for_functions(diff_content=diff_content)
                logger.info(
                    msg="Found modified functions via GitHub API",
                    extra={"function_count": len(modified), "functions": list(modified)},
                )
            else:
                logger.warning(msg="No diff found for file via GitHub API", extra={"file": str(file_path)})

            return modified

        # Otherwise use local git diff (original logic)
        try:
            # Use git diff to find modified functions
            # -U3 gives 3 lines of context for better function detection
            result = subprocess.run(
                ["git", "diff", "-U3", f"{self.base_branch}...HEAD", "--", str(file_path)],
                capture_output=True,
                text=True,
                cwd=self.repo_root,
                timeout=10,
            )

            if result.returncode != 0:
                logger.info(msg="Git diff failed for file", extra={"file": str(file_path), "stderr": result.stderr})
                return modified

            modified = self._parse_diff_for_functions(diff_content=result.stdout)

        except subprocess.TimeoutExpired:
            logger.warning(msg="Git diff timed out for file", extra={"file": str(file_path)})
        except subprocess.CalledProcessError as e:
            logger.info(msg="Git diff failed", extra={"error": str(e)})
        except OSError as e:
            logger.info(msg="Error running git diff", extra={"error": str(e)})

        return modified

    def _parse_diff_for_functions(self, diff_content: str) -> set[str]:
        """Parse unified diff content to extract modified function names.

        Args:
            diff_content: Unified diff content (from git diff or GitHub API patch field)

        Returns:
            Set of modified function names
        """
        modified = set()

        # Track which functions have actual changes
        current_function = None
        has_changes_in_function = False

        for line in diff_content.splitlines():
            # Check for @@ hunk header with function name
            if line.startswith("@@"):
                # Save previous function if it had changes
                if current_function and has_changes_in_function:
                    modified.add(current_function)

                # Extract function from hunk header: @@ ... @@ def function_name
                match = re.search(pattern=r"@@.*@@\s*(?:async\s+)?def\s+(\w+)", string=line)
                if match:
                    current_function = match.group(1)
                    has_changes_in_function = False
                else:
                    current_function = None
                continue

            # Check for actual changes (+ or - lines, not context or file markers)
            if line.startswith(("+", "-")) and not line.startswith(("+++", "---", "@@")):
                # Ignore pure whitespace/comment changes (basic heuristic)
                stripped = line[1:].strip()
                # Count as a change if it's not empty and not just a comment
                if stripped and not stripped.startswith("#"):
                    has_changes_in_function = True

        # Don't forget the last function
        if current_function and has_changes_in_function:
            modified.add(current_function)

        return modified

    def _is_fixture_decorator(self, decorator: ast.AST) -> bool:
        """Check if decorator is @pytest.fixture."""
        if isinstance(decorator, ast.Name):
            return decorator.id == "fixture"
        elif isinstance(decorator, ast.Attribute):
            return (
                isinstance(decorator.value, ast.Name) and decorator.value.id == "pytest" and decorator.attr == "fixture"
            )
        elif isinstance(decorator, ast.Call):
            return self._is_fixture_decorator(decorator=decorator.func)
        return False

    def analyze_dependencies(self) -> None:
        """Analyze dependencies for all marked tests (parallelized)."""
        logger.info(msg="Analyzing test dependencies...")

        # Find all conftest.py files
        self._find_conftest_files()

        # Build fixture dependency graph (already parallelized)
        self.build_fixture_dependency_graph()

        # Analyze each marked test in parallel using ThreadPoolExecutor
        # (I/O-bound: file reading and AST parsing)
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            # Create a list of tests to process
            tests_to_process = list(self.marked_tests.values())

            # Submit all test dependency analysis tasks
            # Use node_id (hashable string) as dict key instead of MarkedTest object (unhashable)
            future_to_node_id = {
                executor.submit(
                    _analyze_single_test_dependencies,
                    marked_test=marked_test,
                    repo_root=self.repo_root,
                    marker_names=self.marker_names,
                ): marked_test.node_id
                for marked_test in tests_to_process
            }

            # Collect results first, then update sequentially after parallel execution completes
            results = {}
            for future in as_completed(future_to_node_id):
                node_id = future_to_node_id[future]
                try:
                    deps, fixtures = future.result()
                    results[node_id] = (deps, fixtures)
                except (SyntaxError, UnicodeDecodeError, OSError) as e:  # fmt: skip
                    logger.info(msg="Error analyzing dependencies", extra={"node_id": node_id, "error": str(e)})

            # Update sequentially after all parallel work completes (thread-safe)
            for node_id, (deps, fixtures) in results.items():
                marked_test = self.marked_tests[node_id]
                marked_test.dependencies.update(deps)
                marked_test.fixtures.update(fixtures)

                # If we got fixture usage from pytest --setup-plan, use it
                if node_id in self.fixture_usage:
                    marked_test.fixtures.update(self.fixture_usage[node_id])

        logger.info(msg="Dependency analysis complete")

    def _find_conftest_files(self) -> None:
        """Find all conftest.py files in the repository."""
        tests_dir = self.repo_root / "tests"
        if tests_dir.exists():
            self.conftest_files = list(tests_dir.rglob("conftest.py"))
        logger.info(msg="Found conftest.py files", extra={"file_count": len(self.conftest_files)})

    def _analyze_test_dependencies(self, marked_test: MarkedTest) -> None:
        """Analyze dependencies for a single marked test."""
        # Add the test file itself as a dependency
        marked_test.dependencies.add(marked_test.file_path)

        # Extract direct imports from test file
        try:
            imports = self._extract_imports(file_path=marked_test.file_path)
            marked_test.dependencies.update(self._resolve_imports(imports=imports, base_file=marked_test.file_path))

            # Extract fixtures used by the test
            fixtures = self._extract_fixtures(file_path=marked_test.file_path)
            marked_test.fixtures.update(fixtures)

            # Add conftest files in the test's directory hierarchy
            conftest_deps = self._find_relevant_conftests(test_file=marked_test.file_path)
            marked_test.dependencies.update(conftest_deps)

            # Analyze transitive imports (1-2 levels deep)
            self._analyze_transitive_imports(marked_test=marked_test, max_depth=MAX_TRANSITIVE_IMPORT_DEPTH)

        except (SyntaxError, UnicodeDecodeError, OSError) as e:  # fmt: skip
            logger.info(
                msg="Error analyzing test dependencies", extra={"file": str(marked_test.file_path), "error": str(e)}
            )

    def _extract_imports(self, file_path: Path) -> set[str]:
        """Extract import statements from a Python file."""
        imports = set()
        try:
            source = file_path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(file_path))
            visitor = ImportVisitor()
            visitor.visit(node=tree)
            imports = visitor.imports
        except SyntaxError as e:
            logger.warning(msg="Syntax error in file", extra={"file": str(file_path), "error": str(e)})
        except UnicodeDecodeError as e:
            logger.warning(msg="Encoding error in file", extra={"file": str(file_path), "error": str(e)})
        except OSError as e:
            logger.info(msg="Unexpected error parsing file", extra={"file": str(file_path), "error": str(e)})

        return imports

    def _extract_fixtures(self, file_path: Path) -> set[str]:
        """Extract fixture names used in test file."""
        fixtures = set()
        try:
            source = file_path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(file_path))
            visitor = FixtureVisitor(marker_names=self.marker_names)
            visitor.visit(node=tree)
            fixtures = visitor.fixtures
        except SyntaxError as e:
            logger.warning(msg="Syntax error in file", extra={"file": str(file_path), "error": str(e)})
        except UnicodeDecodeError as e:
            logger.warning(msg="Encoding error in file", extra={"file": str(file_path), "error": str(e)})
        except OSError as e:
            logger.info(msg="Unexpected error parsing file", extra={"file": str(file_path), "error": str(e)})

        return fixtures

    def _resolve_imports(self, imports: set[str], base_file: Path) -> set[Path]:
        """Resolve import module names to file paths."""
        resolved = set()

        for module in imports:
            # Try to resolve relative to repo root
            module_path = self.repo_root / module.replace(".", "/")

            # Check for Python package
            if (module_path / "__init__.py").exists():
                resolved.add(module_path / "__init__.py")
            # Check for Python module
            elif module_path.with_suffix(".py").exists():
                resolved.add(module_path.with_suffix(".py"))
            # Check in tests directory
            else:
                tests_module_path = self.repo_root / "tests" / module.replace(".", "/")
                if (tests_module_path / "__init__.py").exists():
                    resolved.add(tests_module_path / "__init__.py")
                elif tests_module_path.with_suffix(".py").exists():
                    resolved.add(tests_module_path.with_suffix(".py"))

        return resolved

    def _find_relevant_conftests(self, test_file: Path) -> set[Path]:
        """Find conftest.py files in the test's directory hierarchy."""
        relevant = set()
        current = test_file.parent.resolve()
        repo_root_resolved = self.repo_root.resolve()

        # Safety limit to prevent infinite loops on unusual filesystems
        max_iterations = MAX_CONFTEST_SEARCH_ITERATIONS
        iteration = 0

        while iteration < max_iterations:
            iteration += 1
            conftest = current / "conftest.py"
            if conftest.exists():
                relevant.add(conftest)

            if current == repo_root_resolved:
                break

            # Safety check to prevent infinite loop
            parent = current.parent.resolve()
            if parent == current:  # Reached filesystem root
                break
            current = parent

        if iteration >= max_iterations:
            logger.warning(
                f"Hit iteration limit while finding conftests for {test_file}. "
                f"Current path: {current}, repo root: {repo_root_resolved}"
            )

        return relevant

    def _analyze_transitive_imports(self, marked_test: MarkedTest, max_depth: int) -> None:
        """Analyze transitive imports up to max_depth levels."""
        visited = set()
        to_visit = list(marked_test.dependencies)
        current_depth = 0

        while to_visit and current_depth < max_depth:
            current_level = to_visit[:]
            to_visit = []

            for dep_file in current_level:
                if dep_file in visited or not dep_file.suffix == ".py":
                    continue

                visited.add(dep_file)
                imports = self._extract_imports(file_path=dep_file)
                resolved = self._resolve_imports(imports=imports, base_file=dep_file)

                for resolved_file in resolved:
                    if resolved_file not in marked_test.dependencies:
                        marked_test.dependencies.add(resolved_file)
                        to_visit.append(resolved_file)

            current_depth += 1

    def get_changed_files(self, base_branch: str = "main", files: list[str] | None = None) -> list[Path]:
        """Get list of changed files either from git or from provided list."""
        if files:
            # Use provided files with validation
            validated_files = []
            for file_path_str in files:
                file_path = Path(file_path_str)
                # Security: Skip symlinks to prevent path traversal attacks
                if file_path.is_symlink():
                    logger.warning(msg="Skipping symlink for security", extra={"file": file_path_str})
                    continue
                file_path = file_path.resolve()
                if not file_path.exists():
                    logger.warning(msg="File does not exist", extra={"file": file_path_str})
                    continue
                # Verify it's within repo
                try:
                    file_path.relative_to(other=self.repo_root.resolve())
                    validated_files.append(file_path)
                except ValueError:
                    logger.warning(msg="File is outside repository", extra={"file": file_path_str})
            return validated_files

        # Validate branch name (alphanumeric, dash, underscore, slash, dot)
        if not re.match(pattern=r"^[a-zA-Z0-9/_.-]+$", string=base_branch):
            logger.error(msg="Invalid branch name", extra={"branch": base_branch})
            return []

        # Get changed files from git
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", f"{base_branch}...HEAD"],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=True,
            )
            changed = [self.repo_root / line.strip() for line in result.stdout.splitlines() if line.strip()]
            logger.info(msg="Found changed files from git", extra={"file_count": len(changed)})
            return changed

        except subprocess.CalledProcessError as e:
            logger.error(msg="Failed to get changed files from git", extra={"error": str(e)})
            return []

    def analyze_impact(self, changed_files: list[Path]) -> AnalysisResult:
        """Analyze if changed files impact marked tests (parallelized).

        Only triggers tests when changed files are actually in the dependency
        tree of at least one marked test. For conftest.py changes, uses fixture-level
        dependency tracking to minimize false positives.
        """
        affected_tests = []
        should_run = False
        reasons = []

        # Convert changed files to set for faster lookup
        changed_set = {f.resolve() for f in changed_files}

        # Check each marked test for dependency matches in parallel using ThreadPoolExecutor
        # (I/O-bound: git operations and file reading)
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            # Submit all test impact check tasks
            future_to_test = {
                executor.submit(
                    _check_test_impact,
                    node_id=node_id,
                    marked_test=marked_test,
                    changed_set=changed_set,
                    repo_root=self.repo_root,
                    fixtures_dict=self.fixtures,
                    base_branch=self.base_branch,
                    github_pr_info=self.github_pr_info,
                ): node_id
                for node_id, marked_test in self.marked_tests.items()
            }

            # Collect results as they complete
            for future in as_completed(future_to_test):
                node_id = future_to_test[future]
                try:
                    result = future.result()
                    if result is not None:
                        affected_tests.append(result)
                        should_run = True
                except (SyntaxError, UnicodeDecodeError, OSError, subprocess.SubprocessError) as e:  # fmt: skip
                    logger.info(msg="Error checking impact", extra={"node_id": node_id, "error": str(e)})

        if affected_tests:
            reasons.append(
                f"Changes affect {len(affected_tests)} test(s) with marker expression: {self.marker_expression}"
            )

        # Build final reason
        if not should_run:
            reason = "No changes affect test dependencies"
        else:
            reason = "; ".join(reasons)

        return AnalysisResult(
            should_run_tests=should_run,
            reason=reason,
            marker_expression=self.marker_expression,
            affected_tests=affected_tests,
            changed_files=[str(cf.relative_to(self.repo_root)) for cf in changed_files],
            total_tests=len(self.marked_tests),
        )


def format_markdown_output(result: AnalysisResult) -> str:
    """Format analysis result as Markdown."""
    output = ["## Test Execution Plan", ""]
    output.append(f"**Run tests with marker expression `{result.marker_expression}`: {result.should_run_tests}**")
    output.append("")
    output.append(f"**Reason:** {result.reason}")
    output.append("")

    if result.affected_tests:
        output.append(f"### Affected tests with marker expression `{result.marker_expression}`:")
        for test in result.affected_tests:
            output.append(f"- `{test['node_id']}`")
            output.append(f"  - Test file: `{test['test_file']}`")
            output.append(f"  - Dependencies affected: {len(test['dependencies'])}")
            for dep in test["dependencies"][:3]:  # Show first 3 dependencies
                output.append(f"    - `{dep}`")
            if len(test["dependencies"]) > 3:
                output.append(f"    - ... and {len(test['dependencies']) - 3} more")
        output.append("")

    output.append(f"**Total tests with marker expression `{result.marker_expression}`:** {result.total_tests}")
    output.append(f"**Changed files:** {len(result.changed_files)}")

    return "\n".join(output)


def format_json_output(result: AnalysisResult) -> str:
    """Format analysis result as JSON."""
    return json.dumps(
        {
            "should_run_tests": result.should_run_tests,
            "reason": result.reason,
            "marker_expression": result.marker_expression,
            "changed_files": result.changed_files,
            "affected_tests": result.affected_tests,
            "total_tests": result.total_tests,
        },
        indent=2,
    )


def report_to_external_system(
    result: AnalysisResult,
    url: str,
    format_type: str = "json",
    token: str | None = None,
    headers: list[str] | None = None,
    repo: str | None = None,
    pr_number: int | None = None,
) -> None:
    """Report the test decision to an external system.

    Args:
        result: Analysis result to report
        url: URL to send the report to
        format_type: Report format - 'json', 'form', or 'query'
        token: Optional auth token (sent as Bearer token)
        headers: Optional list of custom headers in "Name: Value" format
        repo: Optional repository name for context
        pr_number: Optional PR number for context
    """
    # Validate URL
    parsed = urllib.parse.urlparse(url=url)
    if parsed.scheme not in ("http", "https"):
        logger.warning(msg="Invalid URL scheme, skipping report", extra={"scheme": parsed.scheme})
        return
    if not parsed.netloc:
        logger.warning(msg="Invalid URL: missing hostname, skipping report")
        return

    try:
        # Build the payload data
        payload_data = {
            "should_run_tests": result.should_run_tests,
            "marker_expression": result.marker_expression,
            "reason": result.reason,
            "affected_tests_count": len(result.affected_tests),
            "total_tests": result.total_tests,
            "changed_files_count": len(result.changed_files),
        }

        # Add optional context fields
        if pr_number is not None:
            payload_data["pr_number"] = pr_number
        if repo is not None:
            payload_data["repo"] = repo

        # Prepare request based on format
        request_headers = {
            "User-Agent": "pytest-marker-analyzer",
        }

        # Add auth token if provided
        if token:
            request_headers["Authorization"] = f"Bearer {token}"

        # Add custom headers if provided
        if headers:
            for header_line in headers:
                if ":" in header_line:
                    name, value = header_line.split(":", 1)
                    request_headers[name.strip()] = value.strip()

        # Build request based on format type
        if format_type == "json":
            # JSON POST request
            request_headers["Content-Type"] = "application/json"
            request_body = json.dumps(obj=payload_data).encode("utf-8")
            request = urllib.request.Request(
                url,
                data=request_body,
                headers=request_headers,
                method="POST",
            )

        elif format_type == "form":
            # Form POST request
            request_headers["Content-Type"] = "application/x-www-form-urlencoded"
            form_data = urllib.parse.urlencode(query=payload_data).encode("utf-8")
            request = urllib.request.Request(
                url,
                data=form_data,
                headers=request_headers,
                method="POST",
            )

        elif format_type == "query":
            # GET request with query parameters
            query_string = urllib.parse.urlencode(query=payload_data)
            full_url = f"{url}?{query_string}"
            request = urllib.request.Request(
                full_url,
                headers=request_headers,
                method="GET",
            )

        else:
            logger.warning(msg="Unknown report format, skipping external reporting", extra={"format": format_type})
            return

        # Send the request
        logger.info(msg="Reporting test decision", extra={"url": url, "format": format_type})
        logger.info(msg="Report payload", extra={"payload": payload_data})

        with urllib.request.urlopen(request, timeout=REPORT_TIMEOUT_SECONDS) as response:
            status_code = response.getcode()
            logger.info(msg="Successfully reported to external system", extra={"http_status": status_code})

    except urllib.error.HTTPError as e:
        logger.warning(msg="Failed to report to external system", extra={"http_code": e.code, "reason": e.reason})
        try:
            error_body = e.read().decode()
            logger.info(msg="Error response from external system", extra={"body": error_body})
        except (OSError, UnicodeDecodeError):  # fmt: skip
            logger.info(msg="Failed to read external system error body")

    except urllib.error.URLError as e:
        logger.warning(msg="Failed to connect to external system", extra={"error": str(e)})

    except (json.JSONDecodeError, OSError) as e:  # fmt: skip
        logger.exception(msg="Unexpected error reporting to external system", extra={"error": str(e)})


def run_github_mode(args: argparse.Namespace) -> tuple[AnalysisResult | None, int]:
    """Handle GitHub PR analysis mode.

    Returns:
        Tuple of (AnalysisResult or None, exit_code)
    """
    original_dir = os.getcwd()  # Save original directory
    if not args.repo or not args.pr:
        logger.error(msg="Both --repo and --pr are required for GitHub mode")
        return None, 1

    token = args.github_token or os.environ.get("GITHUB_TOKEN")
    if not token:
        logger.warning(
            msg="No GitHub token provided. API rate limits will be lower. "
            "Consider providing token via --github-token or GITHUB_TOKEN env var"
        )

    temp_dir = None
    try:
        # Get PR info to determine base branch
        pr_info = get_pr_info(repo=args.repo, pr_number=args.pr, token=token)
        base_branch = pr_info["base_ref"]
        logger.info(
            msg="PR info",
            extra={"pr_number": args.pr, "head_ref": pr_info["head_ref"], "base_branch": base_branch},
        )

        changed_file_names = get_pr_changed_files(repo=args.repo, pr_number=args.pr, token=token)

        if not changed_file_names:
            logger.warning(msg="No files changed in PR", extra={"pr_number": args.pr})

        if args.checkout:
            if args.workdir:
                workdir = args.workdir
                workdir.mkdir(parents=True, exist_ok=True)
            else:
                # Use custom temp base if specified, otherwise system default
                temp_base = args.work_dir if args.work_dir else None
                if temp_base:
                    temp_base.mkdir(parents=True, exist_ok=True)
                temp_dir = tempfile.mkdtemp(prefix="pytest_marker_analyzer_", dir=temp_base)
                workdir = Path(temp_dir)

            checkout_pr(repo=args.repo, pr_number=args.pr, workdir=workdir, token=token)
            repo_root = workdir

            # Change to the cloned repository directory
            os.chdir(repo_root)
            logger.info(msg="Changed working directory", extra={"repo_root": str(repo_root)})

            # Fetch the base branch for comparison
            logger.info(msg="Fetching base branch", extra={"base_branch": base_branch})
            try:
                subprocess.run(
                    ["git", "-C", str(workdir), "fetch", "origin", f"{base_branch}:{base_branch}"],
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=60,
                )
            except subprocess.CalledProcessError as e:
                logger.warning(
                    msg="Failed to fetch base branch", extra={"base_branch": base_branch, "stderr": e.stderr}
                )
                # Continue anyway - the branch might already be available

            # When we checkout, we can use local git diff, so no need to pass github_pr_info
            github_pr_info = None
        else:
            # Remote mode: use current directory and GitHub API for diffs
            repo_root = Path.cwd()
            github_pr_info = {
                "repo": args.repo,
                "pr_number": args.pr,
                "token": token,
            }

        changed_files_list = [repo_root / fname for fname in changed_file_names]

        analyzer = MarkerTestAnalyzer(
            marker_expression=args.markers,
            repo_root=repo_root,
            base_branch=base_branch,
            github_pr_info=github_pr_info,
        )  # Constructor already uses keyword arguments
        analyzer.discover_marked_tests()

        if not analyzer.marked_tests:
            logger.error(msg="No tests found with marker expression", extra={"marker_expression": args.markers})
            return None, 1

        analyzer.analyze_dependencies()
        result = analyzer.analyze_impact(changed_files=changed_files_list)
        return result, 0

    except (ValueError, RuntimeError) as e:  # fmt: skip
        logger.error(msg="GitHub API error", extra={"error": str(e)})
        return None, 1
    finally:
        os.chdir(original_dir)  # Restore original directory
        cleanup_temp_dir(temp_dir=temp_dir)


def run_local_mode(args: argparse.Namespace) -> tuple[AnalysisResult | None, int]:
    """Handle local git analysis mode.

    Returns:
        Tuple of (AnalysisResult or None, exit_code)
    """
    analyzer = MarkerTestAnalyzer(marker_expression=args.markers, base_branch=args.base)  # keyword args used
    analyzer.discover_marked_tests()

    if not analyzer.marked_tests:
        logger.error(msg="No tests found with marker expression", extra={"marker_expression": args.markers})
        return None, 1

    analyzer.analyze_dependencies()
    changed_files = analyzer.get_changed_files(base_branch=args.base, files=args.files)  # keyword args used

    if not changed_files:
        logger.warning(msg="No changed files found")

    result = analyzer.analyze_impact(changed_files=changed_files)
    return result, 0


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Analyze PR changes to determine if tests with specific markers should run",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Marker specification
    parser.add_argument(
        "--markers",
        "-m",
        type=str,
        default="smoke",
        help=(
            "Pytest marker expression to analyze (default: smoke). "
            "Supports full pytest marker syntax:\n"
            "  - Single marker: --markers smoke\n"
            '  - AND logic: --markers "smoke and sanity"\n'
            '  - OR logic: --markers "smoke or sanity"\n'
            '  - NOT logic: --markers "smoke and not slow"\n'
            '  - Complex: --markers "(smoke or sanity) and not slow"\n'
        ),
    )

    # Local mode arguments
    parser.add_argument(
        "--files",
        nargs="+",
        help="Specific files to analyze (instead of using git diff)",
    )
    parser.add_argument(
        "--base",
        default="main",
        help="Base branch to compare against (default: main)",
    )

    # GitHub mode arguments
    parser.add_argument(
        "--repo",
        help="GitHub repository in owner/repo format (e.g., kubevirt/kubevirt)",
    )
    parser.add_argument(
        "--pr",
        type=int,
        help="Pull request number",
    )
    parser.add_argument(
        "--github-token",
        help="GitHub token for API access (can also use GITHUB_TOKEN env var)",
    )
    parser.add_argument(
        "--checkout",
        action="store_true",
        help="Clone and checkout the repository (for CI without pre-checkout)",
    )
    parser.add_argument(
        "--workdir",
        type=Path,
        help="Working directory for checkout (default: temporary directory)",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        help="Base directory for temporary files (default: system temp). Useful in Jenkins to use workspace directory.",
    )

    # Output arguments
    parser.add_argument(
        "--output",
        choices=["markdown", "json"],
        default="markdown",
        help="Output format (default: markdown)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Directory to write output files (creates marker_analysis.json or marker_analysis.md)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    # External reporting arguments
    parser.add_argument(
        "--report-url",
        help="URL to POST/GET the test decision to (e.g., Jenkins input step, webhook)",
    )
    parser.add_argument(
        "--report-format",
        choices=["json", "form", "query"],
        default="json",
        help="Format for reporting: json (POST JSON), form (POST form data), query (GET with params). Default: json",
    )
    parser.add_argument(
        "--report-token",
        help="Optional auth token for reporting (sent as Bearer token in Authorization header)",
    )
    parser.add_argument(
        "--report-header",
        action="append",
        dest="report_headers",
        help="Optional custom header for reporting in 'Name: Value' format (can be repeated)",
    )

    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(level=logging.DEBUG)

    # Determine mode and run
    github_mode = args.repo is not None or args.pr is not None

    if github_mode:
        result, exit_code = run_github_mode(args=args)
    else:
        result, exit_code = run_local_mode(args=args)

    if exit_code != 0 or result is None:
        return exit_code

    # Format output
    if args.output == "json":
        output_content = format_json_output(result=result)
    else:
        output_content = format_markdown_output(result=result)

    # Print to stdout (for backward compatibility)
    print(output_content)

    # Write to output directory if specified
    if args.output_dir:
        try:
            # Create directory if it doesn't exist
            args.output_dir.mkdir(parents=True, exist_ok=True)

            # Determine filename based on format
            if args.output == "json":
                output_file = args.output_dir / "marker_analysis.json"
            else:
                output_file = args.output_dir / "marker_analysis.md"

            # Write output to file
            output_file.write_text(data=output_content, encoding="utf-8")
            logger.info(msg="Analysis output written", extra={"output_file": str(output_file)})

        except OSError as e:
            logger.error(msg="Failed to write output", extra={"output_dir": str(args.output_dir), "error": str(e)})
            return 1

    # Report to external system if URL provided
    if args.report_url:
        report_to_external_system(
            result=result,
            url=args.report_url,
            format_type=args.report_format,
            token=args.report_token,
            headers=args.report_headers,
            repo=args.repo,
            pr_number=args.pr,
        )  # All keyword args already used

    return 0


if __name__ == "__main__":
    sys.exit(main())

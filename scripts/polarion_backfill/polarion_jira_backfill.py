#!/usr/bin/env python3
"""Backfill Jira requirement links into test function docstrings.

Reads @pytest.mark.polarion("CNV-XXXXX") markers from a tests repository,
queries the Polarion API for each test case's linked requirements, extracts
the Jira ID from each requirement's hyperlinks (issues.redhat.com /
redhat.atlassian.net /browse/ URLs), and inserts ``Jira: <ID>`` as the first
line(s) of each test function's docstring.

The Polarion ID -> Jira mapping is cached to a JSON file so re-runs do not
re-hit the API (which may disappear as the code-first adoption proceeds).

Usage:
    # Show what would change, no API calls if mapping cache exists
    uv run --with pylero scripts/polarion_backfill/polarion_jira_backfill.py --tests-repo ~/git/openshift-virtualization-tests --dry-run

    # Apply changes
    uv run --with pylero scripts/polarion_backfill/polarion_jira_backfill.py --tests-repo ~/git/openshift-virtualization-tests --apply

    # Only fetch/refresh the mapping (no file edits)
    uv run --with pylero scripts/polarion_backfill/polarion_jira_backfill.py --tests-repo ~/git/openshift-virtualization-tests --mapping-only

Requires a pylero config (~/.pylero or ./.pylero) with credentials for
https://polarion.engineering.redhat.com/polarion. For the Red Hat internal
CA, set ``cert_path`` in the config or the ``SSL_CERT_FILE`` env var.
"""

from __future__ import annotations

import argparse
import ast
import importlib
import json
import logging
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from itertools import islice
from pathlib import Path
from typing import cast

LOGGER = logging.getLogger("polarion_jira_backfill")

POLARION_ID_RE = re.compile(r"^(CNV-\d+)$")
JIRA_URL_RE = re.compile(r"/browse/([A-Z][A-Z0-9]+-\d+)")
JIRA_URL_TEMPLATE = "https://redhat.atlassian.net/browse/{jid}"
STP_RE = re.compile(r"^\s*STP:?\s*\S", re.MULTILINE)

# Mapping cache statuses
STATUS_NOT_FOUND = "test_case_not_found"
STATUS_NO_REQUIREMENT = "no_linked_requirement"
STATUS_NO_JIRA = "requirement_has_no_jira_link"
STATUS_OK = "ok"


@dataclass
class TestFunction:
    """A test function found in a file, with its Polarion IDs."""

    name: str
    node: ast.FunctionDef | ast.AsyncFunctionDef
    polarion_ids: list[str] = field(default_factory=list)


@dataclass
class FileResult:
    path: Path
    functions: list[TestFunction] = field(default_factory=list)
    skipped_reason: str | None = None
    mapping: dict[str, dict] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------


def _polarion_ids_from_decorator(deco: ast.expr) -> list[str]:
    """Extract Polarion IDs from a single decorator node."""
    ids: list[str] = []

    # @pytest.mark.polarion("CNV-123")
    if (
        isinstance(deco, ast.Call)
        and isinstance(deco.func, ast.Attribute)
        and deco.func.attr == "polarion"
        and len(deco.args) == 1
        and isinstance(deco.args[0], ast.Constant)
        and isinstance(deco.args[0].value, str)
        and POLARION_ID_RE.match(deco.args[0].value)
    ):
        ids.append(deco.args[0].value)

    # @pytest.mark.parametrize(..., pytest.param(..., marks=pytest.mark.polarion("CNV-123")))
    if isinstance(deco, ast.Call) and isinstance(deco.func, ast.Attribute) and deco.func.attr == "parametrize":
        # Argvalues may be positional (2nd arg) or a keyword.
        argvalue_nodes: list[ast.expr] = list(deco.args[1:]) if len(deco.args) > 1 else []
        for keyword in deco.keywords:
            if keyword.arg == "argvalues":
                argvalue_nodes.append(keyword.value)
        for argvalues in argvalue_nodes:
            ids.extend(_polarion_ids_from_argvalues(argvalues))

    return ids


def _polarion_ids_from_argvalues(node: ast.expr) -> list[str]:
    """Extract Polarion IDs from parametrize argvalues (list of pytest.param(...))."""
    ids: list[str] = []
    if not isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return ids
    for elt in node.elts:
        if not isinstance(elt, ast.Call):
            continue
        for keyword in elt.keywords:
            if keyword.arg == "marks":
                marks = keyword.value
                mark_list = marks.elts if isinstance(marks, (ast.Tuple, ast.List)) else [marks]
                for mark in mark_list:
                    ids.extend(_polarion_ids_from_decorator(mark))
    return ids


def scan_file(path: Path, skip_stp: bool) -> FileResult:
    """Parse a test file and collect test functions with their Polarion IDs."""
    result = FileResult(path=path)
    try:
        source = path.read_text()
        tree = ast.parse(source)
    except (SyntaxError, UnicodeDecodeError, OSError) as exc:
        result.skipped_reason = f"parse error: {exc}"
        return result

    # Module docstring STP check: Test -> STP -> Jira is already complete.
    if skip_stp:
        module_doc = ast.get_docstring(tree)
        if module_doc and STP_RE.search(module_doc):
            result.skipped_reason = "module docstring already has STP link"
            return result

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.name.startswith("test_"):
            continue

        polarion_ids: list[str] = []
        for deco in node.decorator_list:
            polarion_ids.extend(_polarion_ids_from_decorator(deco))

        if polarion_ids:
            # Deduplicate while preserving order
            unique_ids = list(dict.fromkeys(polarion_ids))
            result.functions.append(TestFunction(name=node.name, node=node, polarion_ids=unique_ids))

    return result


def scan_repo(tests_repo: Path, team: str | None, skip_stp: bool, limit: int | None = None) -> list[FileResult]:
    """Scan the tests repository for files with Polarion-marked test functions."""
    root = tests_repo / "tests" if (tests_repo / "tests").is_dir() else tests_repo
    results: list[FileResult] = []
    paths = sorted(root.rglob("*.py"))
    if team:
        paths = [p for p in paths if f"/{team}/" in f"/{p.as_posix()}"]

    for path in paths:
        if not _looks_like_test_file(path):
            continue
        result = scan_file(path=path, skip_stp=skip_stp)
        if result.skipped_reason:
            LOGGER.debug("%s skipped: %s", path, result.skipped_reason)
            continue
        if result.functions:
            results.append(result)
            if limit and len(results) >= limit:
                break
    return results


def _looks_like_test_file(path: Path) -> bool:
    parts = path.parts
    return path.name.startswith("test_") or (len(parts) > 1 and parts[-2] == "tests")


# ---------------------------------------------------------------------------
# Polarion API
# ---------------------------------------------------------------------------


class PolarionMapper:
    """Resolves Polarion test case IDs to Jira requirement IDs, with a JSON cache."""

    def __init__(self, cache_file: Path, project_id: str = "CNV"):
        self.cache_file = cache_file
        self.project_id = project_id
        self.cache: dict[str, dict] = {}
        if cache_file.exists():
            try:
                self.cache = json.loads(cache_file.read_text())
            except json.JSONDecodeError:
                LOGGER.warning("cache file %s is corrupt, starting fresh", cache_file)
        self._session_started = False

    def _ensure_session(self) -> None:
        if self._session_started:
            return
        # Importing pylero.work_item initializes the pylero session (config,
        # credentials) as a side effect.
        importlib.import_module(name="pylero.work_item")
        self._session_started = True

    @staticmethod
    def _jira_ids_from_requirement(req) -> list[str]:
        """Extract Jira IDs from a requirement.

        Jira links live in different places depending on how the requirement
        was authored:
        - hyperlinks (role ref_ext) pointing at /browse/<KEY>
        - the 'jiraurl' custom field (a /browse/<KEY> URL)
        """
        jiras: list[str] = []

        def _add(match: re.Match | None) -> None:
            if match and match.group(1) not in jiras:
                jiras.append(match.group(1))

        for hl in req.hyperlinks:
            _add(match=JIRA_URL_RE.search(hl.uri))

        pylero_exceptions = importlib.import_module(name="pylero.exceptions")
        try:
            cf = req.get_custom_field(key="jiraurl")
        except pylero_exceptions.PyleroLibException:
            cf = None  # custom field not defined on this requirement
        value = getattr(cf, "value", None)
        if isinstance(value, str) and value:
            _add(match=JIRA_URL_RE.search(value))

        return jiras

    def resolve(self, polarion_id: str) -> dict:
        """Return (and cache) the mapping entry for a Polarion test case ID."""
        if polarion_id in self.cache:
            return self.cache[polarion_id]

        self._ensure_session()
        pylero_exceptions = importlib.import_module(name="pylero.exceptions")
        pylero_work_item = importlib.import_module(name="pylero.work_item")

        entry: dict = {"status": STATUS_OK, "jira": [], "requirements": []}
        try:
            tc = pylero_work_item.TestCase(project_id=self.project_id, work_item_id=polarion_id)
        except pylero_exceptions.PyleroLibException:
            entry["status"] = STATUS_NOT_FOUND
        else:
            for link in tc.linked_work_items:
                try:
                    req = pylero_work_item.Requirement(project_id=self.project_id, work_item_id=link.work_item_id)
                except pylero_exceptions.PyleroLibException:
                    continue  # linked item is not a requirement
                entry["requirements"].append(req.work_item_id)
                for jira_id in self._jira_ids_from_requirement(req):
                    if jira_id not in entry["jira"]:
                        entry["jira"].append(jira_id)

            if not entry["requirements"]:
                entry["status"] = STATUS_NO_REQUIREMENT
            elif not entry["jira"]:
                entry["status"] = STATUS_NO_JIRA

        self.cache[polarion_id] = entry
        return entry

    def save(self) -> None:
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        self.cache_file.write_text(data=json.dumps(obj=self.cache, indent=2, sort_keys=True))
        LOGGER.info("mapping cache saved to %s (%s IDs)", self.cache_file, len(self.cache))


# ---------------------------------------------------------------------------
# Docstring editing
# ---------------------------------------------------------------------------


def _indent_of(source_lines: list[str], lineno: int) -> str:
    """Leading whitespace of a 1-based line."""
    line = source_lines[lineno - 1]
    return line[: len(line) - len(line.lstrip())]


def _docstring_node(func: ast.FunctionDef | ast.AsyncFunctionDef) -> ast.Constant | None:
    """Return the docstring constant node of a function, if any."""
    if (
        func.body
        and isinstance(func.body[0], ast.Expr)
        and isinstance(func.body[0].value, ast.Constant)
        and isinstance(func.body[0].value.value, str)
    ):
        return func.body[0].value
    return None


def _existing_jira_ids(docstring: str) -> set[str]:
    """IDs of Jira lines already present — matches both bare and URL forms."""
    return set(re.findall(r"Jira:\s*(?:\S*/browse/)?([A-Z][A-Z0-9]+-\d+)", docstring))


def _existing_polarion_ids(docstring: str) -> set[str]:
    """Polarion IDs already present as Polarion: lines."""
    return set(re.findall(r"Polarion:\s*(CNV-\d+)", docstring))


def _polarion_lines(polarion_ids: list[str], indent: str) -> str:
    return "".join(f"{indent}Polarion: {pid}\n" for pid in polarion_ids)


def _jira_lines(jira_ids: list[str], indent: str) -> str:
    return "".join(f"{indent}Jira: {JIRA_URL_TEMPLATE.format(jid=jid)} # <skip-jira-utils-check>\n" for jid in jira_ids)


def _strip_polarion_marks(segment: str) -> str:
    """Remove pytest.mark.polarion(...) marks from a parametrize decorator."""
    polarion_call = r"pytest\.mark\.polarion\(\s*[\"']CNV-\d+[\"']\s*\)"
    # The call wrapped in parens or brackets: (call) / [call]
    wrapped = rf"[\(\[]\s*{polarion_call}\s*[\)\]]"
    if not re.search(polarion_call, segment):
        return segment  # nothing to strip — leave the decorator untouched
    # Sole marks value: marks=call, marks=(call), marks=[call]
    segment = re.sub(rf",\s*marks\s*=\s*(?:{wrapped}|{polarion_call})", "", segment)
    segment = re.sub(rf"marks\s*=\s*(?:{wrapped}|{polarion_call})\s*,\s*", "", segment)
    # Inside a marks tuple/list: strip the call, keep the other marks.
    segment = re.sub(rf"{polarion_call}\s*,\s*", "", segment)
    segment = re.sub(rf",\s*{polarion_call}", "", segment)
    # Dangling empty marks left behind.
    segment = re.sub(r",\s*marks\s*=\s*[\(\[]\s*[\)\]]", "", segment)
    # pytest.param whose only remaining content is a single simple argument
    # (no keywords) collapses to the bare value:
    # pytest.param(\n    "eth2",\n) -> "eth2"
    segment = re.sub(
        r"pytest\.param\(\s*((?:[\"'][^\"'\n]+[\"'])|[A-Za-z_][\w.]*)\s*,?\s*\)",
        r"\1",
        segment,
    )
    return segment


def _remove_polarion_markers(func: TestFunction, lines: list[str], edits: list[tuple[int, str, str]]) -> None:
    """Queue edits removing the function's polarion markers.

    The Polarion ID now lives in the docstring (Polarion: line), so the
    @pytest.mark.polarion decorator is removed. Parametrize decorators keep
    their parameters — only the polarion marks are stripped from them.
    """
    for deco in func.node.decorator_list:
        if not isinstance(deco, ast.Call) or not isinstance(deco.func, ast.Attribute):
            continue
        # end_lineno is Optional in the AST stubs but always set when lineno is.
        deco_end = deco.end_lineno or deco.lineno
        if deco.func.attr == "polarion":
            # Direct @pytest.mark.polarion("CNV-x") — delete the whole decorator.
            for i in range(deco.lineno - 1, deco_end):
                edits.append((i, lines[i], ""))
        elif deco.func.attr == "parametrize":
            start = deco.lineno - 1
            segment = "".join(lines[start:deco_end])
            new_segment = _strip_polarion_marks(segment)
            if new_segment != segment:
                start = deco.lineno - 1
                edits.append((start, lines[start], new_segment))
                for i in range(start + 1, deco_end):
                    edits.append((i, lines[i], ""))


def compute_new_source(result: FileResult) -> tuple[str | None, list[str]]:
    """Compute the edited source for a file.

    Returns (new_source, jira_ids_added); new_source is None when nothing
    changed (all Jira links already present).
    """
    source = result.path.read_text()
    lines = source.splitlines(keepends=True)
    edits: list[tuple[int, str, str]] = []  # (line_index, old, new)
    added: list[str] = []

    for func in result.functions:
        doc = _docstring_node(func=func.node)
        new_jiras = _jira_for_function(func=func, result=result)
        if not new_jiras:
            continue

        if doc is None:
            # No docstring: insert one as the first statement of the body.
            first_stmt = func.node.body[0]
            col = first_stmt.col_offset
            indent = " " * col
            idx = first_stmt.lineno - 1
            line = lines[idx]

            # Leading '#' comments directly above the first statement become
            # docstring text (the comment lines are removed).
            comment_idxs: list[int] = []
            j = idx - 1
            while j >= 0:
                candidate = lines[j]
                if not candidate.strip().startswith("#"):
                    break
                if candidate[:col].strip():
                    break  # less indented than the body — not this function's
                comment_idxs.append(j)
                j -= 1
            comment_texts = [lines[c].strip().lstrip("#").strip() for c in reversed(comment_idxs)]

            comment_lines = "".join(f"{indent}{text}\n" for text in comment_texts if text)
            blank = "\n" if comment_lines else ""
            doc_text = (
                f'{indent}"""\n{_jira_lines(jira_ids=new_jiras, indent=indent)}'
                f"{_polarion_lines(polarion_ids=func.polarion_ids, indent=indent)}"
                f'{blank}{comment_lines}{indent}"""\n'
            )
            edits.append((idx, line, doc_text + line))
            for c in comment_idxs:
                edits.append((c, lines[c], ""))
            _remove_polarion_markers(func=func, lines=lines, edits=edits)
            added.extend(new_jiras)
            continue

        # _docstring_node guarantees the constant holds a str.
        doc_value = cast(str, doc.value)
        existing = _existing_jira_ids(docstring=doc_value)
        to_add = [j for j in new_jiras if j not in existing]
        polarions_to_add = [p for p in func.polarion_ids if p not in _existing_polarion_ids(docstring=doc_value)]
        if not to_add:
            continue

        indent = _indent_of(source_lines=lines, lineno=doc.lineno)
        # The docstring may start on the same line as the opening quotes.
        doc_line = lines[doc.lineno - 1]
        quote_match = re.match(pattern=r"\s*(?:[rRuU]+)?('''|\"\"\")", string=doc_line)
        if not quote_match:
            # Not a triple-quoted docstring (e.g. 'text'): leave it untouched.
            LOGGER.warning(f"{result.path}: {func.name} has a non-triple-quoted docstring, skipping")
            continue
        quote = quote_match.group(1)
        quote_pos = quote_match.start(1)

        # The Polarion ID moves from the marker to the docstring.
        _remove_polarion_markers(func=func, lines=lines, edits=edits)

        # If the docstring already has a Jira line, insert the new Jira
        # line(s) directly after the LAST existing one (grouped together,
        # easy for the team to review). Text stays exactly where it is.
        # end_lineno is Optional in the AST stubs but always set when lineno is.
        doc_end = doc.end_lineno or doc.lineno
        if doc.lineno != doc_end:
            jira_line_idxs = [i for i in range(doc.lineno - 1, doc_end) if re.match(r"\s*Jira:", lines[i])]
            if jira_line_idxs:
                last = jira_line_idxs[-1]
                # Blank line after the inserted Jira/Polarion block when
                # content follows (e.g. Preconditions/Steps), but not before
                # the closing quotes.
                has_following = any(lines[i].strip() for i in range(last + 1, doc_end - 1))
                blank = "\n" if has_following else ""
                insertion = (
                    _jira_lines(jira_ids=to_add, indent=indent)
                    + _polarion_lines(polarion_ids=polarions_to_add, indent=indent)
                    + blank
                )
                edits.append((last, lines[last], lines[last] + insertion))
                added.extend(to_add)
                continue

        if doc.lineno == doc_end:
            # Single-line docstring: """text""" -> multi-line with Jira first
            # and the closing quotes on their own line.
            head = doc_line[: quote_pos + 3]
            quote_end = quote_pos + 3
            tail = doc_line[quote_end:]
            had_newline = tail.endswith("\n")
            body = tail.rstrip("\n")[:-3].rstrip()
            ending = "\n" if had_newline else ""
            blank = "\n" if body else ""
            new_doc_line = (
                f"{head}\n{_jira_lines(jira_ids=to_add, indent=indent)}"
                f"{_polarion_lines(polarion_ids=polarions_to_add, indent=indent)}{blank}"
                f"{indent}{body}\n{indent}{quote}{ending}"
            )
            idx = doc.lineno - 1
            edits.append((idx, lines[idx], new_doc_line))
        else:
            # Multi-line docstring: insert Jira lines after the opening line.
            # If content starts on the opening line ("""\ntext), handle both.
            quote_end = quote_pos + 3
            after_quote = doc_line[quote_end:]
            idx = doc.lineno - 1
            if after_quote.strip() == "":
                # Opening quotes alone on the line: insert lines after it.
                # Blank line between Jira/Polarion and the text, unless docstring is empty.
                blank = "\n" if doc_value.strip() else ""
                insertion = (
                    _jira_lines(jira_ids=to_add, indent=indent)
                    + _polarion_lines(polarion_ids=polarions_to_add, indent=indent)
                    + blank
                )
                line = lines[idx]
                edits.append((idx, line, line + insertion))
            else:
                # Content follows the opening quotes: split into its own line.
                head = doc_line[: quote_pos + 3]
                rest = after_quote.lstrip()
                new_doc_line = (
                    f"{head}\n{_jira_lines(jira_ids=to_add, indent=indent)}"
                    f"{_polarion_lines(polarion_ids=polarions_to_add, indent=indent)}"
                    f"{indent}\n{indent}{rest}"
                )
                edits.append((idx, lines[idx], new_doc_line))
        added.extend(to_add)

    if not edits:
        return None, []

    # Apply edits bottom-up so line numbers stay valid.
    new_lines = list(lines)
    for idx, old, new in sorted(edits, key=lambda e: e[0], reverse=True):
        assert new_lines[idx] == old, f"internal error: line mismatch at {idx + 1}"
        new_lines[idx] = new

    new_source = "".join(new_lines)
    # Sanity check: file must still parse.
    try:
        ast.parse(new_source)
    except SyntaxError as exc:  # pragma: no cover - defensive
        raise RuntimeError(f"{result.path}: edit produced invalid syntax: {exc}") from exc

    return new_source, added


def _jira_for_function(func: TestFunction, result: FileResult) -> list[str]:
    """Look up Jira IDs for a function's Polarion IDs via the file's mapping."""
    jiras: list[str] = []
    for pid in func.polarion_ids:
        entry = result.mapping.get(pid, {})
        for j in entry.get("jira", []):
            if j not in jiras:
                jiras.append(j)
    return jiras


def _fmt_duration(seconds: float) -> str:
    """Format seconds as e.g. '1m 20s' or '45s'."""
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {sec:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m {sec:02d}s"


def _log_resolve_progress(
    i: int,
    total: int,
    started: float,
    counters: dict[str, int],
    current: str,
) -> None:
    """Log a one-line progress status for the Polarion resolution loop."""
    elapsed = time.monotonic() - started
    rate = i / elapsed if elapsed > 0 else 0.0
    remaining = (total - i) / rate if rate > 0 else 0.0
    ok = counters.get(STATUS_OK, 0)
    problems = i - ok
    LOGGER.info(
        "[%s/%s] %3.0f%% | ok: %s | flagged: %s | elapsed: %s | ETA: %s | %s",
        i,
        total,
        100.0 * i / total if total else 100.0,
        ok,
        problems,
        _fmt_duration(elapsed),
        _fmt_duration(remaining),
        current,
    )


# ---------------------------------------------------------------------------
# PR creation
# ---------------------------------------------------------------------------


@dataclass
class PRGroup:
    """A planned PR: a branch with a set of edited files."""

    team: str
    branch: str
    files: list[tuple[Path, str]] = field(default_factory=list)  # (path, new_source)
    jira_ids: list[str] = field(default_factory=list)

    @property
    def title(self) -> str:
        return f"test({self.team}): add Jira requirement links to test docstrings"

    def body(self, flagged: list[str]) -> str:
        """PR body using the repo's required pull_request_template headings."""
        jira_list = ", ".join(sorted(set(self.jira_ids)))
        lines = [
            "##### What this PR does / why we need it:",
            "Adds Jira requirement traceability lines to test function docstrings:",
            "",
            (
                "- `Jira: https://redhat.atlassian.net/browse/<ID> # <skip-jira-utils-check>` "
                "line(s) added to each test docstring (after any existing `Jira:` "
                "lines, otherwise at the top)."
            ),
            (
                '- Polarion test-case IDs move from `@pytest.mark.polarion("CNV-XXXX")` '
                "decorators into the docstring as `Polarion: CNV-XXXX` lines; the "
                "decorators are removed."
            ),
            (
                "- Tests without a docstring get one: leading `#` comments above the "
                "test body become docstring text, and single-line docstrings are "
                "expanded to multi-line."
            ),
            (
                "- Polarion markers removed from parametrize decorators keep their "
                "parameters; only the `marks=pytest.mark.polarion(...)` entries are "
                "stripped."
            ),
            (
                "- Unused imports left behind by the marker removal (e.g. `pytest`) "
                "are cleaned up by the repo's pre-commit hooks (ruff)."
            ),
            "",
            (
                "Test-to-requirement traceability now lives in the code itself "
                "(code-first test management): each test links directly to its Jira "
                "requirement, resolved from the test's Polarion linkage. Polarion IDs "
                "are kept in the docstring so the existing Polarion linkage stays "
                "visible during the migration."
            ),
            "",
            "##### Which issue(s) this PR fixes:",
            "NONE",
            "",
            "##### Special notes for reviewer:",
            f"- {len(self.files)} test files changed",
            f"- Jira links added: {jira_list}",
            (
                "- Existing docstring text is preserved (only reflowed when a "
                "docstring is created or expanded to multi-line)."
            ),
            "- Test behavior is unchanged — docstrings and decorators only.",
        ]
        if flagged:
            flagged_list = ", ".join(sorted(set(flagged)))
            lines.append(f"- Polarion IDs flagged for manual review (no Jira link found): {flagged_list}")
        lines += [
            "",
            "##### jira-ticket:",
            "NONE",
            (
                "<!--  This PR is not tracked by a single Jira ticket — it adds "
                "requirement links to many Jiras; the requirement links live in the "
                "test docstrings. -->"
            ),
        ]
        return "\n".join(lines) + "\n"


def team_of(path: Path, tests_repo: Path) -> str:
    """Team = first directory under tests/ (fallback: repo-relative parent)."""
    try:
        rel = path.relative_to(tests_repo)
    except ValueError:
        return "misc"
    parts = rel.parts
    if len(parts) > 2 and parts[0] == "tests":
        return parts[1]
    if parts and parts[0] != "tests":
        return parts[0]
    return "misc"


def plan_pr_groups(
    changed: list[tuple[FileResult, str, list[str]]],
    tests_repo: Path,
    max_files_per_pr: int,
) -> list[PRGroup]:
    """Group changed files into PRs: by team, then chunks of max N files."""
    by_team: dict[str, list[tuple[Path, str, list[str]]]] = {}
    for result, new_source, jira_ids in changed:
        team = team_of(path=result.path, tests_repo=tests_repo)
        by_team.setdefault(team, []).append((result.path, new_source, jira_ids))

    groups: list[PRGroup] = []
    for team in sorted(by_team):
        files = sorted(by_team[team], key=lambda f: f[0].name)
        chunks = [list(islice(files, i, i + max_files_per_pr)) for i in range(0, len(files), max_files_per_pr)]
        for i, chunk in enumerate(chunks, 1):
            suffix = "" if len(chunks) == 1 else f"-part{i}"
            group = PRGroup(team=team, branch=f"backfill/jira-links-{team}{suffix}")
            for path, new_source, jira_ids in chunk:
                group.files.append((path, new_source))
                group.jira_ids.extend(jira_ids)
            groups.append(group)
    return groups


def _run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    """Run a subprocess, raising a readable error on failure."""
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise RuntimeError(f"command failed ({' '.join(cmd)}):\n{proc.stderr.strip() or proc.stdout.strip()}")
    return proc


def _git(tests_repo: Path, git_args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return _run(cmd=["git", "-C", str(tests_repo), *git_args], check=check)


def _detect_default_base(tests_repo: Path) -> str:
    """Best-effort detection of the upstream default branch (e.g. main)."""
    proc = _git(tests_repo=tests_repo, git_args=["symbolic-ref", "refs/remotes/origin/HEAD"], check=False)
    if proc.returncode == 0 and proc.stdout.strip():
        return proc.stdout.strip().replace("refs/remotes/origin/", "")
    return "main"


def _detect_fork_remote(tests_repo: Path) -> str:
    """Find a push remote that differs from origin (the user's fork)."""
    remotes = _git(tests_repo=tests_repo, git_args=["remote"]).stdout.split()
    if "fork" in remotes:
        return "fork"
    for remote in remotes:
        if remote == "origin":
            continue
        url = _git(tests_repo=tests_repo, git_args=["remote", "get-url", "--push", remote]).stdout.strip()
        origin_url = _git(tests_repo=tests_repo, git_args=["remote", "get-url", "--push", "origin"]).stdout.strip()
        if url and url != origin_url:
            return remote
    return "origin"


def _github_slug(url: str) -> str | None:
    """Extract 'owner/repo' from a git remote URL."""
    match = re.search(r"github\.com[:/]([^/]+/[^/]+?)(\.git)?$", url)
    return match.group(1) if match else None


def clone_upstream(tests_repo: Path, base: str, clone_dir: Path, fork_remote_name: str) -> tuple[Path, str]:
    """Freshly clone the upstream repo (base branch) into clone_dir.

    The local checkout is used only to discover the upstream and fork remote
    URLs — all scanning and edits happen in the clone, never on local code.
    """
    upstream_url = _git(tests_repo=tests_repo, git_args=["remote", "get-url", "--push", "origin"]).stdout.strip()
    fork_url = _git(tests_repo=tests_repo, git_args=["remote", "get-url", "--push", fork_remote_name]).stdout.strip()

    clone_dir.parent.mkdir(parents=True, exist_ok=True)
    _run(
        cmd=[
            "git",
            "clone",
            "--quiet",
            "--depth",
            "1",
            "--branch",
            base,
            "--single-branch",
            upstream_url,
            str(clone_dir),
        ]
    )

    # Add the fork as a push remote in the clone. Return the remote name to
    # use for pushes FROM THE CLONE (the local checkout's name may differ).
    clone_fork_remote = "origin"
    if fork_url and fork_url != upstream_url:
        _git(tests_repo=clone_dir, git_args=["remote", "add", "fork", fork_url])
        clone_fork_remote = "fork"

    # Ensure a commit identity exists (fresh clone may lack global git config).
    name = _git(tests_repo=clone_dir, git_args=["config", "--get", "user.name"], check=False).stdout.strip()
    if not name:
        login = (
            _run(cmd=["gh", "api", "user", "--jq", ".login"], cwd=clone_dir, check=False).stdout.strip()
            or "polarion-jira-backfill"
        )
        _git(tests_repo=clone_dir, git_args=["config", "user.name", login])
        _git(tests_repo=clone_dir, git_args=["config", "user.email", f"{login}@users.noreply.github.com"])

    return clone_dir, clone_fork_remote


def _pre_commit_cmd() -> list[str] | None:
    """Return the pre-commit command prefix, or None if unavailable."""
    if shutil.which("pre-commit"):
        return ["pre-commit"]
    if shutil.which("uvx"):
        return ["uvx", "pre-commit"]
    return None


def run_pre_commit(repo: Path, rel_paths: list[str]) -> None:
    """Run pre-commit on the changed files; it must pass.

    Auto-fixing hooks may modify files and fail the first run — files are
    re-staged and pre-commit is retried once. A second failure is an error
    (hooks are never bypassed).
    """
    if not (repo / ".pre-commit-config.yaml").exists():
        LOGGER.info("%s has no .pre-commit-config.yaml — nothing to run", repo)
        return
    cmd = _pre_commit_cmd()
    if cmd is None:
        raise RuntimeError(
            "pre-commit not found — install it (or make 'uvx' available) so hooks can run; hooks are never bypassed"
        )
    for attempt in (1, 2):
        proc = _run(cmd=[*cmd, "run", "--files", *rel_paths], cwd=repo, check=False)
        if proc.returncode == 0:
            LOGGER.info("pre-commit passed (attempt %s)", attempt)
            # Hooks may have auto-fixed files on a failed attempt that then
            # passed — re-stage whatever the current content is.
            _git(tests_repo=repo, git_args=["add", *rel_paths])
            return
        LOGGER.warning(
            "pre-commit failed (attempt %s of 2):\n%s",
            attempt,
            proc.stdout.strip() or proc.stderr.strip(),
        )
        # Re-stage possible auto-fixes before the retry.
        _git(tests_repo=repo, git_args=["add", *rel_paths])
    raise RuntimeError("pre-commit failed twice — fix the reported issues and re-run; hooks are never bypassed")


def open_prs(
    groups: list[PRGroup],
    tests_repo: Path,
    base: str,
    fork_remote: str,
    flagged: list[str],
    dry_run: bool,
    force_push: bool = False,
) -> list[str]:
    """Create branch + commit + push + PR for each group. Returns PR URLs."""
    # Safety: refuse to run on a dirty tree (our writes must be the only changes).
    status = _git(tests_repo=tests_repo, git_args=["status", "--porcelain"]).stdout
    dirty = [line for line in status.splitlines() if line and not line.startswith("??")]
    if dirty:
        raise RuntimeError(
            f"{tests_repo} has uncommitted changes to tracked files; commit or stash them before using --open-pr"
        )

    original_branch = _git(tests_repo=tests_repo, git_args=["branch", "--show-current"]).stdout.strip()
    base_ref = f"origin/{base}"
    pr_urls: list[str] = []

    upstream_url = _git(tests_repo=tests_repo, git_args=["remote", "get-url", "--push", "origin"]).stdout.strip()
    upstream_slug = _github_slug(url=upstream_url)
    fork_url = _git(tests_repo=tests_repo, git_args=["remote", "get-url", "--push", fork_remote]).stdout.strip()
    fork_slug = _github_slug(url=fork_url)
    fork_owner = fork_slug.split("/")[0] if fork_slug else None

    try:
        for group in groups:
            LOGGER.info(
                "%s PR %s: %s files, %s unique Jira links",
                "[dry-run] would open" if dry_run else "opening",
                group.branch,
                len(group.files),
                len(set(group.jira_ids)),
            )
            if dry_run:
                for path, _ in group.files:
                    LOGGER.info("    %s", path.relative_to(tests_repo))
                continue

            _git(
                tests_repo=tests_repo,
                git_args=["checkout", "-b", group.branch, base_ref],
            )
            for path, new_source in group.files:
                path.write_text(new_source)
            rel_paths = [str(p.relative_to(tests_repo)) for p, _ in group.files]
            _git(tests_repo=tests_repo, git_args=["add", *rel_paths])
            # pre-commit must pass before anything is committed.
            run_pre_commit(repo=tests_repo, rel_paths=rel_paths)
            # -s: DCO sign-off (required by the repo's DCO check).
            _git(
                tests_repo=tests_repo,
                git_args=["commit", "-s", "-m", group.title, "-m", group.body(flagged)],
            )
            # Enforce: the DCO sign-off must actually be on the commit.
            commit_msg = _git(tests_repo=tests_repo, git_args=["log", "-1", "--pretty=%B"]).stdout
            if "Signed-off-by:" not in commit_msg:
                raise RuntimeError(
                    f"{group.branch}: commit is missing the DCO Signed-off-by line "
                    "(check git user.name/user.email are configured)"
                )
            _git(
                tests_repo=tests_repo,
                git_args=[
                    "push",
                    *(["-f"] if force_push else []),
                    "-u",
                    fork_remote,
                    group.branch,
                ],
            )

            if upstream_slug and fork_owner:
                proc = _run(
                    cmd=[
                        "gh",
                        "pr",
                        "create",
                        "--repo",
                        upstream_slug,
                        "--head",
                        f"{fork_owner}:{group.branch}",
                        "--base",
                        base,
                        "--title",
                        group.title,
                        "--body",
                        group.body(flagged),
                    ],
                    cwd=tests_repo,
                    check=False,
                )
                if proc.returncode == 0:
                    pr_urls.append(proc.stdout.strip())
                    LOGGER.info("PR opened: %s", proc.stdout.strip())
                elif "already exists" in (proc.stderr + proc.stdout):
                    LOGGER.info(
                        "PR for %s already exists — the push above updated it",
                        group.branch,
                    )
                else:
                    LOGGER.error(
                        "gh pr create failed for %s:\n%s",
                        group.branch,
                        proc.stderr.strip() or proc.stdout.strip(),
                    )
            else:
                LOGGER.warning(
                    "could not determine GitHub slugs (upstream=%s, fork=%s); branch pushed, open the PR manually",
                    upstream_url,
                    fork_url,
                )
    finally:
        if not dry_run:
            _git(
                tests_repo=tests_repo,
                git_args=["checkout", original_branch],
                check=False,
            )

    return pr_urls


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--tests-repo",
        type=Path,
        required=True,
        help="Path to the tests repository (e.g. ~/git/openshift-virtualization-tests)",
    )
    parser.add_argument(
        "--team",
        help="Only process files under this team directory (e.g. 'storage')",
    )
    parser.add_argument(
        "--mapping-file",
        type=Path,
        default=Path("polarion-jira-mapping.json"),
        help="JSON cache of Polarion ID -> Jira mapping (default: %(default)s)",
    )
    parser.add_argument(
        "--project",
        default="CNV",
        help="Polarion project ID (default: %(default)s)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show changes without writing files")
    parser.add_argument("--apply", action="store_true", help="Write changes to the test files")
    parser.add_argument(
        "--mapping-only",
        action="store_true",
        help="Only build/refresh the mapping cache, do not edit files",
    )
    parser.add_argument(
        "--open-pr",
        action="store_true",
        help=(
            "Apply changes and open PRs (grouped by team, split into chunks of "
            "--max-files-per-pr files). Implies --apply. Requires a clean git tree."
        ),
    )
    parser.add_argument(
        "--max-files-per-pr",
        type=int,
        default=10,
        metavar="N",
        help="Maximum number of changed test files per PR (default: %(default)s)",
    )
    parser.add_argument(
        "--pr-base",
        help="Base branch for PRs (default: upstream default branch, e.g. main)",
    )
    parser.add_argument(
        "--max-prs",
        type=int,
        metavar="N",
        help=(
            "Open at most N PRs (e.g. for testing); remaining files are "
            "skipped and picked up on a later run. No limit when not passed."
        ),
    )
    parser.add_argument(
        "--pr-remote",
        help=("Git remote to push branches to, i.e. your fork (default: remote 'fork', else first non-origin remote)"),
    )
    parser.add_argument(
        "--clone-dir",
        type=Path,
        metavar="DIR",
        help=("Directory to clone the upstream repo into (default: fresh directory under /tmp)"),
    )
    parser.add_argument(
        "--keep-clone",
        action="store_true",
        help=("Keep the temporary clone after the run (always kept when --clone-dir is given)"),
    )
    parser.add_argument(
        "--use-local-repo",
        action="store_true",
        help=(
            "Operate on the local checkout instead of cloning upstream "
            "(not recommended — local code may diverge from upstream)"
        ),
    )
    parser.add_argument("--limit", type=int, help="Process at most N files (for testing)")
    parser.add_argument(
        "--skip-stp",
        action="store_true",
        help=(
            "Skip files whose module docstring already has an STP link "
            "(default: off — the Jira line is added even when an STP link "
            "or a Jira line already exists)"
        ),
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=25,
        metavar="N",
        help=("Log a Polarion resolution progress line every N IDs (default: %(default)s; 1 = every ID, 0 = disable)"),
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help=("Re-query Polarion IDs whose cached status is not ok (e.g. after a bug fix in the extraction logic)"),
    )
    parser.add_argument(
        "--force-push",
        action="store_true",
        help=(
            "Force-push PR branches (replaces existing commits on the fork "
            "branch, e.g. to update an existing PR with regenerated content)"
        ),
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Debug logging")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    if not args.tests_repo.is_dir():
        parser.error(f"tests repo not found: {args.tests_repo}")
    if args.max_files_per_pr < 1:
        parser.error("--max-files-per-pr must be >= 1")

    # Working repo: by default a fresh clone of upstream/<base> — never the
    # local checkout. The local repo is only used to discover remotes.
    base: str | None = None
    fork_remote: str | None = None
    cleanup_clone = False
    if args.use_local_repo:
        work_repo = args.tests_repo
        LOGGER.info("using LOCAL checkout %s (branch state as-is)", work_repo)
    else:
        base = args.pr_base or _detect_default_base(args.tests_repo)
        fork_remote = args.pr_remote or _detect_fork_remote(args.tests_repo)
        if args.open_pr and fork_remote == "origin":
            parser.error(
                "--open-pr needs a fork remote: add a 'fork' remote to your "
                "checkout or pass --pr-remote <name> (refusing to push to origin)"
            )
        if args.clone_dir and args.clone_dir.exists() and any(args.clone_dir.iterdir()):
            parser.error(f"--clone-dir exists and is not empty: {args.clone_dir}")
        cleanup_clone = not (args.keep_clone or args.clone_dir)
        clone_dir = args.clone_dir or Path(tempfile.mkdtemp(prefix="polarion-jira-backfill-", dir="/tmp"))
        LOGGER.info(
            "cloning upstream %s (branch %s) into %s",
            _git(
                tests_repo=args.tests_repo,
                git_args=["remote", "get-url", "--push", "origin"],
            ).stdout.strip(),
            base,
            clone_dir,
        )
        try:
            work_repo, fork_remote = clone_upstream(
                tests_repo=args.tests_repo,
                base=base,
                clone_dir=clone_dir,
                fork_remote_name=fork_remote,
            )
        except RuntimeError as exc:
            LOGGER.error("clone failed: %s", exc)
            if cleanup_clone:
                shutil.rmtree(clone_dir, ignore_errors=True)
            return 1
        if args.apply and not args.open_pr and cleanup_clone:
            LOGGER.warning(
                "--apply without --open-pr on a temporary clone: changes will be "
                "removed with the clone — use --keep-clone or --clone-dir to keep them"
            )

    try:
        return _run_backfill(args=args, work_repo=work_repo, base=base, fork_remote=fork_remote)
    finally:
        if cleanup_clone:
            LOGGER.info("removing temporary clone %s", work_repo)
            shutil.rmtree(work_repo, ignore_errors=True)


def _run_backfill(args: argparse.Namespace, work_repo: Path, base: str | None, fork_remote: str | None) -> int:
    results = scan_repo(
        tests_repo=work_repo,
        team=args.team,
        skip_stp=args.skip_stp,
        limit=args.limit,
    )
    if not results:
        LOGGER.info("no files with Polarion-marked test functions found")
        return 0

    all_ids: list[str] = []
    for r in results:
        for f in r.functions:
            all_ids.extend(f.polarion_ids)
    unique_ids = sorted(set(all_ids))
    LOGGER.info(
        "found %s files, %s test functions, %s unique Polarion IDs",
        len(results),
        sum(len(r.functions) for r in results),
        len(unique_ids),
    )

    mapper = PolarionMapper(cache_file=args.mapping_file, project_id=args.project)
    if args.retry_failed:
        failed = [pid for pid in unique_ids if pid in mapper.cache and mapper.cache[pid].get("status") != STATUS_OK]
        for pid in failed:
            del mapper.cache[pid]
        if failed:
            LOGGER.info("--retry-failed: re-querying %s cached non-ok IDs", len(failed))
    cached = sum(1 for pid in unique_ids if pid in mapper.cache)
    LOGGER.info("%s IDs already in cache, %s to query", cached, len(unique_ids) - cached)

    # Resolve all unique Polarion IDs (uses cache, queries Polarion for misses).
    status_counters: dict[str, int] = {}
    resolve_started = time.monotonic()
    try:
        for i, pid in enumerate(unique_ids, 1):
            entry = mapper.resolve(polarion_id=pid)
            status_counters[entry["status"]] = status_counters.get(entry["status"], 0) + 1
            if args.progress_every and (i % args.progress_every == 0 or i == len(unique_ids)):
                _log_resolve_progress(
                    i=i,
                    total=len(unique_ids),
                    started=resolve_started,
                    counters=status_counters,
                    current=pid,
                )
    finally:
        mapper.save()
        elapsed = time.monotonic() - resolve_started
        LOGGER.info(
            "resolution finished in %s: %s ok, %s flagged",
            _fmt_duration(elapsed),
            status_counters.get(STATUS_OK, 0),
            len(unique_ids) - status_counters.get(STATUS_OK, 0),
        )

    if args.mapping_only:
        _report_mapping(mapper=mapper, unique_ids=unique_ids)
        return 0

    dry_run = args.dry_run or not (args.apply or args.open_pr)
    if dry_run:
        LOGGER.info("DRY RUN — no files will be written (use --apply or --open-pr)")

    # Compute all edits in memory first (also needed for PR grouping).
    changed: list[tuple[FileResult, str, list[str]]] = []
    flagged: dict[str, list[str]] = {}
    for r in results:
        r.mapping = {pid: mapper.cache[pid] for f in r.functions for pid in f.polarion_ids}
        for f in r.functions:
            for pid in f.polarion_ids:
                status = mapper.cache[pid]["status"]
                if status != STATUS_OK:
                    flagged.setdefault(status, []).append(pid)
        try:
            new_source, added = compute_new_source(result=r)
        except RuntimeError as exc:
            LOGGER.error("%s", exc)
            continue
        if new_source is not None:
            changed.append((r, new_source, added))

    if not changed:
        LOGGER.info("no files need changes")
        _report_mapping(mapper=mapper, unique_ids=unique_ids, flagged=flagged)
        return 0

    total_added = [j for _, _, added in changed for j in added]
    LOGGER.info(
        "%s files %s, %s Jira links added",
        len(changed),
        "would change" if dry_run else "changed",
        len(total_added),
    )

    if args.open_pr:
        if base is None:
            base = args.pr_base or _detect_default_base(args.tests_repo)
        if fork_remote is None:
            fork_remote = args.pr_remote or _detect_fork_remote(args.tests_repo)
        if fork_remote == "origin":
            LOGGER.error(
                "--open-pr needs a fork remote: add a 'fork' remote to your "
                "checkout or pass --pr-remote <name> (refusing to push to origin)"
            )
            return 1
        groups = plan_pr_groups(changed=changed, tests_repo=work_repo, max_files_per_pr=args.max_files_per_pr)
        if args.max_prs is not None and len(groups) > args.max_prs:
            max_prs = args.max_prs
            skipped_files = sum(len(g.files) for g in groups[max_prs:])
            skipped_prs = [g.branch for g in groups[max_prs:]]
            groups = groups[:max_prs]
            LOGGER.info(
                "--max-prs %s: limiting to %s PR(s); %s files in %s skipped "
                "PR(s) (%s) — a later run without --max-prs will pick them up",
                args.max_prs,
                len(groups),
                skipped_files,
                len(skipped_prs),
                ", ".join(skipped_prs),
            )
        LOGGER.info(
            "%s PR(s) planned (base=%s, fork remote=%s, max %s files per PR)",
            len(groups),
            base,
            fork_remote,
            args.max_files_per_pr,
        )
        try:
            pr_urls = open_prs(
                groups=groups,
                tests_repo=work_repo,
                base=base,
                fork_remote=fork_remote,
                flagged=[p for ids in flagged.values() for p in ids],
                dry_run=dry_run,
                force_push=args.force_push,
            )
            if pr_urls:
                LOGGER.info("opened %s PRs:\n%s", len(pr_urls), "\n".join(pr_urls))
        except RuntimeError as exc:
            LOGGER.error("%s", exc)
            return 1
    elif not dry_run:
        for r, new_source, added in changed:
            r.path.write_text(new_source)
            LOGGER.info("%s: added %s", r.path, ", ".join(sorted(set(added))))

    _report_mapping(mapper=mapper, unique_ids=unique_ids, flagged=flagged)
    return 0


def _report_mapping(mapper: PolarionMapper, unique_ids: list[str], flagged: dict | None = None) -> None:
    flagged = flagged or {}
    if flagged.get(STATUS_NOT_FOUND):
        LOGGER.warning(
            "test cases not found in Polarion (%s): %s",
            len(flagged[STATUS_NOT_FOUND]),
            ", ".join(sorted(set(flagged[STATUS_NOT_FOUND]))[:20]),
        )
    if flagged.get(STATUS_NO_REQUIREMENT):
        LOGGER.warning(
            "no linked requirement (%s): %s",
            len(flagged[STATUS_NO_REQUIREMENT]),
            ", ".join(sorted(set(flagged[STATUS_NO_REQUIREMENT]))[:20]),
        )
    if flagged.get(STATUS_NO_JIRA):
        LOGGER.warning(
            "requirement has no Jira link (%s): %s",
            len(flagged[STATUS_NO_JIRA]),
            ", ".join(sorted(set(flagged[STATUS_NO_JIRA]))[:20]),
        )
    ok = [pid for pid in unique_ids if mapper.cache.get(pid, {}).get("status") == STATUS_OK]
    LOGGER.info("mapping summary: %s/%s IDs resolved to a Jira link", len(ok), len(unique_ids))


if __name__ == "__main__":
    sys.exit(main())

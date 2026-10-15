"""Check newly introduced linter suppression directives."""

from __future__ import annotations

from ast import Module, dump, parse, stmt, walk
from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
from io import StringIO
from pathlib import Path, PurePosixPath
from re import IGNORECASE, compile, fullmatch
from tokenize import COMMENT, generate_tokens
from tomllib import TOMLDecodeError, loads
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from scripts.pre_commit_hooks.policy_types import PolicyViolation

if TYPE_CHECKING:
    from collections.abc import Collection, Mapping
    from typing import Any

EXCEPTIONS_PATH = Path("scripts/pre_commit_hooks/exceptions.toml")
_DIRECTIVE_PATTERNS = {
    "noqa": compile(pattern=r"#\s*noqa\b", flags=IGNORECASE),
    "type-ignore": compile(pattern=r"#\s*type\s*:\s*ignore\b", flags=IGNORECASE),
    "pylint-disable": compile(pattern=r"#\s*pylint\s*:\s*disable\b", flags=IGNORECASE),
}
_PLACEHOLDER_VALUES = frozenset({"", "-", ".", "n/a", "none", "tba", "tbd"})


class ExceptionManifestError(ValueError):
    """Report an invalid linter-directive exception manifest."""


class _InvalidDirectiveError(ValueError):
    def __init__(self, line_number: int, directive: str) -> None:
        super().__init__(f"line {line_number} must contain exactly one supported suppression: {directive!r}")
        self.line_number = line_number


@dataclass(frozen=True, slots=True)
class DirectiveException:
    """Describe one explicitly reviewed linter-directive exception."""

    rule: str
    path: str
    directive: str
    source_fingerprint: str
    reason: str
    approval_url: str


@dataclass(frozen=True, slots=True)
class _Directive:
    rule: str
    text: str
    line_number: int
    fingerprint: str

    @property
    def identity(self) -> tuple[str, str, str]:
        return self.rule, self.text, self.fingerprint


def _normalized_directive(comment: str) -> str:
    return " ".join(comment.strip().split())


def _rule_for_directive(directive: str) -> str:
    matches = [rule for rule, pattern in _DIRECTIVE_PATTERNS.items() if pattern.search(string=directive)]
    if len(matches) != 1:
        raise ExceptionManifestError(f"directive must contain exactly one supported suppression: {directive!r}")
    return matches[0]


def _statement_fingerprint_source(tree: Module, line_number: int) -> str:
    statements = [
        node
        for node in walk(tree)
        if isinstance(node, stmt)
        and node.lineno <= line_number <= (getattr(node, "end_lineno", node.lineno) or node.lineno)
    ]
    if not statements:
        return "comment"
    statement = min(
        statements,
        key=lambda node: ((getattr(node, "end_lineno", node.lineno) or node.lineno) - node.lineno, -node.col_offset),
    )
    return dump(node=statement, annotate_fields=True, include_attributes=False)


def _compute_source_fingerprint(
    tree: Module,
    line_number: int,
    directive: str,
    rule: str,
) -> str:
    normalized = _normalized_directive(comment=directive)
    statement = _statement_fingerprint_source(tree=tree, line_number=line_number)
    digest = sha256(f"{rule}\0{normalized}\0{statement}".encode()).hexdigest()
    return f"sha256:{digest}"


def compute_source_fingerprint(source: str, line_number: int, directive: str) -> str:
    """Return the stable fingerprint used by ``exceptions.toml``.

    The SHA-256 input is the directive rule, normalized directive comment, and
    the smallest enclosing statement's attribute-free AST. Standalone comments
    use a stable sentinel, so line moves do not change fingerprints.

    Args:
        source: Complete Python source containing the directive.
        line_number: One-based directive comment line.
        directive: Complete directive comment text.

    Returns:
        A ``sha256:<hex>`` fingerprint.

    Raises:
        ExceptionManifestError: If the comment contains zero or multiple
            supported suppression directives.
        SyntaxError: If ``source`` is invalid Python.
    """
    normalized = _normalized_directive(comment=directive)
    return _compute_source_fingerprint(
        tree=parse(source=source),
        line_number=line_number,
        directive=normalized,
        rule=_rule_for_directive(directive=normalized),
    )


def _directives(source: str) -> list[_Directive]:
    tree = parse(source=source)
    directives: list[_Directive] = []
    for token in generate_tokens(readline=StringIO(source).readline):
        if token.type != COMMENT:
            continue
        normalized = _normalized_directive(comment=token.string)
        matching_rules = [rule for rule, pattern in _DIRECTIVE_PATTERNS.items() if pattern.search(string=normalized)]
        if len(matching_rules) > 1:
            raise _InvalidDirectiveError(line_number=token.start[0], directive=normalized)
        if not matching_rules:
            continue
        rule = matching_rules[0]
        directives.append(
            _Directive(
                rule=rule,
                text=normalized,
                line_number=token.start[0],
                fingerprint=_compute_source_fingerprint(
                    tree=tree,
                    line_number=token.start[0],
                    directive=normalized,
                    rule=rule,
                ),
            )
        )
    return directives


def _required_string(record: dict[str, Any], field: str, index: int) -> str:
    value = record.get(field)
    if not isinstance(value, str) or value.strip().lower() in _PLACEHOLDER_VALUES:
        raise ExceptionManifestError(f"exceptions[{index}].{field} must be a non-placeholder string")
    return value.strip()


def _validate_path(path: str, index: int) -> str:
    normalized = PurePosixPath(path).as_posix()
    if path != normalized or PurePosixPath(path).is_absolute() or ".." in PurePosixPath(path).parts:
        raise ExceptionManifestError(f"exceptions[{index}].path must be a normalized repository-relative path")
    if any(character in path for character in "*?[]"):
        raise ExceptionManifestError(f"exceptions[{index}].path cannot contain wildcards")
    return path


def _validate_approval_url(url: str, index: int) -> str:
    parsed = urlparse(url=url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ExceptionManifestError(f"exceptions[{index}].approval_url must be an http(s) review URL")
    return url


def load_exceptions(source: str) -> tuple[DirectiveException, ...]:
    """Parse and strictly validate a linter-directive exception manifest.

    Args:
        source: TOML manifest source.

    Returns:
        Exact exception records.

    Raises:
        ExceptionManifestError: If the manifest is malformed or too broad.
    """
    try:
        data = loads(source)
    except TOMLDecodeError as error:
        raise ExceptionManifestError(f"invalid TOML: {error}") from error
    if set(data) != {"exceptions"} or not isinstance(data["exceptions"], list):
        raise ExceptionManifestError("manifest must contain only an 'exceptions' array")

    expected_fields = {"rule", "path", "directive", "source_fingerprint", "reason", "approval_url"}
    exceptions: list[DirectiveException] = []
    for index, raw_record in enumerate(data["exceptions"]):
        if not isinstance(raw_record, dict) or set(raw_record) != expected_fields:
            raise ExceptionManifestError(
                f"exceptions[{index}] must contain exactly: {', '.join(sorted(expected_fields))}"
            )
        rule = _required_string(record=raw_record, field="rule", index=index)
        if rule not in _DIRECTIVE_PATTERNS:
            raise ExceptionManifestError(
                f"exceptions[{index}].rule must be one of: {', '.join(sorted(_DIRECTIVE_PATTERNS))}"
            )
        directive = _required_string(record=raw_record, field="directive", index=index)
        if _rule_for_directive(directive=directive) != rule:
            raise ExceptionManifestError(f"exceptions[{index}].directive does not match its rule")
        fingerprint = _required_string(record=raw_record, field="source_fingerprint", index=index)
        if fullmatch(pattern=r"sha256:[0-9a-f]{64}", string=fingerprint) is None:
            raise ExceptionManifestError(f"exceptions[{index}].source_fingerprint must be a sha256 fingerprint")
        exceptions.append(
            DirectiveException(
                rule=rule,
                path=_validate_path(
                    path=_required_string(record=raw_record, field="path", index=index),
                    index=index,
                ),
                directive=_normalized_directive(comment=directive),
                source_fingerprint=fingerprint,
                reason=_required_string(record=raw_record, field="reason", index=index),
                approval_url=_validate_approval_url(
                    url=_required_string(record=raw_record, field="approval_url", index=index),
                    index=index,
                ),
            )
        )
    identities = [(record.rule, record.path, record.directive, record.source_fingerprint) for record in exceptions]
    if len(set(identities)) != len(identities):
        raise ExceptionManifestError("duplicate exception records are not allowed")
    return tuple(exceptions)


def _new_directive_identities(
    file_path: Path,
    indexed_source: str,
    head_source: str | None,
) -> list[tuple[str, str, str, str]]:
    indexed_directives = _directives(source=indexed_source)
    head_counts = Counter(directive.identity for directive in _directives(source=head_source or ""))
    identities: list[tuple[str, str, str, str]] = []
    for directive in indexed_directives:
        if head_counts[directive.identity]:
            head_counts[directive.identity] -= 1
        else:
            identities.append((directive.rule, file_path.as_posix(), directive.text, directive.fingerprint))
    return sorted(identities)


def check_manifest_update(
    indexed_source: str,
    head_source: str | None,
    file_path: Path = EXCEPTIONS_PATH,
    staged_sources: Mapping[Path, tuple[str, str | None]] | None = None,
    renamed_away_paths: frozenset[Path] = frozenset(),
) -> list[PolicyViolation]:
    """Validate staged exception records and protect existing approval metadata.

    Args:
        indexed_source: Manifest source from the Git index.
        head_source: Manifest source from ``HEAD``, if it exists.
        file_path: Path used in policy violations.
        staged_sources: Staged Python source and its path-specific ``HEAD``
            baseline. Every new record must match a new directive occurrence.
        renamed_away_paths: Head paths renamed in this commit. Retained
            records for these paths must be removed alongside the rename.

    Returns:
        Malformed metadata, modified approval, or orphan-record violations.
    """
    try:
        indexed = load_exceptions(source=indexed_source)
        head = load_exceptions(source=head_source) if head_source is not None else ()
    except ExceptionManifestError as error:
        return [
            PolicyViolation(
                file_path=file_path,
                line_number=None,
                message=f"linter-directives: fix malformed exception manifest: {error}",
            )
        ]

    indexed_by_identity = {
        (record.rule, record.path, record.directive, record.source_fingerprint): record for record in indexed
    }
    head_identities = {(record.rule, record.path, record.directive, record.source_fingerprint) for record in head}
    for old_record in head:
        identity = (old_record.rule, old_record.path, old_record.directive, old_record.source_fingerprint)
        if new_record := indexed_by_identity.get(identity):
            if (new_record.reason, new_record.approval_url) != (old_record.reason, old_record.approval_url):
                return [
                    PolicyViolation(
                        file_path=file_path,
                        line_number=None,
                        message=(
                            "linter-directives: do not modify existing reason/approval_url fields; "
                            "add a separately reviewed exception record"
                        ),
                    )
                ]

    staged_directives: Counter[tuple[str, str, str, str]] = Counter()
    for source_path, (source, source_at_head) in (staged_sources or {}).items():
        try:
            staged_directives.update(
                _new_directive_identities(
                    file_path=source_path,
                    indexed_source=source,
                    head_source=source_at_head,
                )
            )
        except SyntaxError, _InvalidDirectiveError:
            continue

    violations: list[PolicyViolation] = []
    new_record_identities = sorted(indexed_by_identity.keys() - head_identities)
    for identity in new_record_identities:
        record = indexed_by_identity[identity]
        if staged_directives[identity]:
            staged_directives[identity] -= 1
            continue
        violations.append(
            PolicyViolation(
                file_path=file_path,
                line_number=None,
                message=(
                    "linter-directives: each new exception record must match one newly staged suppression "
                    f"directive occurrence in the same index snapshot: {record.path} {record.directive!r}"
                ),
            )
        )
    for identity, occurrences in sorted(staged_directives.items()):
        if not occurrences:
            continue
        path = identity[1]
        directive = identity[2]
        if identity in indexed_by_identity:
            guidance = (
                "additional identical suppression occurrences cannot be authorized because duplicate exception "
                "records are forbidden; remove the additional suppression"
            )
        else:
            guidance = "add one new exact exception record for this newly staged suppression"
        for _occurrence in range(occurrences):
            violations.append(
                PolicyViolation(
                    file_path=file_path,
                    line_number=None,
                    message=f"linter-directives: {guidance}: {path} {directive!r}",
                )
            )
    for retained_path in sorted({Path(record.path) for record in indexed} & renamed_away_paths):
        violations.append(
            PolicyViolation(
                file_path=file_path,
                line_number=None,
                message=(
                    "linter-directives: this path was renamed; remove the obsolete exception record "
                    f"for {retained_path}"
                ),
            )
        )
    return violations


def check_linter_directives(
    file_path: Path,
    indexed_source: str,
    head_source: str | None,
    exceptions: Collection[DirectiveException],
) -> list[PolicyViolation]:
    """Reject suppression directives newly introduced or changed from ``HEAD``.

    Args:
        file_path: Repository-relative Python source path.
        indexed_source: Current source from the Git index.
        head_source: Previous source from ``HEAD``, if any.
        exceptions: Exact reviewed exception records.

    Returns:
        Invalid or unapproved directive occurrences in source order.
    """
    try:
        indexed_directives = _directives(source=indexed_source)
        head_directives = _directives(source=head_source or "")
    except _InvalidDirectiveError as error:
        return [
            PolicyViolation(
                file_path=file_path,
                line_number=error.line_number,
                message=f"linter-directives: {error}",
            )
        ]
    head_counts = Counter(directive.identity for directive in head_directives)
    allowed = Counter((record.rule, record.path, record.directive, record.source_fingerprint) for record in exceptions)
    violations: list[PolicyViolation] = []
    for directive in indexed_directives:
        if head_counts[directive.identity]:
            head_counts[directive.identity] -= 1
            continue
        exception_identity = (directive.rule, file_path.as_posix(), directive.text, directive.fingerprint)
        if allowed[exception_identity]:
            allowed[exception_identity] -= 1
            continue
        violations.append(
            PolicyViolation(
                file_path=file_path,
                line_number=directive.line_number,
                message=(
                    f"linter-directives/{directive.rule}: remove {directive.text!r} or add an exact, "
                    "reviewed exceptions.toml record"
                ),
            )
        )
    return violations

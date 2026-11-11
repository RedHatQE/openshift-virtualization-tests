"""Unit tests for linter-directive exception policy checks."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from pytest import mark, raises

from scripts.pre_commit_hooks.check_linter_directives import (
    ExceptionManifestError,
    check_linter_directives,
    check_manifest_update,
    compute_source_fingerprint,
    load_exceptions,
)


def test_only_token_comments_are_directives() -> None:
    """Suppression-looking text in strings and docstrings is ignored."""
    source = '''
"""Documentation mentioning # noqa: D100."""
value = "# type: ignore"
# noqa: E501
# type: ignore
# pylint: disable=E501
'''

    violations = check_linter_directives(
        file_path=Path("utilities/example.py"),
        indexed_source=source,
        head_source="",
        exceptions=(),
    )

    assert [(violation.line_number, violation.message) for violation in violations] == [
        (4, "linter-directives/noqa: remove '# noqa: E501' or add an exact, reviewed exceptions.toml record"),
        (5, "linter-directives/type-ignore: remove '# type: ignore' or add an exact, reviewed exceptions.toml record"),
        (
            6,
            "linter-directives/pylint-disable: remove '# pylint: disable=E501' or add an exact, reviewed exceptions.toml record",
        ),
    ], "only real source comments should be treated as suppression directives"


def test_changed_statement_with_same_directive_is_new_and_requires_review() -> None:
    """Changing the statement under an unchanged directive changes its fingerprint."""
    head_source = "value = 1  # noqa: E123\n"
    indexed_source = "value = 2  # noqa: E123\n"

    violations = check_linter_directives(
        file_path=Path("utilities/example.py"),
        indexed_source=indexed_source,
        head_source=head_source,
        exceptions=(),
    )

    assert len(violations) == 1, "a directive attached to changed source must be reviewed again"
    assert violations[0].line_number == 1, "the changed directive should report its source line"
    assert "noqa" in violations[0].message, "the violation should identify the changed directive rule"


def test_changed_sibling_statement_with_same_directive_is_new_and_requires_review() -> None:
    """Changing a same-line sibling under an unchanged directive changes its fingerprint."""
    head_source = "first = 1; second = 2  # noqa: E501\n"
    indexed_source = "first = 1; second = 3  # noqa: E501\n"

    violations = check_linter_directives(
        file_path=Path("utilities/example.py"),
        indexed_source=indexed_source,
        head_source=head_source,
        exceptions=(),
    )

    assert len(violations) == 1, "a directive attached to a changed sibling must be reviewed again"
    assert violations[0].line_number == 1, "the changed directive should report its source line"
    assert "# noqa: E501" in violations[0].message, "the violation should identify the changed directive"


def test_changed_call_in_same_line_sibling_with_directive_requires_review() -> None:
    """Changing a sibling call under an unchanged directive changes its fingerprint."""
    head = "first = 1; second = dangerous()  # noqa: E501\n"
    changed = "first = 1; second = safe()  # noqa: E501\n"

    violations = check_linter_directives(
        file_path=Path("utilities/example.py"),
        indexed_source=changed,
        head_source=head,
        exceptions=(),
    )

    assert [(violation.line_number, violation.message) for violation in violations] == [
        (1, "linter-directives/noqa: remove '# noqa: E501' or add an exact, reviewed exceptions.toml record")
    ], "changing a same-line sibling call must require renewed review of its directive"


def test_unchanged_directive_remains_stable_when_source_line_shifts() -> None:
    """Moving an unchanged directive to another line does not change its fingerprint."""
    head_source = "value = 1  # noqa: E501\n"
    indexed_source = "prefix = 0\n" + head_source

    violations = check_linter_directives(
        file_path=Path("utilities/example.py"),
        indexed_source=indexed_source,
        head_source=head_source,
        exceptions=(),
    )

    assert violations == [], "line shifts must not require a new exception for unchanged source"


def test_edited_directive_is_new_even_when_its_statement_is_unchanged() -> None:
    """Editing the directive text creates a new occurrence."""
    head_source = "value = 1  # noqa: E123\n"
    indexed_source = "value = 1  # noqa: E124\n"

    violations = check_linter_directives(
        file_path=Path("utilities/example.py"),
        indexed_source=indexed_source,
        head_source=head_source,
        exceptions=(),
    )

    assert len(violations) == 1, "an edited directive must not inherit the old approval"
    assert "# noqa: E124" in violations[0].message, "the edited directive should appear in the violation"


def test_legacy_duplicate_directives_are_consumed_by_occurrence_count() -> None:
    """Only occurrences beyond the number present in HEAD are considered new."""
    head_source = "value = 1  # noqa: E123\nvalue = 1  # noqa: E123\n"
    indexed_source = head_source + "value = 1  # noqa: E123\n"

    violations = check_linter_directives(
        file_path=Path("utilities/example.py"),
        indexed_source=indexed_source,
        head_source=head_source,
        exceptions=(),
    )

    assert [(violation.line_number, violation.message) for violation in violations] == [
        (3, "linter-directives/noqa: remove '# noqa: E123' or add an exact, reviewed exceptions.toml record")
    ], "duplicate legacy occurrences should ratchet one occurrence at a time"


def test_exception_requires_exact_path_normalized_directive_and_fingerprint() -> None:
    """An exception permits exactly the reviewed source occurrence."""
    file_path = Path("utilities/example.py")
    source = "value = 1  #    noqa: E123\n"
    fingerprint = compute_source_fingerprint(
        source=source,
        line_number=1,
        directive="#    noqa: E123",
    )
    manifest = f'''[[exceptions]]
rule = "noqa"
path = "{file_path.as_posix()}"
directive = "# noqa: E123"
source_fingerprint = "{fingerprint}"
reason = "legacy generated code"
approval_url = "https://github.com/example/review/1"
'''

    exceptions = load_exceptions(source=manifest)
    violations = check_linter_directives(
        file_path=file_path,
        indexed_source=source,
        head_source="",
        exceptions=exceptions,
    )

    assert violations == [], "normalized directive text and its exact fingerprint should authorize the occurrence"
    assert exceptions[0].directive == "# noqa: E123", "manifest directives should be normalized"


def test_wrong_exception_path_or_fingerprint_does_not_authorize_a_directive() -> None:
    """An otherwise valid exception cannot be reused for another source occurrence."""
    source = "value = 1  # noqa: E123\n"
    fingerprint = compute_source_fingerprint(source=source, line_number=1, directive="# noqa: E123")
    exceptions = load_exceptions(
        source=f'''[[exceptions]]
rule = "noqa"
path = "utilities/other.py"
directive = "# noqa: E123"
source_fingerprint = "{fingerprint}"
reason = "reviewed"
approval_url = "https://github.com/example/review/2"
'''
    )

    violations = check_linter_directives(
        file_path=Path("utilities/example.py"),
        indexed_source=source,
        head_source="",
        exceptions=exceptions,
    )

    assert len(violations) == 1, "an exception for another path must not authorize this directive"


@mark.parametrize(
    argnames="manifest_source, expected_fragment",
    argvalues=[
        (
            '[[exceptions]]\nrule = "noqa"\npath = "utilities/example.py"\ndirective = "# noqa"\nsource_fingerprint = "sha256:'
            + "0" * 64
            + '"\nreason = ""\napproval_url = "https://github.com/example/review/1"\n',
            "reason",
        ),
        (
            '[[exceptions]]\nrule = "noqa"\npath = "utilities/example.py"\ndirective = "# noqa"\nsource_fingerprint = "sha256:'
            + "0" * 64
            + '"\nreason = "reviewed"\napproval_url = "TBD"\n',
            "approval_url",
        ),
        (
            '[[exceptions]]\nrule = "noqa"\npath = "utilities/example.py"\ndirective = "# noqa"\nsource_fingerprint = "sha256:'
            + "0" * 64
            + '"\nreason = "reviewed"\napproval_url = ""\n',
            "approval_url",
        ),
        (
            '[[exceptions]]\nrule = "noqa"\npath = "utilities/*.py"\ndirective = "# noqa"\nsource_fingerprint = "sha256:'
            + "0" * 64
            + '"\nreason = "reviewed"\napproval_url = "https://github.com/example/review/1"\n',
            "wildcards",
        ),
        (
            "[[exceptions]\n",
            "invalid TOML",
        ),
    ],
)
def test_load_exceptions_rejects_blank_wildcard_and_malformed_records(
    manifest_source: str, expected_fragment: str
) -> None:
    """Exception metadata must be complete, narrow, and valid TOML."""
    with raises(expected_exception=ExceptionManifestError, match=expected_fragment):
        load_exceptions(source=manifest_source)


def test_load_exceptions_rejects_duplicate_records() -> None:
    """Duplicate approval records are ambiguous and invalid."""
    record = """rule = "noqa"
path = "utilities/example.py"
directive = "# noqa"
source_fingerprint = "sha256:0000000000000000000000000000000000000000000000000000000000000000"
reason = "reviewed"
approval_url = "https://github.com/example/review/1"
"""
    source = f"[[exceptions]]\n{record}\n[[exceptions]]\n{record}"

    with raises(expected_exception=ExceptionManifestError, match="duplicate"):
        load_exceptions(source=source)


def test_manifest_update_preserves_existing_reason_and_approval() -> None:
    """Changing approval metadata for an existing identity is forbidden."""
    head_source = """[[exceptions]]
rule = "noqa"
path = "utilities/example.py"
directive = "# noqa"
source_fingerprint = "sha256:0000000000000000000000000000000000000000000000000000000000000000"
reason = "original reason"
approval_url = "https://github.com/example/review/1"
"""
    indexed_source = head_source.replace("original reason", "changed reason")

    violations = check_manifest_update(
        indexed_source=indexed_source,
        head_source=head_source,
        file_path=Path("scripts/pre_commit_hooks/exceptions.toml"),
    )

    assert len(violations) == 1, "existing approval metadata must not be edited in place"
    assert "reason/approval_url" in violations[0].message, "the violation should explain which fields are protected"


def test_manifest_update_allows_new_record_with_new_staged_directive() -> None:
    """A new manifest record may accompany its matching staged directive."""
    source = "value = 1  # noqa\n"
    fingerprint = compute_source_fingerprint(source=source, line_number=1, directive="# noqa")
    indexed_source = f'''[[exceptions]]
rule = "noqa"
path = "utilities/example.py"
directive = "# noqa"
source_fingerprint = "{fingerprint}"
reason = "new review"
approval_url = "https://github.com/example/review/3"
'''

    assert (
        check_manifest_update(
            indexed_source=indexed_source,
            head_source=None,
            staged_sources={Path("utilities/example.py"): (source, None)},
        )
        == []
    ), "a newly staged manifest record should match its newly staged directive"


def test_manifest_update_rejects_duplicate_directive_occurrences() -> None:
    """One manifest identity cannot authorize duplicate directive occurrences."""
    source = "value = 1  # noqa\n" * 2
    fingerprint = compute_source_fingerprint(source=source, line_number=1, directive="# noqa")
    indexed_source = f'''[[exceptions]]
rule = "noqa"
path = "utilities/example.py"
directive = "# noqa"
source_fingerprint = "{fingerprint}"
reason = "new review"
approval_url = "https://github.com/example/review/4"
'''

    violations = check_manifest_update(
        indexed_source=indexed_source,
        head_source="exceptions = []\n",
        staged_sources={Path("utilities/example.py"): (source, None)},
    )

    assert len(violations) == 1, "the duplicate staged occurrence must remain unauthorized"
    assert "additional identical suppression occurrences cannot be authorized" in violations[0].message, (
        "the violation should explain that duplicate manifest identities are forbidden"
    )


def test_one_approved_exception_covers_only_one_duplicate_occurrence() -> None:
    """One record authorizes one new occurrence after the HEAD baseline is consumed."""
    head_source = "value = 1  # noqa: E123\n"
    indexed_source = head_source * 3
    directive = "# noqa: E123"
    fingerprint = compute_source_fingerprint(source=head_source, line_number=1, directive=directive)
    exceptions = load_exceptions(
        source=f'''[[exceptions]]
rule = "noqa"
path = "utilities/example.py"
directive = "{directive}"
source_fingerprint = "{fingerprint}"
reason = "reviewed"
approval_url = "https://github.com/example/review/5"
'''
    )

    violations = check_linter_directives(
        file_path=Path("utilities/example.py"),
        indexed_source=indexed_source,
        head_source=head_source,
        exceptions=exceptions,
    )

    assert [(violation.line_number, violation.message) for violation in violations] == [
        (3, "linter-directives/noqa: remove '# noqa: E123' or add an exact, reviewed exceptions.toml record")
    ], "the HEAD baseline and one record must not authorize two newly added duplicates"


def test_existing_exception_does_not_authorize_new_identical_suppression_after_old_one() -> None:
    """An existing exception and one old occurrence cannot authorize a newly added duplicate."""
    file_path = Path("utilities/example.py")
    head_source = "value = 1  # noqa: E123\n"
    indexed_source = head_source * 2
    directive = "# noqa: E123"
    fingerprint = compute_source_fingerprint(source=head_source, line_number=1, directive=directive)
    manifest = f'''[[exceptions]]
rule = "noqa"
path = "{file_path.as_posix()}"
directive = "{directive}"
source_fingerprint = "{fingerprint}"
reason = "reviewed"
approval_url = "https://github.com/example/review/10"
'''

    violations = check_manifest_update(
        indexed_source=manifest,
        head_source=manifest,
        staged_sources={file_path: (indexed_source, head_source)},
    )

    assert len(violations) == 1, "a newly duplicated suppression cannot reuse an existing exception"
    assert "additional identical suppression occurrences cannot be authorized" in violations[0].message, (
        "the manifest violation must explain why another identical record cannot authorize the duplicate"
    )


def test_manifest_update_allows_removing_an_old_record() -> None:
    """Removing obsolete approval metadata is allowed without an immutable archive."""
    head_source = """[[exceptions]]
rule = "noqa"
path = "utilities/example.py"
directive = "# noqa: E123"
source_fingerprint = "sha256:0000000000000000000000000000000000000000000000000000000000000000"
reason = "obsolete"
approval_url = "https://github.com/example/review/6"
"""

    assert check_manifest_update(indexed_source="exceptions = []\n", head_source=head_source) == [], (
        "removed exception records should be permitted when no existing identity is modified"
    )


def test_existing_exception_does_not_authorize_a_copied_identical_suppression() -> None:
    """An approved directive remains bound to its original repository path."""
    original_source = "value = 1  # noqa: E123\n"
    fingerprint = compute_source_fingerprint(source=original_source, line_number=1, directive="# noqa: E123")
    exceptions = load_exceptions(
        source=f'''[[exceptions]]
rule = "noqa"
path = "utilities/original.py"
directive = "# noqa: E123"
source_fingerprint = "{fingerprint}"
reason = "reviewed"
approval_url = "https://github.com/example/review/9"
'''
    )

    violations = check_linter_directives(
        file_path=Path("utilities/copied.py"),
        indexed_source=original_source,
        head_source="",
        exceptions=exceptions,
    )

    assert len(violations) == 1, "a copied suppression must require its own exception record"
    assert violations[0].line_number == 1, "the copied directive must identify its own source line"


def test_manifest_update_skips_staged_source_that_fails_to_parse() -> None:
    """A staged file with malformed Python is skipped instead of crashing the check."""
    violations = check_manifest_update(
        indexed_source="exceptions = []\n",
        head_source=None,
        staged_sources={Path("utilities/broken.py"): ("def broken(:\n", None)},
    )

    assert violations == [], "malformed staged source must be skipped without raising"


def test_manifest_update_rejects_retained_record_for_renamed_away_path() -> None:
    """A rename must not leave the approved record for the old path behind."""
    indexed_source = dedent(
        """
        [[exceptions]]
        rule = "noqa"
        path = "utilities/old_name.py"
        directive = "# noqa: E123"
        source_fingerprint = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        reason = "approved exception"
        approval_url = "https://example.com/approval"
        """
    )
    head_source = indexed_source

    violations = check_manifest_update(
        indexed_source=indexed_source,
        head_source=head_source,
        staged_sources={Path("utilities/new_name.py"): ("print('x')\n", None)},
        renamed_away_paths=frozenset({Path("utilities/old_name.py")}),
    )

    assert [violation.message for violation in violations] == [
        "linter-directives: this path was renamed; remove the obsolete exception record for utilities/old_name.py"
    ], "retaining the old-path record across a rename must fail policy"


def test_manifest_update_allows_obsolete_record_for_ordinary_deletion() -> None:
    """Records for paths deleted outright remain ordinary cleanup territory."""
    indexed_source = dedent(
        """
        [[exceptions]]
        rule = "noqa"
        path = "utilities/gone.py"
        directive = "# noqa: E123"
        source_fingerprint = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        reason = "approved exception"
        approval_url = "https://example.com/approval"
        """
    )
    head_source = indexed_source

    violations = check_manifest_update(
        indexed_source=indexed_source,
        head_source=head_source,
        staged_sources={},
        renamed_away_paths=frozenset(),
    )

    assert violations == [], "a record for a deleted path must not be flagged as a rename leftover"

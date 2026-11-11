"""Unit tests for product-test STD and traceability policy checks."""

from __future__ import annotations

from pathlib import Path

from pytest import mark

from scripts.pre_commit_hooks.check_test_std import check_test_std, is_product_test_path


def test_shared_preconditions_and_tracking_are_inherited_from_module_class_or_test() -> None:
    """A new test may inherit Preconditions and tracking from any enclosing documentation level."""
    for location in ("module", "class", "test"):
        if location == "module":
            source = '''"""Module context.

Preconditions:
- the under-test component is available

https://issues.redhat.com/browse/CNV-94228  # <skip-jira-utils-check>
"""

def test_new_behavior():
    """Validate the new behavior.
    Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>

    Steps:
    - exercise the behavior
    Expected:
    - the behavior succeeds
    """

    assert condition, "the behavior should succeed"
'''
        elif location == "class":
            source = '''"""Jira: https://issues.redhat.com/browse/CNV-94228  # <skip-jira-utils-check>"""

class TestBehavior:
    """Class context.

    Preconditions:
    - the under-test component is available
    """

    def test_new_behavior(self):
        """Validate the new behavior.
        Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>

        Steps:
        - exercise the behavior
        Expected:
        - the behavior succeeds
        """
        assert condition, "the behavior should succeed"
'''
        else:
            source = '''"""Jira: https://issues.redhat.com/browse/CNV-94228  # <skip-jira-utils-check>"""

def test_new_behavior():
    """Validate the new behavior.
    Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>

    Preconditions:
    - the under-test component is available
    Steps:
    - exercise the behavior
    Expected:
    - the behavior succeeds
    """

    assert condition, "the behavior should succeed"
'''

        violations = check_test_std(
            file_path=Path("tests/network/test_behavior.py"),
            indexed_source=source,
            head_source=None,
        )

        assert violations == [], f"shared STD context at {location} should satisfy a new test"


def test_plain_jira_url_is_a_tracking_link_without_a_jira_label() -> None:
    """A repository-style Jira URL is sufficient even when its line has no Jira label."""
    source = '''"""Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>"""

def test_new_behavior():
    """Validate the behavior.
    Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>

    Preconditions:
    - the component is available
    Steps:
    - exercise the behavior
    Expected:
    - the behavior succeeds
    """

    assert condition, "the behavior should succeed"
'''

    violations = check_test_std(
        file_path=Path("tests/storage/test_behavior.py"),
        indexed_source=source,
        head_source=None,
    )

    assert violations == [], "plain tracked Jira URLs used by repository tests should be accepted"


@mark.parametrize(
    argnames="section, invalid_content, expected_message",
    argvalues=[
        ("Preconditions", "TBD", "add nonempty Preconditions: at test, enclosing class, or module level"),
        ("Preconditions", "", "add nonempty Preconditions: at test, enclosing class, or module level"),
        ("Steps", "TBD", "add a nonempty Steps: section to the test docstring"),
        ("Steps", "", "add a nonempty Steps: section to the test docstring"),
        ("Expected", "TBD", "add a nonempty Expected: section to the test docstring"),
        ("Expected", "", "add a nonempty Expected: section to the test docstring"),
    ],
)
def test_empty_or_tbd_std_sections_are_rejected(section: str, invalid_content: str, expected_message: str) -> None:
    """Required STD sections cannot be blank or placeholders."""
    preconditions = invalid_content if section == "Preconditions" else "the component is available"
    steps = invalid_content if section == "Steps" else "exercise the behavior"
    expected = invalid_content if section == "Expected" else "the behavior succeeds"
    source = f'''"""Jira: https://issues.redhat.com/browse/CNV-88909"""

def test_new_behavior():
    """Validate the behavior.
    Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>

    Preconditions:
    - {preconditions}
    Steps:
    - {steps}
    Expected:
    - {expected}
    """

    assert condition, "the behavior should succeed"
'''

    violations = check_test_std(
        file_path=Path("tests/network/test_behavior.py"),
        indexed_source=source,
        head_source=None,
    )

    assert [violation.message.split(": ", maxsplit=1)[1] for violation in violations] == [expected_message], (
        f"{section} must reject empty or placeholder content"
    )


@mark.parametrize(
    argnames="missing_section, expected_message",
    argvalues=[
        ("Preconditions", "add nonempty Preconditions: at test, enclosing class, or module level"),
        ("Steps", "add a nonempty Steps: section to the test docstring"),
        ("Expected", "add a nonempty Expected: section to the test docstring"),
    ],
)
def test_missing_std_section_is_rejected(missing_section: str, expected_message: str) -> None:
    """A missing required STD section is rejected independently of the other sections."""
    sections = {
        "Preconditions": "Preconditions:\n    - the component is available",
        "Steps": "Steps:\n    - exercise the behavior",
        "Expected": "Expected:\n    - the behavior succeeds",
    }
    remaining_sections = "\n    ".join(
        section_text for section_name, section_text in sections.items() if section_name != missing_section
    )
    source = f'''"""Jira: https://issues.redhat.com/browse/CNV-88909"""

def test_new_behavior():
    """Validate the behavior.
    Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>

    {remaining_sections}
    """

    assert condition, "the behavior should succeed"
'''

    violations = check_test_std(
        file_path=Path("tests/network/test_behavior.py"),
        indexed_source=source,
        head_source=None,
    )

    assert [violation.message.split(": ", maxsplit=1)[1] for violation in violations] == [expected_message], (
        f"missing {missing_section} must be rejected"
    )


def test_same_named_incomplete_test_is_checked_against_complete_head_definition() -> None:
    """An incomplete implementation must be checked even when HEAD has the same documented test."""
    head_source = '''"""Jira: https://issues.redhat.com/browse/CNV-88909"""

def test_hidden():
    """Hidden behavior.
    Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>

    Preconditions:
    - the component is available
    Steps:
    - exercise the behavior
    Expected:
    - the behavior succeeds
    """

    pass
'''
    indexed_source = '''"""Jira: https://issues.redhat.com/browse/CNV-88909"""

def test_hidden():
    """Hidden behavior."""
    pass
'''

    violations = check_test_std(
        file_path=Path("tests/network/test_behavior.py"),
        indexed_source=indexed_source,
        head_source=head_source,
    )

    assert [violation.message for violation in violations] == [
        "test-std/test_hidden: add a nonempty Expected: section to the test docstring",
        "test-std/test_hidden: add a nonempty Steps: section to the test docstring",
        "test-std/test_hidden: add nonempty Preconditions: at test, enclosing class, or module level",
    ], "an incomplete same-named test must not inherit the complete HEAD definition"


@mark.parametrize(
    argnames="removed_text, replacement, expected_message",
    argvalues=[
        (
            "Validate the behavior.\n\n    Preconditions:",
            "Preconditions:",
            "add a nonempty test description before the STD sections",
        ),
        (
            "- the component is available\n    Steps:",
            "- TBD\n    Steps:",
            "add nonempty Preconditions: at test, enclosing class, or module level",
        ),
        (
            "- exercise the behavior\n    Expected:",
            "- TBD\n    Expected:",
            "add a nonempty Steps: section to the test docstring",
        ),
        (
            '- the behavior succeeds\n    """',
            '- TBD\n    """',
            "add a nonempty Expected: section to the test docstring",
        ),
        (
            "https://issues.redhat.com/browse/CNV-88909",
            "tracking URL removed",
            "add an STP link or Jira/RFE tracking URL to the test, class, or module docstring",
        ),
    ],
    ids=["description", "preconditions", "steps", "expected", "tracking-url"],
)
def test_existing_valid_std_field_cannot_be_removed(
    removed_text: str,
    replacement: str,
    expected_message: str,
) -> None:
    """Each valid STD dimension in HEAD remains required independently."""
    head_source = '''"""Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>"""

def test_existing():
    """Validate the behavior.

    Preconditions:
    - the component is available
    Steps:
    - exercise the behavior
    Expected:
    - the behavior succeeds
    """
    assert condition, "the behavior should succeed"
'''
    indexed_source = head_source.replace(removed_text, replacement)

    violations = check_test_std(
        file_path=Path("tests/network/test_behavior.py"),
        indexed_source=indexed_source,
        head_source=head_source,
    )

    assert [violation.message for violation in violations] == [f"test-std/test_existing: {expected_message}"], (
        "a documentation dimension that was valid in HEAD must remain valid in the index"
    )


def test_effective_preconditions_and_tracking_may_move_between_allowed_scopes() -> None:
    """Inherited documentation may move without becoming a regression."""
    head_source = '''"""Module context.

Preconditions:
- the component is available

https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>
"""

class TestBehavior:
    def test_existing(self):
        """Validate the behavior.

        Steps:
        - exercise the behavior
        Expected:
        - the behavior succeeds
        """
        assert condition, "the behavior should succeed"
'''
    indexed_source = '''class TestBehavior:
    """Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>"""

    def test_existing(self):
        """Validate the behavior.

        Preconditions:
        - the component is available
        Steps:
        - exercise the behavior
        Expected:
        - the behavior succeeds
        """
        assert condition, "the behavior should succeed"
'''

    assert (
        check_test_std(
            file_path=Path("tests/network/test_behavior.py"),
            indexed_source=indexed_source,
            head_source=head_source,
        )
        == []
    ), "effective Preconditions and tracking may move among test, class, and module docstrings"


def test_duplicate_head_occurrences_preserve_valid_std_independently() -> None:
    """A regression in one duplicate definition cannot hide behind the last definition."""
    head_source = '''"""Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>"""

if condition:
    def test_hidden():
        """Validate the primary behavior.

        Preconditions:
        - the component is available
        Steps:
        - exercise the behavior
        Expected:
        - the behavior succeeds
        """
        assert condition, "the behavior should succeed"
else:
    def test_hidden():
        """Legacy alternate behavior."""
        assert condition, "the alternate behavior should succeed"
'''
    indexed_source = head_source.replace("- exercise the behavior", "- TBD")

    violations = check_test_std(
        file_path=Path("tests/network/test_behavior.py"),
        indexed_source=indexed_source,
        head_source=head_source,
    )

    assert [(violation.line_number, violation.message) for violation in violations] == [
        (4, "test-std/test_hidden: add a nonempty Steps: section to the test docstring")
    ], "each duplicate HEAD occurrence must retain its own previously valid documentation"


@mark.parametrize(
    argnames="duplicate_source, expected_messages",
    argvalues=[
        (
            """def test_existing():
    assert condition, "the duplicate behavior should succeed"
""",
            [
                "test-std/test_existing: add a nonempty Expected: section to the test docstring",
                "test-std/test_existing: add a nonempty Steps: section to the test docstring",
                "test-std/test_existing: add a nonempty test description before the STD sections",
                "test-std/test_existing: add an STP link or Jira/RFE tracking URL to the test, class, or module docstring",
                "test-std/test_existing: add nonempty Preconditions: at test, enclosing class, or module level",
            ],
        ),
        (
            '''class TestBehavior:
    """Shared context.

    Preconditions:
    - the component is available
    """

    __test__ = False

    def test_existing(self):
        """Another occurrence.

        Steps:
        - exercise the duplicate behavior
        Expected:
        - the duplicate behavior succeeds
        """
        assert condition, "the duplicate behavior should succeed"
''',
            ["test-std/TestBehavior.test_existing: remove newly effective __test__ = False from implemented test"],
        ),
    ],
    ids=["incomplete", "disabled-implemented"],
)
def test_appended_occurrence_of_existing_name_retains_head_obligations(
    duplicate_source: str,
    expected_messages: list[str],
) -> None:
    """Extra occurrences retain only the policy dimensions established in HEAD."""
    if duplicate_source.startswith("class"):
        head_source = '''"""Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>"""

class TestBehavior:
    """Shared context.

    Preconditions:
    - the component is available
    """

    def test_existing(self):
        """Validate the behavior.

        Steps:
        - exercise the behavior
        Expected:
        - the behavior succeeds
        """
        assert condition, "the behavior should succeed"
'''
    else:
        head_source = '''def test_existing():
    """Validate the behavior.

    Preconditions:
    - the component is available
    Steps:
    - exercise the behavior
    Expected:
    - the behavior succeeds

    https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>
    """
    assert condition, "the behavior should succeed"
'''

    violations = check_test_std(
        file_path=Path("tests/network/test_behavior.py"),
        indexed_source=f"{head_source}\n{duplicate_source}",
        head_source=head_source,
    )

    assert [violation.message for violation in violations] == expected_messages, (
        "an appended occurrence must preserve the valid documentation and implementation state established in HEAD"
    )


def test_valid_appended_occurrence_of_existing_name_is_allowed() -> None:
    """An additional occurrence is not rejected when it meets the HEAD baseline."""
    head_source = '''"""Shared context.

Preconditions:
- the component is available

https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>
"""

def test_existing():
    """Validate the primary behavior.
    Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>

    Steps:
    - exercise the primary behavior
    Expected:
    - the primary behavior succeeds
    """

    assert condition, "the primary behavior should succeed"
'''
    indexed_source = (
        head_source
        + '''

def test_existing():
    """Validate the alternate behavior.
    Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>

    Steps:
    - exercise the alternate behavior
    Expected:
    - the alternate behavior succeeds
    """

    assert condition, "the alternate behavior should succeed"
'''
    )

    assert (
        check_test_std(
            file_path=Path("tests/network/test_behavior.py"),
            indexed_source=indexed_source,
            head_source=head_source,
        )
        == []
    ), "a valid extra occurrence of an existing qualified name must be allowed"


@mark.parametrize(
    argnames="head_definition, extra_definition",
    argvalues=[
        (
            '''def test_existing():
    """Legacy implemented test."""
    assert condition, "the legacy behavior should succeed"
''',
            '''def test_existing():
    """Another legacy implemented test."""
    assert condition, "the alternate behavior should succeed"
''',
        ),
        (
            '''def test_existing():
    """Legacy enabled placeholder."""
    pass
''',
            '''def test_existing():
    """Another enabled legacy placeholder."""
    pass
''',
        ),
    ],
    ids=["missing-std", "enabled-placeholder"],
)
def test_extra_occurrence_preserves_legacy_omissions_and_placeholder_state(
    head_definition: str,
    extra_definition: str,
) -> None:
    """Extra existing-name occurrences do not turn grandfathered gaps into new-test failures."""
    assert (
        check_test_std(
            file_path=Path("tests/network/test_behavior.py"),
            indexed_source=f"{head_definition}\n{extra_definition}",
            head_source=head_definition,
        )
        == []
    ), "legacy omissions and enabled pass-only placeholders must remain grandfathered"


def test_prepended_duplicate_does_not_shift_reordered_retained_occurrences() -> None:
    """Source identity keeps retained duplicates attached to their own HEAD baselines."""
    head_source = '''"""Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>"""

if primary:
    def test_hidden():
        """Validate the primary behavior.

        Preconditions:
        - the component is available
        Steps:
        - exercise the primary behavior
        Expected:
        - the primary behavior succeeds
        """
        assert primary, "the primary behavior should succeed"
else:
    def test_hidden():
        """Legacy alternate behavior."""
        assert alternate, "the alternate behavior should succeed"
'''
    indexed_source = '''"""Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>"""

if prepended:
    def test_hidden():
        """Another legacy occurrence."""
        assert prepended, "the prepended behavior should succeed"
elif alternate:
    def test_hidden():
        """Legacy alternate behavior."""
        assert alternate, "the alternate behavior should succeed"
else:
    def test_hidden():
        """Validate the primary behavior.

        Preconditions:
        - the component is available
        Steps:
        - exercise the primary behavior
        Expected:
        - the primary behavior succeeds
        """
        assert primary, "the primary behavior should succeed"
'''

    assert (
        check_test_std(
            file_path=Path("tests/network/test_behavior.py"),
            indexed_source=indexed_source,
            head_source=head_source,
        )
        == []
    ), "prepending a grandfathered duplicate must not shift retained definitions onto different HEAD occurrences"


def test_genuinely_new_name_still_receives_full_new_test_checks() -> None:
    """Qualified-name membership, not occurrence count, determines new-test eligibility."""
    head_source = '''def test_existing():
    """Legacy existing test."""
    assert condition, "the existing behavior should succeed"
'''
    indexed_source = (
        head_source
        + '''

@pytest.mark.manual
def test_existing():
    """Another legacy occurrence."""
    assert condition, "the duplicate behavior should succeed"

class TestNew:
    __test__ = False

    def test_genuinely_new(self):
        """New behavior."""
        assert condition, "the new behavior should succeed"
'''
    )

    assert [
        violation.message
        for violation in check_test_std(
            file_path=Path("tests/network/test_behavior.py"),
            indexed_source=indexed_source,
            head_source=head_source,
        )
    ] == [
        "test-std/test_existing: remove @pytest.mark.manual from this implemented test",
        "test-std/TestNew.test_genuinely_new: add a nonempty Expected: section to the test docstring",
        "test-std/TestNew.test_genuinely_new: add a nonempty Steps: section to the test docstring",
        "test-std/TestNew.test_genuinely_new: add an STP link or Jira/RFE tracking URL to the test docstring",
        "test-std/TestNew.test_genuinely_new: add nonempty Preconditions: at test, enclosing class, or module level",
        "test-std/TestNew.test_genuinely_new: remove effective __test__ = False from this implemented test",
    ], (
        "a genuinely new qualified name must still receive complete documentation, placeholder-state, and manual-marker validation"
    )


def test_incomplete_duplicate_test_in_conditional_branch_is_reported() -> None:
    """Every same-named branch-local test definition must receive STD checks."""
    source = '''if condition:
    def test_hidden():
        assert True, 'ok'
else:
    def test_hidden():
        """Description: Validate the visible behavior.

        Preconditions:
        - the component is available
        Steps:
        - exercise the behavior
        Expected:
        - the behavior succeeds

        https://issues.redhat.com/browse/CNV-12345  # <skip-jira-utils-check>
        """
        assert True, 'ok'
'''

    violations = check_test_std(
        file_path=Path("tests/virt/review/test_example.py"),
        indexed_source=source,
        head_source=None,
    )

    assert {(violation.line_number, violation.message) for violation in violations} == {
        (2, "test-std/test_hidden: add a nonempty Expected: section to the test docstring"),
        (2, "test-std/test_hidden: add a nonempty Steps: section to the test docstring"),
        (2, "test-std/test_hidden: add a nonempty test description before the STD sections"),
        (2, "test-std/test_hidden: add an STP link or Jira/RFE tracking URL to the test docstring"),
        (2, "test-std/test_hidden: add nonempty Preconditions: at test, enclosing class, or module level"),
    }, "the incomplete occurrence must not be overwritten by its complete same-named branch"


def test_incomplete_duplicate_class_method_in_conditional_branch_is_reported() -> None:
    """Every same-named class branch method must receive STD checks."""
    source = '''class TestExample:
    if condition:
        def test_hidden(self):
            assert True, 'ok'
    else:
        def test_hidden(self):
            """Description: Validate the visible behavior.

            Preconditions:
            - the component is available
            Steps:
            - exercise the behavior
            Expected:
            - the behavior succeeds

            https://issues.redhat.com/browse/CNV-12345  # <skip-jira-utils-check>
            """
            assert True, 'ok'
'''

    violations = check_test_std(
        file_path=Path("tests/virt/review/test_example.py"),
        indexed_source=source,
        head_source=None,
    )

    assert {(violation.line_number, violation.message) for violation in violations} == {
        (3, "test-std/TestExample.test_hidden: add a nonempty Expected: section to the test docstring"),
        (3, "test-std/TestExample.test_hidden: add a nonempty Steps: section to the test docstring"),
        (3, "test-std/TestExample.test_hidden: add a nonempty test description before the STD sections"),
        (
            3,
            "test-std/TestExample.test_hidden: add an STP link or Jira/RFE tracking URL to the test docstring",
        ),
        (
            3,
            "test-std/TestExample.test_hidden: add nonempty Preconditions: at test, enclosing class, or module level",
        ),
    }, "the incomplete class method must not be overwritten by its complete same-named branch"


def test_new_method_is_checked_without_rechecking_existing_method() -> None:
    """Only a method newly introduced against HEAD receives new-test STD checks."""
    head_source = '''"""Jira: https://issues.redhat.com/browse/CNV-88909"""

class TestBehavior:
    """Shared context.

    Preconditions:
    - the component is available
    """

    def test_existing(self):
        """Existing behavior.

        Steps:
        - exercise the behavior
        Expected:
        - the behavior succeeds
        """
        pass
'''
    indexed_source = (
        head_source
        + '''
    def test_new(self):
        """New behavior."""
        assert condition, "the new behavior should succeed"
'''
    )

    violations = check_test_std(
        file_path=Path("tests/network/test_behavior.py"),
        indexed_source=indexed_source,
        head_source=head_source,
    )

    assert [violation.message for violation in violations] == [
        "test-std/TestBehavior.test_new: add a nonempty Expected: section to the test docstring",
        "test-std/TestBehavior.test_new: add a nonempty Steps: section to the test docstring",
        "test-std/TestBehavior.test_new: add an STP link or Jira/RFE tracking URL to the test docstring",
    ], "existing methods should not be ratcheted when a new method is added"


def test_docstring_only_placeholder_is_allowed_when_effectively_disabled() -> None:
    """A documented placeholder may remain unimplemented when __test__ is false."""
    source = '''"""Jira: https://issues.redhat.com/browse/CNV-88909"""
__test__ = False

@pytest.mark.manual
def test_placeholder():
    """Placeholder scenario.
    Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>

    Preconditions:
    - the component is available
    Steps:
    - implement the scenario
    Expected:
    - the scenario is covered
    """

'''

    violations = check_test_std(
        file_path=Path("tests/network/test_behavior.py"),
        indexed_source=source,
        head_source=None,
    )

    assert violations == [], "disabled docstring-only placeholders should be accepted"


def test_url_only_test_description_is_not_meaningful() -> None:
    """A tracking URL alone cannot satisfy the human-readable test description."""
    source = '''"""Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>"""

def test_new_behavior():
    """Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>

    Preconditions:
    - the component is available
    Steps:
    - exercise the behavior
    Expected:
    - the behavior succeeds
    """
    assert condition, "the behavior should succeed"
'''

    assert [
        violation.message
        for violation in check_test_std(
            file_path=Path("tests/network/test_behavior.py"), indexed_source=source, head_source=None
        )
    ] == ["test-std/test_new_behavior: add a nonempty test description before the STD sections"], (
        "a URL-only description must not count as meaningful test documentation"
    )


@mark.parametrize("label", ["Jira", "STP", "RFE"])
def test_labeled_url_only_test_description_is_not_meaningful(label: str) -> None:
    """A tracking label and URL alone cannot satisfy the human-readable test description."""
    source = f'''"""Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>"""

def test_new_behavior():
    """{label}: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>

    Preconditions:
    - the component is available
    Steps:
    - exercise the behavior
    Expected:
    - the behavior succeeds
    """
    assert condition, "the behavior should succeed"
'''

    assert [
        violation.message
        for violation in check_test_std(
            file_path=Path("tests/network/test_behavior.py"), indexed_source=source, head_source=None
        )
    ] == ["test-std/test_new_behavior: add a nonempty test description before the STD sections"], (
        "a labeled URL-only description must not count as meaningful test documentation"
    )


@mark.parametrize("placeholder_body", ["pass", "..."])
def test_pass_and_ellipsis_bodies_are_docstring_only_placeholders(placeholder_body: str) -> None:
    """Pass and ellipsis bodies remain docstring-only placeholders."""
    source = f'''"""Jira: https://issues.redhat.com/browse/CNV-88909"""
__test__ = False

@pytest.mark.manual
def test_placeholder():
    """Placeholder scenario.
    Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>

    Preconditions:
    - the component is available
    Steps:
    - implement the scenario
    Expected:
    - the scenario is covered
    """

    {placeholder_body}
'''

    assert (
        check_test_std(file_path=Path("tests/network/test_behavior.py"), indexed_source=source, head_source=None) == []
    ), "placeholder bodies must remain allowed while effectively disabled"


def test_implemented_new_test_cannot_be_disabled() -> None:
    """An implemented new test must not use an effective __test__ false flag."""
    source = '''"""Jira: https://issues.redhat.com/browse/CNV-88909"""
__test__ = False

@pytest.mark.manual
def test_implemented():
    """Implemented behavior.
    Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>

    Preconditions:
    - the component is available
    Steps:
    - exercise the behavior
    Expected:
    - the behavior succeeds
    """

    assert condition, "the behavior should succeed"
'''

    violations = check_test_std(
        file_path=Path("tests/network/test_behavior.py"),
        indexed_source=source,
        head_source=None,
    )

    assert [violation.message for violation in violations] == [
        "test-std/test_implemented: remove effective __test__ = False from this implemented test"
    ], "implemented tests must not be disabled"


def test_existing_placeholder_transition_requires_removing_disable_flag() -> None:
    """Implementing an existing placeholder must remove its effective disable flag."""
    head_source = '''"""Jira: https://issues.redhat.com/browse/CNV-88909"""
__test__ = False

@pytest.mark.manual
def test_existing():
    """Existing placeholder.
    Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>

    Steps:
    - implement the scenario
    Expected:
    - the scenario is covered
    """

'''
    indexed_source = (
        head_source
        + """
# implementation is intentionally staged while the old flag remains
"""
    )
    indexed_source = indexed_source.replace(
        '''    """
''',
        '''    """
    assert condition, "the scenario should be covered"
''',
        1,
    )

    violations = check_test_std(
        file_path=Path("tests/network/test_behavior.py"),
        indexed_source=indexed_source,
        head_source=head_source,
    )

    assert [violation.message for violation in violations] == [
        "test-std/test_existing: remove effective __test__ = False when implementing this placeholder"
    ], "placeholder implementation must remove its inherited disable flag"


def test_new_class_level_test_flag_disables_docstring_placeholder() -> None:
    """A class-level false flag is inherited by its new placeholder tests."""
    source = '''"""Jira: https://issues.redhat.com/browse/CNV-88909"""

class TestBehavior:
    __test__ = False

    @pytest.mark.manual
    def test_placeholder(self):
        """Placeholder scenario.

        Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>

        Preconditions:
        - the component is available
        Steps:
        - implement the scenario
        Expected:
        - the scenario is covered
        """
'''

    violations = check_test_std(
        file_path=Path("tests/network/test_behavior.py"),
        indexed_source=source,
        head_source=None,
    )

    assert violations == [], "new class-level __test__ false should disable its placeholder descendants"


def test_plain_stp_text_without_a_url_is_not_traceability() -> None:
    """A bare STP label is not accepted as a tracking link."""
    source = '''"""STP: CNV-88909"""

def test_new_behavior():
    """Validate the behavior.

    Preconditions:
    - the component is available
    Steps:
    - exercise the behavior
    Expected:
    - the behavior succeeds
    """

    assert condition, "the behavior should succeed"
'''

    violations = check_test_std(
        file_path=Path("tests/network/test_behavior.py"),
        indexed_source=source,
        head_source=None,
    )

    assert [violation.message for violation in violations] == [
        "test-std/test_new_behavior: add an STP link or Jira/RFE tracking URL to the test docstring"
    ], "traceability requires a URL rather than only a syntactic STP label"


def test_implemented_test_changed_to_enabled_docstring_placeholder_is_rejected() -> None:
    """Removing an implementation without disabling the test must not bypass STD policy."""
    head_source = '''"""Jira: https://issues.redhat.com/browse/CNV-88909"""

def test_implemented():
    """Implemented behavior.
    Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>

    Preconditions:
    - the component is available
    Steps:
    - exercise the behavior
    Expected:
    - the behavior succeeds
    """

    assert condition, "the behavior should succeed"
'''
    indexed_source = head_source.replace('    assert condition, "the behavior should succeed"\n', "")

    violations = check_test_std(
        file_path=Path("tests/network/test_behavior.py"),
        indexed_source=indexed_source,
        head_source=head_source,
    )

    assert len(violations) == 1, "an implemented test must not become an enabled placeholder"
    assert "test-std/test_implemented" in violations[0].message, (
        "the enabled placeholder violation must identify the affected test"
    )
    assert "placeholder" in violations[0].message and "__test__" in violations[0].message, (
        "the violation must explain how to make a removed implementation an intentional placeholder"
    )


def test_existing_placeholder_enabled_without_implementation_is_rejected() -> None:
    """A disabled docstring-only placeholder cannot be enabled before implementation."""
    head_source = '''"""Jira: https://issues.redhat.com/browse/CNV-88909"""
__test__ = False

@pytest.mark.manual
def test_existing():
    """Existing placeholder.
    Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>

    Steps:
    - implement the scenario
    Expected:
    - the scenario is covered
    """

'''
    indexed_source = head_source.replace("__test__ = False\n", "")

    violations = check_test_std(
        file_path=Path("tests/network/test_behavior.py"),
        indexed_source=indexed_source,
        head_source=head_source,
    )

    assert len(violations) == 1, "enabling an unimplemented existing placeholder must be rejected"
    assert violations[0].message.startswith("test-std/test_existing:"), (
        "the placeholder transition violation should identify the affected test"
    )
    assert "placeholder" in violations[0].message and "__test__" in violations[0].message, (
        "the transition violation should explain that the placeholder remains unimplemented"
    )


@mark.parametrize(
    argnames="test_doc, module_doc",
    argvalues=[
        ("", ""),
        ("Legacy description.", ""),
        ("Legacy description.\n\nSteps:\n- exercise behavior", ""),
        ("Legacy description.\n\nExpected:\n- behavior succeeds", ""),
        ("Legacy description.", "https://issues.redhat.com/browse/CNV-88909"),
    ],
    ids=["all-missing", "sections-missing", "expected-missing", "steps-missing", "inherited-fields-missing"],
)
def test_unchanged_legacy_std_omissions_remain_allowed(test_doc: str, module_doc: str) -> None:
    """The preservation check does not turn legacy omissions into a full audit."""
    source = f'''"""{module_doc}"""

def test_existing():
    """{test_doc}"""
    assert condition, "the legacy behavior should succeed"
'''

    assert (
        check_test_std(
            file_path=Path("tests/network/test_behavior.py"),
            indexed_source=source,
            head_source=source,
        )
        == []
    ), "an STD dimension missing in HEAD may remain missing in an existing test"


def test_unchanged_enabled_legacy_pass_placeholder_remains_allowed() -> None:
    """Placeholder-state enforcement remains transition-based for legacy placeholders."""
    source = '''def test_existing():
    """Legacy pass-only placeholder."""
    pass
'''

    assert (
        check_test_std(
            file_path=Path("tests/network/test_behavior.py"),
            indexed_source=source,
            head_source=source,
        )
        == []
    ), "an unchanged enabled legacy placeholder must not gain a disable violation"


def test_existing_implemented_legacy_test_missing_std_is_unchanged_allowed() -> None:
    """An unchanged implemented legacy test is not retroactively required to gain STD sections."""
    source = '''"""Jira: https://issues.redhat.com/browse/CNV-88909"""

def test_existing():
    """Legacy test without the newer STD sections."""
    assert condition, "the legacy behavior should succeed"
'''

    assert (
        check_test_std(
            file_path=Path("tests/network/test_behavior.py"),
            indexed_source=source,
            head_source=source,
        )
        == []
    ), "unchanged legacy tests should remain ratcheted rather than retroactively rejected"


def test_implemented_product_test_cannot_become_a_disabled_placeholder() -> None:
    """Removing an implemented body must not turn the existing test into a placeholder."""
    head_source = '''"""Jira: https://issues.redhat.com/browse/CNV-88909"""

def test_implemented():
    """Implemented behavior.

    Preconditions:
    - the component is available
    Steps:
    - exercise the behavior
    Expected:
    - the behavior succeeds
    """
    assert condition, "the behavior should succeed"
'''
    indexed_source = head_source.replace(
        '"""Jira: https://issues.redhat.com/browse/CNV-88909"""\n',
        '"""Jira: https://issues.redhat.com/browse/CNV-88909"""\n__test__ = False\n',
    ).replace('    assert condition, "the behavior should succeed"\n', "")

    violations = check_test_std(
        file_path=Path("tests/network/test_behavior.py"),
        indexed_source=indexed_source,
        head_source=head_source,
    )

    assert len(violations) == 1, "implemented tests must not be converted into disabled placeholders"
    assert "test-std/test_implemented" in violations[0].message, (
        "the placeholder transition violation must identify the implemented test"
    )
    assert "implemented" in violations[0].message, "the violation must explain the implemented-test transition"


def test_test_definitions_inside_compound_statements_receive_std_checks() -> None:
    """Module- and class-nested test definitions are not exempt from STD checks."""
    source = '''"""Jira: https://issues.redhat.com/browse/CNV-88909"""

if condition:
    def test_in_module_branch():
        """A branch-local test."""

class TestBehavior:
    if condition:
        def test_in_class_branch(self):
            """A class-branch test."""
'''

    violations = check_test_std(
        file_path=Path("tests/network/test_behavior.py"),
        indexed_source=source,
        head_source=None,
    )
    qualified_names = {violation.message.split(":", maxsplit=1)[0] for violation in violations}

    assert qualified_names == {
        "test-std/test_in_module_branch",
        "test-std/TestBehavior.test_in_class_branch",
    }, "test definitions inside if/try/class compound statements must be collected"


def test_nested_try_definitions_receive_std_checks() -> None:
    """Test definitions nested in module and class try blocks remain STD-checked."""
    source = '''"""Jira: https://issues.redhat.com/browse/CNV-88909"""

try:
    def test_module_try():
        """A module try-branch test."""
except Exception:
    pass

class TestBehavior:
    try:
        def test_class_try(self):
            """A class try-branch test."""
    except Exception:
        pass
'''

    violations = check_test_std(
        file_path=Path("tests/network/test_behavior.py"),
        indexed_source=source,
        head_source=None,
    )
    qualified_names = {violation.message.split(":", maxsplit=1)[0] for violation in violations}

    assert qualified_names == {
        "test-std/test_module_try",
        "test-std/TestBehavior.test_class_try",
    }, "try-nested module and class tests must receive STD checks"


def test_feature_test_suffix_is_checked_like_test_prefix() -> None:
    """Feature-level *_test.py modules are product test paths and receive STD checks."""
    path = Path("tests/network/behavior_test.py")
    source = '''"""Jira: https://issues.redhat.com/browse/CNV-88909"""

def test_behavior():
    """Behavior description."""
    assert condition, "the behavior should succeed"
'''

    assert is_product_test_path(file_path=path), "feature-level *_test.py modules must be covered consistently"
    assert check_test_std(file_path=path, indexed_source=source, head_source=None), (
        "feature-level *_test.py modules must receive STD validation"
    )


def test_product_test_paths_exclude_utilities_scripts_and_non_test_modules() -> None:
    """STD checks apply only to test modules below product feature directories."""
    assert is_product_test_path(file_path=Path("tests/network/test_behavior.py")), (
        "feature test modules should be product test paths"
    )
    assert not is_product_test_path(file_path=Path("utilities/test_behavior.py")), (
        "utility tests must not receive product-test STD rules"
    )
    assert not is_product_test_path(file_path=Path("scripts/test_behavior.py")), (
        "script tests must not receive product-test STD rules"
    )
    assert not is_product_test_path(file_path=Path("tests/test_behavior.py")), (
        "top-level test modules are not product feature paths"
    )
    assert not is_product_test_path(file_path=Path("tests/network/helper.py")), (
        "non-test helper modules must not receive product-test STD rules"
    )


def test_manual_marker_is_required_when_module_level_disables_the_test() -> None:
    """Effective module-level __test__ = False still requires a manual marker on the test."""
    source = '''__test__ = False

def test_placeholder():
    """Placeholder scenario.

    Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>

    Preconditions:
    - the component is available
    Steps:
    - implement the scenario
    Expected:
    - the scenario is covered
    """
'''

    violations = check_test_std(
        file_path=Path("tests/network/test_behavior.py"),
        indexed_source=source,
        head_source=None,
    )

    assert [violation.message for violation in violations] == [
        "test-std/test_placeholder: declare @pytest.mark.manual on this test"
    ], "a disabled test without a direct manual marker must be reported"


def test_enclosing_manual_marker_does_not_satisfy_the_test_requirement() -> None:
    """A manual marker on an enclosing class does not cover its disabled tests."""
    source = '''@pytest.mark.manual
class TestBehavior:
    __test__ = False

    def test_placeholder(self):
        """Placeholder scenario.

        Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>

        Preconditions:
        - the component is available
        Steps:
        - implement the scenario
        Expected:
        - the scenario is covered
        """
'''

    violations = check_test_std(
        file_path=Path("tests/network/test_behavior.py"),
        indexed_source=source,
        head_source=None,
    )

    assert [violation.message for violation in violations] == [
        "test-std/TestBehavior.test_placeholder: declare @pytest.mark.manual on this test"
    ], "the manual marker must be direct on the test, not inherited from the class"


def test_manual_marker_without_disabled_state_is_rejected() -> None:
    """An automated test must not keep the manual classification once it is implemented."""
    source = '''@pytest.mark.manual
def test_new_behavior():
    """Validate the behavior.

    STP: https://github.com/RedHatQE/openshift-virtualization-tests-design-docs/blob/main/stps/sig-virt/x.md

    Preconditions:
    - the component is available
    Steps:
    - exercise the behavior
    Expected:
    - the behavior succeeds
    """
    assert condition, "the behavior should succeed"
'''

    violations = check_test_std(
        file_path=Path("tests/network/test_behavior.py"),
        indexed_source=source,
        head_source=None,
    )

    assert [violation.message for violation in violations] == [
        "test-std/test_new_behavior: remove @pytest.mark.manual from this implemented test"
    ], "a stale manual marker on an implemented test must be reported"


def test_new_test_requires_traceability_in_its_own_docstring() -> None:
    """A module-level tracking link no longer covers a new test."""
    source = '''"""Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>
"""

def test_new_behavior():
    """Validate the behavior.

    Preconditions:
    - the component is available
    Steps:
    - exercise the behavior
    Expected:
    - the behavior succeeds
    """

    assert condition, "the behavior should succeed"
'''

    violations = check_test_std(
        file_path=Path("tests/network/test_behavior.py"),
        indexed_source=source,
        head_source=None,
    )

    assert [violation.message for violation in violations] == [
        "test-std/test_new_behavior: add an STP link or Jira/RFE tracking URL to the test docstring"
    ], "inherited traceability must not satisfy a new test"


def test_new_test_jira_line_requires_the_skip_marker() -> None:
    """A new test's own Jira line must carry the jira-utils skip marker."""
    source = '''def test_new_behavior():
    """Validate the behavior.

    Jira: https://issues.redhat.com/browse/CNV-88909

    Preconditions:
    - the component is available
    Steps:
    - exercise the behavior
    Expected:
    - the behavior succeeds
    """
    assert condition, "the behavior should succeed"
'''

    violations = check_test_std(
        file_path=Path("tests/network/test_behavior.py"),
        indexed_source=source,
        head_source=None,
    )

    assert [violation.message for violation in violations] == [
        "test-std/test_new_behavior: add # <skip-jira-utils-check> to this Jira line"
    ], "the jira-utils skip marker is required on a new test's Jira line"


def test_dropping_the_manual_marker_while_still_disabled_is_reported() -> None:
    """An existing placeholder may not silently lose its manual classification."""
    head_source = '''"""Jira: https://issues.redhat.com/browse/CNV-88909"""
__test__ = False

@pytest.mark.manual
def test_placeholder():
    """Placeholder scenario.

    Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>

    Preconditions:
    - the component is available
    Steps:
    - implement the scenario
    Expected:
    - the scenario is covered
    """
'''
    indexed_source = head_source.replace("@pytest.mark.manual\n", "")

    violations = check_test_std(
        file_path=Path("tests/network/test_behavior.py"),
        indexed_source=indexed_source,
        head_source=head_source,
    )

    assert [violation.message for violation in violations] == [
        "test-std/test_placeholder: declare @pytest.mark.manual on this test"
    ], "removing the marker while the test stays disabled must be reported"


def test_keeping_the_manual_marker_on_an_implemented_test_is_reported() -> None:
    """An automated test must not retain the manual marker after implementation."""
    head_source = '''"""Jira: https://issues.redhat.com/browse/CNV-88909"""
__test__ = False

@pytest.mark.manual
def test_placeholder():
    """Placeholder scenario.

    Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>

    Preconditions:
    - the component is available
    Steps:
    - implement the scenario
    Expected:
    - the scenario is covered
    """
'''
    indexed_source = '''"""Jira: https://issues.redhat.com/browse/CNV-88909"""

@pytest.mark.manual
def test_placeholder():
    """Implemented scenario.

    Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>

    Preconditions:
    - the component is available
    Steps:
    - exercise the scenario
    Expected:
    - the scenario is covered
    """
    assert condition, "the scenario should succeed"
'''

    violations = check_test_std(
        file_path=Path("tests/network/test_behavior.py"),
        indexed_source=indexed_source,
        head_source=head_source,
    )

    assert "test-std/test_placeholder: remove @pytest.mark.manual from this implemented test" in [
        violation.message for violation in violations
    ], "implementing a test must also drop the manual marker"


def test_unchanged_legacy_placeholder_without_a_marker_stays_allowed() -> None:
    """An untouched legacy placeholder keeps grandfathered status."""
    source = '''"""Jira: https://issues.redhat.com/browse/CNV-88909"""

def test_placeholder():
    """Placeholder scenario.

    Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>

    Preconditions:
    - the component is available
    Steps:
    - implement the scenario
    Expected:
    - the scenario is covered
    """
    __test__ = False
'''

    violations = check_test_std(
        file_path=Path("tests/network/test_behavior.py"),
        indexed_source=source,
        head_source=source,
    )

    assert violations == [], "an unchanged legacy placeholder must remain grandfathered"


def test_aliased_manual_marker_satisfies_the_direct_requirement() -> None:
    """A test importing ``from pytest import mark`` still counts as directly marked."""
    source = '''"""Jira: https://issues.redhat.com/browse/CNV-88909"""
from pytest import mark

__test__ = False

@mark.manual
def test_placeholder():
    """Placeholder scenario.

    Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>

    Preconditions:
    - the component is available
    Steps:
    - implement the scenario
    Expected:
    - the scenario is covered
    """
'''

    violations = check_test_std(
        file_path=Path("tests/network/test_behavior.py"),
        indexed_source=source,
        head_source=None,
    )

    assert violations == [], "an aliased pytest marker is still a direct manual marker"


def test_renamed_pytest_mark_import_satisfies_the_direct_requirement() -> None:
    """An aliased ``from pytest import mark as m`` chain still counts as directly marked."""
    source = '''"""Jira: https://issues.redhat.com/browse/CNV-88909"""
from pytest import mark as m

__test__ = False

@m.manual
def test_placeholder():
    """Placeholder scenario.

    Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>

    Preconditions:
    - the component is available
    Steps:
    - implement the scenario
    Expected:
    - the scenario is covered
    """
'''

    violations = check_test_std(
        file_path=Path("tests/network/test_behavior.py"),
        indexed_source=source,
        head_source=None,
    )

    assert violations == [], "a renamed pytest mark import is still a direct manual marker"


def test_pytest_module_alias_import_satisfies_the_direct_requirement() -> None:
    """An aliased ``import pytest as pt`` chain still counts as directly marked."""
    source = '''"""Jira: https://issues.redhat.com/browse/CNV-88909"""
import pytest as pt

__test__ = False

@pt.mark.manual
def test_placeholder():
    """Placeholder scenario.

    Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>

    Preconditions:
    - the component is available
    Steps:
    - implement the scenario
    Expected:
    - the scenario is covered
    """
'''

    violations = check_test_std(
        file_path=Path("tests/network/test_behavior.py"),
        indexed_source=source,
        head_source=None,
    )

    assert violations == [], "a renamed pytest module import is still a direct manual marker"


def test_unrelated_pytest_import_renamed_to_mark_does_not_satisfy_the_requirement() -> None:
    """A non-marker pytest import renamed to ``mark`` cannot impersonate the marker."""
    source = '''"""Jira: https://issues.redhat.com/browse/CNV-88909"""
from pytest import fixture as mark

__test__ = False

@mark.manual
def test_placeholder():
    """Placeholder scenario.

    Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>

    Preconditions:
    - the component is available
    Steps:
    - implement the scenario
    Expected:
    - the scenario is covered
    """
'''

    violations = check_test_std(
        file_path=Path("tests/network/test_behavior.py"),
        indexed_source=source,
        head_source=None,
    )

    assert [violation.message for violation in violations] == [
        "test-std/test_placeholder: declare @pytest.mark.manual on this test"
    ], "only a binding that resolves to pytest.mark satisfies the manual requirement"


def test_manual_marker_on_undisabled_placeholder_reports_only_the_missing_flag() -> None:
    """A placeholder with the manual marker but no disable flag gets one consistent finding."""
    source = '''"""Jira: https://issues.redhat.com/browse/CNV-88909"""
from pytest import mark

@mark.manual
def test_placeholder():
    """Placeholder scenario.

    Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>

    Preconditions:
    - the component is available
    Steps:
    - implement the scenario
    Expected:
    - the scenario is covered
    """
'''

    violations = check_test_std(
        file_path=Path("tests/network/test_behavior.py"),
        indexed_source=source,
        head_source=None,
    )

    assert [violation.message for violation in violations] == [
        "test-std/test_placeholder: mark this docstring-only STD placeholder with effective __test__ = False"
    ], "an undisabled placeholder must not be told to remove its manual marker"


def test_dropping_an_aliased_manual_marker_is_reported() -> None:
    """Losing an aliased manual marker must not bypass the transition check."""
    head_source = '''"""Jira: https://issues.redhat.com/browse/CNV-88909"""
__test__ = False

@mark.manual
def test_placeholder():
    """Placeholder scenario.

    Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>

    Preconditions:
    - the component is available
    Steps:
    - implement the scenario
    Expected:
    - the scenario is covered
    """
'''
    indexed_source = head_source.replace("@mark.manual\n", "")

    violations = check_test_std(
        file_path=Path("tests/network/test_behavior.py"),
        indexed_source=indexed_source,
        head_source=head_source,
    )

    assert [violation.message for violation in violations] == [
        "test-std/test_placeholder: declare @pytest.mark.manual on this test"
    ], "an aliased marker must be recognised so it cannot be dropped silently"


def test_non_pytest_marker_attribute_does_not_satisfy_the_requirement() -> None:
    """An unrelated framework attribute must not pass as the pytest manual marker."""
    source = '''"""Jira: https://issues.redhat.com/browse/CNV-88909"""
__test__ = False

@framework.mark.manual
def test_placeholder():
    """Placeholder scenario.

    Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>

    Preconditions:
    - the component is available
    Steps:
    - implement the scenario
    Expected:
    - the scenario is covered
    """
'''

    violations = check_test_std(
        file_path=Path("tests/network/test_behavior.py"),
        indexed_source=source,
        head_source=None,
    )

    assert [violation.message for violation in violations] == [
        "test-std/test_placeholder: declare @pytest.mark.manual on this test"
    ], "only a pytest marker chain satisfies the manual requirement"


def test_shadowed_pytest_root_does_not_satisfy_the_direct_requirement() -> None:
    """A pytest name rebound to another module cannot impersonate the manual marker."""
    source = '''"""Jira: https://issues.redhat.com/browse/CNV-88909"""
from framework import pytest

__test__ = False

@pytest.mark.manual
def test_placeholder():
    """Placeholder scenario.

    Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>

    Preconditions:
    - the component is available
    Steps:
    - implement the scenario
    Expected:
    - the scenario is covered
    """
'''

    violations = check_test_std(
        file_path=Path("tests/network/test_behavior.py"),
        indexed_source=source,
        head_source=None,
    )

    assert [violation.message for violation in violations] == [
        "test-std/test_placeholder: declare @pytest.mark.manual on this test"
    ], "a pytest name shadowed by another import must not satisfy the manual requirement"


def test_shadowed_mark_root_does_not_satisfy_the_direct_requirement() -> None:
    """A bare ``mark`` name imported from another module cannot pass as the pytest marker."""
    source = '''"""Jira: https://issues.redhat.com/browse/CNV-88909"""
from framework import mark

__test__ = False

@mark.manual
def test_placeholder():
    """Placeholder scenario.

    Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>

    Preconditions:
    - the component is available
    Steps:
    - implement the scenario
    Expected:
    - the scenario is covered
    """
'''

    violations = check_test_std(
        file_path=Path("tests/network/test_behavior.py"),
        indexed_source=source,
        head_source=None,
    )

    assert [violation.message for violation in violations] == [
        "test-std/test_placeholder: declare @pytest.mark.manual on this test"
    ], "a bare mark name shadowed by another import must not satisfy the manual requirement"


def test_reassigned_pytest_name_does_not_satisfy_the_direct_requirement() -> None:
    """An imported pytest name that is later reassigned cannot keep marker authority."""
    source = '''"""Jira: https://issues.redhat.com/browse/CNV-88909"""
import pytest

pytest = framework
__test__ = False

@pytest.mark.manual
def test_placeholder():
    """Placeholder scenario.

    Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>

    Preconditions:
    - the component is available
    Steps:
    - implement the scenario
    Expected:
    - the scenario is covered
    """
'''

    violations = check_test_std(
        file_path=Path("tests/network/test_behavior.py"),
        indexed_source=source,
        head_source=None,
    )

    assert [violation.message for violation in violations] == [
        "test-std/test_placeholder: declare @pytest.mark.manual on this test"
    ], "a reassigned pytest name must not satisfy the manual-marker requirement"


def test_added_manual_marker_on_retained_implemented_test_is_reported() -> None:
    """Adding a manual marker to an implemented test is reported without needing a prior marker."""
    head_source = '''"""Jira: https://issues.redhat.com/browse/CNV-88909"""

def test_behavior():
    """Implemented scenario.

    Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>

    Preconditions:
    - the component is available
    Steps:
    - exercise the scenario
    Expected:
    - the scenario succeeds
    """
    assert condition, "the scenario should succeed"
'''
    indexed_source = head_source.replace("def test_behavior():", "@pytest.mark.manual\ndef test_behavior():")

    violations = check_test_std(
        file_path=Path("tests/network/test_behavior.py"),
        indexed_source=indexed_source,
        head_source=head_source,
    )

    assert [violation.message for violation in violations] == [
        "test-std/test_behavior: remove @pytest.mark.manual from this implemented test"
    ], "a newly added manual marker on an implemented test must be reported regardless of HEAD state"


def test_control_flow_module_test_flag_disables_placeholder() -> None:
    """``__test__ = False`` inside module-level control flow still disables the test."""
    source = '''"""Jira: https://issues.redhat.com/browse/CNV-88909"""
import pytest

if condition:
    __test__ = False

@pytest.mark.manual
def test_placeholder():
    """Placeholder scenario.

    Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>

    Preconditions:
    - the component is available
    Steps:
    - implement the scenario
    Expected:
    - the scenario is covered
    """
'''

    violations = check_test_std(
        file_path=Path("tests/network/test_behavior.py"),
        indexed_source=source,
        head_source=None,
    )

    assert violations == [], "a module-level conditional test flag must disable the placeholder"


def test_control_flow_class_test_flag_disables_placeholder() -> None:
    """``__test__ = False`` inside class-level control flow still disables the test."""
    source = '''"""Jira: https://issues.redhat.com/browse/CNV-88909"""
import pytest

class TestBehavior:
    if condition:
        __test__ = False

    @pytest.mark.manual
    def test_placeholder(self):
        """Placeholder scenario.

        Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>

        Preconditions:
        - the component is available
        Steps:
        - implement the scenario
        Expected:
        - the scenario is covered
        """
'''

    violations = check_test_std(
        file_path=Path("tests/network/test_behavior.py"),
        indexed_source=source,
        head_source=None,
    )

    assert violations == [], "a class-level conditional test flag must disable the placeholder"


def test_function_local_test_flag_does_not_disable_module_tests() -> None:
    """``__test__ = False`` inside a helper function body stays local to that function."""
    source = '''"""Jira: https://issues.redhat.com/browse/CNV-88909"""

def helper():
    __test__ = False

def test_placeholder():
    """Placeholder scenario.

    Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>

    Preconditions:
    - the component is available
    Steps:
    - implement the scenario
    Expected:
    - the scenario is covered
    """
'''

    violations = check_test_std(
        file_path=Path("tests/network/test_behavior.py"),
        indexed_source=source,
        head_source=None,
    )

    assert [violation.message for violation in violations] == [
        "test-std/test_placeholder: mark this docstring-only STD placeholder with effective __test__ = False"
    ], "a function-local test flag must not disable module-level tests"


def test_transition_reports_every_applicable_violation() -> None:
    """Replacing an implemented manual test must not hide the lost manual classification."""
    head_source = '''"""Jira: https://issues.redhat.com/browse/CNV-88909"""

@pytest.mark.manual
def test_behavior():
    """Implemented scenario.

    Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>

    Preconditions:
    - the component is available
    Steps:
    - exercise the scenario
    Expected:
    - the scenario succeeds
    """
    assert condition, "the scenario should succeed"
'''
    indexed_source = '''"""Jira: https://issues.redhat.com/browse/CNV-88909"""
__test__ = False

def test_behavior():
    """Placeholder scenario.

    Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>

    Preconditions:
    - the component is available
    Steps:
    - implement the scenario
    Expected:
    - the scenario is covered
    """
'''

    violations = check_test_std(
        file_path=Path("tests/network/test_behavior.py"),
        indexed_source=indexed_source,
        head_source=head_source,
    )

    assert [violation.message for violation in violations] == [
        "test-std/test_behavior: declare @pytest.mark.manual on this test",
        (
            "test-std/test_behavior: do not replace an implemented test with a docstring-only placeholder; "
            "restore its implementation rather than changing __test__"
        ),
    ], "every applicable transition violation must be reported, not only the first"


def test_annotated_shadow_of_mark_root_does_not_satisfy_the_direct_requirement() -> None:
    """An annotated reassignment of ``mark`` cannot pass as the pytest marker."""
    source = '''"""Jira: https://issues.redhat.com/browse/CNV-88909"""
from pytest import mark

mark: object = framework.mark

__test__ = False

@mark.manual
def test_placeholder():
    """Placeholder scenario.

    Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>

    Preconditions:
    - the component is available
    Steps:
    - implement the scenario
    Expected:
    - the scenario is covered
    """
'''

    violations = check_test_std(
        file_path=Path("tests/network/test_behavior.py"),
        indexed_source=source,
        head_source=None,
    )

    assert [violation.message for violation in violations] == [
        "test-std/test_placeholder: declare @pytest.mark.manual on this test"
    ], "an annotated shadow of the mark root must not satisfy the manual requirement"


def test_conditional_shadow_of_pytest_root_does_not_satisfy_the_direct_requirement() -> None:
    """A control-flow-nested rebinding of ``pytest`` cannot pass as the pytest marker."""
    source = '''"""Jira: https://issues.redhat.com/browse/CNV-88909"""
import pytest

if condition:
    pytest = framework_pytest

__test__ = False

@pytest.mark.manual
def test_placeholder():
    """Placeholder scenario.

    Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>

    Preconditions:
    - the component is available
    Steps:
    - implement the scenario
    Expected:
    - the scenario is covered
    """
'''

    violations = check_test_std(
        file_path=Path("tests/network/test_behavior.py"),
        indexed_source=source,
        head_source=None,
    )

    assert [violation.message for violation in violations] == [
        "test-std/test_placeholder: declare @pytest.mark.manual on this test"
    ], "a conditional shadow of the pytest root must not satisfy the manual requirement"


def test_with_item_shadow_of_mark_root_does_not_satisfy_the_direct_requirement() -> None:
    """A ``with ... as mark`` rebinding cannot pass as the pytest marker."""
    source = '''"""Jira: https://issues.redhat.com/browse/CNV-88909"""
from pytest import mark

with context as mark:
    pass

__test__ = False

@mark.manual
def test_placeholder():
    """Placeholder scenario.

    Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>

    Preconditions:
    - the component is available
    Steps:
    - implement the scenario
    Expected:
    - the scenario is covered
    """
'''

    violations = check_test_std(
        file_path=Path("tests/network/test_behavior.py"),
        indexed_source=source,
        head_source=None,
    )

    assert [violation.message for violation in violations] == [
        "test-std/test_placeholder: declare @pytest.mark.manual on this test"
    ], "a with-item shadow of the mark root must not satisfy the manual requirement"


def test_function_definition_shadow_of_mark_root_does_not_satisfy_the_direct_requirement() -> None:
    """A module-scope function named ``mark`` cannot pass as the pytest marker."""
    source = '''"""Jira: https://issues.redhat.com/browse/CNV-88909"""
from pytest import mark

def mark():
    return None

__test__ = False

@mark.manual
def test_placeholder():
    """Placeholder scenario.

    Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>

    Preconditions:
    - the component is available
    Steps:
    - implement the scenario
    Expected:
    - the scenario is covered
    """
'''

    violations = check_test_std(
        file_path=Path("tests/network/test_behavior.py"),
        indexed_source=source,
        head_source=None,
    )

    assert [violation.message for violation in violations] == [
        "test-std/test_placeholder: declare @pytest.mark.manual on this test"
    ], "a function shadow of the mark root must not satisfy the manual requirement"


def test_destructured_shadow_of_mark_root_does_not_satisfy_the_direct_requirement() -> None:
    """A destructured assignment rebinding ``mark`` cannot pass as the pytest marker."""
    source = '''"""Jira: https://issues.redhat.com/browse/CNV-88909"""
from pytest import mark

value, mark = 1, framework_mark

__test__ = False

@mark.manual
def test_placeholder():
    """Placeholder scenario.

    Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>

    Preconditions:
    - the component is available
    Steps:
    - implement the scenario
    Expected:
    - the scenario is covered
    """
'''

    violations = check_test_std(
        file_path=Path("tests/network/test_behavior.py"),
        indexed_source=source,
        head_source=None,
    )

    assert [violation.message for violation in violations] == [
        "test-std/test_placeholder: declare @pytest.mark.manual on this test"
    ], "a destructured shadow of the mark root must not satisfy the manual requirement"


def test_except_as_shadow_of_mark_root_does_not_satisfy_the_direct_requirement() -> None:
    """An ``except ... as mark`` rebinding cannot pass as the pytest marker."""
    source = '''"""Jira: https://issues.redhat.com/browse/CNV-88909"""
from pytest import mark

try:
    pass
except Exception as mark:
    pass

__test__ = False

@mark.manual
def test_placeholder():
    """Placeholder scenario.

    Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>

    Preconditions:
    - the component is available
    Steps:
    - implement the scenario
    Expected:
    - the scenario is covered
    """
'''

    violations = check_test_std(
        file_path=Path("tests/network/test_behavior.py"),
        indexed_source=source,
        head_source=None,
    )

    assert [violation.message for violation in violations] == [
        "test-std/test_placeholder: declare @pytest.mark.manual on this test"
    ], "an except-as shadow of the mark root must not satisfy the manual requirement"


def test_mutually_exclusive_pytest_branches_fail_closed() -> None:
    """Mutually exclusive pytest bindings merge to an unrelated shadow."""
    source = '''"""Jira: https://issues.redhat.com/browse/CNV-88909"""
if condition:
    pytest = framework_pytest
else:
    import pytest

__test__ = False

@pytest.mark.manual
def test_placeholder():
    """Placeholder scenario.

    Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>

    Preconditions:
    - the component is available
    Steps:
    - implement the scenario
    Expected:
    - the scenario is covered
    """
'''

    violations = check_test_std(
        file_path=Path("tests/network/test_behavior.py"),
        indexed_source=source,
        head_source=None,
    )

    assert [violation.message for violation in violations] == [
        "test-std/test_placeholder: declare @pytest.mark.manual on this test"
    ], "mutually exclusive pytest bindings must fail closed"


def test_empty_loop_path_does_not_satisfy_the_direct_requirement() -> None:
    """A pytest binding inside a loop that may not run cannot pass as the marker."""
    source = '''"""Jira: https://issues.redhat.com/browse/CNV-88909"""
from framework import mark

for _ in items:
    from pytest import mark

__test__ = False

@mark.manual
def test_placeholder():
    """Placeholder scenario.

    Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>

    Preconditions:
    - the component is available
    Steps:
    - implement the scenario
    Expected:
    - the scenario is covered
    """
'''

    violations = check_test_std(
        file_path=Path("tests/network/test_behavior.py"),
        indexed_source=source,
        head_source=None,
    )

    assert [violation.message for violation in violations] == [
        "test-std/test_placeholder: declare @pytest.mark.manual on this test"
    ], "an empty-loop path must not satisfy the manual requirement"


def test_try_body_rebinding_does_not_satisfy_the_direct_requirement() -> None:
    """A try body that may rebind the marker root cannot pass as the marker."""
    source = '''"""Jira: https://issues.redhat.com/browse/CNV-88909"""
from pytest import mark

try:
    mark = framework_mark
except Exception:
    pass

__test__ = False

@mark.manual
def test_placeholder():
    """Placeholder scenario.

    Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>

    Preconditions:
    - the component is available
    Steps:
    - implement the scenario
    Expected:
    - the scenario is covered
    """
'''

    violations = check_test_std(
        file_path=Path("tests/network/test_behavior.py"),
        indexed_source=source,
        head_source=None,
    )

    assert [violation.message for violation in violations] == [
        "test-std/test_placeholder: declare @pytest.mark.manual on this test"
    ], "a try-body rebinding path must not satisfy the manual requirement"


def test_class_body_shadow_of_mark_root_does_not_satisfy_the_direct_requirement() -> None:
    """A class-local rebinding of ``mark`` cannot pass as the pytest marker."""
    source = '''"""Jira: https://issues.redhat.com/browse/CNV-88909"""
from pytest import mark

__test__ = False

class TestBehavior:
    mark = framework_mark

    @mark.manual
    def test_placeholder(self):
        """Placeholder scenario.

        Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>

        Preconditions:
        - the component is available
        Steps:
        - implement the scenario
        Expected:
        - the scenario is covered
        """
'''

    violations = check_test_std(
        file_path=Path("tests/network/test_behavior.py"),
        indexed_source=source,
        head_source=None,
    )

    assert [violation.message for violation in violations] == [
        "test-std/TestBehavior.test_placeholder: declare @pytest.mark.manual on this test"
    ], "a class-body shadow of the mark root must not satisfy the manual requirement"


def test_walrus_shadow_of_mark_root_does_not_satisfy_the_direct_requirement() -> None:
    """A module-scope walrus rebinding of ``mark`` cannot pass as the pytest marker."""
    source = '''"""Jira: https://issues.redhat.com/browse/CNV-88909"""
from pytest import mark

(mark := framework_mark)

__test__ = False

@mark.manual
def test_placeholder():
    """Placeholder scenario.

    Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>

    Preconditions:
    - the component is available
    Steps:
    - implement the scenario
    Expected:
    - the scenario is covered
    """
'''

    violations = check_test_std(
        file_path=Path("tests/network/test_behavior.py"),
        indexed_source=source,
        head_source=None,
    )

    assert [violation.message for violation in violations] == [
        "test-std/test_placeholder: declare @pytest.mark.manual on this test"
    ], "a module-scope walrus shadow of the mark root must not satisfy the manual requirement"


def test_deleted_mark_root_does_not_satisfy_the_direct_requirement() -> None:
    """Deleting ``mark`` at module scope invalidates its imported coverage."""
    source = '''"""Jira: https://issues.redhat.com/browse/CNV-88909"""
from pytest import mark

del mark

__test__ = False

@mark.manual
def test_placeholder():
    """Placeholder scenario.

    Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>

    Preconditions:
    - the component is available
    Steps:
    - implement the scenario
    Expected:
    - the scenario is covered
    """
'''

    violations = check_test_std(
        file_path=Path("tests/network/test_behavior.py"),
        indexed_source=source,
        head_source=None,
    )

    assert [violation.message for violation in violations] == [
        "test-std/test_placeholder: declare @pytest.mark.manual on this test"
    ], "deleting the mark root at module scope must not satisfy the manual requirement"


def test_match_case_shadow_of_mark_root_does_not_satisfy_the_direct_requirement() -> None:
    """A match-case rebinding of ``mark`` cannot pass as the pytest marker."""
    source = '''"""Jira: https://issues.redhat.com/browse/CNV-88909"""
from pytest import mark

match value:
    case _:
        mark = framework_mark

__test__ = False

@mark.manual
def test_placeholder():
    """Placeholder scenario.

    Jira: https://issues.redhat.com/browse/CNV-88909  # <skip-jira-utils-check>

    Preconditions:
    - the component is available
    Steps:
    - implement the scenario
    Expected:
    - the scenario is covered
    """
'''

    violations = check_test_std(
        file_path=Path("tests/network/test_behavior.py"),
        indexed_source=source,
        head_source=None,
    )

    assert [violation.message for violation in violations] == [
        "test-std/test_placeholder: declare @pytest.mark.manual on this test"
    ], "a match-case shadow of the mark root must not satisfy the manual requirement"

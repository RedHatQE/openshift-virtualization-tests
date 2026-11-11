"""Unit tests for explicit resource-client policy checks."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent
from typing import TYPE_CHECKING

from scripts.pre_commit_hooks import check_policy
from scripts.pre_commit_hooks import check_resource_clients as resource_client_policy
from scripts.pre_commit_hooks.check_resource_clients import check_resource_clients, discover_resource_classes
from scripts.pre_commit_hooks.tests.git_repository import commit_all, initialize_git_repository, stage_paths

if TYPE_CHECKING:
    from pytest import MonkeyPatch


def test_discover_resource_classes_parses_dependency_wrappers_and_local_subclasses(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    """Static discovery follows Resource subclasses without importing project modules."""
    dependency_root = tmp_path / "dependency" / "ocp_resources"
    dependency_root.mkdir(parents=True)
    (dependency_root / "resource.py").write_text(
        data=dedent(
            """
            class Resource:
                pass

            class NamespacedResource(Resource):
                pass
            """
        ),
        encoding="utf-8",
    )
    (dependency_root / "wrapped.py").write_text(
        data="from ocp_resources.resource import Resource\n\nclass Wrapped(Resource):\n    pass\n",
        encoding="utf-8",
    )
    local_root = tmp_path / "utilities"
    local_root.mkdir()
    (local_root / "resource_wrappers.py").write_text(
        data=dedent(
            """
            from dataclasses import dataclass
            from ocp_resources.wrapped import Wrapped

            class LocalWrapped(Wrapped):
                pass

            @dataclass
            class OrdinaryData:
                value: str
            """
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        target=resource_client_policy,
        name="_dependency_root",
        value=lambda: dependency_root,
    )

    resources = discover_resource_classes(repository_root=tmp_path)

    assert ("ocp_resources", "wrapped", "Wrapped") in resources, "dependency wrappers should be discovered"
    assert ("utilities", "resource_wrappers", "LocalWrapped") in resources, "local wrappers should be discovered"
    assert ("utilities", "resource_wrappers", "OrdinaryData") not in resources, (
        "unrelated dataclasses must not be classified as resources"
    )


def test_discover_resource_classes_follows_conditional_local_subclasses(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    """Static discovery follows an imported base into conditional local subclasses."""
    dependency_root = tmp_path / "dependency" / "ocp_resources"
    dependency_root.mkdir(parents=True)
    (dependency_root / "resource.py").write_text(data="class Resource:\n    pass\n", encoding="utf-8")
    monkeypatch.setattr(target=resource_client_policy, name="_dependency_root", value=lambda: dependency_root)
    sources = {
        ("utilities", "base"): dedent(
            """
            from ocp_resources.resource import Resource

            class Base(Resource):
                pass
            """
        ),
        ("utilities", "child"): dedent(
            """
            from utilities.base import Base

            if condition:
                class Child(Base):
                    pass
            """
        ),
    }

    def source_reader(module_name: tuple[str, ...]) -> str | None:
        return sources.get(module_name)

    resources = discover_resource_classes(
        repository_root=tmp_path,
        source_reader=source_reader,
        module_names={("utilities", "child")},
    )

    assert ("utilities", "child", "Child") in resources, (
        "conditional subclasses of imported local Resource wrappers must be discovered"
    )


def test_discover_resource_classes_resolves_relative_imports_from_ordinary_modules(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    """Relative imports resolve from an ordinary module's containing package."""
    dependency_root = tmp_path / "dependency" / "ocp_resources"
    dependency_root.mkdir(parents=True)
    (dependency_root / "resource.py").write_text(data="class Resource:\n    pass\n", encoding="utf-8")
    monkeypatch.setattr(target=resource_client_policy, name="_dependency_root", value=lambda: dependency_root)
    sources: dict[tuple[str, ...], str] = {
        ("utilities", "base"): "from ocp_resources.resource import Resource\nclass Base(Resource):pass\n",
        ("utilities", "child"): "from .base import Base\nclass Child(Base):pass\n",
    }

    def source_reader(module_name: tuple[str, ...]) -> str | None:
        return sources.get(module_name)

    resources = discover_resource_classes(
        source_reader=source_reader,
        module_names={("utilities", "child")},
        repository_root=tmp_path,
    )

    assert ("utilities", "child", "Child") in resources, (
        "relative imports in ordinary modules must resolve from the containing package"
    )


def test_discover_resource_classes_follows_conditional_dependency_wrappers(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    """Static discovery includes Resource wrappers defined in conditional module code."""
    dependency_root = tmp_path / "dependency" / "ocp_resources"
    dependency_root.mkdir(parents=True)
    (dependency_root / "resource.py").write_text(data="class Resource:\n    pass\n", encoding="utf-8")
    (dependency_root / "base.py").write_text(
        data="from ocp_resources.resource import Resource\n\nclass Base(Resource):\n    pass\n",
        encoding="utf-8",
    )
    (dependency_root / "wrapped.py").write_text(
        data=dedent(
            """
            from .base import Base

            if condition:
                class ConditionalWrapper(Base):
                    pass
            """
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(target=resource_client_policy, name="_dependency_root", value=lambda: dependency_root)

    resources = discover_resource_classes(repository_root=tmp_path)

    assert ("ocp_resources", "wrapped", "ConditionalWrapper") in resources, (
        "conditional dependency Resource wrappers must be discovered"
    )


def test_check_python_source_reports_missing_client_for_conditional_imported_subclass() -> None:
    """Calls to conditional subclasses of imported Resource wrappers require a client."""
    source = dedent(
        """
        from utilities.base import BaseWrapper

        if condition:
            class ChildWrapper(BaseWrapper):
                pass

        ChildWrapper()
        """
    )

    violations = check_policy.check_python_source(
        file_path=Path("utilities/caller.py"),
        source=source,
        resource_classes={("utilities", "base", "BaseWrapper")},
    )

    assert [(violation.line_number, violation.message) for violation in violations] == [
        (8, "resource-clients: pass an existing non-None client= to this Resource constructor")
    ], "conditional subclasses of imported Resource wrappers must require client="


def test_resource_constructors_require_existing_non_none_clients(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    """Resource constructors accept an existing client and reject omitted or None clients."""
    dependency_root = tmp_path / "dependency" / "ocp_resources"
    dependency_root.mkdir(parents=True)
    (dependency_root / "resource.py").write_text(
        data="class Resource:\n    pass\n",
        encoding="utf-8",
    )
    (dependency_root / "wrapped.py").write_text(
        data="from ocp_resources.resource import Resource\n\nclass Wrapped(Resource):\n    pass\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(target=resource_client_policy, name="_dependency_root", value=lambda: dependency_root)
    source = dedent(
        """
        from ocp_resources.wrapped import Wrapped as ResourceAlias

        ResourceAlias()
        ResourceAlias(client=client)
        ResourceAlias(client=None)
        """
    )

    violations = check_resource_clients(
        file_path=Path("utilities/example.py"),
        source=source,
        repository_root=tmp_path,
    )

    assert [(violation.line_number, violation.message) for violation in violations] == [
        (4, "resource-clients: pass an existing non-None client= to this Resource constructor"),
        (6, "resource-clients: pass an existing non-None client= to this Resource constructor"),
    ], "only omitted and literal-None resource clients should be rejected"


def test_resource_class_get_requires_existing_non_none_client(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    """Resource class get calls apply the same explicit-client rule as constructors."""
    dependency_root = tmp_path / "dependency" / "ocp_resources"
    dependency_root.mkdir(parents=True)
    (dependency_root / "resource.py").write_text(data="class Resource:\n    pass\n", encoding="utf-8")
    (dependency_root / "wrapped.py").write_text(
        data="from ocp_resources.resource import Resource\n\nclass Wrapped(Resource):\n    pass\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(target=resource_client_policy, name="_dependency_root", value=lambda: dependency_root)
    source = dedent(
        """
        from ocp_resources.wrapped import Wrapped as ResourceAlias

        ResourceAlias.get()
        ResourceAlias.get(client=client)
        ResourceAlias.get(client=None)
        """
    )

    violations = check_resource_clients(
        file_path=Path("utilities/example.py"),
        source=source,
        repository_root=tmp_path,
    )

    assert [(violation.line_number, violation.message) for violation in violations] == [
        (4, "resource-clients: pass an existing non-None client= to this Resource class .get()"),
        (6, "resource-clients: pass an existing non-None client= to this Resource class .get()"),
    ], "class get must reject omitted and literal-None clients"


def test_resource_instance_and_dictionary_get_calls_are_not_class_get_calls(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    """Instance and dictionary get methods are not mistaken for Resource class get calls."""
    dependency_root = tmp_path / "dependency" / "ocp_resources"
    dependency_root.mkdir(parents=True)
    (dependency_root / "resource.py").write_text(data="class Resource:\n    pass\n", encoding="utf-8")
    (dependency_root / "wrapped.py").write_text(
        data="from ocp_resources.resource import Resource\n\nclass Wrapped(Resource):\n    pass\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(target=resource_client_policy, name="_dependency_root", value=lambda: dependency_root)
    source = dedent(
        """
        from ocp_resources.wrapped import Wrapped

        resource = Wrapped(client=client)
        resource.get()
        values = {}
        values.get("name")
        """
    )

    violations = check_resource_clients(
        file_path=Path("utilities/example.py"),
        source=source,
        repository_root=tmp_path,
    )

    assert violations == [], "instance and dict get calls must not require Resource class clients"


def test_resource_checks_follow_imported_aliases_and_added_line_ranges(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    """Aliased wrappers are checked only when their call spans an added line."""
    dependency_root = tmp_path / "dependency" / "ocp_resources"
    dependency_root.mkdir(parents=True)
    (dependency_root / "resource.py").write_text(data="class Resource:\n    pass\n", encoding="utf-8")
    (dependency_root / "wrapped.py").write_text(
        data="from ocp_resources.resource import Resource\n\nclass Wrapped(Resource):\n    pass\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(target=resource_client_policy, name="_dependency_root", value=lambda: dependency_root)
    source = dedent(
        """
        from ocp_resources.wrapped import Wrapped as ResourceAlias

        ResourceAlias(
            name="unchanged",
        )
        ResourceAlias(
            name="added",
        )
        """
    )

    violations = check_resource_clients(
        file_path=Path("utilities/example.py"),
        source=source,
        added_lines={8},
        repository_root=tmp_path,
    )

    assert [(violation.line_number, violation.message) for violation in violations] == [
        (7, "resource-clients: pass an existing non-None client= to this Resource constructor")
    ], "a continuation line should activate only its enclosing resource call"


def test_cache_admin_client_accepts_nonempty_prior_inline_and_multiline_comments() -> None:
    """Documented cache-admin calls are accepted in each supported call context."""
    source = dedent(
        """
        from utilities.cluster import cache_admin_client

        # assignment needs the admin cache for setup
        assigned = cache_admin_client()
        with cache_admin_client() as managed:  # context manager owns cleanup
            pass
        multiline = cache_admin_client(
            # multiline call needs the admin cache for setup
        )

        def returned():
            # return path needs the admin cache for setup
            return cache_admin_client(
                # multiline return needs the admin cache for setup
            )
        """
    )

    violations = check_resource_clients(file_path=Path("utilities/example.py"), source=source)

    assert violations == [], "nonempty preceding or inline comments should explain every cache-admin call"


def test_cache_admin_client_accepts_comment_only_immediately_before_return() -> None:
    """A comment on the line immediately before return explains its cache-admin call."""
    source = dedent(
        """
        from utilities.cluster import cache_admin_client

        def returned():
            # required for this return path
            return cache_admin_client()
        """
    )

    assert check_resource_clients(file_path=Path("utilities/example.py"), source=source) == [], (
        "a comment-only line immediately before return should explain the call"
    )


def test_cache_admin_client_rejects_trailing_comment_on_preceding_statement() -> None:
    """A trailing comment on the preceding statement does not explain the next call."""
    source = dedent(
        """
        from utilities.cluster import cache_admin_client

        value = 1  # explains value, not the following cache-admin call
        cache = cache_admin_client()
        """
    )

    violations = check_resource_clients(file_path=Path("utilities/example.py"), source=source)

    assert [(violation.line_number, violation.message) for violation in violations] == [
        (
            5,
            (
                "resource-clients/cache-admin-client: add an immediate or inline comment explaining why "
                "cache_admin_client() is required at this call site"
            ),
        )
    ], "a trailing comment on the preceding statement must not explain a following call"


def test_cache_admin_client_rejects_body_comments_for_conditions() -> None:
    """A comment inside an if body does not explain the cache-admin condition."""
    source = dedent(
        """
        from utilities.cluster import cache_admin_client

        if cache_admin_client():
            # explains the body, not the condition
            pass
        """
    )

    violations = check_resource_clients(file_path=Path("utilities/example.py"), source=source)

    assert [(violation.line_number, violation.message) for violation in violations] == [
        (
            4,
            (
                "resource-clients/cache-admin-client: add an immediate or inline comment explaining why "
                "cache_admin_client() is required at this call site"
            ),
        )
    ], "a body comment must not explain a cache-admin condition"


def test_cache_admin_client_rejects_body_comments_for_decorators_and_defaults() -> None:
    """Function/class body comments do not explain decorators or default arguments."""
    source = dedent(
        """
        from utilities.cluster import cache_admin_client

        @cache_admin_client()
        def decorated_function():
            # explains the function body, not the decorator
            pass

        @cache_admin_client()
        class DecoratedClass:
            # explains the class body, not the decorator
            pass

        def with_default(value=cache_admin_client()):
            # explains the function body, not the default
            pass
        """
    )

    violations = check_resource_clients(file_path=Path("utilities/example.py"), source=source)

    assert [(violation.line_number, violation.message) for violation in violations] == [
        (
            4,
            (
                "resource-clients/cache-admin-client: add an immediate or inline comment explaining why "
                "cache_admin_client() is required at this call site"
            ),
        ),
        (
            9,
            (
                "resource-clients/cache-admin-client: add an immediate or inline comment explaining why "
                "cache_admin_client() is required at this call site"
            ),
        ),
        (
            14,
            (
                "resource-clients/cache-admin-client: add an immediate or inline comment explaining why "
                "cache_admin_client() is required at this call site"
            ),
        ),
    ], "body comments must not explain cache-admin decorators or defaults"


def test_cache_admin_client_accepts_comments_before_decorators_and_in_headers() -> None:
    """Comments before decorators and inline in headers explain cache-admin calls."""
    source = dedent(
        """
        from utilities.cluster import cache_admin_client

        # required for the function decorator
        @cache_admin_client()
        def decorated_function():
            pass

        # required for the class decorator
        @cache_admin_client()
        class DecoratedClass:
            pass

        def with_default(value=cache_admin_client()):  # required for the default
            pass
        """
    )

    assert check_resource_clients(file_path=Path("utilities/example.py"), source=source) == [], (
        "comments before decorators and inline in headers should explain cache-admin calls"
    )


def test_cache_admin_client_rejects_empty_comments_and_missing_comments() -> None:
    """Blank comments do not satisfy the cache-admin explanation requirement."""
    source = dedent(
        """
        from utilities.cluster import cache_admin_client

        #
        blank = cache_admin_client()
        missing = cache_admin_client()
        inline = cache_admin_client()  # use the cached administrator
        """
    )

    violations = check_resource_clients(file_path=Path("utilities/example.py"), source=source)

    assert [(violation.line_number, violation.message) for violation in violations] == [
        (
            5,
            "resource-clients/cache-admin-client: add an immediate or inline comment explaining why cache_admin_client() is required at this call site",
        ),
        (
            6,
            "resource-clients/cache-admin-client: add an immediate or inline comment explaining why cache_admin_client() is required at this call site",
        ),
    ], "empty and absent comments should be rejected while inline explanations pass"


def test_unrelated_cache_admin_imports_and_local_functions_are_not_misidentified() -> None:
    """Only the approved cache-admin client bindings receive the explanation rule."""
    source = dedent(
        """
        from unrelated.module import cache_admin_client as unrelated_cache_admin_client

        def cache_admin_client():
            return object()

        unrelated_cache_admin_client()
        cache_admin_client()
        """
    )

    violations = check_resource_clients(file_path=Path("utilities/example.py"), source=source)

    assert violations == [], "unrelated imports and local functions must not trigger cache-admin policy"


def test_sibling_argument_and_control_edits_do_not_activate_unchanged_cache_calls() -> None:
    """Sibling edits must not re-report unchanged undocumented cache-admin calls."""
    cases = (
        (
            dedent(
                """
                from utilities.cluster import cache_admin_client

                result = build(
                    mode="old",
                    client=cache_admin_client(),
                )
                """
            ),
            dedent(
                """
                from utilities.cluster import cache_admin_client

                result = build(
                    mode="new",
                    client=cache_admin_client(),
                )
                """
            ),
            frozenset({5}),
            "sibling argument",
        ),
        (
            dedent(
                """
                from utilities.cluster import cache_admin_client

                if (
                    old_condition
                    and cache_admin_client()
                ):
                    run()
                """
            ),
            dedent(
                """
                from utilities.cluster import cache_admin_client

                if (
                    new_condition
                    and cache_admin_client()
                ):
                    run()
                """
            ),
            frozenset({5}),
            "sibling control expression",
        ),
    )

    for head_source, indexed_source, added_lines, edit_description in cases:
        violations = check_resource_clients(
            file_path=Path("utilities/example.py"),
            source=indexed_source,
            added_lines=added_lines,
            head_source=head_source,
        )

        assert violations == [], f"a {edit_description} edit must not activate the unchanged cache call"


def test_removed_cache_admin_comment_is_detected_as_a_changed_policy_violation() -> None:
    """Removing the only explanation from an unchanged call must remain detectable."""
    head_source = (
        "from utilities.cluster import cache_admin_client\n# required for setup\ncache = cache_admin_client()\n"
    )
    indexed_source = "from utilities.cluster import cache_admin_client\ncache = cache_admin_client()\n"

    violations = check_resource_clients(
        file_path=Path("utilities/example.py"),
        source=indexed_source,
        head_source=head_source,
    )

    assert [(violation.line_number, violation.message) for violation in violations] == [
        (
            2,
            "resource-clients/cache-admin-client: add an immediate or inline comment explaining why cache_admin_client() is required at this call site",
        )
    ], "a removed explanatory comment must activate the unchanged call-site check"


def test_approved_cache_admin_binding_activates_an_unchanged_call() -> None:
    """Changing a call's binding to cache_admin_client must activate its policy check."""
    head_source = dedent(
        """
        def cache_admin_client():
            return object()

        cache_admin_client()
        """
    )
    indexed_source = dedent(
        """
        from utilities.cluster import cache_admin_client

        cache_admin_client()
        """
    )

    violations = check_resource_clients(
        file_path=Path("utilities/example.py"),
        source=indexed_source,
        added_lines=frozenset({2}),
        head_source=head_source,
    )

    assert [(violation.line_number, violation.message) for violation in violations] == [
        (
            4,
            (
                "resource-clients/cache-admin-client: add an immediate or inline comment explaining why "
                "cache_admin_client() is required at this call site"
            ),
        )
    ], "an approved binding must activate the unchanged undocumented call"


def test_approved_cache_admin_import_alias_is_checked_but_local_function_is_valid() -> None:
    """Only the approved cache-admin import alias receives the explanation rule."""
    source = dedent(
        """
        from utilities.cluster import cache_admin_client as approved_cache

        def cache_admin_client():
            return object()

        approved_cache()
        cache_admin_client()
        """
    )

    violations = check_resource_clients(file_path=Path("utilities/example.py"), source=source)

    assert [(violation.line_number, violation.message) for violation in violations] == [
        (
            7,
            "resource-clients/cache-admin-client: add an immediate or inline comment explaining why "
            + "cache_admin_client() is required at this call site",
        )
    ], "approved aliases must be checked without flagging unrelated local functions"


def test_local_resource_subclass_calls_use_the_shared_resolver_and_allow_explicit_clients(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    """Local Resource subclasses require clients while specs, dictionaries, and instances remain valid."""
    dependency_root = tmp_path / "dependency" / "ocp_resources"
    dependency_root.mkdir(parents=True)
    (dependency_root / "resource.py").write_text(data="class Resource:\n    pass\n", encoding="utf-8")
    monkeypatch.setattr(target=resource_client_policy, name="_dependency_root", value=lambda: dependency_root)
    source = dedent(
        """
        from ocp_resources.resource import Resource

        class LocalResource(Resource):
            pass

        LocalResource()
        LocalResource.get()
        LocalResource(client=client)
        LocalResource.get(client=client)
        spec = {"name": "spec"}
        spec.get("name")
        instance = LocalResource(client=client)
        instance.get()
        """
    )

    violations = check_policy.check_python_source(file_path=Path("utilities/example.py"), source=source)

    assert [(violation.line_number, violation.message) for violation in violations] == [
        (7, "resource-clients: pass an existing non-None client= to this Resource constructor"),
        (8, "resource-clients: pass an existing non-None client= to this Resource class .get()"),
    ], "the integrated resolver must enforce local subclasses without flagging valid explicit clients or instances"


def test_index_resource_discovery_ignores_divergent_worktree_wrappers(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    """Staged callers use indexed wrapper inheritance instead of a divergent worktree helper."""
    dependency_root = tmp_path / "dependency" / "ocp_resources"
    dependency_root.mkdir(parents=True)
    (dependency_root / "resource.py").write_text(data="class Resource:\n    pass\n", encoding="utf-8")
    utilities_root = tmp_path / "utilities"
    utilities_root.mkdir()
    wrapper_path = utilities_root / "wrappers.py"
    indexed_wrapper = "from ocp_resources.resource import Resource\n\nclass Wrapper(Resource):\n    pass\n"
    wrapper_path.write_text(data=indexed_wrapper, encoding="utf-8")
    initialize_git_repository(repository_root=tmp_path)
    commit_all(repository_root=tmp_path)
    wrapper_path.write_text(data="class Wrapper:\n    pass\n", encoding="utf-8")
    caller_path = utilities_root / "caller.py"
    caller_path.write_text(data="from utilities.wrappers import Wrapper\nWrapper()\n", encoding="utf-8")
    stage_paths(repository_root=tmp_path, paths=("utilities/caller.py",))
    monkeypatch.setattr(target=resource_client_policy, name="_dependency_root", value=lambda: dependency_root)
    monkeypatch.chdir(path=tmp_path)

    assert check_policy.main(arguments=["utilities/caller.py"]) == 1, (
        "indexed Resource inheritance must reject the staged caller despite divergent worktree source"
    )


def test_deletion_only_cache_reason_removal_is_detected_in_a_real_repository(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """A deletion-only staged diff still checks a removed cache-admin explanation."""
    initialize_git_repository(repository_root=tmp_path)
    source_path = tmp_path / "example.py"
    source_path.write_text(
        data="from utilities.cluster import cache_admin_client\n# required for setup\ncache = cache_admin_client()\n",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "scripts/pre_commit_hooks/exceptions.toml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(data="exceptions = []\n", encoding="utf-8")
    commit_all(repository_root=tmp_path)
    source_path.write_text(
        data="from utilities.cluster import cache_admin_client\ncache = cache_admin_client()\n",
        encoding="utf-8",
    )
    stage_paths(repository_root=tmp_path, paths=("example.py",))
    monkeypatch.chdir(path=tmp_path)

    assert check_policy.main(arguments=["example.py"]) == 1, (
        "deletion-only cache reason removal must fail policy checks"
    )


def test_unrelated_deletion_does_not_activate_unchanged_undocumented_cache_call(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """An unrelated deletion must not activate an unchanged undocumented cache-admin call."""
    initialize_git_repository(repository_root=tmp_path)
    source_path = tmp_path / "example.py"
    source_path.write_text(
        data="from utilities.cluster import cache_admin_client\ncache = cache_admin_client()\nvalue = 1\n",
        encoding="utf-8",
    )
    deleted_path = tmp_path / "deleted.txt"
    deleted_path.write_text(data="remove me\n", encoding="utf-8")
    manifest_path = tmp_path / "scripts/pre_commit_hooks/exceptions.toml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(data="exceptions = []\n", encoding="utf-8")
    commit_all(repository_root=tmp_path)
    deleted_path.unlink()
    stage_paths(repository_root=tmp_path, paths=("deleted.txt",))
    monkeypatch.chdir(path=tmp_path)

    assert check_policy.main(arguments=["example.py"]) == 0, (
        "unrelated deletions must not activate unchanged cache calls"
    )


def test_duplicate_cache_calls_report_the_call_whose_comment_was_removed() -> None:
    """A removed comment must not consume another identical call's HEAD baseline."""
    head_source = dedent(
        """
        from utilities.cluster import cache_admin_client
        # first call needs the administrator cache
        first = cache_admin_client()
        second = cache_admin_client()
        """
    )
    indexed_source = dedent(
        """
        from utilities.cluster import cache_admin_client
        first = cache_admin_client()
        second = cache_admin_client()
        """
    )

    violations = check_resource_clients(
        file_path=Path("utilities/example.py"),
        source=indexed_source,
        added_lines=frozenset(),
        head_source=head_source,
    )

    assert [(violation.line_number, violation.message) for violation in violations] == [
        (
            3,
            (
                "resource-clients/cache-admin-client: add an immediate or inline comment explaining why "
                "cache_admin_client() is required at this call site"
            ),
        )
    ], "the changed first call must not consume the second call's identical baseline"


def test_duplicate_identical_cache_calls_reject_the_newly_undocumented_call_after_comment_move() -> None:
    """Moving one comment between identical calls must not authorize the newly undocumented first call."""
    head_source = dedent(
        """
        from utilities.cluster import cache_admin_client
        # the first call needs administrator access
        cache_admin_client()
        cache_admin_client()
        """
    )
    indexed_source = dedent(
        """
        from utilities.cluster import cache_admin_client
        cache_admin_client()
        # the first call needs administrator access
        cache_admin_client()
        """
    )

    violations = check_resource_clients(
        file_path=Path("utilities/example.py"),
        source=indexed_source,
        added_lines=frozenset(),
        head_source=head_source,
    )

    assert [(violation.line_number, violation.message) for violation in violations] == [
        (
            3,
            (
                "resource-clients/cache-admin-client: add an immediate or inline comment explaining why "
                "cache_admin_client() is required at this call site"
            ),
        )
    ], "a moved comment must not let the old identical-call baseline hide the new undocumented call"


def test_resource_discovery_follows_local_reexport_facades(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    """Staged Resource checks follow facades and package submodule re-exports."""
    dependency_root = tmp_path / "dependency" / "ocp_resources"
    dependency_root.mkdir(parents=True)
    (dependency_root / "resource.py").write_text(data="class Resource:\n    pass\n", encoding="utf-8")
    utilities_root = tmp_path / "utilities"
    package_root = utilities_root / "package"
    package_root.mkdir(parents=True)
    (utilities_root / "__init__.py").write_text(data="from utilities import facade\n", encoding="utf-8")
    (utilities_root / "wrappers.py").write_text(
        data="from ocp_resources.resource import Resource\n\nclass Wrapped(Resource):\n    pass\n",
        encoding="utf-8",
    )
    (utilities_root / "facade.py").write_text(
        data="from utilities.wrappers import Wrapped\n",
        encoding="utf-8",
    )
    (package_root / "__init__.py").write_text(data="from .submodule import SubWrapped as Wrapped\n", encoding="utf-8")
    (package_root / "submodule.py").write_text(
        data="from ocp_resources.resource import Resource\n\nclass SubWrapped(Resource):\n    pass\n",
        encoding="utf-8",
    )
    caller_path = utilities_root / "caller.py"
    caller_path.write_text(data="value = 1\n", encoding="utf-8")
    initialize_git_repository(repository_root=tmp_path)
    commit_all(repository_root=tmp_path)
    caller_path.write_text(
        data=(
            "from utilities import facade\n"
            "from utilities.package import Wrapped\n"
            "\n"
            "if condition:\n"
            "    ResourceAlias = Wrapped\n"
            "else:\n"
            "    ResourceAlias = safe\n"
            "ResourceAlias()\n"
        ),
        encoding="utf-8",
    )
    stage_paths(repository_root=tmp_path, paths=("utilities/caller.py",))
    monkeypatch.setattr(target=resource_client_policy, name="_dependency_root", value=lambda: dependency_root)
    monkeypatch.chdir(path=tmp_path)

    assert check_policy.main(arguments=["utilities/caller.py"]) == 1, (
        "relative package re-exports and conditional Resource aliases must require client="
    )

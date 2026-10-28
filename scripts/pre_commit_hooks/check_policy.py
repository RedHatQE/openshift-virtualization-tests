#!/usr/bin/env -S uv run python
"""Check repository policies for files selected by pre-commit."""

from __future__ import annotations

import string
from ast import (
    AST,
    AnnAssign,
    Assign,
    AsyncFor,
    AsyncFunctionDef,
    Attribute,
    AugAssign,
    Break,
    Call,
    ClassDef,
    Continue,
    DictComp,
    For,
    FunctionDef,
    GeneratorExp,
    Global,
    If,
    IfExp,
    Import,
    ImportFrom,
    Lambda,
    List,
    ListComp,
    Match,
    Module,
    Name,
    NamedExpr,
    Nonlocal,
    Raise,
    Return,
    SetComp,
    Starred,
    Store,
    Try,
    TryStar,
    Tuple,
    While,
    arguments,
    expr,
    iter_child_nodes,
    parse,
    stmt,
    walk,
)
from dataclasses import dataclass, field
from importlib import import_module
from json import loads
from pathlib import Path
from re import compile as re_compile
from sys import argv
from sys import modules as system_modules
from typing import TYPE_CHECKING, cast

from scripts.pre_commit_hooks.ast_names import dotted_name
from scripts.pre_commit_hooks.check_linter_directives import (
    EXCEPTIONS_PATH,
    ExceptionManifestError,
    check_linter_directives,
    check_manifest_update,
    load_exceptions,
)
from scripts.pre_commit_hooks.check_resource_clients import (
    _relative_import_prefixes,
    check_resource_clients,
    discover_resource_classes,
    imported_module_names,
)
from scripts.pre_commit_hooks.check_stp_links import (
    STP_REPOSITORY,
    check_stp_links,
    stp_references,
    unverified_stp_violation,
)
from scripts.pre_commit_hooks.check_test_basics import check_test_basics
from scripts.pre_commit_hooks.check_test_std import check_test_std
from scripts.pre_commit_hooks.policy_types import PolicyViolation

if TYPE_CHECKING:
    from collections.abc import Callable, Collection, Sequence


run_command = cast(
    "Callable[..., tuple[bool, str, str]]",
    import_module("pyhelper_utils.shell").run_command,
)


@dataclass(frozen=True, slots=True)
class StagedChanges:
    """Describe the staged result.

    Deleted source files are skipped for source analysis, but their paths stay
    visible to path-policy checks and manifest-deletion validation.
    """

    changed_paths: frozenset[Path]
    deleted_paths: frozenset[Path]
    renamed_paths: frozenset[Path]
    renamed_away_paths: frozenset[Path]
    symlinked_paths: frozenset[Path]
    added_lines: dict[Path, frozenset[int]]
    sources: dict[Path, str]
    head_sources: dict[Path, str] = field(default_factory=dict)
    copied_paths: frozenset[Path] = frozenset()


@dataclass(frozen=True, slots=True)
class _StagedEntry:
    status: str
    path: Path
    head_path: Path | None
    source_path: Path | None = None


@dataclass(slots=True)
class _IndexSourceReader:
    paths: dict[tuple[str, ...], Path]
    sources: dict[tuple[str, ...], str] = field(default_factory=dict)

    def __call__(self, module_name: tuple[str, ...]) -> str | None:
        path = self.paths.get(module_name)
        if path is None:
            return None
        if module_name not in self.sources:
            self.sources[module_name] = _git_output(command=["git", "show", f":0:{path}"])
        return self.sources[module_name]


@dataclass(slots=True)
class _DiffState:
    """Track the current file and source line while parsing a diff."""

    current_path: Path | None
    current_line: int | None = None
    in_hunk: bool = False


_HUNK_HEADER = re_compile(pattern=r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
_STAGED_DIFF_OPTIONS = (
    "--cached",
    "--find-renames",
    "--unified=0",
    "--no-color",
    "--no-ext-diff",
    "--no-textconv",
)
_SYMLINKED_PYTHON_MESSAGE = (
    "policy: staged Python symlinks are not allowed; commit the real file so its source is checked"
)
_SYMLINKED_MANIFEST_MESSAGE = (
    "policy: the exception manifest must be a real file; commit the actual manifest so its records are checked"
)


@dataclass(slots=True)
class _Binding:
    value: expr | None
    node: AST
    imported_name: tuple[str, ...] | None = None
    visible_phase: int | None = None


@dataclass(slots=True)
class _Scope:
    parent: _Scope | None
    kind: str
    bindings: dict[str, list[_Binding]] = field(default_factory=dict)
    local_names: set[str] = field(default_factory=set)
    global_names: set[str] = field(default_factory=set)
    nonlocal_names: set[str] = field(default_factory=set)
    active_bindings: dict[str, tuple[_Binding, ...]] = field(default_factory=dict)


@dataclass(slots=True)
class _LoopExits:
    tracked_scopes: tuple[_Scope, ...]
    break_outputs: list[list[dict[str, tuple[_Binding, ...]]]] = field(default_factory=list)
    continue_outputs: list[list[dict[str, tuple[_Binding, ...]]]] = field(default_factory=list)


def _scope_statements(statements: Sequence[stmt]) -> tuple[stmt, ...]:
    collected: list[stmt] = []
    for statement in statements:
        collected.append(statement)
        if not isinstance(statement, (ClassDef, FunctionDef, AsyncFunctionDef)):
            collected.extend(
                _scope_statements(
                    statements=tuple(child for child in iter_child_nodes(statement) if isinstance(child, stmt))
                )
            )
    return tuple(collected)


@dataclass(frozen=True, slots=True)
class _Scopes:
    root: _Scope
    node_scopes: dict[AST, _Scope]
    node_phases: dict[AST, int]
    node_bindings: dict[AST, tuple[_Binding, ...]]


class _ScopeBuilder:
    """Build lexical scopes and ordered name bindings for an AST."""

    def __init__(
        self,
        tree: Module,
        module_name: tuple[str, ...] = (),
        is_package: bool = False,
    ) -> None:
        self.module_name = module_name
        self.is_package = is_package
        self.root = _Scope(parent=None, kind="module")
        self.node_scopes: dict[AST, _Scope] = {}
        self.node_phases: dict[AST, int] = {}
        self.node_bindings: dict[AST, tuple[_Binding, ...]] = {}
        self.scopes = [self.root]
        self._loop_exits: list[_LoopExits] = []
        self._visit(node=tree, scope=self.root)

    def build(self) -> _Scopes:
        return _Scopes(
            root=self.root,
            node_scopes=self.node_scopes,
            node_phases=self.node_phases,
            node_bindings=self.node_bindings,
        )

    def _binding_scope(self, scope: _Scope, name: str) -> _Scope:
        if name in scope.global_names:
            return self.root
        if name in scope.nonlocal_names:
            parent = scope.parent
            while parent is not None and parent.kind != "function":
                parent = parent.parent
            if parent is not None:
                return parent
        return scope

    def _bind(
        self,
        scope: _Scope,
        name: str,
        value: expr | None,
        node: AST,
        imported_name: tuple[str, ...] | None = None,
        visible_phase: int | None = None,
    ) -> None:
        scope = self._binding_scope(scope=scope, name=name)
        binding = _Binding(
            value=value,
            node=node,
            imported_name=imported_name,
            visible_phase=visible_phase,
        )
        scope.bindings.setdefault(name, []).append(binding)
        scope.active_bindings[name] = (binding,)
        scope.local_names.add(name)

    def _mark(self, node: AST, scope: _Scope) -> None:
        self.node_scopes[node] = scope
        for child in iter_child_nodes(node):
            self._mark(node=child, scope=scope)

    def _mark_phase(self, node: AST, phase: int) -> None:
        self.node_phases.setdefault(node, phase)
        for child in iter_child_nodes(node):
            self._mark_phase(node=child, phase=phase)

    def _visit(self, node: AST, scope: _Scope) -> None:
        self.node_scopes[node] = scope
        if isinstance(node, Name):
            self.node_bindings[node] = scope.active_bindings.get(node.id, ())
        self._visitor_for(node=node)(node=node, scope=scope)

    def _visitor_for(self, node: AST) -> Callable[..., None]:
        if isinstance(node, Import):
            return self._visit_import
        if isinstance(node, ImportFrom):
            return self._visit_importfrom
        if isinstance(node, Assign):
            return self._visit_assign
        if isinstance(node, AnnAssign):
            return self._visit_annassign
        if isinstance(node, AugAssign):
            return self._visit_augassign
        if isinstance(node, Name):
            return self._visit_name
        if isinstance(node, Global):
            return self._visit_global
        if isinstance(node, Nonlocal):
            return self._visit_nonlocal
        if isinstance(node, NamedExpr):
            return self._visit_namedexpr
        if isinstance(node, Lambda):
            return self._visit_lambda
        if isinstance(node, (ListComp, SetComp, GeneratorExp, DictComp)):
            return self._visit_comprehension
        if isinstance(node, FunctionDef):
            return self._visit_functiondef
        if isinstance(node, AsyncFunctionDef):
            return self._visit_asyncfunctiondef
        if isinstance(node, ClassDef):
            return self._visit_classdef
        if isinstance(node, If):
            return self._visit_if
        if isinstance(node, (For, AsyncFor)):
            return self._visit_for
        if isinstance(node, While):
            return self._visit_while
        if isinstance(node, Break):
            return self._visit_break
        if isinstance(node, Continue):
            return self._visit_continue
        if isinstance(node, (Try, TryStar)):
            return self._visit_try
        if isinstance(node, Match):
            return self._visit_match
        return self._visit_children

    def _visit_children(self, node: AST, scope: _Scope) -> None:
        for child in iter_child_nodes(node):
            self._visit(node=child, scope=scope)

    @staticmethod
    def _state(scope: _Scope) -> dict[str, tuple[_Binding, ...]]:
        return dict(scope.active_bindings)

    @staticmethod
    def _merge_states(states: list[dict[str, tuple[_Binding, ...]]]) -> dict[str, tuple[_Binding, ...]]:
        merged: dict[str, tuple[_Binding, ...]] = {}
        for name in {name for state in states for name in state}:
            bindings: list[_Binding] = []
            for state in states:
                for binding in state.get(name, ()):
                    if all(existing is not binding for existing in bindings):
                        bindings.append(binding)
            if bindings:
                merged[name] = tuple(bindings)
        return merged

    def _visit_branches(
        self,
        branches: list[list[stmt]],
        scope: _Scope,
        *,
        include_incoming: bool,
    ) -> None:
        tracked_scopes = tuple(self.scopes)
        incoming = [self._state(scope=item) for item in tracked_scopes]
        outputs: list[list[dict[str, tuple[_Binding, ...]]]] = []
        if include_incoming:
            outputs.append(incoming)
        for branch in branches:
            for tracked_scope, state in zip(tracked_scopes, incoming, strict=True):
                tracked_scope.active_bindings = dict(state)
            for statement in branch:
                self._visit(node=statement, scope=scope)
            if self._statements_fall_through(statements=branch):
                outputs.append([self._state(scope=item) for item in tracked_scopes])
        self._restore_states(
            tracked_scopes=tracked_scopes,
            states=self._merged_scope_states(outputs=outputs) if outputs else incoming,
        )

    def _visit_if(self, node: If, scope: _Scope) -> None:
        self._visit(node=node.test, scope=scope)
        branches = [node.body]
        if node.orelse:
            branches.append(node.orelse)
        self._visit_branches(branches=branches, scope=scope, include_incoming=not node.orelse)

    def _visit_for(self, node: For | AsyncFor, scope: _Scope) -> None:
        self._visit(node=node.iter, scope=scope)
        self._visit_loop(node=node, scope=scope)

    def _visit_while(self, node: While, scope: _Scope) -> None:
        self._visit(node=node.test, scope=scope)
        self._visit_loop(node=node, scope=scope)

    def _visit_loop(self, node: For | AsyncFor | While, scope: _Scope) -> None:
        tracked_scopes = tuple(self.scopes)
        incoming = [self._state(scope=item) for item in tracked_scopes]
        loop_exits = _LoopExits(tracked_scopes=tracked_scopes)
        self._loop_exits.append(loop_exits)
        if isinstance(node, (For, AsyncFor)):
            self._bind_targets(target=node.target, scope=scope, value=None, node=node.target)
            self._mark(node=node.target, scope=scope)
        for statement in node.body:
            self._visit(node=statement, scope=scope)
        self._loop_exits.pop()

        normal_outputs = [incoming, *loop_exits.continue_outputs]
        if self._statements_fall_through(statements=node.body):
            normal_outputs.append([self._state(scope=item) for item in tracked_scopes])
        self._restore_states(
            tracked_scopes=tracked_scopes,
            states=self._merged_scope_states(outputs=normal_outputs),
        )

        for statement in node.orelse:
            self._visit(node=statement, scope=scope)
        continuing_outputs = list(loop_exits.break_outputs)
        if self._statements_fall_through(statements=node.orelse):
            continuing_outputs.append([self._state(scope=item) for item in tracked_scopes])
        self._restore_states(
            tracked_scopes=tracked_scopes,
            states=self._merged_scope_states(outputs=continuing_outputs) if continuing_outputs else incoming,
        )

    def _visit_break(self, node: Break, scope: _Scope) -> None:
        if self._loop_exits:
            loop_exits = self._loop_exits[-1]
            loop_exits.break_outputs.append([self._state(scope=item) for item in loop_exits.tracked_scopes])

    def _visit_continue(self, node: Continue, scope: _Scope) -> None:
        if self._loop_exits:
            loop_exits = self._loop_exits[-1]
            loop_exits.continue_outputs.append([self._state(scope=item) for item in loop_exits.tracked_scopes])

    @staticmethod
    def _statements_fall_through(statements: list[stmt]) -> bool:
        return all(_ScopeBuilder._statement_falls_through(statement=statement) for statement in statements)

    @staticmethod
    def _statement_falls_through(statement: stmt) -> bool:
        if isinstance(statement, (Break, Continue, Raise, Return)):
            return False
        if isinstance(statement, If) and statement.orelse:
            return any(
                _ScopeBuilder._statements_fall_through(statements=branch)
                for branch in (statement.body, statement.orelse)
            )
        return True

    def _restore_states(
        self,
        tracked_scopes: tuple[_Scope, ...],
        states: list[dict[str, tuple[_Binding, ...]]],
    ) -> None:
        for tracked_scope, state in zip(tracked_scopes, states, strict=True):
            tracked_scope.active_bindings = dict(state)

    def _merged_scope_states(
        self,
        outputs: list[list[dict[str, tuple[_Binding, ...]]]],
    ) -> list[dict[str, tuple[_Binding, ...]]]:
        return [self._merge_states(states=[output[index] for output in outputs]) for index in range(len(outputs[0]))]

    def _visit_try(self, node: Try | TryStar, scope: _Scope) -> None:
        tracked_scopes = tuple(self.scopes)
        incoming = [self._state(scope=item) for item in tracked_scopes]
        exceptional_outputs = [incoming]
        normal_falls_through = True
        for statement in node.body:
            self._visit(node=statement, scope=scope)
            exceptional_outputs.append([self._state(scope=item) for item in tracked_scopes])
            if not self._statement_falls_through(statement=statement):
                normal_falls_through = False
                break

        continuing_outputs: list[list[dict[str, tuple[_Binding, ...]]]] = []
        if normal_falls_through:
            for statement in node.orelse:
                self._visit(node=statement, scope=scope)
            continuing_outputs.append([self._state(scope=item) for item in tracked_scopes])

        handler_entry = self._merged_scope_states(outputs=exceptional_outputs)
        abrupt_outputs: list[list[dict[str, tuple[_Binding, ...]]]] = []
        for handler in node.handlers:
            self._restore_states(tracked_scopes=tracked_scopes, states=handler_entry)
            self.node_scopes[handler] = scope
            if handler.type is not None:
                self._visit(node=handler.type, scope=scope)
            if handler.name is not None:
                self._bind(scope=scope, name=handler.name, value=None, node=handler)
            handler_falls_through = True
            for statement in handler.body:
                self._visit(node=statement, scope=scope)
                if not self._statement_falls_through(statement=statement):
                    handler_falls_through = False
                    break
            if handler.name is not None:
                binding_scope = self._binding_scope(scope=scope, name=handler.name)
                binding_scope.active_bindings.pop(handler.name, None)
            handler_output = [self._state(scope=item) for item in tracked_scopes]
            if handler_falls_through:
                continuing_outputs.append(handler_output)
            else:
                abrupt_outputs.append(handler_output)

        if node.finalbody:
            final_inputs = [*continuing_outputs, *abrupt_outputs]
            if not node.handlers:
                final_inputs.extend(exceptional_outputs)
            self._restore_states(
                tracked_scopes=tracked_scopes,
                states=self._merged_scope_states(outputs=final_inputs),
            )
            for statement in node.finalbody:
                self._visit(node=statement, scope=scope)
            final_node_bindings = {
                child: self.node_bindings[child]
                for statement in node.finalbody
                for child in walk(statement)
                if child in self.node_bindings
            }
            if continuing_outputs:
                self._restore_states(
                    tracked_scopes=tracked_scopes,
                    states=self._merged_scope_states(outputs=continuing_outputs),
                )
                for statement in node.finalbody:
                    self._visit(node=statement, scope=scope)
                self.node_bindings.update(final_node_bindings)
        elif continuing_outputs:
            self._restore_states(
                tracked_scopes=tracked_scopes,
                states=self._merged_scope_states(outputs=continuing_outputs),
            )
        else:
            self._restore_states(tracked_scopes=tracked_scopes, states=incoming)

    def _visit_match(self, node: Match, scope: _Scope) -> None:
        self._visit(node=node.subject, scope=scope)
        for case in node.cases:
            self._visit(node=case.pattern, scope=scope)
            if case.guard is not None:
                self._visit(node=case.guard, scope=scope)
        self._visit_branches(
            branches=[case.body for case in node.cases],
            scope=scope,
            include_incoming=True,
        )

    def _visit_import(self, node: Import, scope: _Scope) -> None:
        for imported in node.names:
            local_name = imported.asname or imported.name.split(".", maxsplit=1)[0]
            imported_name = tuple(imported.name.split(".")) if imported.asname else (local_name,)
            self._bind(scope=scope, name=local_name, value=None, node=node, imported_name=imported_name)
        self._mark(node=node, scope=scope)

    def _visit_importfrom(self, node: ImportFrom, scope: _Scope) -> None:
        imported_prefix = tuple(node.module.split(".")) if node.module else ()
        if node.level > 0:
            relative_prefixes = _relative_import_prefixes(module_name=self.module_name, node=node)
            imported_prefix = relative_prefixes[0 if self.is_package else -1]
        for imported in node.names:
            if imported.name == "*" and imported_prefix == ("pytest",) and node.level == 0:
                for exported_name in ("skip", "mark", "pytestmark"):
                    self._bind(
                        scope=scope,
                        name=exported_name,
                        value=None,
                        node=node,
                        imported_name=("pytest", exported_name),
                    )
            elif imported.name != "*":
                imported_name = (*imported_prefix, imported.name)
                self._bind(
                    scope=scope,
                    name=imported.asname or imported.name,
                    value=None,
                    node=node,
                    imported_name=imported_name,
                )
        self._mark(node=node, scope=scope)

    def _bind_targets(
        self,
        target: AST,
        scope: _Scope,
        value: expr | None,
        node: AST,
        visible_phase: int | None = None,
    ) -> None:
        if isinstance(target, Name):
            self._bind(scope=scope, name=target.id, value=value, node=node, visible_phase=visible_phase)
            return
        if isinstance(target, Starred):
            self._bind_targets(target=target.value, scope=scope, value=None, node=node, visible_phase=visible_phase)
            return
        if isinstance(target, (Tuple, List)):
            values = value.elts if isinstance(value, (Tuple, List)) and len(value.elts) == len(target.elts) else ()
            for index, child in enumerate(target.elts):
                child_value = values[index] if values else None
                self._bind_targets(
                    target=child,
                    scope=scope,
                    value=child_value,
                    node=node,
                    visible_phase=visible_phase,
                )

    def _visit_assign(self, node: Assign, scope: _Scope) -> None:
        self._visit(node=node.value, scope=scope)
        for target in node.targets:
            self._bind_targets(target=target, scope=scope, value=node.value, node=node)
            self._mark(node=target, scope=scope)

    def _visit_annassign(self, node: AnnAssign, scope: _Scope) -> None:
        self._visit(node=node.annotation, scope=scope)
        if node.value is not None:
            self._visit(node=node.value, scope=scope)
        self._bind_targets(target=node.target, scope=scope, value=node.value, node=node)
        self._mark(node=node.target, scope=scope)

    def _visit_augassign(self, node: AugAssign, scope: _Scope) -> None:
        self._bind_targets(target=node.target, scope=scope, value=None, node=node)
        self._visit(node=node.value, scope=scope)
        self._mark(node=node.target, scope=scope)

    def _visit_name(self, node: Name, scope: _Scope) -> None:
        if isinstance(node.ctx, Store):
            self._bind(scope=scope, name=node.id, value=None, node=node)

    def _visit_global(self, node: Global, scope: _Scope) -> None:
        scope.global_names.update(node.names)
        self._mark(node=node, scope=scope)

    def _visit_nonlocal(self, node: Nonlocal, scope: _Scope) -> None:
        scope.nonlocal_names.update(node.names)
        self._mark(node=node, scope=scope)

    def _visit_namedexpr(self, node: NamedExpr, scope: _Scope) -> None:
        binding_scope = scope
        while binding_scope.kind == "comprehension" and binding_scope.parent is not None:
            binding_scope = binding_scope.parent
        self._visit(node=node.value, scope=scope)
        self._bind_targets(target=node.target, scope=binding_scope, value=node.value, node=node)
        self._mark(node=node.target, scope=scope)

    def _visit_header(self, node: FunctionDef | AsyncFunctionDef, scope: _Scope) -> None:
        arguments = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
        if node.args.vararg is not None:
            arguments.append(node.args.vararg)
        if node.args.kwarg is not None:
            arguments.append(node.args.kwarg)
        expressions = [
            *node.decorator_list,
            *node.args.defaults,
            *[value for value in node.args.kw_defaults if value],
            *[argument.annotation for argument in arguments if argument.annotation is not None],
        ]
        if node.returns is not None:
            expressions.append(node.returns)
        for expression in expressions:
            self._visit(node=expression, scope=scope)

    def _visit_arguments(self, node: arguments, scope: _Scope) -> None:
        arguments = [*node.posonlyargs, *node.args, *node.kwonlyargs]
        if node.vararg is not None:
            arguments.append(node.vararg)
        if node.kwarg is not None:
            arguments.append(node.kwarg)
        for argument in arguments:
            self._bind(scope=scope, name=argument.arg, value=None, node=argument)
            self.node_scopes[argument] = scope

    def _visit_lambda(self, node: Lambda, scope: _Scope) -> None:
        for default in [*node.args.defaults, *[value for value in node.args.kw_defaults if value]]:
            self._visit(node=default, scope=scope)
        lambda_scope = _Scope(parent=self._function_parent(scope=scope), kind="function")
        self.scopes.append(lambda_scope)
        self._visit_arguments(node=node.args, scope=lambda_scope)
        self._visit(node=node.body, scope=lambda_scope)

    def _visit_comprehension(
        self,
        node: ListComp | SetComp | GeneratorExp | DictComp,
        scope: _Scope,
    ) -> None:
        comprehension_scope = _Scope(parent=self._function_parent(scope=scope), kind="comprehension")
        self.scopes.append(comprehension_scope)
        for index, generator in enumerate(node.generators):
            phase = index + 1
            self._visit(node=generator.iter, scope=scope if index == 0 else comprehension_scope)
            self._mark_phase(node=generator.iter, phase=index)
            self._bind_targets(
                target=generator.target,
                scope=comprehension_scope,
                value=None,
                node=generator.target,
                visible_phase=phase,
            )
            self._mark(node=generator.target, scope=comprehension_scope)
            for condition in generator.ifs:
                self._visit(node=condition, scope=comprehension_scope)
                self._mark_phase(node=condition, phase=phase)
        expressions = (node.key, node.value) if isinstance(node, DictComp) else (node.elt,)
        for expression in expressions:
            self._visit(node=expression, scope=comprehension_scope)
            self._mark_phase(node=expression, phase=len(node.generators))

    def _visit_functiondef(self, node: FunctionDef, scope: _Scope) -> None:
        self._visit_function_body(node=node, scope=scope)

    def _visit_asyncfunctiondef(self, node: AsyncFunctionDef, scope: _Scope) -> None:
        self._visit_function_body(node=node, scope=scope)

    def _function_parent(self, scope: _Scope) -> _Scope:
        while scope.kind == "class" and scope.parent is not None:
            scope = scope.parent
        return scope

    def _visit_function_body(
        self,
        node: FunctionDef | AsyncFunctionDef,
        scope: _Scope,
    ) -> None:
        self._bind(scope=scope, name=node.name, value=None, node=node)
        self._visit_header(node=node, scope=scope)
        function_scope = _Scope(parent=self._function_parent(scope=scope), kind="function")
        self.scopes.append(function_scope)
        for statement in _scope_statements(node.body):
            if isinstance(statement, Global):
                function_scope.global_names.update(statement.names)
            elif isinstance(statement, Nonlocal):
                function_scope.nonlocal_names.update(statement.names)
        self._visit_arguments(node=node.args, scope=function_scope)
        tracked_scopes = tuple(self.scopes[:-1])
        incoming = [self._state(scope=item) for item in tracked_scopes]
        for statement in node.body:
            self._visit(node=statement, scope=function_scope)
        body_output = [self._state(scope=item) for item in tracked_scopes]
        for index, tracked_scope in enumerate(tracked_scopes):
            tracked_scope.active_bindings = self._merge_states(states=[incoming[index], body_output[index]])

    def _visit_classdef(self, node: ClassDef, scope: _Scope) -> None:
        self._bind(scope=scope, name=node.name, value=None, node=node, imported_name=("<local>", node.name))
        for expression in [*node.decorator_list, *node.bases, *node.keywords]:
            self._visit(node=expression, scope=scope)
        class_scope = _Scope(parent=scope, kind="class")
        self.scopes.append(class_scope)
        for statement in node.body:
            self._visit(node=statement, scope=class_scope)


def _scopes(
    tree: Module,
    module_name: tuple[str, ...] = (),
    is_package: bool = False,
) -> _Scopes:
    return _ScopeBuilder(tree=tree, module_name=module_name, is_package=is_package).build()


def _module_name(file_path: Path) -> tuple[str, ...]:
    parts = file_path.with_suffix("").parts
    return parts[:-1] if parts and parts[-1] == "__init__" else parts


def _git_output(command: list[str]) -> str:
    success, stdout, stderr = run_command(
        command=command,
        check=False,
        verify_stderr=False,
    )
    if not success:
        raise RuntimeError(f"Git command failed: {' '.join(command)}: {stderr}")
    return stdout


_GIT_SIMPLE_ESCAPES = {
    "a": 0x07,
    "b": 0x08,
    "f": 0x0C,
    "n": 0x0A,
    "r": 0x0D,
    "t": 0x09,
    "v": 0x0B,
    "\\": 0x5C,
    '"': 0x22,
}


def _git_unquote(quoted: str) -> str:
    r"""Decode a Git C-quoted path to its raw path.

    Git quotes paths that contain non-ASCII bytes or special characters by
    wrapping them in double quotes and encoding bytes as C escapes such as
    ``\303\251``. ``shlex`` does not decode these escapes, so quoted paths
    must be decoded explicitly. Invalid UTF-8 byte sequences are preserved
    with ``surrogateescape`` so distinct paths never collide on a replacement
    character.

    Args:
        quoted: A Git-quoted path including its surrounding double quotes, or
            an already unquoted path.

    Returns:
        The decoded path.
    """
    if not (quoted.startswith('"') and quoted.endswith('"')):
        return quoted
    body = quoted[1:-1]
    raw = bytearray()
    index = 0
    while index < len(body):
        char = body[index]
        index += 1
        if char != "\\":
            raw.extend(char.encode(encoding="utf-8", errors="surrogateescape"))
            continue
        if index >= len(body):
            raw.append(0x5C)
            break
        escape = body[index]
        index += 1
        if escape in _GIT_SIMPLE_ESCAPES:
            raw.append(_GIT_SIMPLE_ESCAPES[escape])
            continue
        octal_digits = ""
        if escape in string.octdigits:
            octal_digits = escape
            while index < len(body) and len(octal_digits) < 3 and body[index] in string.octdigits:
                octal_digits += body[index]
                index += 1
        if octal_digits:
            raw.append(int(octal_digits, base=8))
        else:
            raw.extend(("\\" + escape).encode(encoding="utf-8", errors="surrogateescape"))
    return raw.decode(encoding="utf-8", errors="surrogateescape")


def _git_quoted_token(text: str) -> tuple[str, str] | None:
    """Split one C-quoted token from the start of a Git diff header.

    Args:
        text: Header remainder starting at the opening double quote.

    Returns:
        The quoted token including quotes and the remaining text, or ``None``
        when no closing quote is found.
    """
    index = 1
    while index < len(text):
        if text[index] == "\\":
            index += 2
            continue
        if text[index] == '"':
            token_end = index + 1
            return text[:token_end], text[token_end:]
        index += 1
    return None


def _git_header_token(text: str) -> tuple[str, str] | None:
    """Split one path token (quoted or bare) from a diff-header remainder.

    Git quotes each header path independently, so a valid header can mix a
    quoted and a bare path. A bare token ends at the first space, which Git
    guarantees because paths containing spaces are always quoted in
    ``diff --git`` headers.

    Args:
        text: Header remainder starting at the token.

    Returns:
        The token (quotes included when quoted) and the remaining text after
        it, or ``None`` for an unterminated quoted token.
    """
    if text.startswith('"'):
        return _git_quoted_token(text=text)
    space_index = text.find(" ")
    if space_index == -1:
        return text, ""
    separator = space_index + 1
    return text[:space_index], text[separator:]


def _diff_header_path(diff_line: str) -> Path | None:
    prefix = "diff --git "
    if not diff_line.startswith(prefix):
        return None
    prefix_length = len(prefix)
    rest = diff_line[prefix_length:]
    first = _git_header_token(text=rest)
    if first is None:
        return None
    first_token, first_remainder = first
    if first_token.startswith('"'):
        if not first_remainder.startswith(" "):
            return None
        second_text = first_remainder[1:]
    else:
        second_text = first_remainder
    second = _git_header_token(text=second_text)
    if second is None:
        return None
    second_token, trailing = second
    if trailing:
        return None
    right = _git_unquote(quoted=second_token)
    if not right.startswith("b/"):
        return None
    return Path(right[2:])


def _process_diff_control_line(
    diff_line: str,
    state: _DiffState,
    path: Path | None,
    added_lines: dict[Path, set[int]],
) -> bool:
    if diff_line.startswith("diff --git "):
        state.current_path = path or _diff_header_path(diff_line=diff_line)
        state.current_line = None
        state.in_hunk = False
        if state.current_path is not None:
            # A resolvable header maps the file even when the diff carries no
            # hunks (an exact rename), so the file is not treated as unmappable.
            added_lines.setdefault(state.current_path, set())
        return True
    if not state.in_hunk and diff_line.startswith("+++ "):
        if path is None and state.current_path is None and diff_line.startswith("+++ b/"):
            state.current_path = Path(diff_line[6:])
        if state.current_path is not None:
            added_lines.setdefault(state.current_path, set())
        state.current_line = None
        return True
    hunk = _HUNK_HEADER.match(string=diff_line)
    if hunk:
        state.current_line = int(hunk.group(1))
        state.in_hunk = True
        return True
    return False


def _process_diff_line(
    diff_line: str,
    state: _DiffState,
    path: Path | None,
    added_lines: dict[Path, set[int]],
) -> None:
    if _process_diff_control_line(diff_line=diff_line, state=state, path=path, added_lines=added_lines):
        return
    current_path = state.current_path
    current_line = state.current_line
    if current_path is None or current_line is None or diff_line.startswith("\\"):
        return
    if diff_line.startswith("+"):
        added_lines[current_path].add(current_line)
    if not diff_line.startswith("-"):
        state.current_line = current_line + 1


def _added_lines_by_path(
    diff: str,
    path: Path | None = None,
) -> dict[Path, frozenset[int]]:
    added_lines: dict[Path, set[int]] = {} if path is None else {path: set()}
    state = _DiffState(current_path=path)
    for diff_line in diff.split("\n"):
        _process_diff_line(
            diff_line=diff_line,
            state=state,
            path=path,
            added_lines=added_lines,
        )
    return {file_path: frozenset(lines) for file_path, lines in added_lines.items()}


def _parse_staged_entries(status_output: str) -> tuple[_StagedEntry, ...]:
    fields = [field for field in status_output.split("\0") if field]
    entries: list[_StagedEntry] = []
    index = 0
    while index < len(fields):
        status = fields[index][0]
        index += 1
        first_path = Path(fields[index])
        index += 1
        if status in "RC":
            path = Path(fields[index])
            index += 1
            entries.append(
                _StagedEntry(
                    status=status,
                    path=path,
                    head_path=first_path if status == "R" else None,
                    source_path=first_path,
                )
            )
        else:
            entries.append(
                _StagedEntry(status=status, path=first_path, head_path=None if status == "A" else first_path)
            )
    return tuple(entries)


def _parse_staged_status(status_output: str) -> frozenset[Path]:
    """Return staged paths whose index state is a deletion.

    Renamed-away head paths count as deletions; all other paths (including
    copy and rename sources) remain available to callers via the parsed
    entries.

    Args:
        status_output: NUL-separated ``git diff --cached --name-status -z`` output.

    Returns:
        Paths deleted from the index, including renamed-away head paths.
    """
    entries = _parse_staged_entries(status_output=status_output)
    deleted_paths = {entry.path for entry in entries if entry.status == "D"}
    deleted_paths.update(entry.head_path for entry in entries if entry.status == "R" and entry.head_path is not None)
    return frozenset(deleted_paths)


def _parse_index_stage_records(output: str) -> list[tuple[str, Path]]:
    """Parse ``git ls-files --stage -z`` output into index mode and path pairs."""
    records: list[tuple[str, Path]] = []
    for record in output.split("\0"):
        metadata, separator, raw_path = record.partition("\t")
        if separator:
            records.append((metadata.split(" ", maxsplit=1)[0], Path(raw_path)))
    return records


def _symlinked_staged_paths(staged_paths: Collection[Path]) -> frozenset[Path]:
    """Return staged paths whose index entry is a symbolic link.

    A staged symlink's ``git show`` blob is only the link target text, not
    the Python source that executes after checkout, so symlinked Python must
    be rejected rather than checked.

    Args:
        staged_paths: Paths staged in the current index snapshot.

    Returns:
        The subset of staged paths stored with Git's symlink mode ``120000``.
    """
    output = _git_output(command=["git", "ls-files", "--stage", "-z", "--"])
    symlinked: set[Path] = set()
    for mode, path in _parse_index_stage_records(output=output):
        if mode == "120000" and path in staged_paths:
            symlinked.add(path)
    return frozenset(symlinked)


def _staged_changes() -> StagedChanges:
    status_output = _git_output(command=["git", "diff", "--cached", "--find-renames", "--name-status", "-z", "--"])
    entries = _parse_staged_entries(status_output=status_output)
    deleted_paths = _parse_staged_status(status_output=status_output)
    changed_paths = frozenset(entry.path for entry in entries)
    renamed_paths = frozenset(entry.path for entry in entries if entry.status == "R")
    renamed_away_paths = frozenset(
        entry.head_path for entry in entries if entry.status == "R" and entry.head_path is not None
    )
    active_entries = [entry for entry in entries if entry.status != "D"]
    if not active_entries:
        return StagedChanges(
            changed_paths=changed_paths,
            deleted_paths=deleted_paths,
            renamed_paths=renamed_paths,
            renamed_away_paths=renamed_away_paths,
            symlinked_paths=frozenset(),
            added_lines={},
            sources={},
            head_sources={},
            copied_paths=frozenset(),
        )

    symlinked_paths = _symlinked_staged_paths(staged_paths={entry.path for entry in active_entries})
    python_entries = [entry for entry in active_entries if entry.path.suffix == ".py"]
    staged_diff = _git_output(command=["git", "diff", *_STAGED_DIFF_OPTIONS, "--"]) if python_entries else ""
    added_lines = _added_lines_by_path(diff=staged_diff)
    known_paths = {entry.path for entry in entries}
    known_paths.update(entry.source_path for entry in entries if entry.source_path is not None)
    # A diff-header path that matches no staged status entry means the header
    # could not be decoded to a staged path; drop the mapping so the file is
    # treated as unmappable and checked line by line (fail closed).
    for unknown_path in set(added_lines) - known_paths:
        del added_lines[unknown_path]
    source_paths = {
        entry.path
        for entry in active_entries
        if (entry.path.suffix == ".py" or entry.path == EXCEPTIONS_PATH) and entry.path not in symlinked_paths
    }
    sources = {path: _git_output(command=["git", "show", f":0:{path}"]) for path in source_paths}
    copied_paths = frozenset(entry.path for entry in active_entries if entry.status == "C")
    for copied_path in copied_paths & sources.keys():
        added_lines[copied_path] = frozenset(range(1, len(sources[copied_path].split("\n")) + 1))
    head_sources = {
        entry.path: _git_output(command=["git", "show", f"HEAD:{entry.head_path}"])
        for entry in active_entries
        if entry.path in source_paths and entry.head_path is not None
    }
    return StagedChanges(
        changed_paths=changed_paths,
        deleted_paths=deleted_paths,
        renamed_paths=renamed_paths,
        renamed_away_paths=renamed_away_paths,
        symlinked_paths=symlinked_paths,
        added_lines=added_lines,
        sources=sources,
        head_sources=head_sources,
        copied_paths=copied_paths,
    )


def _index_source_reader() -> _IndexSourceReader:
    tracked = _git_output(command=["git", "ls-files", "--stage", "-z", "--", "libs", "tests", "utilities"])
    paths: dict[tuple[str, ...], Path] = {}
    for mode, path in _parse_index_stage_records(output=tracked):
        if mode == "120000":
            # A tracked symlink stores only its link-target text; skip it so
            # local-module resolution fails closed instead of parsing the
            # target path string as Python.
            continue
        if path.suffix != ".py":
            continue
        module_name = path.with_suffix("").parts
        if module_name[-1] == "__init__":
            module_name = module_name[:-1]
        paths[module_name] = path
    return _IndexSourceReader(paths=paths)


def check_site_path(file_path: Path) -> PolicyViolation | None:
    """Reject changes to the generated documentation site.

    Args:
        file_path: Repository-relative path selected by pre-commit.

    Returns:
        A violation when the path is under ``docs/site/``; otherwise ``None``.
    """
    if file_path.parts[:2] == ("docs", "site"):
        return PolicyViolation(
            file_path=file_path,
            line_number=None,
            message="docs/site/ is generated and must not be modified",
        )
    return None


def check_top_level_test_path(file_path: Path) -> PolicyViolation | None:
    """Reject test modules placed directly in the top-level tests directory.

    Args:
        file_path: Repository-relative path selected by pre-commit.

    Returns:
        A violation for a top-level pytest test module; otherwise ``None``.
    """
    is_top_level_test = (
        len(file_path.parts) == 2
        and file_path.parts[0] == "tests"
        and file_path.suffix == ".py"
        and (file_path.name.startswith("test_") or file_path.name.endswith("_test.py"))
    )
    if is_top_level_test:
        return PolicyViolation(
            file_path=file_path,
            line_number=None,
            message="test files must be placed in a feature subdirectory under tests/",
        )
    return None


_DYNAMIC_CLIENT_NAMES = {
    ("kubernetes", "dynamic", "DynamicClient"),
    ("kubernetes", "dynamic", "client", "DynamicClient"),
}
_FORBIDDEN_SKIP_MARKERS = (("pytest", "mark", "skip"), ("pytest", "mark", "skipif"))


def _root_name(node: AST) -> Name | None:
    while isinstance(node, Attribute):
        node = node.value
    return node if isinstance(node, Name) else None


def _bindings_for_name(name: str, reference: AST, scopes: _Scopes) -> tuple[_Binding, ...]:
    reference_scope = scopes.node_scopes.get(reference, scopes.root)
    current_scope: _Scope | None = reference_scope
    root_name = _root_name(node=reference)
    reference_phase = scopes.node_phases.get(reference)
    deferred = reference_scope.kind in {"comprehension", "function"}
    first_scope = True
    while current_scope is not None:
        if first_scope and root_name is not None:
            bindings = scopes.node_bindings.get(root_name, ())
        elif deferred:
            bindings = current_scope.active_bindings.get(name, ()) or tuple(current_scope.bindings.get(name, ()))
        else:
            bindings = ()
        if reference_phase is not None:
            bindings = tuple(
                binding
                for binding in bindings
                if binding.visible_phase is None or binding.visible_phase <= reference_phase
            )
        if bindings:
            return bindings
        if current_scope.kind == "function" and name in current_scope.local_names:
            return current_scope.active_bindings.get(name, ()) or (
                _Binding(value=None, node=reference, imported_name=()),
            )
        current_scope = current_scope.parent
        first_scope = False
    return ()


def _resolved_names(
    node: AST,
    scopes: _Scopes,
    resolving: frozenset[AST] = frozenset(),
) -> frozenset[tuple[str, ...]]:
    if isinstance(node, NamedExpr):
        node = node.value
    if isinstance(node, IfExp):
        return _resolved_names(node=node.body, scopes=scopes, resolving=resolving) | _resolved_names(
            node=node.orelse,
            scopes=scopes,
            resolving=resolving,
        )
    name = dotted_name(node=node)
    if name is None:
        return frozenset()
    root_name, *suffix = name
    bindings = _bindings_for_name(name=root_name, reference=node, scopes=scopes)
    if not bindings:
        return frozenset({(root_name, *suffix)})
    resolved: set[tuple[str, ...]] = set()
    for binding in bindings:
        if binding.node in resolving:
            continue
        if binding.imported_name is not None:
            resolved.add((*binding.imported_name, *suffix))
        elif binding.value is not None:
            resolved.update(
                (*binding_name, *suffix)
                for binding_name in _resolved_names(
                    node=binding.value,
                    scopes=scopes,
                    resolving=resolving | {binding.node},
                )
            )
    return frozenset(resolved)


def _is_dynamic_client_call(node: Call, scopes: _Scopes) -> bool:
    return bool(_resolved_names(node=node.func, scopes=scopes) & ({("DynamicClient",)} | _DYNAMIC_CLIENT_NAMES))


def _is_pytest_skip_call(node: Call, scopes: _Scopes) -> bool:
    return ("pytest", "skip") in _resolved_names(node=node.func, scopes=scopes)


def _is_forbidden_skip_decorator(
    node: expr,
    scopes: _Scopes,
    resolving: frozenset[AST] = frozenset(),
) -> bool:
    marker = node.func if isinstance(node, Call) else node
    if bool(_resolved_names(node=marker, scopes=scopes) & set(_FORBIDDEN_SKIP_MARKERS)):
        return True
    # A decorator name whose module-scope value embeds a forbidden marker (for
    # example ``value = wrap(pytest.mark.skip)``) is rejected like a pytestmark
    # alias, so wrapping a marker in a call cannot smuggle it past the check.
    return _is_forbidden_bound_name(node=marker, scopes=scopes, resolving=resolving)


def _pytestmark_value_children(node: expr) -> tuple[expr, ...]:
    if isinstance(node, (ListComp, SetComp, GeneratorExp, DictComp)):
        children = [node.key, node.value] if isinstance(node, DictComp) else [node.elt]
        children.extend(generator.iter for generator in node.generators)
        children.extend(condition for generator in node.generators for condition in generator.ifs)
        return tuple(children)
    return tuple(child for child in iter_child_nodes(node) if isinstance(child, expr))


def _is_forbidden_bound_name(
    node: expr,
    scopes: _Scopes,
    resolving: frozenset[AST],
) -> bool:
    if not isinstance(node, Name):
        return False
    bindings = _bindings_for_name(name=node.id, reference=node, scopes=scopes)
    return any(
        binding.node not in resolving
        and (
            binding.imported_name in _FORBIDDEN_SKIP_MARKERS
            or (
                binding.value is not None
                and _is_forbidden_pytestmark_value(
                    node=binding.value,
                    scopes=scopes,
                    resolving=resolving | {binding.node},
                )
            )
        )
        for binding in bindings
    )


def _is_forbidden_pytestmark_value(
    node: expr,
    scopes: _Scopes,
    resolving: frozenset[AST] = frozenset(),
) -> bool:
    if _is_forbidden_skip_decorator(node=node, scopes=scopes, resolving=resolving):
        return True
    return any(
        _is_forbidden_pytestmark_value(node=child, scopes=scopes, resolving=resolving)
        for child in _pytestmark_value_children(node=node)
    )


def _name_intersects_added_lines(
    node: Name,
    added_lines: Collection[int],
    scopes: _Scopes,
    resolving: frozenset[AST],
) -> bool:
    return any(
        binding.node not in resolving
        and (
            _node_intersects_added_lines(node=binding.node, added_lines=added_lines)
            or (
                binding.value is not None
                and _value_intersects_added_lines(
                    node=binding.value,
                    added_lines=added_lines,
                    scopes=scopes,
                    resolving=resolving | {binding.node},
                )
            )
        )
        for binding in _bindings_for_name(name=node.id, reference=node, scopes=scopes)
    )


def _value_children(node: AST) -> tuple[AST, ...]:
    return tuple(iter_child_nodes(node))


def _value_intersects_added_lines(
    node: AST,
    added_lines: Collection[int] | None,
    scopes: _Scopes,
    resolving: frozenset[AST] = frozenset(),
) -> bool:
    if added_lines is None:
        return True
    if isinstance(node, Name) and _name_intersects_added_lines(
        node=node, added_lines=added_lines, scopes=scopes, resolving=resolving
    ):
        return True
    return any(
        _value_intersects_added_lines(node=child, added_lines=added_lines, scopes=scopes, resolving=resolving)
        for child in _value_children(node=node)
    )


def _pytestmark_value(node: stmt) -> expr | None:
    if isinstance(node, Assign):
        is_pytestmark = any(isinstance(target, Name) and target.id == "pytestmark" for target in node.targets)
        return node.value if is_pytestmark else None
    if isinstance(node, AnnAssign) and isinstance(node.target, Name) and node.target.id == "pytestmark":
        return node.value
    if isinstance(node, AugAssign) and isinstance(node.target, Name) and node.target.id == "pytestmark":
        return node.value
    return None


def _node_intersects_added_lines(
    node: AST,
    added_lines: Collection[int] | None,
) -> bool:
    if added_lines is None:
        return True
    start_line = getattr(node, "lineno", None)
    end_line = getattr(node, "end_lineno", start_line)
    return (
        start_line is not None and end_line is not None and any(start_line <= line <= end_line for line in added_lines)
    )


def _node_or_dependency_intersects_added_lines(
    node: AST,
    dependency: AST,
    added_lines: Collection[int] | None,
    scopes: _Scopes,
) -> bool:
    return _node_intersects_added_lines(node=node, added_lines=added_lines) or _value_intersects_added_lines(
        node=dependency, added_lines=added_lines, scopes=scopes
    )


def _pytestmark_is_added(
    node: stmt,
    value: expr,
    added_lines: Collection[int] | None,
    scopes: _Scopes,
) -> bool:
    return _node_or_dependency_intersects_added_lines(
        node=node, dependency=value, added_lines=added_lines, scopes=scopes
    )


def _check_module_pytestmark(
    file_path: Path,
    node: stmt,
    added_lines: Collection[int] | None,
    scopes: _Scopes,
) -> PolicyViolation | None:
    value = _pytestmark_value(node=node)
    if value is None or not _is_forbidden_pytestmark_value(node=value, scopes=scopes):
        return None
    if not _pytestmark_is_added(node=node, value=value, added_lines=added_lines, scopes=scopes):
        return None
    return PolicyViolation(
        file_path=file_path,
        line_number=node.lineno,
        message="module-level pytestmark skip markers are forbidden",
    )


def _call_message(node: Call, scopes: _Scopes) -> str | None:
    if _is_dynamic_client_call(node=node, scopes=scopes):
        return "reuse the DynamicClient passed through the call path instead of constructing one"
    if _is_pytest_skip_call(node=node, scopes=scopes):
        return "pytest.skip() is forbidden"
    return None


def _pytest_param_marker_message(node: Call, scopes: _Scopes) -> str | None:
    if ("pytest", "param") not in _resolved_names(node=node.func, scopes=scopes):
        return None
    marks = next((keyword.value for keyword in node.keywords if keyword.arg == "marks"), None)
    if marks is None or not _is_forbidden_pytestmark_value(node=marks, scopes=scopes):
        return None
    return "pytest.mark.skip and pytest.mark.skipif are forbidden"


def _check_call(
    file_path: Path,
    node: Call,
    added_lines: Collection[int] | None,
    scopes: _Scopes,
) -> PolicyViolation | None:
    message = _call_message(node=node, scopes=scopes)
    dependency: AST = node.func
    if message is None:
        message = _pytest_param_marker_message(node=node, scopes=scopes)
        dependency = node
    if not _node_or_dependency_intersects_added_lines(
        node=node, dependency=dependency, added_lines=added_lines, scopes=scopes
    ):
        return None
    return (
        None
        if message is None
        else PolicyViolation(
            file_path=file_path,
            line_number=node.lineno,
            message=message,
        )
    )


def _check_decorators(
    file_path: Path,
    node: ClassDef | FunctionDef | AsyncFunctionDef,
    added_lines: Collection[int] | None,
    scopes: _Scopes,
) -> list[PolicyViolation]:
    return [
        PolicyViolation(
            file_path=file_path,
            line_number=decorator.lineno,
            message="pytest.mark.skip and pytest.mark.skipif are forbidden",
        )
        for decorator in node.decorator_list
        if _is_forbidden_skip_decorator(node=decorator, scopes=scopes)
        and _node_or_dependency_intersects_added_lines(
            node=decorator, dependency=decorator, added_lines=added_lines, scopes=scopes
        )
    ]


def _check_ast_node(
    file_path: Path,
    node: AST,
    added_lines: Collection[int] | None,
    scopes: _Scopes,
) -> list[PolicyViolation]:
    if isinstance(node, Call):
        violation = _check_call(file_path=file_path, node=node, added_lines=added_lines, scopes=scopes)
        return [] if violation is None else [violation]
    if isinstance(node, (ClassDef, FunctionDef, AsyncFunctionDef)):
        return _check_decorators(file_path=file_path, node=node, added_lines=added_lines, scopes=scopes)
    return []


def _check_module_assignments(
    file_path: Path,
    tree: Module,
    added_lines: Collection[int] | None,
    scopes: _Scopes,
) -> list[PolicyViolation]:
    assignment_types = (Assign, AnnAssign, AugAssign)
    return [
        violation
        for node in walk(tree)
        if isinstance(node, assignment_types) and scopes.node_scopes.get(node) is scopes.root
        if (
            violation := _check_module_pytestmark(
                file_path=file_path,
                node=node,
                added_lines=added_lines,
                scopes=scopes,
            )
        )
        is not None
    ]


def _check_ast_nodes(
    file_path: Path,
    tree: Module,
    added_lines: Collection[int] | None,
    scopes: _Scopes,
) -> list[PolicyViolation]:
    violations: list[PolicyViolation] = []
    for node in walk(tree):
        violations.extend(_check_ast_node(file_path=file_path, node=node, added_lines=added_lines, scopes=scopes))
    return violations


def _check_source_tree(
    file_path: Path,
    source: str,
    tree: Module,
    added_lines: Collection[int] | None,
    head_source: str | None,
    resource_classes: Collection[tuple[str, ...]] | None,
) -> list[PolicyViolation]:
    module_name = _module_name(file_path=file_path)
    is_package = file_path.name == "__init__.py"
    scopes = _scopes(tree=tree, module_name=module_name, is_package=is_package)

    def resolve_name(node: AST) -> frozenset[tuple[str, ...]]:
        return _resolved_names(node=node, scopes=scopes)

    def node_or_dependency_intersects(node: AST, dependency: AST) -> bool:
        return _node_or_dependency_intersects_added_lines(
            node=node,
            dependency=dependency,
            added_lines=added_lines,
            scopes=scopes,
        )

    head_tree = parse(source=head_source, filename=str(file_path)) if head_source is not None else None
    head_scopes = (
        _scopes(tree=head_tree, module_name=module_name, is_package=is_package) if head_tree is not None else None
    )

    def head_resolve_name(node: AST) -> frozenset[tuple[str, ...]]:
        return _resolved_names(node=node, scopes=head_scopes) if head_scopes is not None else frozenset()

    violations = _check_module_assignments(file_path=file_path, tree=tree, added_lines=added_lines, scopes=scopes)
    violations += _check_ast_nodes(file_path=file_path, tree=tree, added_lines=added_lines, scopes=scopes)
    violations += check_resource_clients(
        file_path=file_path,
        source=source,
        added_lines=added_lines,
        resolve_name=resolve_name,
        head_source=head_source,
        head_tree=head_tree,
        head_resolve_name=head_resolve_name if head_tree is not None else None,
        tree=tree,
        known_resources=resource_classes,
        node_or_dependency_added=node_or_dependency_intersects,
    )
    violations += check_test_basics(
        file_path=file_path,
        source=source,
        added_lines=added_lines,
        resolve_name=resolve_name,
        tree=tree,
        node_or_dependency_intersects=node_or_dependency_intersects,
    )
    return sorted(violations, key=lambda violation: (violation.line_number is None, violation.line_number or 0))


def check_python_source(
    file_path: Path,
    source: str,
    added_lines: Collection[int] | None = None,
    *,
    head_source: str | None = None,
    resource_classes: Collection[tuple[str, ...]] | None = None,
) -> list[PolicyViolation]:
    """Check Python source against every source-level policy.

    Covers forbidden skip patterns, relative imports, mechanical
    Python-basics checks, Resource client requirements, and cache-client
    comment requirements. Linter directives are validated separately by
    ``check_linter_directives`` in the staged entry-point flow.

    Args:
        file_path: Path used in violation messages.
        source: Python source to inspect.
        added_lines: If provided, only violations whose AST node or relevant
            name-resolution dependencies intersect these added source lines are
            returned, except deletion-sensitive checks.
        head_source: Source from ``HEAD`` for deletion-sensitive comparisons.
        resource_classes: Resource subclasses discovered for this staged snapshot.

    Returns:
        All policy violations found in the source, optionally limited to added
        lines and relevant changed bindings. Removing a required cache-client
        comment is also detected against ``head_source`` when the call is unchanged.

    Raises:
        SyntaxError: If ``source`` is not valid Python.
    """
    tree = parse(source=source, filename=str(file_path))
    return _check_source_tree(
        file_path=file_path,
        source=source,
        tree=tree,
        added_lines=added_lines,
        head_source=head_source,
        resource_classes=resource_classes,
    )


def _check_python_file(
    file_path: Path,
    added_lines: Collection[int] | None,
    source: str | None,
    head_source: str | None,
    resource_classes: Collection[tuple[str, ...]] | None,
) -> list[PolicyViolation]:
    if file_path.suffix != ".py" or (source is None and not file_path.is_file()):
        return []
    if added_lines is not None and not added_lines and head_source is None:
        return []
    file_source = source if source is not None else file_path.read_text(encoding="utf-8")
    return check_python_source(
        file_path=file_path,
        source=file_source,
        added_lines=added_lines,
        head_source=head_source,
        resource_classes=resource_classes,
    )


def check_file(
    file_path: Path,
    staged: bool = False,
    added_lines: Collection[int] | None = None,
    source: str | None = None,
    *,
    head_source: str | None = None,
    resource_classes: Collection[tuple[str, ...]] | None = None,
) -> list[PolicyViolation]:
    """Run every policy check for one pre-commit file.

    Args:
        file_path: Repository-relative path selected by pre-commit.
        staged: Whether the path is staged in Git.
        added_lines: Added Python source lines to check. ``None`` keeps the
            direct-call behavior of checking the complete source.
        source: Source content to check instead of reading the working tree; staged checks use the Git index content.
        head_source: Source from ``HEAD`` for deletion-sensitive checks.
        resource_classes: Resource subclasses discovered for this staged snapshot.

    Returns:
        All policy violations for the path and, for staged Python files, added source.
    """
    violations: list[PolicyViolation] = []
    if staged:
        top_level_test_violation = check_top_level_test_path(file_path=file_path)
        if top_level_test_violation is not None:
            violations.append(top_level_test_violation)
        site_violation = check_site_path(file_path=file_path)
        if site_violation is not None:
            violations.append(site_violation)
    effective_added_lines = (
        None
        if staged and source is not None and added_lines is not None and not added_lines and head_source is None
        else added_lines
    )
    violations.extend(
        _check_python_file(
            file_path=file_path,
            added_lines=effective_added_lines,
            source=source,
            head_source=head_source,
            resource_classes=resource_classes,
        )
    )
    return violations


_CHECK_FAMILIES = ("path-policy", "linter-directives", "python-source", "test-std", "stp-links")


def _parse_arguments(arguments: Sequence[str] | None) -> tuple[list[str], frozenset[str]]:
    """Split command-line arguments into filenames and selected check families.

    Args:
        arguments: Raw arguments, or ``None`` to use command-line arguments.

    Returns:
        Filenames and the selected check families; without an explicit
        ``--check`` selection every family runs.
    """
    raw_arguments = list(argv[1:]) if arguments is None else list(arguments)
    file_names: list[str] = []
    selected: set[str] = set()
    index = 0
    while index < len(raw_arguments):
        argument = raw_arguments[index]
        if argument == "--check":
            index += 1
            if index >= len(raw_arguments):
                raise SystemExit("check_policy: --check requires a check family name")
            selected.add(raw_arguments[index])
        else:
            file_names.append(argument)
        index += 1
    unknown_families = selected - set(_CHECK_FAMILIES)
    if unknown_families:
        raise SystemExit(f"check_policy: unknown check family: {sorted(unknown_families)}")
    return file_names, frozenset(selected) or frozenset(_CHECK_FAMILIES)


def _resolved_added_lines(staged_changes: StagedChanges, file_path: Path) -> Collection[int] | None:
    """Resolve the added-line filter for a path pre-commit supplied.

    Args:
        staged_changes: Parsed staged state.
        file_path: Path pre-commit supplied.

    Returns:
        Added line numbers, ``None`` to check every line (fail closed), or an
        empty collection when nothing is staged for the path.
    """
    staged_added_lines = staged_changes.added_lines.get(file_path)
    if staged_added_lines is None:
        if file_path in staged_changes.sources:
            # A staged file whose diff could not be mapped (binary content
            # or an undecodable diff header); fail closed and check every line.
            return None
        # Not staged; nothing is being committed for this path.
        return frozenset()
    if (
        file_path in staged_changes.changed_paths
        and staged_changes.sources.get(file_path) is not None
        and not staged_added_lines
        and staged_changes.head_sources.get(file_path) is None
    ):
        return None
    return staged_added_lines


def _path_policy_violations(staged_changes: StagedChanges) -> list[PolicyViolation]:
    """Check staged path layout, staged symlinks, and manifest deletion.

    Args:
        staged_changes: Parsed staged state.

    Returns:
        Path-policy violations for the whole staged index.
    """
    violations = [
        violation
        for staged_path in sorted(staged_changes.changed_paths | staged_changes.deleted_paths)
        for path_check in (check_site_path, check_top_level_test_path)
        if (violation := path_check(file_path=staged_path)) is not None
    ]
    violations.extend(
        PolicyViolation(
            file_path=symlinked_path,
            line_number=None,
            message=_SYMLINKED_MANIFEST_MESSAGE if symlinked_path == EXCEPTIONS_PATH else _SYMLINKED_PYTHON_MESSAGE,
        )
        for symlinked_path in sorted(
            path for path in staged_changes.symlinked_paths if path.suffix == ".py" or path == EXCEPTIONS_PATH
        )
    )
    if EXCEPTIONS_PATH in staged_changes.deleted_paths:
        violations.append(
            PolicyViolation(
                file_path=EXCEPTIONS_PATH,
                line_number=None,
                message="linter-directives: the exception manifest must not be deleted",
            )
        )
    return violations


def _linter_directives_violations(
    staged_changes: StagedChanges,
    staged_python_sources: dict[Path, tuple[str, str | None]],
    staged_python_paths: list[Path],
) -> list[PolicyViolation]:
    """Validate the exception manifest and staged suppression directives.

    Args:
        staged_changes: Parsed staged state.
        staged_python_sources: Staged Python sources with HEAD baselines.
        staged_python_paths: Staged Python paths pre-commit supplied.

    Returns:
        Manifest validation and per-file directive violations.
    """
    violations: list[PolicyViolation] = []
    manifest_changed = EXCEPTIONS_PATH in staged_changes.sources
    manifest_symlinked = EXCEPTIONS_PATH in staged_changes.symlinked_paths
    manifest_deleted = EXCEPTIONS_PATH in staged_changes.deleted_paths
    exceptions_source: str | None = staged_changes.sources.get(EXCEPTIONS_PATH)
    if (
        not manifest_symlinked
        and (staged_python_sources or manifest_changed)
        and exceptions_source is None
        and not manifest_deleted
    ):
        try:
            exceptions_source = _git_output(command=["git", "show", f":0:{EXCEPTIONS_PATH}"])
        except RuntimeError as error:
            if "does not exist" not in str(error) and "not in the index" not in str(error):
                raise
            violations.append(
                PolicyViolation(
                    file_path=EXCEPTIONS_PATH,
                    line_number=None,
                    message="linter-directives: the exception manifest must exist in the Git index",
                )
            )
    if exceptions_source is not None:
        manifest_head_source = staged_changes.head_sources.get(EXCEPTIONS_PATH)
        if not manifest_changed and staged_python_sources:
            try:
                manifest_head_source = _git_output(command=["git", "show", f"HEAD:{EXCEPTIONS_PATH}"])
            except RuntimeError as error:
                if "does not exist" not in str(error) and "not in the index" not in str(error):
                    raise
        if manifest_changed or staged_python_sources:
            violations.extend(
                check_manifest_update(
                    indexed_source=exceptions_source,
                    head_source=manifest_head_source,
                    staged_sources=staged_python_sources,
                    renamed_away_paths=staged_changes.renamed_away_paths,
                )
            )
        try:
            exceptions = load_exceptions(source=exceptions_source)
        except ExceptionManifestError as error:
            if not any(violation.file_path == EXCEPTIONS_PATH for violation in violations):
                violations.append(
                    PolicyViolation(
                        file_path=EXCEPTIONS_PATH,
                        line_number=None,
                        message=f"linter-directives: fix malformed exception manifest: {error}",
                    )
                )
    else:
        exceptions = ()
    for file_path in staged_python_paths:
        violations.extend(
            check_linter_directives(
                file_path=file_path,
                indexed_source=staged_changes.sources[file_path],
                head_source=staged_changes.head_sources.get(file_path),
                exceptions=exceptions,
            )
        )
    return violations


def _python_source_violations(
    staged_changes: StagedChanges,
    file_paths: list[Path],
    staged_python_paths: list[Path],
) -> list[PolicyViolation]:
    """Check supplied files against every source-level policy.

    Args:
        staged_changes: Parsed staged state.
        file_paths: Paths pre-commit supplied.
        staged_python_paths: Staged Python paths pre-commit supplied.

    Returns:
        Source-level violations for the supplied files.
    """
    imported_modules = {
        module_name
        for path in staged_python_paths
        for module_name in imported_module_names(
            tree=parse(source=staged_changes.sources[path], filename=str(path)),
            module_name=_module_name(file_path=path),
        )
    }
    relevant_modules = {
        module_name
        for module_name in imported_modules
        if module_name and module_name[0] in {"libs", "tests", "utilities", "ocp_resources"}
    }
    resource_classes: Collection[tuple[str, ...]] = frozenset()
    if relevant_modules:
        resource_classes = discover_resource_classes(
            source_reader=_index_source_reader(),
            module_names=relevant_modules,
        )
    violations: list[PolicyViolation] = []
    for file_path in file_paths:
        if file_path in staged_changes.deleted_paths or file_path in staged_changes.symlinked_paths:
            # Symlinked paths already carry a rejection violation and must
            # not fall back to reading their worktree target.
            continue
        violations.extend(
            check_file(
                file_path=file_path,
                staged=False,
                added_lines=_resolved_added_lines(staged_changes=staged_changes, file_path=file_path),
                source=staged_changes.sources.get(file_path),
                head_source=staged_changes.head_sources.get(file_path),
                resource_classes=resource_classes,
            )
        )
    return violations


def _test_std_violations(staged_changes: StagedChanges, staged_python_paths: list[Path]) -> list[PolicyViolation]:
    """Check STD docstrings and manual markers for staged test files.

    Args:
        staged_changes: Parsed staged state.
        staged_python_paths: Staged Python paths pre-commit supplied.

    Returns:
        STD violations for the staged test files.
    """
    return [
        violation
        for file_path in staged_python_paths
        for violation in check_test_std(
            file_path=file_path,
            indexed_source=staged_changes.sources[file_path],
            head_source=(
                None if file_path in staged_changes.renamed_paths else staged_changes.head_sources.get(file_path)
            ),
        )
    ]


def _merged_stp_paths() -> frozenset[str]:
    """Return design-docs paths merged on the default branch.

    Returns:
        Repository-relative paths present in the design-docs default branch tree.

    Raises:
        RuntimeError: When the tree listing cannot be fetched or parsed.
    """
    try:
        tree_source = _git_output(command=["gh", "api", f"repos/{STP_REPOSITORY}/git/trees/main?recursive=1"])
        tree = loads(tree_source)
        entries = tree["tree"]
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise RuntimeError(f"design-docs tree listing failed: {error}") from error
    if tree.get("truncated"):
        raise RuntimeError("design-docs tree listing was truncated by the GitHub API")
    return frozenset(entry["path"] for entry in entries)


def _stp_links_violations(staged_changes: StagedChanges, staged_python_paths: list[Path]) -> list[PolicyViolation]:
    """Reject staged STP references whose design-docs document is not merged.

    Args:
        staged_changes: Parsed staged state.
        staged_python_paths: Staged Python paths pre-commit supplied.

    Returns:
        Violations for unmerged STP references; a fail-closed violation per
        file when the merged set cannot be fetched.
    """
    file_references: dict[Path, dict[str, int]] = {}
    for file_path in staged_python_paths:
        if file_path.parts[:1] != ("tests",):
            # STP references are a product-test concern; tooling sources and
            # their embedded fixture URLs are not verified.
            continue
        references = stp_references(
            indexed_source=staged_changes.sources[file_path],
            added_lines=_resolved_added_lines(staged_changes=staged_changes, file_path=file_path),
        )
        if references:
            file_references[file_path] = references
    if not file_references:
        return []
    try:
        merged_paths = _merged_stp_paths()
    except RuntimeError as error:
        return [unverified_stp_violation(file_path=file_path, error=str(error)) for file_path in file_references]
    return [
        violation
        for file_path, references in file_references.items()
        for violation in check_stp_links(file_path=file_path, references=references, merged_paths=merged_paths)
    ]


def main(arguments: Sequence[str] | None = None) -> int:
    """Run policy checks over the staged index and the supplied filenames.

    Each check family can be selected individually with ``--check <family>``
    so pre-commit runs them as separate hooks; without a selection every
    family runs. Path-policy and manifest checks always cover the whole
    staged index, while Python source and STD checks are limited to the
    filenames pre-commit supplies in ``arguments``.

    Args:
        arguments: Filenames and optional ``--check`` selections, or ``None``
            to use command-line arguments.

    Returns:
        Zero when all files comply, otherwise one.
    """
    file_names, selected_checks = _parse_arguments(arguments=arguments)
    staged_changes = _staged_changes()
    file_paths = [Path(file_name) for file_name in file_names]
    staged_python_sources = {
        # Renamed paths keep their old-path HEAD baseline so unchanged
        # suppressions remain grandfathered; only genuinely new directives
        # need new-path records, and renamed-away records must be removed.
        path: (source, staged_changes.head_sources.get(path))
        for path, source in staged_changes.sources.items()
        if path.suffix == ".py"
    }
    staged_python_paths = [path for path in file_paths if path in staged_python_sources]

    violations: list[PolicyViolation] = []
    if "path-policy" in selected_checks:
        violations.extend(_path_policy_violations(staged_changes=staged_changes))
    if "linter-directives" in selected_checks:
        violations.extend(
            _linter_directives_violations(
                staged_changes=staged_changes,
                staged_python_sources=staged_python_sources,
                staged_python_paths=staged_python_paths,
            )
        )
    if "python-source" in selected_checks:
        violations.extend(
            _python_source_violations(
                staged_changes=staged_changes,
                file_paths=file_paths,
                staged_python_paths=staged_python_paths,
            )
        )
    if "test-std" in selected_checks:
        violations.extend(_test_std_violations(staged_changes=staged_changes, staged_python_paths=staged_python_paths))
    if "stp-links" in selected_checks:
        violations.extend(_stp_links_violations(staged_changes=staged_changes, staged_python_paths=staged_python_paths))

    violations.sort(
        key=lambda violation: (
            violation.file_path.as_posix(),
            violation.line_number is None,
            violation.line_number or 0,
            violation.message,
        )
    )
    for violation in violations:
        print(violation, file=system_modules["sys"].stderr)
    return int(bool(violations))


if __name__ == "__main__":
    raise SystemExit(main())

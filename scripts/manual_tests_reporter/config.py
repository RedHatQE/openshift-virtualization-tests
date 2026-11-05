"""Config-file support for the manual tests reporter.

Loads optional YAML defaults for run attributes so repeated runs do not need
the same CLI flags every time. Precedence (highest first):

1. CLI flags
2. Batch-file metadata and saved attributes (a retry replays its recorded
   run; config defaults only fill gaps the saved attributes leave — unless
   ``--from-cluster`` is combined with the retry file, in which case the
   run is not a replay and cluster-derived values replace the saved ones)
3. This config file
4. Cluster-derived values (``--from-cluster``)
"""

from __future__ import annotations

from pathlib import Path

import click
import yaml
from yaml import YAMLError


class UniqueKeySafeLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys."""


# Merge-key tag (``<<``) — flattened by construct_mapping, which also lets an
# explicit key override a value merged from another mapping.
_YAML_MERGE_TAG = "tag:yaml.org,2002:merge"


def _ensure_hashable_key(key: object, key_node: yaml.Node) -> None:
    """Reject an unhashable mapping key as a YAML error.

    A YAML complex key (e.g. ``[team]: value``) constructs to a list, which
    would otherwise raise a bare ``TypeError`` from the set lookup before
    PyYAML's own unhashable-key check can produce a ``ConstructorError``.
    """
    try:
        hash(key)
    except TypeError as type_error:
        raise yaml.constructor.ConstructorError(
            problem=f"unhashable key {key!r}",
            problem_mark=key_node.start_mark,
        ) from type_error


def _check_merge_source_duplicates(
    loader: UniqueKeySafeLoader,
    source: yaml.MappingNode,
    visited: set[int] | None = None,
) -> None:
    """Reject duplicate keys inside a merge source before flattening.

    flatten_mapping splices merge-source pairs directly into the parent
    mapping without constructing them, so duplicates there would otherwise
    silently last-win.
    """
    seen_keys: set[object] = set()
    merge_marker_seen = False
    for key_node, value_node in source.value:
        if key_node.tag == _YAML_MERGE_TAG:
            if merge_marker_seen:
                raise yaml.constructor.ConstructorError(
                    problem="repeated merge key '<<' in merge source",
                    problem_mark=key_node.start_mark,
                )
            merge_marker_seen = True
            _check_merge_value_duplicates(loader=loader, merge_value=value_node, visited=visited)
            continue
        key = loader.construct_object(node=key_node, deep=True)
        _ensure_hashable_key(key=key, key_node=key_node)
        if key in seen_keys:
            raise yaml.constructor.ConstructorError(
                problem=f"duplicate key {key!r} in merge source",
                problem_mark=key_node.start_mark,
            )
        seen_keys.add(key)


def _check_merge_value_duplicates(
    loader: UniqueKeySafeLoader,
    merge_value: yaml.Node,
    visited: set[int] | None = None,
) -> None:
    """Duplicate-check a merge value: a mapping or a sequence of mappings.

    Already-visited nodes are skipped: YAML aliases can point at a mapping
    that merges itself (``a: &a {<<: *a, x: 1}``), which PyYAML resolves
    fine but which would otherwise recurse here until RecursionError.
    """
    if visited is None:
        visited = set()
    node_id = id(merge_value)
    if node_id in visited:
        return
    visited.add(node_id)
    if isinstance(merge_value, yaml.MappingNode):
        _check_merge_source_duplicates(loader=loader, source=merge_value, visited=visited)
    elif isinstance(merge_value, yaml.SequenceNode):
        for item in merge_value.value:
            _check_merge_value_duplicates(loader=loader, merge_value=item, visited=visited)


def _construct_unique_mapping(
    loader: UniqueKeySafeLoader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> dict:
    seen_keys: set[object] = set()
    merge_marker_seen = False
    for key_node, value_node in node.value:
        if key_node.tag == _YAML_MERGE_TAG:
            if merge_marker_seen:
                raise yaml.constructor.ConstructorError(
                    problem="repeated merge key '<<'",
                    problem_mark=key_node.start_mark,
                )
            merge_marker_seen = True
            # Merged pairs are flattened (not constructed) by construct_mapping;
            # check the merge source for duplicates here instead.
            _check_merge_value_duplicates(loader=loader, merge_value=value_node)
            continue
        key = loader.construct_object(node=key_node, deep=deep)
        _ensure_hashable_key(key=key, key_node=key_node)
        if key in seen_keys:
            raise yaml.constructor.ConstructorError(
                problem=f"duplicate key {key!r}",
                problem_mark=key_node.start_mark,
            )
        seen_keys.add(key)
    return loader.construct_mapping(node, deep=deep)


UniqueKeySafeLoader.add_constructor(
    tag=yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    constructor=_construct_unique_mapping,
)

DEFAULT_CONFIG_PATH: Path | None
try:
    DEFAULT_CONFIG_PATH = Path.home() / ".config" / "manual_tests_reporter" / "config.yaml"
except RuntimeError:
    # No resolvable home directory — disable config auto-discovery instead
    # of crashing at import time (Path.home() raises RuntimeError when HOME
    # is unset and the passwd lookup fails).
    DEFAULT_CONFIG_PATH = None

# Run-attribute config keys mapped to the attribute key they set. This is
# the single source of truth: the accepted-keys check derives from it, and
# generated drift-guard tests exercise both the fresh-run and replay CLI
# wiring, so a new attribute cannot be accepted-but-ignored.
CONFIG_KEY_TO_ATTRIBUTE_KEY = {
    "tier": "tier",
    "cnv-version": "cnv_xy_version",
    "owner": "owner",
    "cluster-id": "cluster_id",
    "ocp-version": "ocp_version",
    "cluster-name": "cluster",
    "cluster-domain": "cluster_domain",
    "sc": "storage_class",
    "channel": "cnv_channel",
    "ip-stack": "ip_stack",
    "iib-image": "iib_image",
    "hco-bundle-version": "hco_bundle_version",
    "rootcoz-url": "rootcoz.url",
}

# Config keys that set run attributes.
ATTRIBUTE_CONFIG_KEYS = frozenset(CONFIG_KEY_TO_ATTRIBUTE_KEY)

# Non-attribute config keys: bundle feeds CNV-version derivation instead of
# emitting its own tag (the Jenkins tag set has cnv_version/cnv_xy_version,
# no bundle).
_NON_ATTRIBUTE_CONFIG_KEYS = frozenset({"tests-dir", "bundle"})

# All accepted config keys.
_ACCEPTED_CONFIG_KEYS = ATTRIBUTE_CONFIG_KEYS | _NON_ATTRIBUTE_CONFIG_KEYS

# Keys that were removed from the accepted set, mapped to the hint a user
# carrying an old config file needs to migrate. Appended to the unknown-key
# error in sorted-key order.
_REMOVED_CONFIG_KEY_HINTS = {
    "arch": " The 'arch' key was removed - the arch tag is no longer uploaded; delete the key from the config file.",
    "team": (
        " The 'team' key was removed - TEAM is now derived from the tests "
        "directory; delete the key from the config file."
    ),
    "service": (
        " The 'service' key was removed - the reporter no longer tags a Datadog service "
        "itself; pass --service to datadog-ci at upload time instead. "
        "Delete the key from the config file."
    ),
}


def load_config(config_path: Path | None) -> tuple[dict[str, str], str]:
    """Load run-attribute defaults from a YAML config file.

    Args:
        config_path: Explicit config path, or ``None`` to fall back to
            :data:`DEFAULT_CONFIG_PATH` when it exists.

    Returns:
        Tuple of the validated config mapping (empty when no config is in
        effect) and a human-readable description of the source path (empty
        when no config was loaded).

    Raises:
        click.ClickException: The file is unreadable, is not valid YAML or
            not UTF-8, or contains unknown keys or invalid values.
    """
    if config_path is None:
        if DEFAULT_CONFIG_PATH is None or not DEFAULT_CONFIG_PATH.is_file():
            return {}, ""
        effective_path = DEFAULT_CONFIG_PATH
    else:
        effective_path = config_path
    source = str(effective_path)

    try:
        with effective_path.open(encoding="utf-8") as handle:
            raw_config = yaml.load(stream=handle, Loader=UniqueKeySafeLoader)
    except OSError as exc:
        raise click.ClickException(f"Cannot read config file {source}: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise click.ClickException(f"Config file {source} is not valid UTF-8: {exc}") from exc
    except YAMLError as exc:
        raise click.ClickException(f"Config file {source} is not valid YAML: {exc}") from exc

    if raw_config is None:
        return {}, source
    if not isinstance(raw_config, dict):
        raise click.ClickException(f"Config file {source} must be a YAML mapping of config keys to values")

    non_string_keys = sorted(str(key) for key in raw_config if not isinstance(key, str))
    if non_string_keys:
        raise click.ClickException(
            f"Config file {source} has non-string key(s): {', '.join(non_string_keys)}. "
            f"Every valid key is a string: {', '.join(sorted(_ACCEPTED_CONFIG_KEYS))}"
        )

    unknown_keys = sorted(set(raw_config) - _ACCEPTED_CONFIG_KEYS)
    if unknown_keys:
        removal_hint = "".join(
            _REMOVED_CONFIG_KEY_HINTS[key] for key in unknown_keys if key in _REMOVED_CONFIG_KEY_HINTS
        )
        raise click.ClickException(
            f"Unknown config key(s) in {source}: {', '.join(unknown_keys)}. "
            f"Valid keys: {', '.join(sorted(_ACCEPTED_CONFIG_KEYS))}.{removal_hint}"
        )

    validated: dict[str, str] = {}
    for key, value in raw_config.items():
        if not isinstance(value, str) or not value.strip():
            hint = ""
            if isinstance(value, int | float) and not isinstance(value, bool):
                hint = f" (YAML parsed a number — quote the value, e.g. {key}: '4.22')"
            elif isinstance(value, bool):
                hint = f" (YAML parsed a boolean — quote the value, e.g. {key}: 'true')"
            elif value is None:
                hint = f" (no value for '{key}' — give it a string)"
            raise click.ClickException(
                f"Config key '{key}' in {source} must be a non-empty string, got {value!r}{hint}"
            )
        validated[key] = value.strip()

    return validated, source

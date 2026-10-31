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


class _UniqueKeySafeLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys."""


def _construct_unique_mapping(
    loader: _UniqueKeySafeLoader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> dict:
    seen_keys: set[object] = set()
    for key_node, _value_node in node.value:
        key = loader.construct_object(node=key_node, deep=deep)
        if key in seen_keys:
            raise yaml.constructor.ConstructorError(
                problem=f"duplicate key {key!r}",
                problem_mark=key_node.start_mark,
            )
        seen_keys.add(key)
    return loader.construct_mapping(node, deep=deep)


_UniqueKeySafeLoader.add_constructor(
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
    "team": "TEAM",
    "tier": "TIER",
    "bundle": "BUNDLE",
    "cnv-version": "CNV_XY_VER",
    "arch": "ARCH",
    "ocp-version": "OCP",
    "cluster-name": "CLUSTER_NAME",
    "cluster-domain": "CLUSTER_DOMAIN",
    "sc": "SC",
    "channel": "CHANNEL",
}

# Config keys that set run attributes.
ATTRIBUTE_CONFIG_KEYS = frozenset(CONFIG_KEY_TO_ATTRIBUTE_KEY)

# Non-attribute config keys.
_NON_ATTRIBUTE_CONFIG_KEYS = frozenset({"tests-dir", "service"})

# All accepted config keys.
_ACCEPTED_CONFIG_KEYS = ATTRIBUTE_CONFIG_KEYS | _NON_ATTRIBUTE_CONFIG_KEYS


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
            raw_config = yaml.load(stream=handle, Loader=_UniqueKeySafeLoader)
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
        raise click.ClickException(
            f"Unknown config key(s) in {source}: {', '.join(unknown_keys)}. "
            f"Valid keys: {', '.join(sorted(_ACCEPTED_CONFIG_KEYS))}"
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

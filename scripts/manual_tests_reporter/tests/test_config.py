# Co-authored-by: Claude <noreply@anthropic.com>
"""Tests for scripts.manual_tests_reporter.config module.

See scripts/manual_tests_reporter/README.md for the tool this module belongs to.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from click import ClickException

from scripts.manual_tests_reporter import config as config_module
from scripts.manual_tests_reporter.config import load_config


class TestLoadConfigExplicitPath:
    def test_valid_config_loaded(self, tmp_path: Path) -> None:
        """Verify a valid config file loads with its source path."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(data="team: NETWORK\nbundle: v4.22.0\n", encoding="utf-8")

        config, source = load_config(config_path=config_path)

        assert config == {"team": "NETWORK", "bundle": "v4.22.0"}, f"Got {config!r}"
        assert source == str(config_path), f"Got {source!r}"

    def test_empty_config_file(self, tmp_path: Path) -> None:
        """Verify an empty config file yields an empty mapping."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(data="", encoding="utf-8")

        config, source = load_config(config_path=config_path)

        assert config == {}, f"Got {config!r}"
        assert source == str(config_path), f"Got {source!r}"

    def test_unknown_key_rejected(self, tmp_path: Path) -> None:
        """Verify an unknown config key fails with the key named."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(data="teams: NETWORK\n", encoding="utf-8")

        with pytest.raises(ClickException, match=r"Unknown config key.*teams"):
            load_config(config_path=config_path)

    def test_non_string_value_rejected(self, tmp_path: Path) -> None:
        """Verify a non-string config value fails cleanly."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(data="team: 5\n", encoding="utf-8")

        with pytest.raises(ClickException, match=r"'team'.*non-empty string"):
            load_config(config_path=config_path)

    def test_numeric_value_hint_mentions_quoting(self, tmp_path: Path) -> None:
        """Verify a numeric YAML value fails with a hint to quote it."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(data="cnv-version: 4.22\n", encoding="utf-8")

        with pytest.raises(ClickException, match="YAML parsed a number"):
            load_config(config_path=config_path)

    def test_boolean_value_hint_mentions_quoting(self, tmp_path: Path) -> None:
        """Verify a boolean YAML value fails with a boolean hint, not the number hint."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(data="team: true\n", encoding="utf-8")

        with pytest.raises(ClickException, match="YAML parsed a boolean"):
            load_config(config_path=config_path)

    def test_duplicate_config_key_rejected(self, tmp_path: Path) -> None:
        """Verify duplicate mapping keys in the config file are rejected, not last-wins."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(data="team: NETWORK\nteam: STORAGE\n", encoding="utf-8")

        with pytest.raises(ClickException, match="not valid YAML"):
            load_config(config_path=config_path)

    def test_non_string_key_rejected(self, tmp_path: Path) -> None:
        """Verify a non-string YAML key fails cleanly instead of crashing."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(data="5: x\n", encoding="utf-8")

        with pytest.raises(ClickException, match="non-string key"):
            load_config(config_path=config_path)

    def test_non_mapping_config_rejected(self, tmp_path: Path) -> None:
        """Verify a non-mapping config file fails cleanly."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(data="- team\n- bundle\n", encoding="utf-8")

        with pytest.raises(ClickException, match="must be a YAML mapping"):
            load_config(config_path=config_path)

    def test_invalid_yaml_rejected(self, tmp_path: Path) -> None:
        """Verify malformed YAML fails with a clean error naming the file."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(data="team: [unclosed\n", encoding="utf-8")

        with pytest.raises(ClickException, match="not valid YAML"):
            load_config(config_path=config_path)


class TestLoadConfigDefaultPath:
    def test_no_default_file_yields_empty_config(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify the absence of a default config file yields no config."""
        monkeypatch.setattr(target=config_module, name="DEFAULT_CONFIG_PATH", value=tmp_path / "absent.yaml")

        config, source = load_config(config_path=None)

        assert config == {}, f"Got {config!r}"
        assert source == "", f"Got {source!r}"

    def test_unresolvable_home_disables_auto_discovery(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify a None default path (unresolvable home) yields no config."""
        monkeypatch.setattr(target=config_module, name="DEFAULT_CONFIG_PATH", value=None)

        config, source = load_config(config_path=None)

        assert config == {}, f"Got {config!r}"
        assert source == "", f"Got {source!r}"

    def test_non_utf8_config_rejected(self, tmp_path: Path) -> None:
        """Verify a non-UTF-8 config file fails with a clean error."""
        config_path = tmp_path / "config.yaml"
        config_path.write_bytes(data="team: NETWORK\n".encode(encoding="utf-16"))

        with pytest.raises(ClickException, match="not valid UTF-8"):
            load_config(config_path=config_path)

    def test_unreadable_config_rejected(self, tmp_path: Path) -> None:
        """Verify an unreadable config path (a directory) fails with a clean error."""
        with pytest.raises(ClickException, match="Cannot read config file"):
            load_config(config_path=tmp_path)

    def test_none_value_hint_mentions_missing_value(self, tmp_path: Path) -> None:
        """Verify a key with no value fails with a hint to set a string."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(data="team:\n", encoding="utf-8")

        with pytest.raises(ClickException, match="no value for 'team'"):
            load_config(config_path=config_path)

    def test_import_time_home_failure_disables_default_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify an unresolvable home at import time disables the default path."""

        def broken_home() -> Path:
            raise RuntimeError("no home directory")

        original_home = Path.home
        monkeypatch.setattr(target=Path, name="home", value=broken_home)
        try:
            importlib.reload(module=config_module)

            assert config_module.DEFAULT_CONFIG_PATH is None, "Expected: fallback to None, not a crash"
        finally:
            # Restore the real module state even when the assertion fails, so
            # a regression here cannot poison the module for the rest of the
            # session.
            monkeypatch.setattr(target=Path, name="home", value=original_home)
            importlib.reload(module=config_module)

        assert config_module.DEFAULT_CONFIG_PATH is not None, "Expected: real default path restored"

    def test_default_file_loaded_when_present(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify the default config path is used when it exists."""
        default_path = tmp_path / "config.yaml"
        default_path.write_text(data="team: STORAGE\n", encoding="utf-8")
        monkeypatch.setattr(target=config_module, name="DEFAULT_CONFIG_PATH", value=default_path)

        config, source = load_config(config_path=None)

        assert config == {"team": "STORAGE"}, f"Got {config!r}"
        assert source == str(default_path), f"Got {source!r}"

    def test_explicit_path_wins_over_default(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify an explicit --config path ignores the default path entirely."""
        default_path = tmp_path / "default.yaml"
        default_path.write_text(data="team: STORAGE\n", encoding="utf-8")
        monkeypatch.setattr(target=config_module, name="DEFAULT_CONFIG_PATH", value=default_path)
        explicit_path = tmp_path / "explicit.yaml"
        explicit_path.write_text(data="team: NETWORK\n", encoding="utf-8")

        config, _source = load_config(config_path=explicit_path)

        assert config == {"team": "NETWORK"}, f"Got {config!r}"

"""Unit tests for utilities.infra helpers."""

import importlib
import sys
from unittest.mock import patch

import pytest

import utilities
from utilities.constants.architecture import AARCH_64, AMD_64, ARM_64, S390X, X86_64

# conftest.py mocks utilities.infra; retain the real module without leaking it to other tests.
original_infra_module = sys.modules["utilities.infra"]
original_infra_attribute = utilities.infra
try:
    del sys.modules["utilities.infra"]
    infra_module = importlib.import_module("utilities.infra")
finally:
    sys.modules["utilities.infra"] = original_infra_module
    utilities.infra = original_infra_attribute


class TestGetMachinePlatform:
    """Test host architecture normalization."""

    @pytest.mark.parametrize(
        argnames=("machine_type", "expected_machine_type"),
        argvalues=[
            pytest.param(AARCH_64, ARM_64, id="aarch64_to_arm64"),
            pytest.param(X86_64, AMD_64, id="x86_64_to_amd64"),
            pytest.param(S390X, S390X, id="s390x_unchanged"),
            pytest.param("unknown_arch", "unknown_arch", id="unknown_arch_unchanged"),
        ],
    )
    def test_get_machine_platform(self, machine_type: str, expected_machine_type: str) -> None:
        """Normalize supported host names and preserve unknown names."""
        with patch.object(target=infra_module.platform, attribute="machine", return_value=machine_type):
            assert infra_module.get_machine_platform() == expected_machine_type, (
                f"Expected {machine_type} to normalize to {expected_machine_type}"
            )

"""Unit tests for machine platform normalization."""

from unittest.mock import patch

import pytest

from utilities.constants.architecture import AARCH_64, AMD_64, ARM_64, S390X, X86_64
from utilities.machine_platform import get_machine_platform


class TestGetMachinePlatform:
    """Test host architecture normalization."""

    @pytest.mark.parametrize(
        ("machine_type", "expected_machine_type"),
        [
            pytest.param(AARCH_64, ARM_64, id="aarch64_to_arm64"),
            pytest.param(X86_64, AMD_64, id="x86_64_to_amd64"),
            pytest.param(S390X, S390X, id="s390x_unchanged"),
        ],
    )
    def test_get_machine_platform(self, machine_type: str, expected_machine_type: str) -> None:
        """Normalize supported host names and preserve unknown names."""
        with patch(target="utilities.machine_platform.platform.machine", return_value=machine_type):
            assert get_machine_platform() == expected_machine_type, (
                f"Expected {machine_type} to normalize to {expected_machine_type}"
            )

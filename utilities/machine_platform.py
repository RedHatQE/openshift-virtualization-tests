"""Normalize host architecture names for cluster binary artifacts."""

import platform

from utilities.constants.architecture import AARCH_64, AMD_64, ARM_64, X86_64


def get_machine_platform() -> str:
    """Return the host architecture using cluster binary artifact naming."""
    machine_type = platform.machine()
    return {X86_64: AMD_64, AARCH_64: ARM_64}.get(machine_type, machine_type)

"""Shared value types for project policy checks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class PolicyViolation:
    """Describe one repository policy violation."""

    file_path: Path
    line_number: int | None
    message: str

    def __str__(self) -> str:
        """Return a pre-commit-friendly description of the violation."""
        location = str(self.file_path)
        if self.line_number is not None:
            location = f"{location}:{self.line_number}"
        return f"{location}: {self.message}"

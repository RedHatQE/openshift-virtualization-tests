from dataclasses import dataclass


@dataclass
class LabelSelector:
    matchLabels: dict[str, str] | None = None

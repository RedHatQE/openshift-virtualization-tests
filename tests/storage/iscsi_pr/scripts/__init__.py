"""PowerShell templates for the iSCSI WSFC environment."""

from pathlib import Path

from jinja2 import StrictUndefined, Template


def render_powershell_script(*, name: str, **context: object) -> str:
    """Render guest configuration; credentials are supplied separately through InputData.

    Returns:
        PowerShell source with the supplied non-secret configuration values.
    """
    return Template(
        source=Path(__file__).with_name(name).read_text(encoding="utf-8"),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    ).render(**context)

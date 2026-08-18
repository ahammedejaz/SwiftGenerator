"""Deterministic YAML emission.

Identical source bytes + identical compiler version ⇒ identical pack bytes. Keys keep the
model's declaration order (never sorted alphabetically — for `structure`, document order
*is* element order), no timestamps enter the content, and the emitted text is proven
loadable by re-validating it through :class:`MxMessageSpec` before it is returned.
"""

from __future__ import annotations

from typing import Any

import yaml

from app.studio.mx.models import MxMessageSpec


class _PackDumper(yaml.SafeDumper):
    """Block style throughout; insertion order preserved."""


_PackDumper.add_representer(
    dict,
    lambda dumper, data: dumper.represent_mapping(
        "tag:yaml.org,2002:map", data.items(), flow_style=False
    ),
)


def emit_pack(spec: dict[str, Any], *, header_comment: str) -> str:
    """Render the pack, prove it loads, and return the exact bytes to write."""
    body = yaml.dump(
        spec,
        Dumper=_PackDumper,
        sort_keys=False,
        allow_unicode=True,
        width=96,
        default_flow_style=False,
    )
    text = "".join(f"# {line}".rstrip() + "\n" for line in header_comment.splitlines())
    text += body
    # The single most important property of the emitter: what it writes, the ordinary
    # registry can load. Proven on every emission, not assumed.
    MxMessageSpec.model_validate(yaml.safe_load(text))
    return text

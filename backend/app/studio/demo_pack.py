"""Build the synthetic demonstration pack in ``demo/``.

Everything in the pack is produced by the **production composer** — the same code path the
browser, the JSON API and the Excel importer use. That is deliberate: a hand-written
"expected output" is a claim about the software, and claims drift. These are recordings of
what the software actually does, and ``--check`` fails if they stop matching.

Two things have to be pinned for the pack to be byte-reproducible:

* MX writes ``CreDt`` and derives ``BizMsgIdr`` from the clock. Both are supplied explicitly
  in the request files, which is also the honest thing for a demo — the reader can see that
  a timestamp is an input, not something invented at render time.
* MT sample dates are fixed constants, and the FIN envelope comes from the client profile,
  so MT needs no pinning.

Nothing here is real. The BICs, accounts, references and identifiers are the synthetic
demonstration values configured in ``backend/config/profiles`` and the sample library; the
ISIN is a documentation placeholder. No client data, no live network values, no keys.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.studio.excel import build_template
from app.studio.models import (
    EnvelopeOverride,
    GenerateRequest,
    MessageFormat,
    OutputMode,
    SampleVariant,
)
from app.studio.samples import build_sample
from app.studio.service import studio_service

DEMO_ROOT = Path(__file__).resolve().parents[3] / "demo"

#: Fixed so the pack is byte-reproducible. A demo whose expected output changes every time
#: it is generated cannot be diffed, and cannot be trusted as a reference.
PINNED_CREATION = "2026-08-16T09:00:00Z"

MT_MESSAGES = ("MT541", "MT548", "MT545")
MX_MESSAGES = ("sese.023", "sese.024", "sese.025")

#: The one value the import/diff demo changes, so the comparison shows exactly one line.
EDITED_REFERENCE = "DEMOEDIT0001"


def _envelope(format_: MessageFormat, message_type: str) -> EnvelopeOverride | None:
    if format_ is MessageFormat.MT:
        return None
    return EnvelopeOverride(
        business_message_identifier=f"{message_type.replace('.', '').upper()}DEMO0000001",
        creation_date=PINNED_CREATION,
    )


def _request(format_: MessageFormat, message_type: str) -> GenerateRequest:
    sample = build_sample(format_, message_type, SampleVariant.TYPICAL)
    return GenerateRequest(
        format=format_,
        message_type=message_type,
        profile_id="BASE_DEMO_V1",
        scenario_id=f"DEMO-{message_type.replace('.', '').upper()}",
        fields=list(sample.inputs),
        elements=list(sample.elements),
        envelope=_envelope(format_, message_type),
        persist=False,
    )


def _body(request: GenerateRequest) -> dict[str, Any]:
    """The request as an automation caller would POST it, camelCase and without nulls."""
    payload = request.model_dump(mode="json", by_alias=True, exclude_none=True)
    payload.pop("fields" if not request.fields else "elements", None)
    return payload


def _generated(request: GenerateRequest) -> tuple[str, str]:
    """Returns (filename suffix, message text) for the message this request produces."""
    result = studio_service.generate(
        request.model_copy(
            update={
                "output_modes": [OutputMode.FIN, OutputMode.BLOCK4]
                if request.format is MessageFormat.MT
                else [OutputMode.XML, OutputMode.DOCUMENT, OutputMode.APPHDR]
            }
        )
    )
    if not result.valid:
        problems = "; ".join(item.message for item in result.validation.errors)
        raise RuntimeError(f"{request.message_type} sample is not valid: {problems}")
    if request.format is MessageFormat.MT:
        assert result.outputs.fin is not None
        return "fin", result.outputs.fin
    assert result.outputs.xml is not None
    return "xml", result.outputs.xml


def build() -> dict[Path, bytes]:
    """Every file the pack contains, as bytes, keyed by path."""
    files: dict[Path, bytes] = {}

    for format_, messages in (
        (MessageFormat.MT, MT_MESSAGES),
        (MessageFormat.MX, MX_MESSAGES),
    ):
        for message_type in messages:
            stem = message_type.replace(".", "")
            request = _request(format_, message_type)
            suffix, text = _generated(request)
            files[DEMO_ROOT / "requests" / f"{stem}-generate.json"] = (
                json.dumps(_body(request), indent=2) + "\n"
            ).encode()
            files[DEMO_ROOT / "expected" / f"{stem}.{suffix}"] = text.encode()

    # Import and diff: the message to paste in, and the same values with one reference
    # changed, so the comparison shows exactly one line and names the field.
    mt_request = _request(MessageFormat.MT, "MT541")
    _, mt541 = _generated(mt_request)
    edited = [
        item.model_copy(update={"value": EDITED_REFERENCE})
        if (item.id or "").endswith("20C-SEME")
        else item
        for item in mt_request.fields
    ]
    files[DEMO_ROOT / "requests" / "MT541-import.json"] = (
        json.dumps({"text": mt541}, indent=2) + "\n"
    ).encode()
    files[DEMO_ROOT / "requests" / "MT541-diff.json"] = (
        json.dumps(
            {
                "format": "MT",
                "messageType": "MT541",
                "original": mt541,
                "fields": [
                    item.model_dump(mode="json", by_alias=True, exclude_none=True)
                    for item in edited
                ],
            },
            indent=2,
        )
        + "\n"
    ).encode()

    for format_ in (MessageFormat.MT, MessageFormat.MX):
        files[DEMO_ROOT / "excel" / f"demo-{format_.value}.xlsx"] = build_template(format_)

    return files


def write() -> list[Path]:
    written = []
    for path, content in build().items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        written.append(path)
    return sorted(written)


def stale() -> list[Path]:
    """Which pack files no longer match what the composer produces.

    Excel workbooks are zip archives whose bytes differ between builds even when the
    content is identical, so they are checked for existence rather than for equality —
    claiming to verify something that cannot be verified would be worse than saying so.
    """
    problems = []
    for path, content in build().items():
        if not path.exists():
            problems.append(path)
        elif path.suffix != ".xlsx" and path.read_bytes() != content:
            problems.append(path)
    return sorted(problems)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build or verify the demo pack")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if args.check:
        problems = stale()
        if problems:
            for path in problems:
                print(f"stale or missing: {path.relative_to(DEMO_ROOT.parent)}")
            print("demo/ is out of date — run `make demo-pack`")
            return 1
        print("demo/ matches what the composer produces")
        return 0
    if args.write:
        for path in write():
            print(f"wrote {path.relative_to(DEMO_ROOT.parent)}")
        return 0
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

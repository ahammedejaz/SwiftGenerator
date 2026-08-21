"""Where the knowledge base speaks about MT ↔ ISO 20022 correspondence — found, not recalled.

The mapping registry may only contain relationships the knowledge base supports, so the
search for that support is a deterministic, exhaustive sweep of the local index: every
segment of every source is matched against a fixed vocabulary (coexistence, migration,
"ISO 20022 equivalent", the ISO business-area prefixes, "mapping", "replaced by"), and every
hit is recorded by identity — source id, checksum, page, section, segment hash, the phrase
that matched — never by quoting the document. No model takes part.

The committed index (``backend/config/mappings/evidence-index.json``) is what the
relationships file cites and what the generated coverage report lists; ``--check``
re-renders the report from the index so the two cannot drift.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.config import CONFIG_ROOT, PROJECT_ROOT

EVIDENCE_SCHEMA = "mt-mx-mapping-evidence/1"
INDEX_PATH = CONFIG_ROOT / "mappings" / "evidence-index.json"
COVERAGE_DOC = PROJECT_ROOT / "docs" / "generated" / "mt-mx-mapping-coverage.md"

#: The vocabulary of correspondence. A phrase is a whole-word FTS match; ``"ISO 20022"`` is
#: the literal phrase. Business-area prefixes catch an MT guide that names its ISO twin.
PHRASES: tuple[tuple[str, str], ...] = (
    ("coexistence", "coexistence"),
    ("migration", "migration"),
    ("ISO 20022", '"ISO 20022"'),
    ("equivalent", "equivalent"),
    ("replaced by", '"replaced by"'),
    ("mapping", "mapping"),
    ("translation", "translation"),
    ("pacs", "pacs"),
    ("pain", "pain"),
    ("camt", "camt"),
    ("sese", "sese"),
    ("seev", "seev"),
    ("semt", "semt"),
    ("MX", "MX"),
    ("FINplus", "FINplus"),
    ("InterAct", "InterAct"),
    ("Financial Institution Credit Transfer", '"Financial Institution Credit Transfer"'),
)


@dataclass(frozen=True)
class EvidenceHit:
    phrase: str
    source_id: str
    source_checksum: str
    format: str
    message_type: str | None
    release: str | None
    document_type: str
    page: int | None
    section: str
    segment_hash: str

    def as_payload(self) -> dict[str, Any]:
        return {
            "phrase": self.phrase,
            "sourceId": self.source_id,
            "sourceChecksum": self.source_checksum,
            "format": self.format,
            "messageType": self.message_type,
            "release": self.release,
            "documentType": self.document_type,
            "page": self.page,
            "section": self.section,
            "segmentHash": self.segment_hash,
        }


@dataclass
class EvidenceIndex:
    sources_scanned: int = 0
    segments_scanned: int = 0
    hits: list[EvidenceHit] = field(default_factory=list)

    def as_payload(self) -> dict[str, Any]:
        return {
            "schemaVersion": EVIDENCE_SCHEMA,
            "phrases": [phrase for phrase, _query in PHRASES],
            "sourcesScanned": self.sources_scanned,
            "segmentsScanned": self.segments_scanned,
            "hitCount": len(self.hits),
            "hits": [hit.as_payload() for hit in self.hits],
            "liveModelCalls": 0,
        }


def scan_knowledge_base() -> EvidenceIndex:
    """Every phrase against every indexed segment, through the FTS index the knowledge base
    already maintains. Sweeps the whole corpus — there is no top-k here."""
    from app.knowledge_base.service import knowledge_service

    index = EvidenceIndex()
    if not knowledge_service.indexed:
        return index
    with knowledge_service.database.read() as connection:
        index.sources_scanned = int(
            connection.execute(
                "SELECT COUNT(*) FROM knowledge_source WHERE deleted = 0"
            ).fetchone()[0]
        )
        index.segments_scanned = int(
            connection.execute("SELECT COUNT(*) FROM knowledge_segment").fetchone()[0]
        )
        for phrase, query in PHRASES:
            rows = connection.execute(
                "SELECT s.source_id, s.checksum, s.format, s.message_type, s.release, "
                "s.section, s.page, s.segment_hash, src.document_type "
                "FROM knowledge_fts f "
                "JOIN knowledge_segment s ON s.segment_id = f.segment_id "
                "JOIN knowledge_source src ON src.source_id = s.source_id "
                "WHERE knowledge_fts MATCH ? AND src.deleted = 0 "
                "ORDER BY s.source_id, s.ordinal",
                (query,),
            ).fetchall()
            for row in rows:
                index.hits.append(
                    EvidenceHit(
                        phrase=phrase,
                        source_id=str(row[0]),
                        source_checksum=str(row[1]),
                        format=str(row[2]),
                        message_type=row[3],
                        release=row[4],
                        section=str(row[5]),
                        page=row[6],
                        segment_hash=str(row[7]),
                        document_type=str(row[8]),
                    )
                )
    return index


def write_index(index: EvidenceIndex, path: Path | None = None) -> Path:
    target = path or INDEX_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(index.as_payload(), indent=1) + "\n", encoding="utf-8")
    return target


def load_index(path: Path | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = json.loads((path or INDEX_PATH).read_text(encoding="utf-8"))
    if payload.get("schemaVersion") != EVIDENCE_SCHEMA:
        raise ValueError(f"evidence index is {payload.get('schemaVersion')}, not {EVIDENCE_SCHEMA}")
    return payload


def _document(lines: list[str]) -> str:
    return "\n".join(lines).rstrip("\n") + "\n"


def render_coverage(evidence: dict[str, Any], proofs: list[dict[str, Any]] | None = None) -> str:
    """The mapping coverage report: evidence found, relationships recorded, packs and their
    class, and the conversion proofs an operator ran locally (recorded, never re-run here)."""
    from app.mapping.registry import mapping_registry

    registry = mapping_registry()
    by_phrase = Counter(str(hit["phrase"]) for hit in evidence["hits"])
    by_source: dict[str, Counter[str]] = {}
    for hit in evidence["hits"]:
        by_source.setdefault(str(hit["sourceId"]), Counter())[str(hit["phrase"])] += 1
    lines = [
        "# MT → MX mapping coverage",
        "",
        "Generated by `python -m app.mapping evidence --write`. Three things, kept apart: what "
        "the knowledge base *says* about MT ↔ ISO 20022 correspondence (an exhaustive lexical "
        "sweep, recorded by identity and page — no text); which relationships the registry "
        "records and on what class of evidence; and which Mapping Packs exist, how far they "
        "reach, and what the local conversion proofs showed. No relationship or field mapping "
        "comes from model memory; a pack's class says exactly how much the sources support.",
        "",
        "## Evidence sweep",
        "",
        f"- Sources scanned: {evidence['sourcesScanned']} · segments scanned: "
        f"{evidence['segmentsScanned']} · phrase hits: {evidence['hitCount']}",
        "",
        "| Phrase | Segments matched |",
        "|---|---:|",
    ]
    for phrase, _query in PHRASES:
        lines.append(f"| {phrase} | {by_phrase.get(phrase, 0)} |")
    lines += [
        "",
        "### Sources with correspondence vocabulary",
        "",
        "| Source | Matches |",
        "|---|---|",
    ]
    for source_id, counts in sorted(by_source.items()):
        detail = ", ".join(f"{phrase} ×{count}" for phrase, count in sorted(counts.items()))
        lines.append(f"| {source_id} | {detail} |")
    lines += [
        "",
        "## Relationships recorded",
        "",
        "| Relationship | Source | Target | Evidence class | Citations | Also covers | Blocker |",
        "|---|---|---|---|---|---|---|",
    ]
    for item in registry.relationships:
        citations = "; ".join(
            f"{cite.source_id}" + (f" p.{cite.page}" if cite.page else "")
            for cite in item.citations
        )
        source_label = f"{item.source.message_type} ({item.source.release or '—'})"
        target_label = f"{item.target.message_type} {item.target.release or ''}"
        lines.append(
            f"| {item.relationship_id} | {source_label} | {target_label} | "
            f"{item.evidence_class.value} | {citations or '—'} | "
            f"{', '.join(item.also_covers) or '—'} | {item.blocker or '—'} |"
        )
    lines += [
        "",
        "## Mapping Packs",
        "",
        "| Pack | Source | Target | Review state | Evidence class | Rules | Cited rules | "
        "Production eligible |",
        "|---|---|---|---|---|---:|---:|---|",
    ]
    for pack in registry.packs:
        source_label = (
            f"{pack.source.message_type} ({pack.source.release or '—'}, {pack.source.lane.value})"
        )
        target_label = (
            f"{pack.target.message_type} {pack.target.release or ''} ({pack.target.lane.value})"
        )
        lines.append(
            f"| {pack.pack_id} {pack.version} | {source_label} | {target_label} | "
            f"{pack.provenance.review_state.value} | {pack.provenance.evidence_class.value} | "
            f"{len(pack.rules)} | {pack.cited_rule_count} | "
            f"{'yes' if pack.provenance.production_eligible else 'no'} |"
        )
    lines += [
        "",
        "## Conversion proofs",
        "",
        "Run locally against the operator's knowledge base "
        "(`python -m app.mapping evidence --write` records them); the packs that target a "
        "knowledge-preview structure need that structure compiled, which CI never has.",
        "",
        "| Pack | Status | Mandatory target mapped | Source rows represented | "
        "Missing target fields | XSD |",
        "|---|---|---|---|---|---|",
    ]
    for proof in proofs or []:
        lines.append(
            f"| {proof['packId']} | {proof['status']} | {proof['mandatoryTargetMapped']}/"
            f"{proof['mandatoryTargetTotal']} | {proof['sourceRowsRepresented']}/"
            f"{proof['sourceRowsTotal']} | {proof['missing']} | {proof['xsd']} |"
        )
    if not proofs:
        lines.append("| — | not run | — | — | — | — |")
    return _document(lines)


def run_proofs() -> list[dict[str, Any]]:
    """Convert the deterministic MINIMAL sample of each pack's source through the pack and
    record what came back. Opt-in preview is set explicitly: every pack here is a candidate
    or synthetic, and the report says so."""
    from app.mapping.models import ConvertRequest
    from app.mapping.registry import mapping_registry
    from app.mapping.service import MappingError, mapping_service
    from app.studio.catalogue import message_spec
    from app.studio.models import ElementInput, FieldInput, SampleVariant
    from app.studio.samples import build_sample

    proofs: list[dict[str, Any]] = []
    for pack in mapping_registry().packs:
        try:
            sample = build_sample(
                pack.source.format,
                pack.source.message_type,
                SampleVariant.MINIMAL,
                lane=pack.source.lane,
                release=pack.source.release,
            )
            fields = [
                FieldInput(id=item.id, occurrence=item.occurrence, value=item.value)
                for item in sample.inputs
            ]
            response = mapping_service.convert(
                ConvertRequest(
                    source_message=pack.source.message_type,
                    source_release=pack.source.release,
                    source_lane=pack.source.lane,
                    fields=fields,
                    target_message=pack.target.message_type,
                    target_version=pack.target.release or pack.target.message_type,
                    target_lane=pack.target.lane,
                    mapping_pack_id=pack.pack_id,
                    allow_synthetic_preview=True,
                ),
                fields,
            )
        except (MappingError, LookupError, KeyError, ValueError) as error:
            proofs.append(
                {
                    "packId": pack.pack_id,
                    "status": f"NOT_RUN ({type(error).__name__})",
                    "mandatoryTargetMapped": "—",
                    "mandatoryTargetTotal": "—",
                    "sourceRowsRepresented": "—",
                    "sourceRowsTotal": "—",
                    "missing": str(error)[:80],
                    "xsd": "—",
                }
            )
            continue
        first_status = response.status
        supplied: list[str] = []
        if response.status == "NEEDS_INPUT":
            # Then, as the studio does, the caller answers the questions — here from the
            # target's own deterministic MINIMAL sample, synthetic values the target structure
            # accepts — until the conversion reaches the composer and the XSD, or stops
            # asking. A question the sample cannot answer ends the proof as NEEDS_INPUT.
            target_sample = build_sample(
                pack.target.format,
                pack.target.release or pack.target.message_type,
                SampleVariant.MINIMAL,
                lane=pack.target.lane,
            )
            answers = {item.path: item.value for item in target_sample.elements}
            target_key = pack.target.release or pack.target.message_type
            target_spec = message_spec(pack.target.format, target_key, pack.target.lane)
            _TARGET_FIELDS[target_key] = (
                {field.id: field for field in target_spec.fields},
                pack.target.lane,
            )
            given: dict[str, str] = {}
            for _round in range(4):
                if response.status != "NEEDS_INPUT" or response.report is None:
                    break
                progressed = False
                for item in response.report.target_required_missing:
                    path, value = _answer(item.field_id, answers, given)
                    if path is not None and value is not None:
                        given[path] = value
                        progressed = True
                if not progressed:
                    break
                supplied = sorted(given)
                response = mapping_service.convert(
                    ConvertRequest(
                        source_message=pack.source.message_type,
                        source_release=pack.source.release,
                        source_lane=pack.source.lane,
                        fields=fields,
                        target_message=pack.target.message_type,
                        target_version=pack.target.release or pack.target.message_type,
                        target_lane=pack.target.lane,
                        target_values=[
                            ElementInput(path=path, value=value) for path, value in given.items()
                        ],
                        mapping_pack_id=pack.pack_id,
                        allow_synthetic_preview=True,
                    ),
                    fields,
                )
        report = response.report
        coverage = report.coverage if report else None
        xsd = "—"
        if response.generation is not None:
            xsd = "accepted" if response.generation.valid else "rejected"
        status = response.status
        if first_status == "NEEDS_INPUT" and supplied:
            status = f"NEEDS_INPUT → {response.status} after {len(supplied)} answer(s)"
        proofs.append(
            {
                "packId": pack.pack_id,
                "status": status,
                "mandatoryTargetMapped": coverage.mandatory_target_mapped if coverage else "—",
                "mandatoryTargetTotal": coverage.mandatory_target_total if coverage else "—",
                "sourceRowsRepresented": coverage.source_rows_represented if coverage else "—",
                "sourceRowsTotal": coverage.source_rows_total if coverage else "—",
                "missing": ", ".join(
                    item.field_id.rsplit("/", 1)[-1] for item in report.target_required_missing
                )
                if report and report.target_required_missing
                else "none",
                "xsd": xsd,
            }
        )
    return proofs


def _answer(
    field_id: str, answers: dict[str, str], given: dict[str, str]
) -> tuple[str | None, str | None]:
    """The sample's value for the asked leaf, or a synthetic value for that very leaf from
    the same value table the studio's samples use; never a different element."""
    if field_id in answers:
        return field_id, answers[field_id]
    if field_id in given:
        return None, None
    return field_id, _synthetic_for(field_id)


_TARGET_FIELDS: dict[str, Any] = {}


def _synthetic_for(field_id: str) -> str | None:
    from app.studio.models import Lane, MessageFormat
    from app.studio.samples import SampleContext, _sample_value

    for key, (spec, lane) in _TARGET_FIELDS.items():
        field = spec.get(field_id)
        if field is not None:
            return _sample_value(field, key, SampleContext(lane=lane))
    del Lane, MessageFormat
    return None


PROOFS_PATH = CONFIG_ROOT / "mappings" / "conversion-proofs.json"


def write_reports(*, run: bool) -> list[Path]:
    evidence = load_index()
    proofs: list[dict[str, Any]]
    if run:
        proofs = run_proofs()
        PROOFS_PATH.write_text(json.dumps(proofs, indent=1) + "\n", encoding="utf-8")
    else:
        proofs = json.loads(PROOFS_PATH.read_text(encoding="utf-8")) if PROOFS_PATH.exists() else []
    COVERAGE_DOC.parent.mkdir(parents=True, exist_ok=True)
    COVERAGE_DOC.write_text(render_coverage(evidence, proofs), encoding="utf-8")
    return [COVERAGE_DOC]


def stale_reports() -> list[Path]:
    evidence = load_index()
    proofs = json.loads(PROOFS_PATH.read_text(encoding="utf-8")) if PROOFS_PATH.exists() else []
    rendered = render_coverage(evidence, proofs)
    if not COVERAGE_DOC.exists() or COVERAGE_DOC.read_text(encoding="utf-8") != rendered:
        return [COVERAGE_DOC]
    return []

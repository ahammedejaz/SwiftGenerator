"""The registry is specification-driven: messages exist because configuration declares
them, and onboarding one is a YAML change, not a code change.

The onboarding test builds a complete synthetic message (manifest entry + knowledge
records) in a temporary directory and proves the registries accept it with no edit to any
Python file — the property AGENTS.md promises and the specification engine depends on.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from app.knowledge.loader import TagKnowledgeRepository
from app.specifications.manifest import ManifestIndex
from app.specifications.registry import specification_registry

CONFIG = Path(__file__).resolve().parents[2] / "config"


def _load(path: Path) -> dict:  # type: ignore[type-arg]
    return yaml.safe_load(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _write(path: Path, payload: dict) -> None:  # type: ignore[type-arg]
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


@pytest.fixture()
def synthetic_message(tmp_path: Path) -> tuple[Path, Path]:
    """A manifest and knowledge directory that add MT599 purely through YAML."""
    manifest = _load(CONFIG / "specifications" / "supported_subset_v1.yaml")
    manifest["messages"].append(
        {
            "messageType": "MT599",
            "name": "Synthetic Test Message",
            "scope": "Synthetic onboarding-proof subset.",
            "shortDescription": "Prove a message onboards through configuration alone.",
            "workflowModule": "SETTLEMENT",
            "sequences": [
                {"path": "A", "code": "GENL", "order": 1, "minOccurs": 1, "maxOccurs": 1}
            ],
        }
    )
    manifest_path = tmp_path / "manifest.yaml"
    _write(manifest_path, manifest)

    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    (knowledge_dir / "overlays").mkdir()
    source = _load(CONFIG / "knowledge" / "settlement_v1.yaml")
    # Reuse a real, verified reference record so every review/source constraint holds;
    # only its message binding is synthetic.
    template = next(
        record
        for record in source["records"]
        if record.get("fieldTag") == "20C" and record.get("qualifier") == "SEME"
    )
    record = copy.deepcopy(template)
    record["messageTypes"] = ["MT599"]
    record["sequencePath"] = "A"
    # The synthetic message has one field, so cross-field dependencies cannot resolve.
    for relation in ("dependsOn", "requiredWith", "conflictsWith", "relatedFields"):
        record.pop(relation, None)
    for pack in CONFIG.joinpath("knowledge").glob("*.yaml"):
        (knowledge_dir / pack.name).write_text(
            pack.read_text(encoding="utf-8"), encoding="utf-8"
        )
    _write(knowledge_dir / "zz_synthetic.yaml", {"records": [record]})
    return manifest_path, knowledge_dir


def test_a_new_message_onboards_through_yaml_alone(
    synthetic_message: tuple[Path, Path],
) -> None:
    manifest_path, knowledge_dir = synthetic_message
    index = ManifestIndex(manifest_path)
    assert index.known("MT599")
    repository = TagKnowledgeRepository(knowledge_dir, manifest=index)
    records = repository.list_records(message_type="MT599")
    assert [item.record.field_tag for item in records] == ["20C"]


def test_the_manifest_refuses_a_duplicate_message(tmp_path: Path) -> None:
    manifest = _load(CONFIG / "specifications" / "supported_subset_v1.yaml")
    manifest["messages"].append(copy.deepcopy(manifest["messages"][0]))
    path = tmp_path / "manifest.yaml"
    _write(path, manifest)
    with pytest.raises(ValueError, match="Duplicate manifest message"):
        ManifestIndex(path)


def test_the_manifest_refuses_a_message_without_an_owner(tmp_path: Path) -> None:
    manifest = _load(CONFIG / "specifications" / "supported_subset_v1.yaml")
    manifest["messages"][0].pop("workflowModule")
    path = tmp_path / "manifest.yaml"
    _write(path, manifest)
    with pytest.raises(ValueError, match="workflowModule"):
        ManifestIndex(path)


def test_the_manifest_refuses_a_non_mt_identifier(tmp_path: Path) -> None:
    manifest = _load(CONFIG / "specifications" / "supported_subset_v1.yaml")
    manifest["messages"][0]["messageType"] = "PACS008"
    path = tmp_path / "manifest.yaml"
    _write(path, manifest)
    with pytest.raises(ValueError, match="not an MT identifier"):
        ManifestIndex(path)


def test_the_registry_answers_known_for_strings_and_legacy_enums() -> None:
    from app.domain.enums import MessageType

    assert specification_registry.known("MT541")
    assert specification_registry.known("mt541")
    assert not specification_registry.known("MT999")
    # StrEnum members are strings, so the legacy surface needs no adapter.
    assert specification_registry.get(MessageType.MT541).message_type == "MT541"


def test_catalogue_descriptions_come_from_the_manifest() -> None:
    spec = specification_registry.get("MT541")
    assert spec.short_description == (
        "Instruct the receipt of securities against a cash payment."
    )


def test_every_manifest_message_reaches_the_studio_catalogue() -> None:
    from app.studio.catalogue import build_catalogue
    from app.studio.models import MessageFormat

    catalogue_types = {
        entry.message_type
        for entry in build_catalogue().messages
        if entry.format is MessageFormat.MT
    }
    assert catalogue_types == set(
        spec.message_type for spec in specification_registry.list()
    )


def test_the_format_neutral_registry_projects_both_formats() -> None:
    from app.studio import registry
    from app.studio.models import MessageFormat

    definitions = registry.all_definitions()
    formats = {item.format for item in definitions}
    assert formats == {MessageFormat.MT, MessageFormat.MX}
    assert registry.get("MT541").family == "MT5"
    assert registry.get("sese.023").family == "sese"
    assert registry.by_family("sese") == registry.by_format(MessageFormat.MX)
    assert registry.capabilities("MT541").structure.value == "CONFIGURED_SUBSET"
    with pytest.raises(KeyError):
        registry.get("pacs.008")

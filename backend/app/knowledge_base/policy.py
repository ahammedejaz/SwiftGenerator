"""Whether a source's text may leave the machine.

Two gates, both explicit: the global switch and the per-classification list. Silence is
"blocked", an API key is not permission, and the decision is recorded on the source so
every later consumer — the embedder, the prompt builder, the citation renderer — reads the
same answer rather than re-deriving it.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings
from app.knowledge_base.models import ExternalPolicy, SourceClassification


@dataclass(frozen=True)
class SourcePolicy:
    embedding: ExternalPolicy
    llm: ExternalPolicy
    #: Short quoted excerpts in citations. Synthetic fixtures only, by default.
    snippets: bool
    reason: str


def allowed_classifications(settings: Settings) -> frozenset[SourceClassification]:
    names = {
        item.strip().upper()
        for item in settings.knowledge_external_processing_classifications.split(",")
        if item.strip()
    }
    result: set[SourceClassification] = set()
    for name in names:
        try:
            result.add(SourceClassification(name))
        except ValueError:
            continue
    return frozenset(result)


def policy_for(classification: SourceClassification, settings: Settings) -> SourcePolicy:
    if classification is SourceClassification.SYNTHETIC_FIXTURE:
        return SourcePolicy(
            embedding=ExternalPolicy.ALLOWED,
            llm=ExternalPolicy.ALLOWED,
            snippets=True,
            reason="synthetic fixture owned by this repository",
        )
    permitted = classification in allowed_classifications(settings)
    embedding = (
        ExternalPolicy.ALLOWED
        if settings.knowledge_external_embedding_allowed and permitted
        else ExternalPolicy.BLOCKED
    )
    llm = (
        ExternalPolicy.ALLOWED
        if settings.knowledge_external_llm_allowed and permitted
        else ExternalPolicy.BLOCKED
    )
    if embedding is ExternalPolicy.BLOCKED and llm is ExternalPolicy.BLOCKED:
        reason = (
            "licensed or operator-supplied material; external processing requires "
            "KNOWLEDGE_EXTERNAL_EMBEDDING_ALLOWED / KNOWLEDGE_EXTERNAL_LLM_ALLOWED and the "
            "classification listed in KNOWLEDGE_EXTERNAL_PROCESSING_CLASSIFICATIONS"
        )
    else:
        reason = "explicitly permitted by operator configuration"
    return SourcePolicy(embedding=embedding, llm=llm, snippets=False, reason=reason)


def policy_statement(blocked_sources: int, total_sources: int) -> str | None:
    if blocked_sources == 0:
        return None
    if blocked_sources == total_sources:
        return "Semantic embedding disabled by source policy; using local lexical retrieval."
    return (
        f"Semantic embedding disabled by source policy for {blocked_sources} of "
        f"{total_sources} sources; local lexical retrieval covers them."
    )

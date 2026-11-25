"""Deterministic offline agent loop with extractive, grounded answers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re

from .retrieval import Evidence, Retriever, _tokens


SENTENCE_PATTERN = re.compile(r"(?<=[.!?])\s+")
STOPWORDS = {
    "a", "an", "and", "are", "be", "do", "does", "for", "from", "how",
    "in", "is", "it", "must", "of", "on", "the", "to", "what", "when",
    "where", "who", "why", "with",
}


def _content_tokens(value: str) -> set[str]:
    return _tokens(value) - STOPWORDS


@dataclass(frozen=True)
class AgentResponse:
    query: str
    action: str
    answer: str | None
    evidence: tuple[Evidence, ...]
    citations: tuple[str, ...]
    reason: str

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["evidence"] = [item.to_dict() for item in self.evidence]
        payload["citations"] = list(self.citations)
        return payload


class OfflineAgent:
    """Route a query to retrieval or a safe abstention, without generation."""

    def __init__(self, retriever: Retriever, min_query_token_overlap: int = 2) -> None:
        if min_query_token_overlap < 1:
            raise ValueError("min_query_token_overlap must be at least 1")
        self.retriever = retriever
        self.min_query_token_overlap = min_query_token_overlap

    def run(self, query: str, top_k: int = 3) -> AgentResponse:
        evidence = self.retriever.search(query, top_k=top_k)
        query_tokens = _content_tokens(query)
        supported = [
            item
            for item in evidence
            if len(query_tokens & _content_tokens(f"{item.title} {item.excerpt}"))
            >= self.min_query_token_overlap
        ]
        if not supported:
            return AgentResponse(
                query=query,
                action="abstain",
                answer=None,
                evidence=tuple(evidence),
                citations=(),
                reason="insufficient_evidence",
            )

        source = supported[0]
        sentences = [
            sentence.strip()
            for sentence in SENTENCE_PATTERN.split(source.excerpt)
            if sentence.strip()
        ]
        answer = max(
            enumerate(sentences),
            key=lambda item: (
                len(query_tokens & _content_tokens(item[1])),
                -item[0],
            ),
        )[1]
        return AgentResponse(
            query=query,
            action="retrieve",
            answer=answer,
            evidence=tuple(evidence),
            citations=(source.citation,),
            reason="grounded_extract_found",
        )


"""Small deterministic lexical retriever with grounded citation output."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import re
from typing import Iterable


TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


def _tokens(value: str) -> set[str]:
    return set(TOKEN_PATTERN.findall(value.casefold()))


@dataclass(frozen=True)
class Document:
    source_id: str
    title: str
    text: str
    authority: int = 0
    is_current: bool = True


@dataclass(frozen=True)
class Evidence:
    source_id: str
    title: str
    excerpt: str
    score: float
    citation: str
    authority: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def load_documents(path: Path) -> list[Document]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [Document(**item) for item in payload["documents"]]


class Retriever:
    """Rank current documents by authority, then lexical relevance."""

    def __init__(self, documents: Iterable[Document]) -> None:
        self.documents = tuple(documents)
        if not self.documents:
            raise ValueError("at least one document is required")
        self._document_tokens = {
            document.source_id: _tokens(f"{document.title} {document.text}")
            for document in self.documents
        }
        frequencies: dict[str, int] = {}
        for tokens in self._document_tokens.values():
            for token in tokens:
                frequencies[token] = frequencies.get(token, 0) + 1
        total = len(self.documents)
        self._idf = {
            token: math.log((total + 1) / (frequency + 1)) + 1.0
            for token, frequency in frequencies.items()
        }

    def search(self, query: str, top_k: int = 3) -> list[Evidence]:
        if top_k < 1:
            raise ValueError("top_k must be at least 1")
        query_tokens = _tokens(query)
        ranked: list[tuple[int, float, str, Document]] = []
        for document in self.documents:
            if not document.is_current:
                continue
            overlap = query_tokens & self._document_tokens[document.source_id]
            score = sum(self._idf[token] for token in overlap)
            if score > 0:
                ranked.append(
                    (document.authority, score, document.source_id, document)
                )
        ranked.sort(key=lambda item: (-item[0], -item[1], item[2]))
        return [
            Evidence(
                source_id=document.source_id,
                title=document.title,
                excerpt=document.text,
                score=round(score, 6),
                citation=f"[{document.source_id}]",
                authority=authority,
            )
            for authority, score, _, document in ranked[:top_k]
        ]


def retrieval_response(query: str, evidence: list[Evidence]) -> dict[str, object]:
    """Build a response whose citations can only originate in evidence."""
    return {
        "query": query,
        "evidence": [item.to_dict() for item in evidence],
        "citations": [item.citation for item in evidence],
    }

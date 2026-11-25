"""Offline retrieval and grounded agent loop for a fictional corpus."""

from .agent import AgentResponse, OfflineAgent
from .retrieval import Document, Evidence, Retriever, load_documents

__all__ = [
    "AgentResponse", "Document", "Evidence", "OfflineAgent", "Retriever",
    "load_documents",
]

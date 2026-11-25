import json
from pathlib import Path
import tempfile
import unittest

from enterprise_rag.cli import DEFAULT_CORPUS, DEFAULT_EVALUATION, evaluate
from enterprise_rag.retrieval import Retriever, load_documents, retrieval_response

AUTHORITY_ADVERSARIAL_CORPUS = (
    DEFAULT_CORPUS.parent / "documents.authority-adversarial.v1.json"
)


class RetrievalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.retriever = Retriever(load_documents(DEFAULT_CORPUS))

    def test_expected_security_policy_ranks_first(self) -> None:
        evidence = self.retriever.search(
            "critical security incident escalation time", top_k=2
        )
        self.assertEqual("SEC-IR-001", evidence[0].source_id)

    def test_current_authoritative_policy_beats_adversarial_sources(self) -> None:
        retriever = Retriever(load_documents(AUTHORITY_ADVERSARIAL_CORPUS))
        evidence = retriever.search(
            "critical security incident escalation", top_k=3
        )

        self.assertEqual("SEC-POLICY-CURRENT", evidence[0].source_id)
        self.assertNotIn(
            "SEC-NOTE-OBSOLETE", [item.source_id for item in evidence]
        )
        self.assertGreater(evidence[0].authority, evidence[1].authority)

    def test_citations_are_exactly_the_retrieved_sources(self) -> None:
        evidence = self.retriever.search("invoice approval reviewers", top_k=2)
        response = retrieval_response("invoice approval reviewers", evidence)
        retrieved_ids = {item.source_id for item in evidence}
        cited_ids = {citation.strip("[]") for citation in response["citations"]}
        self.assertEqual(retrieved_ids, cited_ids)

    def test_no_overlap_returns_no_evidence_or_citations(self) -> None:
        response = retrieval_response(
            "xylophone nebula", self.retriever.search("xylophone nebula")
        )
        self.assertEqual([], response["evidence"])
        self.assertEqual([], response["citations"])

    def test_versioned_evaluation_meets_threshold(self) -> None:
        result = evaluate(self.retriever, DEFAULT_EVALUATION)
        self.assertTrue(result["passed"])
        self.assertGreaterEqual(result["score"], result["threshold"])
        self.assertTrue(all(result["budget_results"].values()))

    def test_evaluation_reports_deterministic_latency_percentiles(self) -> None:
        timestamps_ms = iter([0, 1, 10, 12, 20, 23, 30, 34])
        result = evaluate(
            self.retriever,
            DEFAULT_EVALUATION,
            clock_ns=lambda: next(timestamps_ms) * 1_000_000,
        )
        self.assertEqual({"p50": 2.5, "p95": 3.85}, result["latency_ms"])
        self.assertEqual([1.0, 2.0, 3.0, 4.0], [
            case["latency_ms"] for case in result["cases"]
        ])

    def test_offline_evaluation_has_zero_external_cost(self) -> None:
        result = evaluate(self.retriever, DEFAULT_EVALUATION)
        self.assertEqual(0.0, result["external_cost_usd"])
        self.assertEqual(0.0, result["budgets"]["external_cost_usd"])
        self.assertTrue(result["budget_results"]["external_cost_usd"])

    def test_latency_budget_failure_fails_evaluation(self) -> None:
        specification = json.loads(DEFAULT_EVALUATION.read_text(encoding="utf-8"))
        specification["budgets"]["latency_p95_ms"] = 3.8
        timestamps_ms = iter([0, 1, 10, 12, 20, 23, 30, 34])
        with tempfile.TemporaryDirectory() as directory:
            evaluation_path = Path(directory) / "evaluation.json"
            evaluation_path.write_text(json.dumps(specification), encoding="utf-8")
            result = evaluate(
                self.retriever,
                evaluation_path,
                clock_ns=lambda: next(timestamps_ms) * 1_000_000,
            )
        self.assertEqual(3.85, result["latency_ms"]["p95"])
        self.assertFalse(result["budget_results"]["latency_p95_ms"])
        self.assertFalse(result["passed"])

    def test_evaluation_declares_supported_metric(self) -> None:
        payload = json.loads(DEFAULT_EVALUATION.read_text(encoding="utf-8"))
        self.assertEqual("recall_at_k", payload["metric"])

    def test_top_k_must_be_positive(self) -> None:
        with self.assertRaises(ValueError):
            self.retriever.search("security", top_k=0)


if __name__ == "__main__":
    unittest.main()

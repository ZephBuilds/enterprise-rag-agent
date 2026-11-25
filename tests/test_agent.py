import json
from pathlib import Path
import tempfile
import unittest

from enterprise_rag.agent import OfflineAgent
from enterprise_rag.cli import (
    DEFAULT_AGENT_EVALUATION,
    DEFAULT_CORPUS,
    evaluate_agent,
    main,
)
from enterprise_rag.retrieval import Retriever, load_documents


class OfflineAgentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.agent = OfflineAgent(Retriever(load_documents(DEFAULT_CORPUS)))

    def test_positive_answer_is_exact_extract_with_evidence_citation(self) -> None:
        response = self.agent.run(
            "How quickly must a critical security incident be escalated?"
        )
        self.assertEqual("retrieve", response.action)
        self.assertEqual(
            "Critical security incidents must be escalated to the incident "
            "commander within 15 minutes of detection.",
            response.answer,
        )
        evidence_by_citation = {
            item.citation: item.excerpt for item in response.evidence
        }
        self.assertTrue(set(response.citations) <= set(evidence_by_citation))
        self.assertTrue(any(
            response.answer in evidence_by_citation[citation]
            for citation in response.citations
        ))

    def test_unknown_subject_abstains_without_claim_or_citation(self) -> None:
        response = self.agent.run("What is served on the cafeteria lunch menu?")
        self.assertEqual("abstain", response.action)
        self.assertIsNone(response.answer)
        self.assertEqual((), response.citations)

    def test_partial_overlap_is_insufficient_and_abstains(self) -> None:
        response = self.agent.run("What salary do employees receive?")
        self.assertEqual("abstain", response.action)
        self.assertIsNone(response.answer)

    def test_versioned_grounding_evaluation_passes(self) -> None:
        result = evaluate_agent(self.agent, DEFAULT_AGENT_EVALUATION)
        self.assertTrue(result["passed"])
        self.assertEqual(1.0, result["grounding_rate"])
        self.assertEqual(1.0, result["decision_accuracy"])
        self.assertEqual(1.0, result["adversarial_pass_rate"])
        self.assertEqual(1.0, result["adversarial_threshold"])
        self.assertGreaterEqual(
            sum(case["adversarial"] for case in result["cases"]), 2
        )
        self.assertTrue(all(case["passed"] for case in result["cases"]))

    def test_versioned_authority_conflict_gate_selects_its_corpus(self) -> None:
        evaluation = (
            DEFAULT_AGENT_EVALUATION.parent
            / "agent.authority-adversarial.v1.json"
        )
        result = evaluate_agent(self.agent, evaluation)

        self.assertTrue(result["passed"])
        case = result["cases"][0]
        self.assertEqual(["[SEC-POLICY-CURRENT]"], case["citations"])
        self.assertNotIn("SEC-NOTE-OBSOLETE", case["retrieved_source_ids"])
        self.assertIn("SEC-BLOG-UNTRUSTED", case["retrieved_source_ids"])
        self.assertTrue(case["absent_sources_correct"])

    def test_adversarial_subgate_fails_below_its_threshold(self) -> None:
        specification = json.loads(
            DEFAULT_AGENT_EVALUATION.read_text(encoding="utf-8")
        )
        adversarial_case = next(
            case for case in specification["cases"] if case.get("adversarial")
        )
        adversarial_case["expected_answer"] = "Unsupported adversarial claim."
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "failing-adversarial-evaluation.json"
            path.write_text(json.dumps(specification), encoding="utf-8")
            result = evaluate_agent(self.agent, path)
        self.assertLess(
            result["adversarial_pass_rate"],
            result["adversarial_threshold"],
        )
        self.assertFalse(result["passed"])

    def test_cli_returns_nonzero_when_agent_gate_fails(self) -> None:
        specification = json.loads(
            DEFAULT_AGENT_EVALUATION.read_text(encoding="utf-8")
        )
        specification["cases"][0]["expected_answer"] = "Unsupported claim."
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "failing-agent-evaluation.json"
            path.write_text(json.dumps(specification), encoding="utf-8")
            exit_code = main(["evaluate-agent", "--evaluation", str(path)])
        self.assertEqual(1, exit_code)

    def test_overlap_threshold_must_be_positive(self) -> None:
        retriever = Retriever(load_documents(DEFAULT_CORPUS))
        with self.assertRaises(ValueError):
            OfflineAgent(retriever, min_query_token_overlap=0)


if __name__ == "__main__":
    unittest.main()

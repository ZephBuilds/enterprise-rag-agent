import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
README = PROJECT_ROOT / "README.md"
ARCHITECTURE = PROJECT_ROOT / "docs" / "architecture.md"
DEMO_OUTPUT = PROJECT_ROOT / "docs" / "demo-output.json"
VERIFY_OUTPUT = PROJECT_ROOT / "docs" / "verify-output.v1.json"
INVALID_EVALUATION_OUTPUT = (
    PROJECT_ROOT / "docs" / "invalid-evaluation-output.v1.json"
)
CASE_STUDY = PROJECT_ROOT / "docs" / "case-study.md"
CI_WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
RETRIEVAL_EVALUATION = PROJECT_ROOT / "evaluation" / "retrieval.v1.json"
INVALID_RETRIEVAL_EVALUATION = (
    PROJECT_ROOT / "evaluation" / "retrieval.invalid.v1.json"
)
AGENT_EVALUATION = PROJECT_ROOT / "evaluation" / "agent.v1.json"
AUTHORITY_EVALUATION = (
    PROJECT_ROOT / "evaluation" / "agent.authority-adversarial.v1.json"
)
ARCHITECTURE_BOUNDARIES_REFERENCE = (
    "architecture.md#trust-and-security-boundaries"
)
DEMO_QUERY = "How quickly must a critical security incident be escalated?"
CANONICAL_CI_REPRODUCTION_BLOCK = """```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 -m compileall -q src tests
PYTHONPATH=src python3 -m enterprise_rag.cli verify
```"""
CANONICAL_CI_COMMANDS = tuple(
    CANONICAL_CI_REPRODUCTION_BLOCK.removeprefix("```bash\n")
    .removesuffix("\n```")
    .splitlines()
)


class PublicArtifactsContractTest(unittest.TestCase):
    def test_saved_demo_output_exactly_matches_real_cli(self) -> None:
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(PROJECT_ROOT / "src")
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "enterprise_rag.cli",
                "demo",
                DEMO_QUERY,
                "--top-k",
                "2",
            ],
            cwd=PROJECT_ROOT,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertEqual("", result.stderr)
        self.assertEqual(DEMO_OUTPUT.read_text(encoding="utf-8"), result.stdout)

        payload = json.loads(result.stdout)
        evidence_citations = {
            item["citation"] for item in payload["evidence"]
        }
        self.assertTrue(set(payload["citations"]).issubset(evidence_citations))

    def test_saved_verify_output_exactly_matches_real_cli(self) -> None:
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(PROJECT_ROOT / "src")
        result = subprocess.run(
            [sys.executable, "-m", "enterprise_rag.cli", "verify"],
            cwd=PROJECT_ROOT,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertEqual("", result.stderr)
        self.assertEqual(VERIFY_OUTPUT.read_text(encoding="utf-8"), result.stdout)

        payload = json.loads(result.stdout)
        self.assertTrue(payload["passed"])
        self.assertTrue(
            all(check["passed"] for check in payload["checks"].values())
        )

    def test_saved_invalid_evaluation_output_exactly_matches_real_cli(self) -> None:
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(PROJECT_ROOT / "src")
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "enterprise_rag.cli",
                "evaluate",
                "--evaluation",
                str(INVALID_RETRIEVAL_EVALUATION),
            ],
            cwd=PROJECT_ROOT,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(2, result.returncode)
        self.assertEqual("", result.stdout)
        self.assertEqual(
            INVALID_EVALUATION_OUTPUT.read_text(encoding="utf-8"),
            result.stderr,
        )
        for forbidden_value in (
            "Traceback",
            str(PROJECT_ROOT),
            str(INVALID_RETRIEVAL_EVALUATION),
            "SYNTHETIC_INPUT_MUST_NOT_LEAK",
            "SYNTHETIC-SOURCE",
        ):
            with self.subTest(forbidden_value=forbidden_value):
                self.assertNotIn(forbidden_value, result.stderr)

    def test_readme_and_architecture_keep_essential_public_contract(self) -> None:
        readme = README.read_text(encoding="utf-8")
        architecture = ARCHITECTURE.read_text(encoding="utf-8")

        for reference in (
            "docs/architecture.md",
            "docs/demo-output.json",
            "docs/verify-output.v1.json",
            "docs/invalid-evaluation-output.v1.json",
            "docs/case-study.md",
        ):
            with self.subTest(reference=reference):
                self.assertIn(reference, readme)

        for stage in (
            "Untrusted user query",
            "Currency filter and authority metadata",
            "Lexical retriever",
            "Evidence and citation builder",
            "Deterministic JSON output",
            "Snapshot and evaluation gates",
        ):
            with self.subTest(stage=stage):
                self.assertIn(stage, architecture)

    def test_public_reproduction_uses_the_canonical_ci_gates(self) -> None:
        readme = README.read_text(encoding="utf-8")
        case_study = CASE_STUDY.read_text(encoding="utf-8")
        workflow = CI_WORKFLOW.read_text(encoding="utf-8")

        for artifact_name, artifact in (
            ("README", readme),
            ("case study", case_study),
        ):
            with self.subTest(artifact=artifact_name):
                self.assertEqual(
                    1, artifact.count(CANONICAL_CI_REPRODUCTION_BLOCK)
                )

        # The case study has one reproduction block: `verify` already runs the
        # individual retrieval and agent evaluations, so listing them again
        # would duplicate work for reviewers.
        self.assertEqual(1, case_study.count("```bash"))

        workflow_positions = []
        for command in CANONICAL_CI_COMMANDS:
            with self.subTest(workflow_command=command):
                self.assertEqual(1, workflow.count(f"run: {command}"))
                workflow_positions.append(workflow.index(f"run: {command}"))
        self.assertEqual(sorted(workflow_positions), workflow_positions)

    def test_case_study_metrics_match_versioned_gates(self) -> None:
        case_study = CASE_STUDY.read_text(encoding="utf-8")
        retrieval = json.loads(RETRIEVAL_EVALUATION.read_text(encoding="utf-8"))
        agent = json.loads(AGENT_EVALUATION.read_text(encoding="utf-8"))
        authority = json.loads(AUTHORITY_EVALUATION.read_text(encoding="utf-8"))
        verify_output_reference = "verify-output.v1.json"

        self.assertIn(f"]({verify_output_reference})", case_study)
        self.assertTrue(
            (CASE_STUDY.parent / verify_output_reference).resolve().is_file()
        )
        verify_output = json.loads(VERIFY_OUTPUT.read_text(encoding="utf-8"))
        self.assertTrue(verify_output["passed"])
        self.assertTrue(verify_output["checks"])
        self.assertTrue(
            all(check["passed"] for check in verify_output["checks"].values())
        )

        expected_claims = (
            f"**{retrieval['threshold']:.0%} recall@{retrieval['top_k']}**",
            f"**{agent['threshold']:.0%} grounding**",
            f"**{agent['adversarial_threshold']:.0%} pass rate**",
            f"**USD {retrieval['budgets']['external_cost_usd']:.2f}**",
            f"**p95 ≤ {retrieval['budgets']['latency_p95_ms']:g} ms**",
        )
        for claim in expected_claims:
            with self.subTest(claim=claim):
                self.assertIn(claim, case_study)

        self.assertEqual(
            agent["adversarial_threshold"], authority["adversarial_threshold"]
        )
        for reference in (
            "../evaluation/retrieval.v1.json",
            "../evaluation/agent.v1.json",
            "../evaluation/agent.authority-adversarial.v1.json",
        ):
            with self.subTest(reference=reference):
                self.assertIn(reference, case_study)
                self.assertTrue((CASE_STUDY.parent / reference).resolve().is_file())

    def test_case_study_links_sanitized_invalid_evaluation_artifact(self) -> None:
        case_study = CASE_STUDY.read_text(encoding="utf-8")
        artifact_reference = "invalid-evaluation-output.v1.json"

        self.assertIn(f"]({artifact_reference})", case_study)
        artifact_path = (CASE_STUDY.parent / artifact_reference).resolve()
        self.assertTrue(artifact_path.is_file())

        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
        self.assertEqual("invalid_evaluation", payload["error"]["code"])
        self.assertEqual(
            "Evaluation input is invalid.", payload["error"]["message"]
        )

    def test_case_study_links_canonical_trust_boundaries(self) -> None:
        case_study = CASE_STUDY.read_text(encoding="utf-8")

        self.assertIn(
            f"]({ARCHITECTURE_BOUNDARIES_REFERENCE})",
            case_study,
        )
        relative_path, _, _ = ARCHITECTURE_BOUNDARIES_REFERENCE.partition("#")
        architecture_path = (CASE_STUDY.parent / relative_path).resolve()
        self.assertTrue(architecture_path.is_file())

        architecture = architecture_path.read_text(encoding="utf-8")
        for boundary_marker in (
            "## Trust and security boundaries",
            "**Untrusted input:**",
            "**Governance boundary:**",
            "**Output boundary:**",
            "**Operational limit:**",
            "production-load, or model-quality claim.",
        ):
            with self.subTest(boundary_marker=boundary_marker):
                self.assertIn(boundary_marker, architecture)


if __name__ == "__main__":
    unittest.main()

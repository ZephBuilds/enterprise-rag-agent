import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from enterprise_rag.cli import main


class EvaluationCliContractTest(unittest.TestCase):
    @staticmethod
    def _valid_retrieval_evaluation() -> dict[str, object]:
        return {
            "version": 1,
            "metric": "recall_at_k",
            "threshold": 1.0,
            "top_k": 1,
            "budgets": {
                "latency_p95_ms": 50.0,
                "external_cost_usd": 0.0,
            },
            "cases": [
                {
                    "query": "PRIVATE_INPUT_SENTINEL",
                    "relevant_source_ids": ["SEC-IR-001"],
                }
            ],
        }

    @staticmethod
    def _valid_agent_evaluation() -> dict[str, object]:
        return {
            "version": 1,
            "metric": "grounding_rate",
            "threshold": 1.0,
            "top_k": 1,
            "cases": [
                {
                    "query": "PRIVATE_INPUT_SENTINEL",
                    "expected_action": "retrieve",
                    "expected_answer": "answer",
                    "expected_source_id": "SEC-IR-001",
                }
            ],
        }

    def _assert_sanitized_error(self, command: str, path: Path) -> None:
        expected_error = {
            "error": {
                "code": "invalid_evaluation",
                "message": "Evaluation input is invalid.",
            }
        }
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            with contextlib.redirect_stderr(stderr):
                exit_code = main([command, "--evaluation", str(path)])

        self.assertEqual(2, exit_code)
        self.assertEqual("", stdout.getvalue())
        self.assertEqual(
            json.dumps(expected_error, sort_keys=True) + "\n", stderr.getvalue()
        )
        self.assertNotIn("Traceback", stderr.getvalue())
        self.assertNotIn("PRIVATE_INPUT_SENTINEL", stderr.getvalue())
        self.assertNotIn("PRIVATE_PATH_SENTINEL", stderr.getvalue())

    def test_invalid_evaluations_return_sanitized_machine_readable_error(self) -> None:
        retrieval = self._valid_retrieval_evaluation()
        agent = self._valid_agent_evaluation()

        retrieval_mutations = {
            "non_object_root": [],
            "missing_version": {k: v for k, v in retrieval.items() if k != "version"},
            "boolean_version": {**retrieval, "version": True},
            "wrong_metric": {**retrieval, "metric": "grounding_rate"},
            "threshold_out_of_range": {**retrieval, "threshold": 1.1},
            "boolean_top_k": {**retrieval, "top_k": True},
            "missing_budgets": {k: v for k, v in retrieval.items() if k != "budgets"},
            "negative_budget": {
                **retrieval,
                "budgets": {
                    "latency_p95_ms": -1,
                    "external_cost_usd": 0,
                },
            },
            "empty_query": {
                **retrieval,
                "cases": [{"query": " ", "relevant_source_ids": ["source"]}],
            },
            "empty_relevant_sources": {
                **retrieval,
                "cases": [{"query": "query", "relevant_source_ids": []}],
            },
            "invalid_relevant_source": {
                **retrieval,
                "cases": [{"query": "query", "relevant_source_ids": [""]}],
            },
        }
        agent_mutations = {
            "empty_cases": {**agent, "cases": []},
            "case_not_object": {**agent, "cases": ["PRIVATE_INPUT_SENTINEL"]},
            "wrong_metric": {**agent, "metric": "recall_at_k"},
            "invalid_adversarial_threshold": {
                **agent,
                "adversarial_threshold": 1.1,
            },
            "unknown_corpus_selector": {
                **agent,
                "corpus": "../../PRIVATE_PATH_SENTINEL.json",
            },
            "non_string_corpus_selector": {
                **agent,
                "corpus": ["default-v1"],
            },
            "non_boolean_adversarial_marker": {
                **agent,
                "cases": [
                    {
                        "query": "query",
                        "adversarial": "yes",
                        "expected_action": "abstain",
                    }
                ],
            },
            "invalid_absent_source": {
                **agent,
                "cases": [
                    {
                        **agent["cases"][0],
                        "expected_absent_source_ids": [""],
                    }
                ],
            },
            "invalid_action": {
                **agent,
                "cases": [{"query": "query", "expected_action": "answer"}],
            },
            "retrieve_missing_answer": {
                **agent,
                "cases": [
                    {
                        "query": "query",
                        "expected_action": "retrieve",
                        "expected_source_id": "source",
                    }
                ],
            },
            "retrieve_empty_source": {
                **agent,
                "cases": [
                    {
                        "query": "query",
                        "expected_action": "retrieve",
                        "expected_answer": "answer",
                        "expected_source_id": " ",
                    }
                ],
            },
            "abstain_with_answer": {
                **agent,
                "cases": [
                    {
                        "query": "query",
                        "expected_action": "abstain",
                        "expected_answer": "answer",
                    }
                ],
            },
        }

        for command, invalid_inputs in (
            ("evaluate", retrieval_mutations),
            ("evaluate-agent", agent_mutations),
        ):
            for input_name, specification in invalid_inputs.items():
                with self.subTest(command=command, input=input_name):
                    with tempfile.TemporaryDirectory(
                        prefix="PRIVATE_PATH_SENTINEL-"
                    ) as directory:
                        path = Path(directory) / "evaluation.json"
                        path.write_text(json.dumps(specification), encoding="utf-8")
                        self._assert_sanitized_error(command, path)

    def test_unreadable_or_undecodable_evaluations_are_sanitized(self) -> None:
        for command in ("evaluate", "evaluate-agent"):
            for input_name in (
                "missing",
                "directory",
                "invalid_utf8",
                "malformed_json",
            ):
                with self.subTest(command=command, input=input_name):
                    with tempfile.TemporaryDirectory(
                        prefix="PRIVATE_PATH_SENTINEL-"
                    ) as directory:
                        root = Path(directory)
                        path = root / "PRIVATE_INPUT_SENTINEL.json"
                        if input_name == "directory":
                            path.mkdir()
                        elif input_name == "invalid_utf8":
                            path.write_bytes(b"\xffPRIVATE_INPUT_SENTINEL")
                        elif input_name == "malformed_json":
                            path.write_text(
                                '{"private": "PRIVATE_INPUT_SENTINEL"',
                                encoding="utf-8",
                            )
                        self._assert_sanitized_error(command, path)


if __name__ == "__main__":
    unittest.main()

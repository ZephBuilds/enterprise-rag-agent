import contextlib
import io
import json
import unittest
from unittest.mock import patch

from enterprise_rag.cli import main


class VerifyCliContractTest(unittest.TestCase):
    @staticmethod
    def _invoke() -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            with contextlib.redirect_stderr(stderr):
                exit_code = main(["verify"])
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def test_verify_runs_real_demo_and_all_three_gates(self) -> None:
        exit_code, stdout, stderr = self._invoke()

        self.assertEqual(0, exit_code)
        self.assertEqual("", stderr)
        expected = {
            "checks": {
                "agent": {"passed": True},
                "agent_authority_adversarial": {"passed": True},
                "demo": {"passed": True},
                "retrieval": {"passed": True},
            },
            "passed": True,
        }
        self.assertEqual(expected, json.loads(stdout))
        self.assertEqual(json.dumps(expected, indent=2, sort_keys=True) + "\n", stdout)
        for forbidden_key in (
            "query",
            "cases",
            "evaluation/",
            "fixtures/",
            "latency_ms",
        ):
            self.assertNotIn(forbidden_key, stdout)

    @patch("enterprise_rag.cli.evaluate_agent")
    @patch("enterprise_rag.cli.evaluate")
    @patch("enterprise_rag.cli.retrieval_response")
    def test_verify_is_sanitized_and_fails_if_any_gate_fails(
        self,
        demo_response,
        retrieval_gate,
        agent_gate,
    ) -> None:
        demo_response.return_value = {
            "query": "PRIVATE_QUERY_SENTINEL",
            "path": "PRIVATE_PATH_SENTINEL",
        }
        retrieval_gate.return_value = {
            "passed": False,
            "cases": ["PRIVATE_QUERY_SENTINEL"],
        }
        agent_gate.side_effect = [
            {"passed": True},
            {"passed": False, "path": "PRIVATE_PATH_SENTINEL"},
        ]

        exit_code, stdout, stderr = self._invoke()
        output = json.loads(stdout)

        self.assertEqual(1, exit_code)
        self.assertEqual("", stderr)
        self.assertFalse(output["passed"])
        self.assertFalse(output["checks"]["retrieval"]["passed"])
        self.assertFalse(
            output["checks"]["agent_authority_adversarial"]["passed"]
        )
        self.assertEqual(1, demo_response.call_count)
        self.assertEqual(1, retrieval_gate.call_count)
        self.assertEqual(2, agent_gate.call_count)
        self.assertNotIn("PRIVATE_QUERY_SENTINEL", stdout)
        self.assertNotIn("PRIVATE_PATH_SENTINEL", stdout)


if __name__ == "__main__":
    unittest.main()

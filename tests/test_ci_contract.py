from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
REQUIRED_QUALITY_GATE_COMMANDS = (
    "run: PYTHONPATH=src python3 -m unittest discover -s tests -v",
    "run: python3 -m compileall -q src tests",
    "run: PYTHONPATH=src python3 -m enterprise_rag.cli verify",
)
CONTAINER_BUILD_COMMAND = (
    "run: docker build --network none --tag enterprise-rag-agent:ci ."
)
CONTAINER_RUN_COMMAND = (
    "run: docker run --rm --network none enterprise-rag-agent:ci"
)


class CiContractTest(unittest.TestCase):
    def workflow_lines(self) -> list[str]:
        return [
            line.strip()
            for line in CI_WORKFLOW.read_text(encoding="utf-8").splitlines()
        ]

    def test_workflow_invokes_canonical_quality_gates_once_in_order(self) -> None:
        workflow_lines = self.workflow_lines()

        for command in REQUIRED_QUALITY_GATE_COMMANDS:
            self.assertEqual(1, workflow_lines.count(command))

        positions = [
            workflow_lines.index(command)
            for command in REQUIRED_QUALITY_GATE_COMMANDS
        ]
        self.assertEqual(sorted(positions), positions)

    def test_workflow_builds_and_runs_container_with_network_disabled(self) -> None:
        workflow_lines = self.workflow_lines()

        self.assertEqual(1, workflow_lines.count(CONTAINER_BUILD_COMMAND))
        self.assertEqual(1, workflow_lines.count(CONTAINER_RUN_COMMAND))


if __name__ == "__main__":
    unittest.main()

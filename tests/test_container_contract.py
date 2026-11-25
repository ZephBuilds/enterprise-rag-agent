from pathlib import Path
import json
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = PROJECT_ROOT / "Dockerfile"
DOCKERIGNORE = PROJECT_ROOT / ".dockerignore"

REQUIRED_GATE_COMMANDS = (
    "python3 -m unittest discover -s tests -v",
    "python3 -m compileall -q src tests",
    "PYTHONPATH=src python3 -m enterprise_rag.cli verify",
)


class ContainerContractTest(unittest.TestCase):
    def test_default_command_runs_every_gate_in_order(self) -> None:
        lines = [
            line.strip()
            for line in DOCKERFILE.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        command_line = next(line for line in lines if line.startswith("CMD "))
        command = json.loads(command_line.removeprefix("CMD "))

        self.assertEqual(["sh", "-c"], command[:2])
        gate_command = command[2]
        self.assertEqual(" && ".join(REQUIRED_GATE_COMMANDS), gate_command)

    def test_image_is_dependency_free_and_runs_unprivileged(self) -> None:
        dockerfile = DOCKERFILE.read_text(encoding="utf-8")

        self.assertIn("FROM python:3.12-slim", dockerfile)
        self.assertIn("PYTHONPATH=/app/src", dockerfile)
        self.assertIn("COPY --chown=65532:65532 . .", dockerfile)
        self.assertIn("USER 65532:65532", dockerfile)
        for forbidden in ("RUN pip", "pip install", "apt-get", "curl ", "wget "):
            self.assertNotIn(forbidden, dockerfile)

    def test_build_context_excludes_secrets_and_generated_files(self) -> None:
        ignored = {
            line.strip()
            for line in DOCKERIGNORE.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }

        self.assertTrue(
            {".git", ".env", ".env.*", "*.pem", "*.key", "__pycache__/"}
            <= ignored
        )
        self.assertNotIn(".github", ignored)


if __name__ == "__main__":
    unittest.main()

"""Command-line demo and offline quality gates."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from time import perf_counter_ns
from typing import Callable, Literal, cast

from .agent import OfflineAgent
from .retrieval import Retriever, load_documents, retrieval_response


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CORPUS = PROJECT_ROOT / "fixtures" / "documents.v1.json"
DEFAULT_EVALUATION = PROJECT_ROOT / "evaluation" / "retrieval.v1.json"
DEFAULT_AGENT_EVALUATION = PROJECT_ROOT / "evaluation" / "agent.v1.json"
AUTHORITY_ADVERSARIAL_EVALUATION = (
    PROJECT_ROOT / "evaluation" / "agent.authority-adversarial.v1.json"
)
AUTHORITY_ADVERSARIAL_CORPUS = (
    PROJECT_ROOT / "fixtures" / "documents.authority-adversarial.v1.json"
)
CANONICAL_DEMO_QUERY = (
    "How quickly must a critical security incident be escalated?"
)
AGENT_CORPORA = {
    "default-v1": DEFAULT_CORPUS,
    "authority-adversarial-v1": AUTHORITY_ADVERSARIAL_CORPUS,
}


class InvalidEvaluationError(ValueError):
    """Raised when an evaluation file cannot define runnable cases."""


EvaluationKind = Literal["retrieval", "agent"]


def _is_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _is_non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _load_evaluation(
    evaluation_path: Path, kind: EvaluationKind
) -> dict[str, object]:
    try:
        specification = json.loads(evaluation_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise InvalidEvaluationError from error
    if not isinstance(specification, dict):
        raise InvalidEvaluationError

    version = specification.get("version")
    metric = specification.get("metric")
    threshold = specification.get("threshold")
    top_k = specification.get("top_k")
    expected_metric = "recall_at_k" if kind == "retrieval" else "grounding_rate"
    if (
        not isinstance(version, int)
        or isinstance(version, bool)
        or version <= 0
        or metric != expected_metric
        or not _is_number(threshold)
        or not 0 <= threshold <= 1
        or not isinstance(top_k, int)
        or isinstance(top_k, bool)
        or top_k <= 0
    ):
        raise InvalidEvaluationError

    if kind == "retrieval":
        budgets = specification.get("budgets")
        if not isinstance(budgets, dict):
            raise InvalidEvaluationError
        if any(
            not _is_number(budgets.get(name)) or budgets[name] < 0
            for name in ("latency_p95_ms", "external_cost_usd")
        ):
            raise InvalidEvaluationError
    else:
        corpus = specification.get("corpus", "default-v1")
        if not isinstance(corpus, str) or corpus not in AGENT_CORPORA:
            raise InvalidEvaluationError
        adversarial_threshold = specification.get(
            "adversarial_threshold", threshold
        )
        if (
            not _is_number(adversarial_threshold)
            or not 0 <= adversarial_threshold <= 1
        ):
            raise InvalidEvaluationError

    cases = specification.get("cases")
    if not isinstance(cases, list) or not cases:
        raise InvalidEvaluationError
    for case in cases:
        if not isinstance(case, dict) or not _is_non_empty_string(case.get("query")):
            raise InvalidEvaluationError
        if kind == "retrieval":
            relevant_source_ids = case.get("relevant_source_ids")
            if (
                not isinstance(relevant_source_ids, list)
                or not relevant_source_ids
                or any(
                    not _is_non_empty_string(source_id)
                    for source_id in relevant_source_ids
                )
            ):
                raise InvalidEvaluationError
            continue

        expected_action = case.get("expected_action")
        if expected_action not in ("retrieve", "abstain"):
            raise InvalidEvaluationError
        if "adversarial" in case and not isinstance(case["adversarial"], bool):
            raise InvalidEvaluationError
        for optional_field in ("expected_answer", "expected_source_id"):
            if optional_field in case and not _is_non_empty_string(
                case[optional_field]
            ):
                raise InvalidEvaluationError
        expected_absent_source_ids = case.get("expected_absent_source_ids", [])
        if (
            not isinstance(expected_absent_source_ids, list)
            or any(
                not _is_non_empty_string(source_id)
                for source_id in expected_absent_source_ids
            )
        ):
            raise InvalidEvaluationError
        has_expected_answer = "expected_answer" in case
        has_expected_source = "expected_source_id" in case
        if expected_action == "retrieve" and not (
            has_expected_answer and has_expected_source
        ):
            raise InvalidEvaluationError
        if expected_action == "abstain" and (
            has_expected_answer or has_expected_source
        ):
            raise InvalidEvaluationError
    return cast(dict[str, object], specification)


def _percentile(values: list[float], percentile: float) -> float:
    """Return a linearly interpolated percentile for a non-empty sample."""
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * weight


def evaluate(
    retriever: Retriever,
    evaluation_path: Path,
    clock_ns: Callable[[], int] = perf_counter_ns,
) -> dict[str, object]:
    specification = _load_evaluation(evaluation_path, "retrieval")
    top_k = int(specification["top_k"])
    case_results = []
    recalls = []
    latencies_ms = []
    for case in specification["cases"]:
        started_ns = clock_ns()
        evidence = retriever.search(case["query"], top_k=top_k)
        latency_ms = (clock_ns() - started_ns) / 1_000_000
        latencies_ms.append(latency_ms)
        retrieved = {item.source_id for item in evidence}
        relevant = set(case["relevant_source_ids"])
        recall = len(retrieved & relevant) / len(relevant)
        recalls.append(recall)
        case_results.append(
            {
                "query": case["query"],
                "retrieved_source_ids": [item.source_id for item in evidence],
                "relevant_source_ids": sorted(relevant),
                "recall": recall,
                "latency_ms": round(latency_ms, 6),
            }
        )
    score = sum(recalls) / len(recalls)
    threshold = float(specification["threshold"])
    latency_p50_ms = _percentile(latencies_ms, 0.50)
    latency_p95_ms = _percentile(latencies_ms, 0.95)
    external_cost_usd = 0.0
    budgets = specification["budgets"]
    latency_budget_ms = float(budgets["latency_p95_ms"])
    cost_budget_usd = float(budgets["external_cost_usd"])
    budget_results = {
        "latency_p95_ms": latency_p95_ms <= latency_budget_ms,
        "external_cost_usd": external_cost_usd <= cost_budget_usd,
    }
    return {
        "evaluation_version": specification["version"],
        "metric": specification["metric"],
        "top_k": top_k,
        "score": score,
        "threshold": threshold,
        "latency_ms": {
            "p50": round(latency_p50_ms, 6),
            "p95": round(latency_p95_ms, 6),
        },
        "external_cost_usd": external_cost_usd,
        "budgets": {
            "latency_p95_ms": latency_budget_ms,
            "external_cost_usd": cost_budget_usd,
        },
        "budget_results": budget_results,
        "passed": score >= threshold and all(budget_results.values()),
        "cases": case_results,
    }


def evaluate_agent(
    agent: OfflineAgent,
    evaluation_path: Path,
) -> dict[str, object]:
    """Evaluate routing and prove every returned claim is extractive."""
    specification = _load_evaluation(evaluation_path, "agent")
    corpus = specification.get("corpus", "default-v1")
    if corpus != "default-v1":
        agent = OfflineAgent(Retriever(load_documents(AGENT_CORPORA[corpus])))
    case_results = []
    grounded_values = []
    decision_values = []
    adversarial_values = []
    for case in specification["cases"]:
        response = agent.run(case["query"], top_k=int(specification["top_k"]))
        evidence_by_citation = {
            item.citation: item for item in response.evidence
        }
        citations_valid = bool(response.citations) and all(
            citation in evidence_by_citation for citation in response.citations
        )
        answer_is_extract = bool(response.answer) and any(
            response.answer in evidence_by_citation[citation].excerpt
            for citation in response.citations
            if citation in evidence_by_citation
        )
        if response.action == "abstain":
            grounded = response.answer is None and not response.citations
        else:
            grounded = citations_valid and answer_is_extract
        decision_correct = response.action == case["expected_action"]
        expected_answer_correct = (
            "expected_answer" not in case
            or response.answer == case["expected_answer"]
        )
        expected_source_correct = (
            "expected_source_id" not in case
            or f"[{case['expected_source_id']}]" in response.citations
        )
        retrieved_source_ids = [item.source_id for item in response.evidence]
        absent_sources_correct = not (
            set(case.get("expected_absent_source_ids", []))
            & set(retrieved_source_ids)
        )
        case_passed = (
            grounded
            and decision_correct
            and expected_answer_correct
            and expected_source_correct
            and absent_sources_correct
        )
        grounded_values.append(float(grounded))
        decision_values.append(float(decision_correct))
        if case.get("adversarial", False):
            adversarial_values.append(float(case_passed))
        case_results.append(
            {
                "query": case["query"],
                "adversarial": case.get("adversarial", False),
                "action": response.action,
                "answer": response.answer,
                "citations": list(response.citations),
                "retrieved_source_ids": retrieved_source_ids,
                "grounded": grounded,
                "decision_correct": decision_correct,
                "absent_sources_correct": absent_sources_correct,
                "passed": case_passed,
            }
        )
    grounding_rate = sum(grounded_values) / len(grounded_values)
    decision_accuracy = sum(decision_values) / len(decision_values)
    threshold = float(specification["threshold"])
    adversarial_pass_rate = (
        sum(adversarial_values) / len(adversarial_values)
        if adversarial_values
        else 1.0
    )
    adversarial_threshold = float(
        specification.get("adversarial_threshold", threshold)
    )
    return {
        "evaluation_version": specification["version"],
        "metric": specification["metric"],
        "grounding_rate": grounding_rate,
        "decision_accuracy": decision_accuracy,
        "threshold": threshold,
        "adversarial_pass_rate": adversarial_pass_rate,
        "adversarial_threshold": adversarial_threshold,
        "passed": (
            grounding_rate >= threshold
            and decision_accuracy >= threshold
            and adversarial_pass_rate >= adversarial_threshold
            and all(case["passed"] for case in case_results)
        ),
        "cases": case_results,
    }


def verify(retriever: Retriever) -> dict[str, object]:
    """Run the canonical demo and every public gate, returning no case data."""
    retrieval_response(
        CANONICAL_DEMO_QUERY,
        retriever.search(CANONICAL_DEMO_QUERY, top_k=2),
    )
    agent = OfflineAgent(retriever)
    checks = {
        "demo": {"passed": True},
        "retrieval": {
            "passed": bool(evaluate(retriever, DEFAULT_EVALUATION)["passed"])
        },
        "agent": {
            "passed": bool(
                evaluate_agent(agent, DEFAULT_AGENT_EVALUATION)["passed"]
            )
        },
        "agent_authority_adversarial": {
            "passed": bool(
                evaluate_agent(agent, AUTHORITY_ADVERSARIAL_EVALUATION)["passed"]
            )
        },
    }
    return {
        "checks": checks,
        "passed": all(check["passed"] for check in checks.values()),
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo", help="retrieve grounded evidence")
    demo.add_argument("query")
    demo.add_argument("--top-k", type=int, default=3)
    check = commands.add_parser("evaluate", help="run the versioned evaluation")
    check.add_argument("--evaluation", type=Path, default=DEFAULT_EVALUATION)
    agent = commands.add_parser("agent", help="run the offline grounded agent")
    agent.add_argument("query")
    agent.add_argument("--top-k", type=int, default=3)
    agent_check = commands.add_parser(
        "evaluate-agent", help="run the versioned agent evaluation"
    )
    agent_check.add_argument(
        "--evaluation", type=Path, default=DEFAULT_AGENT_EVALUATION
    )
    commands.add_parser(
        "verify",
        help="run the canonical demo and all offline quality gates",
    )
    return root


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    retriever = Retriever(load_documents(DEFAULT_CORPUS))
    if arguments.command == "demo":
        output = retrieval_response(
            arguments.query, retriever.search(arguments.query, arguments.top_k)
        )
        print(json.dumps(output, indent=2, sort_keys=True))
        return 0
    if arguments.command == "agent":
        output = OfflineAgent(retriever).run(
            arguments.query, arguments.top_k
        ).to_dict()
        print(json.dumps(output, indent=2, sort_keys=True))
        return 0
    try:
        if arguments.command == "verify":
            output = verify(retriever)
        elif arguments.command == "evaluate-agent":
            output = evaluate_agent(OfflineAgent(retriever), arguments.evaluation)
        else:
            output = evaluate(retriever, arguments.evaluation)
    except InvalidEvaluationError:
        error = {
            "error": {
                "code": "invalid_evaluation",
                "message": "Evaluation input is invalid.",
            }
        }
        print(json.dumps(error, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0 if output["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

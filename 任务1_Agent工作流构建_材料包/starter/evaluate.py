from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from agent_interface import Agent


SCRIPT_DIR = Path(__file__).resolve().parent
PACKAGE_DIR = SCRIPT_DIR.parent


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def task_constraints(instruction: str) -> dict[str, Any]:
    item_match = re.search(r"\b(shirt|mug)\b", instruction, re.IGNORECASE)
    if not item_match:
        raise ValueError("task does not specify shirt or mug")

    tag_match = re.search(
        r"(?:about\s+([A-Za-z][A-Za-z-]*)|([A-Za-z][A-Za-z-]*)\s+themed|"
        r"related to\s+([A-Za-z][A-Za-z-]*)|featuring\s+([A-Za-z][A-Za-z-]*))",
        instruction,
        re.IGNORECASE,
    )
    if not tag_match:
        tag_match = re.search(
            r"\b(?!a\b|an\b|the\b|affordable\b)([A-Za-z][A-Za-z-]*)\s+(?:shirt|mug)\b",
            instruction,
            re.IGNORECASE,
        )
    if not tag_match:
        raise ValueError("task does not specify a required tag")

    price_match = re.search(
        r"(?:budget\s+|priced\s+|for\s+)?(?:under|less than)\s*\$?\s*(\d+(?:\.\d+)?)",
        instruction,
        re.IGNORECASE,
    )
    manufacturer_match = re.search(
        r"\b(from|prefer)\s+([A-Za-z0-9-]+)", instruction, re.IGNORECASE
    )
    return {
        "item_type": item_match.group(1).lower(),
        "required_tag": next(group for group in tag_match.groups() if group),
        "max_price": float(price_match.group(1)) if price_match else None,
        "manufacturer": manufacturer_match.group(2) if manufacturer_match else None,
        "manufacturer_is_hard": bool(
            manufacturer_match and manufacturer_match.group(1).lower() == "from"
        ),
    }


def first_event(result: dict[str, Any], step: str) -> dict[str, Any]:
    return next((event for event in result.get("trace", []) if event.get("step") == step), {})


def evaluate_task(
    task: dict[str, Any],
    result: dict[str, Any],
    products_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Evaluate recommendation quality on complete shopping requests."""
    constraints = task_constraints(task["instruction"])
    hard_candidates = [
        product
        for product in products_by_id.values()
        if product["item_type"].lower() == constraints["item_type"]
        and constraints["required_tag"].lower()
        in {str(tag).lower() for tag in product.get("tags", [])}
        and (
            constraints["max_price"] is None
            or product["price"] < constraints["max_price"]
        )
        and (
            not constraints["manufacturer_is_hard"]
            or product["manufacturer"].lower() == constraints["manufacturer"].lower()
        )
    ]
    preferred_candidates = [
        product
        for product in hard_candidates
        if constraints["manufacturer"]
        and product["manufacturer"].lower() == constraints["manufacturer"].lower()
    ]
    oracle_candidates = preferred_candidates or hard_candidates
    oracle = (
        min(oracle_candidates, key=lambda product: (product["price"], product["product_id"]))
        if oracle_candidates
        else None
    )
    selected = products_by_id.get(result.get("purchased_product_id"))
    selected_is_valid = selected is not None and selected in hard_candidates
    preference_satisfied = not preferred_candidates or (
        selected is not None and selected in preferred_candidates
    )
    price_regret = (
        None
        if not selected_is_valid or oracle is None
        else round(selected["price"] - oracle["price"], 2)
    )
    optimal_price_choice = (
        selected_is_valid
        and oracle is not None
        and selected["price"] == oracle["price"]
        and (not preferred_candidates or selected in preferred_candidates)
    )
    no_solution_correct = (oracle is None) == (selected is None)
    parser_method = first_event(result, "parse_instruction").get("method", "unknown")
    task_family = (
        "Buy"
        if task["instruction"].startswith("Buy")
        else "I need"
        if task["instruction"].startswith("I need")
        else "Find"
    )
    return {
        "task_id": task["task_id"],
        "task_family": task_family,
        "has_feasible_solution": oracle is not None,
        "hard_constraint_satisfied": selected_is_valid,
        "preference_satisfied": preference_satisfied,
        "no_solution_correct": no_solution_correct,
        "oracle_product_id": oracle["product_id"] if oracle else None,
        "selected_product_id": selected["product_id"] if selected else None,
        "optimal_price_choice": optimal_price_choice,
        "parser_method": parser_method,
        "price_regret": price_regret,
        "latency_ms": result.get("latency_ms"),
    }


def evaluate_row(
    task: dict[str, Any],
    result: dict[str, Any],
    products_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Evaluate recommend/reject/clarify behavior on reliability tasks."""
    selected_id = result.get("purchased_product_id")
    parsed = result.get("parsed_request")
    parse_failed = first_event(result, "parse_instruction").get("status") == "failed"
    is_clarification = parsed is None and parse_failed
    is_rejected = parsed is not None and selected_id is None
    expected = task["expected"]
    behavior_correct = (
        (expected == "recommend" and selected_id is not None)
        or (expected == "reject" and is_rejected)
        or (expected == "clarify" and is_clarification)
    )
    reference_correct = (
        not task.get("reference_product_id")
        or selected_id == task["reference_product_id"]
    )
    hard_constraint_satisfied = False
    if selected_id in products_by_id:
        product = products_by_id[selected_id]
        constraints = task_constraints(task["instruction"])
        hard_constraint_satisfied = (
            product["item_type"].lower() == constraints["item_type"]
            and constraints["required_tag"].lower()
            in {str(tag).lower() for tag in product.get("tags", [])}
            and (
                constraints["max_price"] is None
                or product["price"] < constraints["max_price"]
            )
            and (
                not constraints["manufacturer_is_hard"]
                or product["manufacturer"].lower()
                == constraints["manufacturer"].lower()
            )
        )
    return {
        "task_id": task["task_id"],
        "scenario": task.get("scenario", "unspecified"),
        "expected": expected,
        "actual": (
            "recommend"
            if selected_id
            else "clarify"
            if is_clarification
            else "reject"
            if is_rejected
            else "parse_error"
        ),
        "behavior_correct": behavior_correct,
        "reference_product_correct": reference_correct,
        "hard_constraint_satisfied": hard_constraint_satisfied,
        "selected_product_id": selected_id,
        "parser_method": first_event(result, "parse_instruction").get("method", "unknown"),
        "latency_ms": result.get("latency_ms"),
    }


def _load_or_run_results(
    tasks: list[dict[str, Any]],
    data_dir: Path,
    results_path: Path,
    rerun: bool,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    if results_path.exists() and not rerun:
        saved_results = {row["task_id"]: row for row in read_jsonl(results_path)}
        missing = [
            task["task_id"]
            for task in tasks
            if task["task_id"] not in saved_results
        ]
        if missing:
            raise ValueError(f"results file is missing task IDs: {missing[:5]}")
        return [(task, saved_results[task["task_id"]]) for task in tasks]

    agent = Agent(data_dir)
    return [(task, agent.run(task["instruction"])) for task in tasks]


def _detect_protocol(tasks: list[dict[str, Any]], requested: str) -> str:
    if requested != "auto":
        return requested
    if any("expected" in task or "scenario" in task for task in tasks):
        return "behavior"
    return "recommendation"


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0
    values = sorted(values)
    index = min(len(values) - 1, int(round((len(values) - 1) * fraction)))
    return values[index]


def _evaluate_recommendation(
    task_results: list[tuple[dict[str, Any], dict[str, Any]]],
    products_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    details = [
        evaluate_task(task, result, products_by_id)
        for task, result in task_results
    ]
    selected_details = [
        detail for detail in details if detail["selected_product_id"] is not None
    ]
    feasible_details = [
        detail for detail in details if detail["oracle_product_id"] is not None
    ]
    regrets = [
        detail["price_regret"]
        for detail in details
        if detail["price_regret"] is not None
    ]
    latencies = [
        detail["latency_ms"]
        for detail in details
        if detail["latency_ms"] is not None
    ]

    parser_methods: dict[str, int] = {}
    family_metrics: dict[str, dict[str, Any]] = {}
    for detail in details:
        method = detail["parser_method"]
        parser_methods[method] = parser_methods.get(method, 0) + 1
        family = detail["task_family"]
        family_metrics.setdefault(
            family,
            {
                "task_count": 0,
                "feasible_task_count": 0,
                "hard_constraint_satisfied": 0,
                "no_solution_correct": 0,
            },
        )
        family_metrics[family]["task_count"] += 1
        family_metrics[family]["no_solution_correct"] += int(
            detail["no_solution_correct"]
        )
        if detail["has_feasible_solution"]:
            family_metrics[family]["feasible_task_count"] += 1
            family_metrics[family]["hard_constraint_satisfied"] += int(
                detail["hard_constraint_satisfied"]
            )

    for metrics in family_metrics.values():
        feasible_count = metrics["feasible_task_count"]
        task_count = metrics["task_count"]
        metrics["hard_constraint_satisfaction_rate"] = (
            round(metrics["hard_constraint_satisfied"] / feasible_count, 4)
            if feasible_count
            else 0
        )
        metrics["no_solution_identification_rate"] = (
            round(metrics["no_solution_correct"] / task_count, 4)
            if task_count
            else 0
        )
        del metrics["hard_constraint_satisfied"]
        del metrics["no_solution_correct"]

    summary = {
        "protocol": "recommendation",
        "task_count": len(details),
        "feasible_task_count": len(feasible_details),
        "hard_constraint_satisfaction_rate": (
            round(
                sum(d["hard_constraint_satisfied"] for d in feasible_details)
                / len(feasible_details),
                4,
            )
            if feasible_details
            else 0
        ),
        "preference_satisfaction_rate": (
            round(
                sum(d["preference_satisfied"] for d in feasible_details)
                / len(feasible_details),
                4,
            )
            if feasible_details
            else 0
        ),
        "no_solution_identification_rate": (
            round(
                sum(d["no_solution_correct"] for d in details) / len(details),
                4,
            )
            if details
            else 0
        ),
        "exact_oracle_choice_rate": (
            round(
                sum(
                    d["selected_product_id"] == d["oracle_product_id"]
                    for d in feasible_details
                )
                / len(feasible_details),
                4,
            )
            if feasible_details
            else 0
        ),
        "optimal_price_choice_rate": (
            round(
                sum(d["optimal_price_choice"] for d in feasible_details)
                / len(feasible_details),
                4,
            )
            if feasible_details
            else 0
        ),
        "hard_constraint_violation_rate": (
            round(
                1
                - sum(d["hard_constraint_satisfied"] for d in feasible_details)
                / len(feasible_details),
                4,
            )
            if feasible_details
            else 0
        ),
        "mean_price_regret": round(sum(regrets) / len(regrets), 4) if regrets else 0,
        "selected_count": len(selected_details),
        "mean_latency_ms": (
            round(sum(latencies) / len(latencies), 4) if latencies else 0
        ),
        "p50_latency_ms": _percentile(latencies, 0.5),
        "p95_latency_ms": _percentile(latencies, 0.95),
        "parser_methods": parser_methods,
        "task_family_metrics": family_metrics,
    }
    return {"summary": summary, "details": details}


def _evaluate_behavior(
    task_results: list[tuple[dict[str, Any], dict[str, Any]]],
    products_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    details = [
        evaluate_row(task, result, products_by_id)
        for task, result in task_results
    ]
    by_scenario: dict[str, dict[str, Any]] = {}
    for detail in details:
        metrics = by_scenario.setdefault(
            detail["scenario"], {"count": 0, "correct": 0}
        )
        metrics["count"] += 1
        metrics["correct"] += int(detail["behavior_correct"])
    for metrics in by_scenario.values():
        metrics["accuracy"] = round(metrics["correct"] / metrics["count"], 4)

    recommendation_count = sum(
        detail["expected"] == "recommend" for detail in details
    )
    summary = {
        "protocol": "behavior",
        "task_count": len(details),
        "behavior_accuracy": (
            round(sum(d["behavior_correct"] for d in details) / len(details), 4)
            if details
            else 0
        ),
        "reference_product_accuracy": (
            round(
                sum(d["reference_product_correct"] for d in details) / len(details),
                4,
            )
            if details
            else 0
        ),
        "hard_constraint_satisfaction_rate": (
            round(
                sum(
                    d["hard_constraint_satisfied"]
                    for d in details
                    if d["expected"] == "recommend"
                )
                / recommendation_count,
                4,
            )
            if recommendation_count
            else 0
        ),
        "scenario_metrics": by_scenario,
        "parser_methods": {
            method: sum(d["parser_method"] == method for d in details)
            for method in sorted({d["parser_method"] for d in details})
        },
    }
    return {"summary": summary, "details": details}


def main(
    default_tasks: str | None = None,
    default_results: str | None = None,
    default_out: str | None = None,
    default_protocol: str = "auto",
) -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate the shopping Agent with a selectable protocol."
    )
    parser.add_argument(
        "--tasks",
        default=default_tasks or str(PACKAGE_DIR / "data" / "tasks.jsonl"),
    )
    parser.add_argument("--data", default=str(PACKAGE_DIR / "data"))
    parser.add_argument(
        "--results",
        default=default_results
        or str(PACKAGE_DIR / "outputs" / "agent_simulation.jsonl"),
    )
    parser.add_argument(
        "--out",
        default=default_out or str(PACKAGE_DIR / "outputs" / "evaluation.json"),
    )
    parser.add_argument(
        "--protocol",
        choices=["auto", "recommendation", "behavior"],
        default=default_protocol,
        help="Auto detects behavior tasks by expected/scenario fields.",
    )
    parser.add_argument(
        "--rerun",
        action="store_true",
        help="Call the Agent again instead of reusing --results.",
    )
    args = parser.parse_args()

    data_dir = Path(args.data)
    tasks = read_jsonl(Path(args.tasks))
    products = read_jsonl(data_dir / "products.jsonl")
    products_by_id = {product["product_id"]: product for product in products}
    task_results = _load_or_run_results(
        tasks=tasks,
        data_dir=data_dir,
        results_path=Path(args.results),
        rerun=args.rerun,
    )
    protocol = _detect_protocol(tasks, args.protocol)
    if protocol == "behavior":
        output = _evaluate_behavior(task_results, products_by_id)
    else:
        output = _evaluate_recommendation(task_results, products_by_id)

    output_path = Path(args.out)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(output["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from pathlib import Path
from typing import Any, Callable

from agent_interface import Agent
from evaluate import evaluate_row, read_jsonl
from model_client import ModelClient


SCRIPT_DIR = Path(__file__).resolve().parent
PACKAGE_DIR = SCRIPT_DIR.parent


def product_map(data_dir: Path) -> dict[str, dict[str, Any]]:
    return {row["product_id"]: row for row in read_jsonl(data_dir / "products.jsonl")}


def direct_llm_result(instruction: str, products: list[dict[str, Any]], client: ModelClient) -> dict[str, Any]:
    started = time.perf_counter()
    product_id = client.recommend_product(instruction, products)
    return {"purchased_product_id": product_id, "trace": [{"step": "direct_llm", "method": "llm"}], "latency_ms": round((time.perf_counter() - started) * 1000, 2)}


def unsafe_rule_result(instruction: str, agent: Agent) -> dict[str, Any]:
    """Ablation that retrieves by type/tag but skips price and manufacturer checks."""
    started = time.perf_counter()
    try:
        parsed = agent._normalise_request(agent._fallback_parse(instruction))
    except Exception as exc:
        return {"purchased_product_id": None, "parsed_request": None, "trace": [{"step": "parse_instruction", "status": "failed"}], "summary": str(exc), "latency_ms": round((time.perf_counter() - started) * 1000, 2)}
    retrieved = agent.products_by_type_and_tag.get((parsed["item_type"], parsed["required_tag"].lower()), [])
    ranked = sorted(retrieved, key=lambda product: (product["price"], product["product_id"]))
    product = ranked[0] if ranked else None
    return {
        "purchased_product_id": product["product_id"] if product else None,
        "parsed_request": parsed,
        "candidates": [product["product_id"] for product in ranked],
        "trace": [{"step": "parse_instruction", "status": "success", "method": "fallback"}, {"step": "unsafe_decision", "status": "selected" if product else "rejected"}],
        "summary": "Unsafe ablation decision without final constraint verification.",
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def run_experiment(tasks: list[dict[str, Any]], data_dir: Path, mode: str, ablation: str) -> list[dict[str, Any]]:
    products = list(product_map(data_dir).values())
    if mode == "hybrid":
        runner: Callable[[str], dict[str, Any]] = Agent(data_dir).run
    elif mode == "rule":
        agent = Agent(data_dir)
        agent.model_client.api_key = None
        if ablation == "no_verification":
            return [unsafe_rule_result(task["instruction"], agent) for task in tasks]
        if ablation == "no_preference":
            original = agent._retrieve_and_rank
            def without_preference(request: dict[str, Any]):
                retrieved, ranked = original(request)
                return retrieved, sorted(ranked, key=lambda product: (product["price"], product["product_id"]))
            agent._retrieve_and_rank = without_preference
        runner = agent.run
    else:
        client = ModelClient()
        runner = lambda instruction: direct_llm_result(instruction, products, client)

    results = []
    for task in tasks:
        try:
            result = runner(task["instruction"])
            results.append(result)
        except Exception as exc:
            results.append({"purchased_product_id": None, "trace": [{"step": "experiment", "status": "failed", "error": type(exc).__name__}], "latency_ms": None})
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare shopping Agent strategies on reliability scenarios.")
    parser.add_argument("--mode", choices=["rule", "hybrid", "direct_llm"], default="rule")
    parser.add_argument("--ablation", choices=["none", "no_preference", "no_verification"], default="none")
    parser.add_argument("--tasks", default=str(PACKAGE_DIR / "data" / "tasks2.jsonl"))
    parser.add_argument("--data", default=str(PACKAGE_DIR / "data"))
    parser.add_argument("--out", default=str(PACKAGE_DIR / "outputs" / "experiment.json"))
    args = parser.parse_args()
    tasks = read_jsonl(Path(args.tasks))
    results = run_experiment(tasks, Path(args.data), args.mode, args.ablation)
    products_by_id = product_map(Path(args.data))
    details = [evaluate_row(task, result, products_by_id) for task, result in zip(tasks, results)]
    scenario_metrics = {}
    for detail in details:
        group = scenario_metrics.setdefault(detail["scenario"], {"count": 0, "correct": 0})
        group["count"] += 1
        group["correct"] += int(detail["behavior_correct"])
    for group in scenario_metrics.values():
        group["accuracy"] = round(group["correct"] / group["count"], 4)
    latencies = [detail["latency_ms"] for detail in details if detail["latency_ms"] is not None]
    summary = {
        "mode": args.mode,
        "ablation": args.ablation,
        "task_count": len(details),
        "behavior_accuracy": round(sum(d["behavior_correct"] for d in details) / len(details), 4) if details else 0,
        "reference_product_accuracy": round(sum(d["reference_product_correct"] for d in details) / len(details), 4) if details else 0,
        "hard_constraint_satisfaction_rate": round(sum(d["hard_constraint_satisfied"] for d in details if d["expected"] == "recommend") / sum(d["expected"] == "recommend" for d in details), 4) if any(d["expected"] == "recommend" for d in details) else 0,
        "scenario_metrics": scenario_metrics,
        "mean_latency_ms": round(statistics.mean(latencies), 2) if latencies else 0,
        "p95_latency_ms": sorted(latencies)[min(len(latencies) - 1, int(round((len(latencies) - 1) * 0.95)))] if latencies else 0,
    }
    output = {"summary": summary, "details": details}
    output_path = Path(args.out)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

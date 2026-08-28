from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from model_client import ModelClient


class Agent:
    """Agent task interface.

    Keep this public calling convention:

        agent = Agent(data_dir)
        result = agent.run(instruction)
    """

    def __init__(self, data_dir: str | Path):
        # Root directory of the provided dataset. Implementations may load
        # products, prompts, indexes, caches, or model configuration from here.
        self.data_dir = Path(data_dir)
        products_path = self.data_dir / "products.jsonl"
        with products_path.open("r", encoding="utf-8") as file:
            self.products = [json.loads(line) for line in file if line.strip()]
        self.products_by_type_and_tag: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for product in self.products:
            for tag in product.get("tags", []):
                key = (product["item_type"].lower(), str(tag).lower())
                self.products_by_type_and_tag.setdefault(key, []).append(product)
        self.model_client = ModelClient()

    def _fallback_parse(self, instruction: str) -> dict[str, Any]:
        text = instruction.strip()
        item_match = re.search(r"\b(shirt|mug)\b", text, re.IGNORECASE)
        tag_match = re.search(r"(?:about\s+([A-Za-z][A-Za-z-]*)|([A-Za-z][A-Za-z-]*)\s+themed|related to\s+([A-Za-z][A-Za-z-]*)|featuring\s+([A-Za-z][A-Za-z-]*))", text, re.IGNORECASE)
        if not tag_match:
            tag_match = re.search(r"\b(?!a\b|an\b|the\b|affordable\b)([A-Za-z][A-Za-z-]*)\s+(?:shirt|mug)\b", text, re.IGNORECASE)
        price_match = re.search(r"(?:budget\s+|priced\s+|for\s+)?(?:under|less than)\s*\$?\s*(\d+(?:\.\d+)?)", text, re.IGNORECASE)
        manufacturer_match = re.search(r"\b(from|prefer)\s+([A-Za-z0-9-]+)", text, re.IGNORECASE)
        if not item_match or not tag_match:
            raise ValueError("could not parse item type and required tag")
        manufacturer = manufacturer_match.group(2) if manufacturer_match else None
        return {
            "item_type": item_match.group(1).lower(),
            "required_tag": next(group for group in tag_match.groups() if group),
            "max_price": float(price_match.group(1)) if price_match else None,
            "manufacturer": manufacturer,
            "manufacturer_is_hard": bool(manufacturer_match and manufacturer_match.group(1).lower() == "from"),
            "objective": "affordable" if re.search(r"\baffordable\b", text, re.IGNORECASE) else None,
        }

    def _parse_request(self, instruction: str) -> tuple[dict[str, Any], str, str | None]:
        if self._has_conflicting_requirements(instruction):
            raise ValueError("conflicting requirements need clarification")
        if self.model_client.enabled:
            try:
                return self._normalise_request(self.model_client.parse_request(instruction)), "llm", None
            except Exception as exc:
                fallback_reason = f"LLM parsing failed: {type(exc).__name__}"
        else:
            fallback_reason = "LLM_API_KEY is not configured"
        return self._normalise_request(self._fallback_parse(instruction)), "fallback", fallback_reason

    def _has_conflicting_requirements(self, instruction: str) -> bool:
        text = instruction.lower()
        asks_for_both_types = "shirt" in text and "mug" in text
        price_and_preference_conflict = (
            "prefer" in text
            and ("only choose" in text or "cheapest" in text)
            and "if" in text
        )
        return asks_for_both_types or price_and_preference_conflict

    def _normalise_request(self, request: dict[str, Any]) -> dict[str, Any]:
        item_type = str(request.get("item_type", "")).lower().strip()
        required_tag = str(request.get("required_tag", "")).strip()
        if item_type not in {"shirt", "mug"} or not required_tag:
            raise ValueError("invalid parsed request")
        max_price = request.get("max_price")
        if max_price is not None:
            max_price = float(max_price)
            if max_price < 0:
                raise ValueError("max_price must not be negative")
        manufacturer = request.get("manufacturer")
        return {
            "item_type": item_type,
            "required_tag": required_tag,
            "max_price": max_price,
            "manufacturer": str(manufacturer).strip() if manufacturer else None,
            "manufacturer_is_hard": bool(request.get("manufacturer_is_hard", False)),
            "objective": "affordable" if request.get("objective") == "affordable" else None,
        }

    def _retrieve_and_rank(self, request: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        key = (request["item_type"], request["required_tag"].lower())
        retrieved = list(self.products_by_type_and_tag.get(key, []))
        candidates = [
            product for product in retrieved
            if request["max_price"] is None or product["price"] < request["max_price"]
        ]
        if request["manufacturer"] and request["manufacturer_is_hard"]:
            candidates = [p for p in candidates if p["manufacturer"].lower() == request["manufacturer"].lower()]
        ranked = sorted(
            candidates,
            key=lambda product: (
                0 if request["manufacturer"] and product["manufacturer"].lower() == request["manufacturer"].lower() else 1,
                product["price"],
                product["product_id"],
            ),
        )
        return retrieved, ranked

    def _verify(self, product: dict[str, Any] | None, request: dict[str, Any]) -> dict[str, bool]:
        if product is None:
            return {"product_exists": False, "item_type": False, "required_tag": False, "price": False, "manufacturer": False}
        return {
            "product_exists": product in self.products,
            "item_type": product["item_type"].lower() == request["item_type"],
            "required_tag": request["required_tag"].lower() in {str(tag).lower() for tag in product.get("tags", [])},
            "price": request["max_price"] is None or product["price"] < request["max_price"],
            "manufacturer": not request["manufacturer_is_hard"] or product["manufacturer"].lower() == request["manufacturer"].lower(),
        }

    def run(self, instruction: str) -> dict:
        """Run the complete agent workflow for one shopping instruction.

        Return at least:
            instruction: str
            purchased_product_id: str | None
            trace: list
            summary: str
        """
        started = time.perf_counter()
        trace: list[dict[str, Any]] = []
        try:
            request, parser, fallback_reason = self._parse_request(instruction)
        except Exception as exc:
            trace.append({"step": "parse_instruction", "status": "failed", "error": str(exc)})
            return {
                "instruction": instruction,
                "purchased_product_id": None,
                "trace": trace,
                "summary": f"Unable to understand the shopping request: {exc}",
                "parsed_request": None,
                "candidates": [],
                "verification": {},
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            }

        parse_event: dict[str, Any] = {"step": "parse_instruction", "status": "success", "method": parser}
        if fallback_reason:
            parse_event["fallback_reason"] = fallback_reason
        trace.append(parse_event)
        retrieved, ranked = self._retrieve_and_rank(request)
        trace.append({"step": "retrieve_candidates", "status": "success", "retrieved_count": len(retrieved), "candidate_count": len(ranked)})
        product = ranked[0] if ranked else None
        verification = self._verify(product, request)
        is_valid = bool(product) and all(verification.values())
        trace.append({"step": "verify_decision", "status": "passed" if is_valid else "no_valid_product", "checks": verification})
        if product and is_valid:
            summary = (
                f"Selected {product['product_id']} ({product['name']}) at ${product['price']:.2f}. "
                f"It is a {product['item_type']} with the '{request['required_tag']}' tag."
            )
            if request["manufacturer"]:
                summary += f" Manufacturer preference: {request['manufacturer']}."
        else:
            summary = "No product satisfies all hard constraints."
        trace.append({"step": "final_decision", "status": "selected" if is_valid else "rejected", "product_id": product["product_id"] if is_valid else None})
        return {
            "instruction": instruction,
            "purchased_product_id": product["product_id"] if is_valid else None,
            "trace": trace,
            "summary": summary,
            "parsed_request": request,
            "candidates": [p["product_id"] for p in ranked],
            "verification": verification,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        }

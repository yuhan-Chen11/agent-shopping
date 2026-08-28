from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
import requests


class ModelClient:
    """Small OpenAI-compatible client used only for requirement extraction."""

    def __init__(self) -> None:
        load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=True)
        self.api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
        self.base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.model = os.getenv("LLM_MODEL", "gpt-4o-mini")
        self.timeout = float(os.getenv("LLM_TIMEOUT_SECONDS", "30"))

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def parse_request(self, instruction: str) -> dict[str, Any]:
        if not self.enabled:
            raise RuntimeError("LLM_API_KEY is not configured")

        system_prompt = (
            "Extract a shopping request into JSON only. Do not invent values. "
            "Use this schema: item_type (shirt or mug), required_tag (string), "
            "max_price (number or null), manufacturer (string or null), "
            "manufacturer_is_hard (boolean), objective (affordable or null). "
            "Treat 'from MANUFACTURER' as hard and 'prefer MANUFACTURER' as soft. "
            "A price phrase 'under' or 'less than' is a strict upper bound."
        )
        payload = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": instruction},
            ],
            "response_format": {"type": "json_object"},
        }
        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        body = response.json()
        content = body["choices"][0]["message"]["content"]
        if isinstance(content, list):
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", str(content).strip())
        result = json.loads(content)
        if not isinstance(result, dict):
            raise ValueError("model response must be a JSON object")
        return result

    def recommend_product(self, instruction: str, products: list[dict[str, Any]]) -> str | None:
        """Baseline-only direct recommendation; deliberately has no local verifier."""
        if not self.enabled:
            raise RuntimeError("LLM_API_KEY is not configured")
        catalogue = json.dumps(products, ensure_ascii=False)
        payload = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": "Choose one product from the catalogue for the user request. Return JSON only: {\"product_id\": string or null}. Never invent an ID."},
                {"role": "user", "content": f"Request:\n{instruction}\nCatalogue:\n{catalogue}"},
            ],
            "response_format": {"type": "json_object"},
        }
        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        result = json.loads(re.sub(r"^```(?:json)?\s*|\s*```$", "", str(content).strip()))
        product_id = result.get("product_id") if isinstance(result, dict) else None
        return str(product_id) if product_id else None

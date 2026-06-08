"""
LLM-based extractor: converts raw rule chunks into structured JSON records
using Ollama with format="json" for native structured output.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Any

from tenacity import retry, stop_after_attempt, wait_exponential

from src.chunking.rule_chunker import RuleChunk

try:
    import ollama
except ImportError:
    ollama = None  # type: ignore[assignment]

RATE_CELL_PATTERN = re.compile(
    r"(?P<pct>\d+\.?\d*)\s*%\s*\+?\s*\$?(?P<fixed>\d+\.?\d*)?"
    r"(?:.*?(?:cap|max)\s*\$?(?P<cap>\d+\.?\d*))?"
    r"(?:.*?(?:min|floor)\s*\$?(?P<floor>\d+\.?\d*))?",
    re.IGNORECASE,
)

EXTRACTION_PROMPT = """You are an expert in payment network interchange regulations.
Parse the interchange fee rule below into strict JSON with these fields:
- fee_program: string (exact program name)
- rate_pct: float (percentage as decimal, e.g. 1.65 for 1.65%)
- rate_fixed_usd: float (fixed component in USD, e.g. 0.15)
- cap_usd: float or null (maximum cap in USD)
- floor_usd: float or null (minimum floor in USD)
- card_present: boolean (true = Card Present)
- conditions: list of strings (applicable footnote conditions)

Rule: {rule_text}
Footnotes: {footnotes}

Return ONLY valid JSON, no commentary."""


@dataclass
class InterchangeRule:
    fee_program: str
    rate_pct: float
    rate_fixed_usd: float
    cap_usd: float | None
    floor_usd: float | None
    card_present: bool
    conditions: list[str]
    brand: str
    card_category: str
    product: str
    page_number: int


class LLMExtractor:
    def __init__(self, model: str = "qwen2.5:72b", use_regex_fallback: bool = True) -> None:
        self.model = model
        self.use_regex_fallback = use_regex_fallback

    def extract(self, chunks: list[RuleChunk]) -> list[InterchangeRule]:
        rules: list[InterchangeRule] = []
        for chunk in chunks:
            rule = self._extract_one(chunk)
            if rule:
                rules.append(rule)
        return rules

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def _extract_one(self, chunk: RuleChunk) -> InterchangeRule | None:
        parsed = self._try_llm(chunk) if ollama else None
        if parsed is None and self.use_regex_fallback:
            parsed = self._regex_parse(chunk)
        if parsed is None:
            return None

        return InterchangeRule(
            fee_program=parsed.get("fee_program", chunk.fee_program),
            rate_pct=float(parsed.get("rate_pct", 0)),
            rate_fixed_usd=float(parsed.get("rate_fixed_usd", 0)),
            cap_usd=parsed.get("cap_usd"),
            floor_usd=parsed.get("floor_usd"),
            card_present=parsed.get("card_present", chunk.modality == "card_present"),
            conditions=parsed.get("conditions", chunk.conditions),
            brand=chunk.brand,
            card_category=chunk.card_category,
            product=chunk.product,
            page_number=chunk.page_number,
        )

    def _try_llm(self, chunk: RuleChunk) -> dict[str, Any] | None:
        prompt = EXTRACTION_PROMPT.format(
            rule_text=f"{chunk.fee_program}: {chunk.rate_raw}",
            footnotes="; ".join(chunk.conditions) or "none",
        )
        try:
            response = ollama.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                format="json",
            )
            return json.loads(response["message"]["content"])
        except Exception:
            return None

    def _regex_parse(self, chunk: RuleChunk) -> dict[str, Any] | None:
        match = RATE_CELL_PATTERN.search(chunk.rate_raw)
        if not match:
            return None
        return {
            "fee_program": chunk.fee_program,
            "rate_pct": float(match.group("pct") or 0),
            "rate_fixed_usd": float(match.group("fixed") or 0),
            "cap_usd": float(match.group("cap")) if match.group("cap") else None,
            "floor_usd": float(match.group("floor")) if match.group("floor") else None,
            "card_present": chunk.modality == "card_present",
            "conditions": chunk.conditions,
        }

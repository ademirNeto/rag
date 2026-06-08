"""
Structural chunking: converts raw PageBlocks into atomic rule chunks.
Each chunk = one interchange rule row with full inherited context (brand, card type, modality).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from src.ingestion.pdf_loader import PageBlock


HEADER_KEYWORDS = {"card present", "card not present", "credit", "debit", "prepaid", "program"}
RATE_PATTERN = re.compile(r"\d+\.\d+%?\s*\+?\s*\$?\d*\.?\d*")
FOOTNOTE_REF_PATTERN = re.compile(r"[\*\†\‡\§\d]+")


@dataclass
class RuleChunk:
    """Minimum indexable unit: one interchange rule with full context."""

    page_number: int
    brand: str
    card_category: str
    product: str
    modality: str  # card_present | card_not_present
    fee_program: str
    rate_raw: str
    conditions: list[str] = field(default_factory=list)
    footnote_refs: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class RuleChunker:
    def __init__(self, blocks: list[PageBlock], brand: str = "unknown") -> None:
        self.blocks = blocks
        self.brand = brand
        self._footnotes: dict[str, str] = {}

    def build_rule_chunks(self) -> list[RuleChunk]:
        self._collect_footnotes()
        chunks: list[RuleChunk] = []

        for block in self.blocks:
            if block.block_type != "table":
                continue
            table = block.content
            if not isinstance(table, list) or len(table) < 2:
                continue

            header_rows, data_rows = self._split_headers(table)
            merged_header = self._merge_hierarchical_headers(header_rows)

            for row in data_rows:
                chunk = self._row_to_chunk(row, merged_header, block.page_number)
                if chunk:
                    chunks.append(chunk)

        return chunks

    def _collect_footnotes(self) -> None:
        for block in self.blocks:
            if block.block_type == "footnote" and isinstance(block.content, str):
                match = re.match(r"^([\*\†\‡\§\d\w]{1,3})[\s\.](.*)", block.content)
                if match:
                    self._footnotes[match.group(1)] = match.group(2).strip()

    def _split_headers(
        self, table: list[list[str]]
    ) -> tuple[list[list[str]], list[list[str]]]:
        header_rows = []
        for i, row in enumerate(table):
            non_empty = [c for c in row if c and c.strip()]
            if any(kw in " ".join(non_empty).lower() for kw in HEADER_KEYWORDS):
                header_rows.append(row)
            else:
                return header_rows or [table[0]], table[i:]
        return table[:1], table[1:]

    def _merge_hierarchical_headers(self, header_rows: list[list[str]]) -> list[str]:
        if not header_rows:
            return []
        max_cols = max(len(r) for r in header_rows)
        merged = [""] * max_cols
        for row in header_rows:
            for i, cell in enumerate(row):
                if i < max_cols and cell and cell.strip():
                    merged[i] = (merged[i] + " " + cell.strip()).strip()
        return merged

    def _row_to_chunk(
        self, row: list[str | None], header: list[str], page: int
    ) -> RuleChunk | None:
        if not row or all(not (c or "").strip() for c in row):
            return None

        row_dict = {
            header[i]: (row[i] or "").strip()
            for i in range(min(len(header), len(row)))
        }

        rate_raw = next(
            (v for v in row_dict.values() if RATE_PATTERN.search(v)), ""
        )
        if not rate_raw:
            return None

        fee_program = next(
            (v for k, v in row_dict.items() if "program" in k.lower() or i == 0),
            row[0] or "",
        )

        footnote_refs = FOOTNOTE_REF_PATTERN.findall(rate_raw)
        conditions = [
            self._footnotes[ref]
            for ref in footnote_refs
            if ref in self._footnotes
        ]

        modality = "card_not_present"
        header_text = " ".join(header).lower()
        if "card present" in header_text or " cp " in header_text:
            modality = "card_present"

        return RuleChunk(
            page_number=page,
            brand=self.brand,
            card_category=self._infer_card_category(row_dict),
            product=self._infer_product(row_dict),
            modality=modality,
            fee_program=fee_program,
            rate_raw=rate_raw,
            conditions=conditions,
            footnote_refs=footnote_refs,
            metadata={"raw_row": row_dict},
        )

    def _infer_card_category(self, row: dict[str, str]) -> str:
        text = " ".join(row.values()).lower()
        if "debit" in text:
            return "debit"
        if "prepaid" in text:
            return "prepaid"
        return "credit"

    def _infer_product(self, row: dict[str, str]) -> str:
        text = " ".join(row.values()).lower()
        for product in ("infinite", "signature", "world elite", "world high value", "world", "core"):
            if product in text:
                return product.replace(" ", "_")
        return "standard"

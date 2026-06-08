"""
PDF ingestion: extracts page blocks (tables, text, footnotes) from interchange fee manuals.
Uses pdfplumber as primary, with pytesseract OCR fallback for non-digital pages.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import pdfplumber


BlockType = Literal["table", "text", "footnote"]

FOOTNOTE_SYMBOLS_PATTERN = re.compile(r"^[\*\†\‡\§\d\w]{1,3}[\s\.]")
OCR_CHAR_DENSITY_THRESHOLD = 5  # chars per cm²


@dataclass
class PageBlock:
    page_number: int
    block_type: BlockType
    content: list[list[str]] | str
    bbox: tuple[float, float, float, float] | None = None
    footnote_symbols: list[str] = field(default_factory=list)


class PDFLoader:
    def __init__(self, pdf_path: str | Path, ocr_fallback: bool = True) -> None:
        self.pdf_path = Path(pdf_path)
        self.ocr_fallback = ocr_fallback

    def extract_blocks(self) -> list[PageBlock]:
        blocks: list[PageBlock] = []
        with pdfplumber.open(self.pdf_path) as pdf:
            for page in pdf.pages:
                blocks.extend(self._process_page(page))
        return blocks

    def _process_page(self, page: pdfplumber.page.Page) -> list[PageBlock]:
        blocks: list[PageBlock] = []

        for table in page.extract_tables():
            if table:
                block = PageBlock(
                    page_number=page.page_number,
                    block_type="table",
                    content=table,
                    bbox=None,
                )
                blocks.append(block)

        text = page.extract_text() or ""
        if self.ocr_fallback and self._needs_ocr(text, page):
            text = self._ocr_page(page)

        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if FOOTNOTE_SYMBOLS_PATTERN.match(stripped):
                blocks.append(
                    PageBlock(
                        page_number=page.page_number,
                        block_type="footnote",
                        content=stripped,
                    )
                )
            else:
                blocks.append(
                    PageBlock(
                        page_number=page.page_number,
                        block_type="text",
                        content=stripped,
                    )
                )

        return blocks

    def _needs_ocr(self, text: str, page: pdfplumber.page.Page) -> bool:
        if not text:
            return True
        width_cm = (page.width / 72) * 2.54
        height_cm = (page.height / 72) * 2.54
        area_cm2 = width_cm * height_cm
        density = len(text) / area_cm2 if area_cm2 > 0 else 0
        return density < OCR_CHAR_DENSITY_THRESHOLD

    def _ocr_page(self, page: pdfplumber.page.Page) -> str:
        try:
            import pytesseract
            from PIL import Image

            img = page.to_image(resolution=300).original
            return pytesseract.image_to_string(img, lang="eng")
        except ImportError:
            return ""

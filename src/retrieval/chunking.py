"""Markdown-aware chunking for retrieval ingestion.

Splits markdown text into overlapping chunks sized for embedding:
1. Split on headings (`# `, `## `, etc.) into sections.
2. Split each section into paragraphs (blank-line separated).
3. Merge paragraphs into chunks up to `target_words`.
4. Carry a small word overlap from the end of one chunk into the next.
"""

from __future__ import annotations

import re

_HEADING_RE = re.compile(r"^(#{1,6})\s+.*$", re.MULTILINE)


def _split_into_sections(text: str) -> list[str]:
    """Split markdown text into sections, each starting at a heading (if any)."""
    matches = list(_HEADING_RE.finditer(text))
    if not matches:
        return [text]

    sections: list[str] = []
    starts = [m.start() for m in matches]
    if starts[0] > 0:
        sections.append(text[: starts[0]])
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(text)
        sections.append(text[start:end])
    return sections


def _split_into_paragraphs(section: str) -> list[str]:
    """Split a section into paragraphs on blank lines."""
    paragraphs = re.split(r"\n\s*\n", section)
    return [p.strip() for p in paragraphs if p.strip()]


def chunk_markdown(text: str, target_words: int = 400, overlap_words: int = 50) -> list[str]:
    """Split markdown text into overlapping chunks of roughly `target_words` words.

    Returns an empty list for empty/whitespace-only input.
    """
    if not text or not text.strip():
        return []

    chunks: list[str] = []
    carry_over = ""

    for section in _split_into_sections(text):
        paragraphs = _split_into_paragraphs(section)
        if not paragraphs:
            continue

        current_parts: list[str] = [carry_over] if carry_over else []
        current_words = len(carry_over.split()) if carry_over else 0
        carry_over = ""

        for paragraph in paragraphs:
            paragraph_words = len(paragraph.split())

            if current_words + paragraph_words > target_words and current_parts:
                chunk_text = "\n\n".join(current_parts).strip()
                if chunk_text:
                    chunks.append(chunk_text)
                # Carry the tail of this chunk forward for overlap.
                tail_words = chunk_text.split()[-overlap_words:] if overlap_words > 0 else []
                carry_over = " ".join(tail_words)
                current_parts = [carry_over] if carry_over else []
                current_words = len(carry_over.split()) if carry_over else 0

            current_parts.append(paragraph)
            current_words += paragraph_words

        if current_parts:
            chunk_text = "\n\n".join(current_parts).strip()
            if chunk_text:
                chunks.append(chunk_text)
            tail_words = chunk_text.split()[-overlap_words:] if overlap_words > 0 else []
            carry_over = " ".join(tail_words)

    return chunks
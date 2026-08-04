"""Lightweight OCR evidence units.

The fixed-field Qwen prompt consumes ``evidence_units`` produced by the backend
so that field-level evidence can be located in raw OCR via ``start_offset`` /
``end_offset`` instead of being inferred from chapter headings.

Design rules (see the spec):

- Use the same page-text separator that ``merged_text`` uses (``"\\n\\n"``).
- Never rewrite or correct OCR text; preserve typos such as ``品后诊断``.
- Never reorder pages; the saved page order from backend metadata wins.
- Split primarily by newline, Chinese period (``。``) and semicolon (``；``).
  Long fragments get a controlled long-comma (``、``) fallback so that vital
  signs, blood gases and diagnosis lines stay together.
- Vital-sign rows, blood-gas groups and diagnosis items must remain as a
  single unit to avoid value错位.
- IDs are stable within a single OCR result: ``u001``, ``u002``, ...
- ``page_no`` is attached when the unit fully comes from a single page.
- ``section_key`` is best-effort and not relied upon for offset logic.
"""

from __future__ import annotations

import re

# Same separator used by the active OCR port to join per-page text into
# ``merged_text``. Tests and downstream consumers depend on this exact string
# so do not change without coordinating with the OCR port.
PAGE_SEPARATOR = "\n\n"

# Characters that always end a unit.
_PRIMARY_SPLIT_CHARS = ("\n", "。", "；")
# Long-comma fallback: only used when a fragment is too long to be useful as a
# single unit. Fragments shorter than this threshold stay together.
_LONG_COMMA_FALLBACK = 80

# A normal vital-sign row is short and label-led.  This guard prevents a long
# history/physical-examination paragraph containing words such as ``呼吸`` or
# ``体重`` from being mistaken for the whole vital-sign row.
_VITAL_SIGN_MAX_CHARS = 180

# Best-effort section hints. Used purely as an aid for human readability; never
# relied upon for offset computation or unit boundaries.
_SECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("chief_complaint", re.compile(r"^\s*(?:#{1,6}\s*)?主诉(?:\b|[：:])")),
    ("history_of_present_illness", re.compile(r"^\s*(?:#{1,6}\s*)?现病史(?:\b|[：:])")),
    ("past_medical_history", re.compile(r"^\s*(?:#{1,6}\s*)?既往史(?:\b|[：:])")),
    ("personal_history", re.compile(r"^\s*(?:#{1,6}\s*)?个人史(?:\b|[：:])")),
    ("family_history", re.compile(r"^\s*(?:#{1,6}\s*)?家族史(?:\b|[：:])")),
    ("physical_examination", re.compile(r"^\s*(?:#{1,6}\s*)?体格检查(?:\b|[：:])")),
    ("ancillary_tests", re.compile(r"^\s*(?:#{1,6}\s*)?辅助检查(?:\b|[：:])")),
    ("diagnosis", re.compile(r"^\s*(?:#{1,6}\s*)?(初步诊断|最终诊断|诊断)(?:\b|[：:])")),
)

# Blood gas labels used to detect a blood-gas group. The presence of any two of
# these labels in a fragment signals "do not split this further".
_BLOOD_GAS_LABELS: tuple[str, ...] = (
    "pH",
    "pCO2",
    "pO2",
    "PO2",
    "Na+",
    "FIO2",
    "FiO2",
    "氧合指数",
)


def build_evidence_units(document_result: dict) -> list[dict]:
    """Return lightweight evidence units for ``document_result``.

    The function takes the OCR document result dict (with ``pages`` and
    ``merged_text``) and produces a list of evidence-unit dicts:

    .. code-block:: json

        {
            "id": "u001",
            "text": "主诉：反复咳嗽、咳痰15年。",
            "start_offset": 0,
            "end_offset": 17,
            "page_no": 1,
            "section_key": "chief_complaint"
        }

    ``page_no`` and ``section_key`` are best-effort optional fields; offsets
    are mandatory and must round-trip against ``document_result["merged_text"]``.
    """
    if not isinstance(document_result, dict):
        return []
    pages = document_result.get("pages")
    merged_text = document_result.get("merged_text", "") or ""
    if not isinstance(pages, list) or not isinstance(merged_text, str):
        return []

    # Walk the pages in their saved (backend) order and split each page into
    # raw lines. We then re-assemble units whose offsets are recomputed against
    # ``merged_text`` below so that they match the saved concatenation exactly.
    raw_fragments: list[dict] = []
    for page in pages:
        if not isinstance(page, dict):
            continue
        if page.get("status") == "failed":
            continue
        page_text = page.get("text", "") or ""
        if not page_text:
            continue
        page_no = page.get("page_no")
        for line in page_text.splitlines():
            if line == "":
                continue
            raw_fragments.append({
                "text": line,
                "page_no": page_no,
            })

    units: list[dict] = []
    for fragment in raw_fragments:
        for piece in _split_fragment(fragment["text"]):
            units.append({
                "text": piece,
                "page_no": fragment["page_no"],
            })

    # Recompute offsets against ``merged_text`` so they always round-trip.
    offset = 0
    annotated: list[dict] = []
    for unit in units:
        idx = merged_text.find(unit["text"], offset)
        if idx < 0:
            # If the fragment cannot be located (e.g. OCR normalised whitespace
            # differently between per-page text and merged_text), skip rather
            # than invent offsets. This keeps the contract honest.
            continue
        annotated.append({
            "text": unit["text"],
            "start_offset": idx,
            "end_offset": idx + len(unit["text"]),
            "page_no": unit["page_no"],
        })
        offset = idx + len(unit["text"])

    # Best-effort section hints (never used for offset or boundary logic).
    section_starts: list[tuple[int, str]] = []
    for unit in annotated:
        section = _guess_section_key(unit["text"])
        if section:
            unit["section_key"] = section
            section_starts.append((unit["start_offset"], section))
    section_starts.sort()
    if section_starts:
        for unit in annotated:
            if "section_key" in unit:
                continue
            key = _latest_section(section_starts, unit["start_offset"])
            if key:
                unit["section_key"] = key

    # Assign stable IDs.
    for index, unit in enumerate(annotated, start=1):
        unit["id"] = f"u{index:03d}"

    # Final shape: id, text, start_offset, end_offset, optional page_no,
    # optional section_key.
    final_units: list[dict] = []
    for unit in annotated:
        item: dict = {
            "id": unit["id"],
            "text": unit["text"],
            "start_offset": unit["start_offset"],
            "end_offset": unit["end_offset"],
        }
        if unit.get("page_no") is not None:
            item["page_no"] = unit["page_no"]
        if unit.get("section_key"):
            item["section_key"] = unit["section_key"]
        final_units.append(item)
    return final_units


def _split_fragment(text: str) -> list[str]:
    """Split a single line into one or more evidence units.

    The split is coarse: newline and Chinese period/semicolon are hard
    delimiters. Long fragments get a controlled ``、`` fallback so that the
    resulting units stay useful for OCR highlighting. Blood-gas groups,
    diagnosis lines and vital-sign rows are detected by their label density
    and kept together.
    """
    if not text:
        return []

    pieces: list[str] = []
    buf = ""
    for char in text:
        buf += char
        if char in _PRIMARY_SPLIT_CHARS:
            stripped = buf.strip()
            if stripped:
                pieces.extend(_protect_special_fragment(stripped))
            buf = ""
    tail = buf.strip()
    if tail:
        pieces.extend(_protect_special_fragment(tail))
    return pieces


def _protect_special_fragment(fragment: str) -> list[str]:
    """Keep only genuinely short coupled rows intact.

    Special-row detection happens *after* strong-boundary splitting.  This is
    important because OCR frequently puts a complete physical examination on
    one line; matching ``呼吸`` + ``体重`` in that line must not suppress all
    sentence boundaries.
    """
    if _looks_like_blood_gas_group(fragment) or _looks_like_vital_sign_row(fragment):
        return [fragment]
    return _apply_comma_fallback(fragment)


def _apply_comma_fallback(fragment: str) -> list[str]:
    """Apply controlled long-comma fallback for very long fragments."""
    if len(fragment) <= _LONG_COMMA_FALLBACK:
        return [fragment]
    if _looks_like_history_negation_scope(fragment):
        return [fragment]
    parts = [p.strip() for p in fragment.split("、") if p.strip()]
    if not parts:
        return [fragment]
    # If splitting by 、 already produces reasonably-sized units, use them.
    if all(len(p) <= _LONG_COMMA_FALLBACK for p in parts):
        return parts
    return [fragment]


def _looks_like_blood_gas_group(text: str) -> bool:
    if "血气" not in text and "pH" not in text and "pCO2" not in text and "pO2" not in text:
        return False
    matches = sum(1 for label in _BLOOD_GAS_LABELS if label in text)
    return matches >= 2


def _looks_like_vital_sign_row(text: str) -> bool:
    # A short line containing vital-sign labels should remain as one unit so
    # temperature/pulse/respiration/blood-pressure values stay together.  The
    # label-led check prevents ordinary clinical prose from matching merely
    # because it mentions two of these words later in the paragraph.
    if len(text) > _VITAL_SIGN_MAX_CHARS:
        return False
    if not re.match(r"^\s*(?:体温|脉搏|呼吸|血压|身高|体重|BMI)\s*[:：]", text):
        return False
    keywords = ("体温", "脉搏", "呼吸", "血压", "身高", "体重", "BMI")
    matches = sum(1 for k in keywords if k in text)
    return matches >= 2


def _looks_like_history_negation_scope(text: str) -> bool:
    """Keep medical-history denial scopes intact.

    Phrases such as ``否认糖尿病、冠心病等病史`` rely on the enumeration
    punctuation to define one shared negation scope. Splitting by ``、`` would
    turn the second disease into a standalone positive-looking fragment.
    """
    if "否认" not in text and "无" not in text and "未见" not in text:
        return False
    history_markers = ("病史", "既往史", "传染病史", "手术史", "输血史", "外伤史", "家族史")
    return any(marker in text for marker in history_markers)


def _guess_section_key(text: str) -> str | None:
    for key, pattern in _SECTION_PATTERNS:
        if pattern.search(text):
            return key
    return None


def _latest_section(section_starts: list[tuple[int, str]], offset: int) -> str | None:
    current: str | None = None
    for start, key in section_starts:
        if start <= offset:
            current = key
        else:
            break
    return current

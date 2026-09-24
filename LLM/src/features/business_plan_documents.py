"""Inspect supported business-plan forms and render drafts without changing uploads."""

from __future__ import annotations

import base64
import binascii
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from html import escape
from io import BytesIO
from pathlib import Path
from typing import Any

from hwpx import HwpxDocument
from PIL import Image
import pymupdf
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, NameObject
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.pdfgen import canvas as pdf_canvas


MAX_TEMPLATE_BYTES = 4 * 1024 * 1024
MAX_FIELDS = 40
MARKER = re.compile(r"\{\{\s*([^{}]{1,80}?)\s*\}\}")
MISSING = "정보 부족"
SECTION_HEADING = re.compile(r"^\s*\d+(?:[-.]\d+)+\.?\s*\S")
MAJOR_HEADING = re.compile(r"^\s*\d+\.\s")


@dataclass
class StaticPdfField:
    name: str
    page_index: int
    regions: list[pymupdf.Rect]
    kind: str = "multiline_text"
    columns: tuple[str, ...] = ()
    table_cells: list[list[pymupdf.Rect | None]] | None = None
    fixed_row_labels: bool = False


@dataclass
class HwpxTableField:
    name: str
    table_index: int
    header_index: int
    columns: tuple[str, ...]
    row_labels: list[str]

DEFAULT_OVERVIEW_FIELDS = [
    ("applicationStatus", "신청현황"),
    ("generalStatus", "일반현황"),
    ("itemOverview", "창업아이템 개요(요약)"),
]

DEFAULT_PLAN_GROUPS = [
    (
        "1. 문제인식\n(Problem)",
        [
            ("motivation", "1-1. 창업아이템의 개발 동기 / 개발 추진경과(이력)", [
                "제품·서비스를 개발하게 된 내·외적 동기",
                "사업 신청 전 기획·추진한 경과(이력)",
                "소셜벤처는 인식하고 있는 사회적 문제를 함께 기재",
            ]),
            ("purpose", "1-2. 창업아이템의 개발 목적", [
                "발견한 문제점의 해결 방안과 제품·서비스의 개발 목적",
                "소셜벤처는 사회적 문제 해결방안과 사회적 성과를 함께 기재",
            ]),
            ("targetMarket", "1-3. 창업아이템의 목표시장 분석", [
                "목표시장의 규모·상황·특성, 경쟁 강도와 고객 특성",
            ]),
        ],
    ),
    (
        "2. 실현가능성\n(Solution)",
        [
            ("developmentPlan", "2-1. 창업아이템의 개발 방안 / 진행(준비) 정도", [
                "협약기간 내 개발할 제품·서비스의 최종 산출물",
                "개발 방법, 신청 시점의 개발 단계와 진행(준비) 정도",
                "기술 유출 방지를 위한 기술 보호 계획",
            ]),
            ("differentiation", "2-2. 창업아이템의 차별화 방안", [
                "보유역량을 기반으로 경쟁 제품·서비스 대비 경쟁력을 확보할 방안",
            ]),
        ],
    ),
    (
        "3. 성장전략\n(Scale-up)",
        [
            ("commercialization", "3-1. 창업아이템의 사업화 방안", [
                "제품·서비스의 수익 모델(비즈니스 모델)",
                "생산·출시, 홍보·마케팅, 유통·판매 등 목표시장 진출 방안",
            ]),
            ("schedule", "3-2. 사업 추진 일정", [
                "전체 사업 단계의 목표와 상세 추진 일정",
                "협약기간 내 달성 가능한 목표와 상세 추진 일정",
            ]),
            ("funding", "3-3. 자금소요 및 조달계획", [
                "정부지원금 사용계획과 구체적인 조달계획",
                "본인 부담금과 추가 자본금의 구체적인 조달계획",
            ]),
        ],
    ),
    (
        "4. 팀 구성\n(Team)",
        [
            ("representative", "4-1. 대표자 현황 및 보유역량", [
                "대표자가 보유한 창업아이템 구현·판매 관련 역량",
                "소셜벤처는 사회적 가치창출 관련 경력·교육·활동을 함께 기재",
            ]),
            ("teamCapability", "4-2. 팀 현황 및 보유역량", [
                "팀원 또는 채용 예정 인력의 창업아이템 관련 역량",
                "1인 기업은 대표자의 역량을 중심으로 기재",
                "업무 파트너(협력기업)의 현황과 역량",
            ]),
        ],
    ),
]


class BusinessPlanDocumentError(ValueError):
    """A form cannot be filled safely or its layout cannot be identified."""


class BusinessPlanRendererUnavailable(BusinessPlanDocumentError):
    """The deployment has no HWPX-capable PDF renderer."""


def decode_template(file_name: str, content_base64: str) -> tuple[str, bytes]:
    kind = Path(file_name).suffix.lower().lstrip(".")
    if kind not in {"pdf", "hwpx"}:
        raise BusinessPlanDocumentError("PDF 또는 HWPX 양식만 제출할 수 있습니다.")
    if len(content_base64) > (MAX_TEMPLATE_BYTES * 4 // 3 + 8):
        raise BusinessPlanDocumentError("양식 파일은 4 MiB 이하여야 합니다.")
    try:
        data = base64.b64decode(content_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise BusinessPlanDocumentError("양식 파일 데이터가 올바르지 않습니다.") from exc
    if not data or len(data) > MAX_TEMPLATE_BYTES:
        raise BusinessPlanDocumentError("양식 파일은 4 MiB 이하여야 합니다.")
    if kind == "pdf" and not data.startswith(b"%PDF-"):
        raise BusinessPlanDocumentError("PDF 파일 형식이 아닙니다.")
    if kind == "hwpx" and not data.startswith(b"PK"):
        raise BusinessPlanDocumentError("HWPX 파일 형식이 아닙니다.")
    return kind, data


def _pdf_lines(page: pymupdf.Page) -> list[dict]:
    lines = []
    for block in page.get_text("dict")["blocks"]:
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            spans = line["spans"]
            text = "".join(span["text"] for span in spans).strip()
            if text:
                lines.append({
                    "text": text,
                    "rect": pymupdf.Rect(line["bbox"]),
                    "size": max(span["size"] for span in spans),
                    "spans": spans,
                })
    return lines


def _is_blue_guidance(color: int) -> bool:
    red, green, blue = ((color >> shift) & 255 for shift in (16, 8, 0))
    return blue > 120 and blue > red * 1.3 and blue > green * 1.2


def _is_section_heading(line: dict) -> bool:
    text = line["text"]
    if SECTION_HEADING.match(text):
        return line["size"] >= 12
    return (12 <= line["size"] <= 16 and 3 <= len(text) <= 80
            and line["rect"].x0 < 250 and not text.startswith("□")
            and not MAJOR_HEADING.match(text)
            and any(span["flags"] & 16 for span in line["spans"]))


def _field_name_with_guidance(name: str, lines: list[dict], start: float, end: float) -> str:
    guidance = next((line["text"].lstrip("※ ").strip() for line in lines
                     if start <= line["rect"].y0 < end and line["text"].startswith("※")), "")
    if not guidance:
        return name
    available = 200 - len(name) - len(" [작성 안내: ]")
    return f"{name} [작성 안내: {guidance[:available]}]" if available > 0 else name


def _static_pdf_layout(document: pymupdf.Document) -> list[StaticPdfField]:
    fields: list[StaticPdfField] = []
    seen: set[str] = set()
    numbered_sections = any(
        SECTION_HEADING.match(line["text"])
        for page in document for line in _pdf_lines(page)
    )
    for page_index, page in enumerate(document):
        lines = _pdf_lines(page)
        if not lines:
            continue
        tables = list(page.find_tables().tables)
        drawings = page.get_drawings()
        filled_cells = [pymupdf.Rect(item["rect"]) for item in drawings
                        if item["type"] in {"f", "fs"} and item.get("fill") is not None]
        horizontal_lines = [pymupdf.Rect(item["rect"]) for item in drawings
                            if item["type"] == "s" and item["rect"].height < 1]
        for table in tables:
            rows = table.extract()
            if not rows:
                continue
            # A populated header followed by blank rows is a row/column table,
            # not a collection of label/value fields.
            if any(len(rows) - header_index >= 3 and len(header) >= 3
                   and all(value and value.strip() for value in header)
                   and any(sum(not value or not value.strip() for value in body) >= 2
                           for body in rows[header_index + 1:])
                   for header_index, header in enumerate(rows[:2])):
                continue
            value_columns = {column for row in rows for column in range(1, len(row))
                             if row[column - 1] and not row[column]}
            for row_index, row in enumerate(rows):
                row_cells = table.rows[row_index].cells
                row_rects = [pymupdf.Rect(cell) for cell in row_cells if cell]
                if not row_rects:
                    continue
                row_top = min(rect.y0 for rect in row_rects)
                row_bottom = max(rect.y1 for rect in row_rects)
                border = min(page.rect.width - 4, max(
                    (line.x1 for line in horizontal_lines if abs(line.y0 - row_top) < 2
                     and line.x0 <= row_rects[0].x0 + 2), default=table.bbox[2]))
                for column, cell in enumerate(row_cells):
                    if not cell:
                        continue
                    label_rect = pymupdf.Rect(cell)
                    cell_lines = sorted((line for line in lines
                                         if label_rect.contains(line["rect"])),
                                        key=lambda line: line["rect"].y0)
                    if (len(cell_lines) >= 3
                            and len({line["text"] for line in cell_lines}) >= 3
                            and min(b["rect"].y0 - a["rect"].y0
                                    for a, b in zip(cell_lines, cell_lines[1:]))
                            > max(line["size"] for line in cell_lines) * 1.4):
                        next_cell = row_cells[column + 1] if column + 1 < len(row_cells) else None
                        right = min(border, pymupdf.Rect(next_cell).x1 if next_cell else border) - 3
                        if right - label_rect.x1 > 25:
                            for index, line in enumerate(cell_lines):
                                label = line["text"].strip()
                                name = f"{label} [유형: metadata]"
                                if not label or name in seen:
                                    continue
                                bottom = (cell_lines[index + 1]["rect"].y0 - 2
                                          if index + 1 < len(cell_lines) else line["rect"].y1 + 14)
                                fields.append(StaticPdfField(
                                    name, page_index,
                                    [pymupdf.Rect(label_rect.x1 + 3, line["rect"].y0 - 3, right, bottom)],
                                    "metadata"))
                                seen.add(name)
                        continue
                    label = re.sub(r"\s+", " ", row[column] or "").strip()
                    if (not label or len(label) > 30 or not 1 <= len(cell_lines) <= 2
                            or row_bottom - row_top > max(line["size"] for line in cell_lines) * 6
                            or re.search(r"이미지|사진|도면|로고|image|photo|logo", label, re.I)):
                        continue
                    shaded = any(fill.x0 <= label_rect.x0 + 2 and fill.x1 >= label_rect.x1 - 2
                                 and fill.y0 <= row_top + 2 and fill.y1 >= row_bottom - 2
                                 for fill in filled_cells)
                    next_cell = row_cells[column + 1] if column + 1 < len(row_cells) else None
                    next_text = row[column + 1] if column + 1 < len(row) else None
                    if (not shaded and next_text and next_text.strip()
                            and column + 1 not in value_columns):
                        continue
                    if next_cell:
                        right = pymupdf.Rect(next_cell).x1
                    else:
                        right = min((pymupdf.Rect(other).x0 for other in row_cells[column + 1:]
                                     if other), default=border)
                    target = pymupdf.Rect(label_rect.x1 + 3, row_top + 2,
                                          min(right, border) - 3, row_bottom - 2)
                    name = f"{label} [유형: metadata]"
                    if target.width > 25 and name not in seen:
                        fields.append(StaticPdfField(name, page_index, [target], "metadata"))
                        seen.add(name)
        for table in tables:
            rows = table.extract()
            header_index = next((index for index, row in enumerate(rows[:2])
                                 if len(row) >= 3 and sum(bool(value and value.strip()) for value in row) >= 3), None)
            if header_index is None or len(rows) - header_index < 3:
                continue
            columns = tuple(re.sub(r"\s+", " ", value or "").strip()
                            for value in rows[header_index])
            if any(not column for column in columns):
                continue
            body = rows[header_index + 1:]
            if not any(sum(not value or not value.strip() for value in row) >= 2 for row in body):
                continue
            preceding = [line for line in lines if line["rect"].y0 < table.bbox[1]
                         and line["size"] >= 12
                         and (SECTION_HEADING.match(line["text"]) or line["text"].startswith("□"))]
            section = preceding[-1]["text"] if preceding else ""
            table_label = ("사업 추진일정" if "추진기간" in columns else
                           "사업비" if "비목" in columns else
                           "팀원 현황" if "담당업무" in "".join(columns) else "작성 표")
            row_labels = [re.sub(r"\s+", " ", row[0] or "").strip() for row in body]
            fixed_labels = columns[0] == "비목"
            name = f"{section} / {table_label} [표: {' | '.join(columns)}]"
            if fixed_labels:
                name += f" [행: {', '.join(label for label in row_labels if label)}]"
            cells = [[pymupdf.Rect(cell) if cell else None for cell in table.rows[index].cells]
                     for index in range(header_index + 1, len(rows))]
            name += f" [최대 행: {len(cells)}]"
            if name not in seen and len(name) <= 200:
                fields.append(StaticPdfField(name, page_index, [], "table", columns, cells, fixed_labels))
                seen.add(name)
        # A table's left cell names the section; colored text in the wide right
        # cell is sample guidance, never source material for the draft.
        for table in tables:
            rows = table.extract()
            for row_index, row in enumerate(rows):
                name = re.sub(r"\s+", " ", row[0] or "").strip() if row else ""
                if not name or name in seen:
                    continue
                if re.search(r"이미지|사진|도면|로고|image|photo|logo", name, re.I):
                    first_target = next((cell for cell in table.rows[row_index].cells[1:] if cell), None)
                    if first_target:
                        fields.append(StaticPdfField(f"{name} [유형: image]", page_index,
                                                     [pymupdf.Rect(first_target)], "image"))
                        seen.add(name)
                    continue
                if len(name) > 80:
                    continue
                cells = table.rows[row_index].cells
                for cell in cells[1:]:
                    if cell is None:
                        continue
                    rect = pymupdf.Rect(cell)
                    if rect.width < 180 or rect.height < 60:
                        continue
                    if any(_is_blue_guidance(span["color"])
                           and pymupdf.Rect(span["bbox"]).intersects(rect)
                           for line in lines for span in line["spans"]):
                        name = _field_name_with_guidance(name, lines, rect.y0, rect.y1)
                        fields.append(StaticPdfField(name, page_index, [rect + (6, 6, -6, -6)]))
                        seen.add(name)
                        break

        if numbered_sections:
            headings = [line for line in lines if line["size"] >= 12
                        and (SECTION_HEADING.match(line["text"]) or line["text"].startswith("○"))]
        else:
            headings = [line for line in lines if _is_section_heading(line)]
        headings.sort(key=lambda item: item["rect"].y0)
        parent_heading = ""
        for index, heading in enumerate(headings):
            if heading["text"].startswith("○"):
                name = f"{parent_heading} / {heading['text'].lstrip('○ ').strip()}"
            else:
                name = heading["text"]
                parent_heading = name
            if name in seen:
                continue
            start = heading["rect"].y1 + 18
            end = (headings[index + 1]["rect"].y0 - 8
                   if index + 1 < len(headings) else page.rect.height - 58)
            # A table is a separate input field. Empty space below it does not
            # belong to the preceding prose field.
            table_starts = [pymupdf.Rect(table.bbox).y0 for table in tables
                            if start < pymupdf.Rect(table.bbox).y0 < end]
            if table_starts:
                end = min(end, min(table_starts) - 7)
            guidance = [line["rect"].y1 for line in lines
                        if heading["rect"].y1 < line["rect"].y0 < start + 30
                        and (line["text"].startswith("※") or
                             all(_is_blue_guidance(span["color"]) for span in line["spans"]))]
            if guidance:
                start = max(start, max(guidance) + 20)
            intervals = [(start, end)]
            obstacles = [(pymupdf.Rect(table.bbox).y0 - 7,
                          pymupdf.Rect(table.bbox).y1 + 7) for table in tables]
            obstacles += [
                (line["rect"].y0 - 6, line["rect"].y1 + 8)
                for line in lines if start < line["rect"].y0 < end
                and line["size"] >= 10 and len(line["text"]) > 5
                and not line["text"].startswith("※")
                and not all(_is_blue_guidance(span["color"]) for span in line["spans"])
            ]
            for obstacle_start, obstacle_end in sorted(obstacles):
                remaining = []
                for a, b in intervals:
                    if obstacle_end <= a or obstacle_start >= b:
                        remaining.append((a, b))
                    else:
                        if a < obstacle_start:
                            remaining.append((a, obstacle_start))
                        if obstacle_end < b:
                            remaining.append((obstacle_end, b))
                intervals = remaining
            regions = [pymupdf.Rect(100, a, page.rect.width - 55, b)
                       for a, b in sorted(intervals) if b - a >= 35]
            if regions:
                name = _field_name_with_guidance(name, lines, heading["rect"].y1,
                                                 min(end, heading["rect"].y1 + 85))
                markers = [line["text"] for line in lines
                           if line["text"] in {"○", "●", "•", "-", "–"}
                           and any(rect.y0 - 12 <= line["rect"].y0 < rect.y1
                                   and line["rect"].x1 < rect.x0 + 25 for rect in regions)]
                marker_hint = f" [글머리표: {' '.join(markers)}]" if markers else ""
                if len(name) + len(marker_hint) <= 200:
                    name += marker_hint
                fields.append(StaticPdfField(name, page_index, regions))
                seen.add(name)
    if not fields:
        raise BusinessPlanDocumentError(
            "PDF에서 작성 항목을 찾지 못했습니다. 텍스트와 제목이 있는 양식을 사용해 주세요."
        )
    return sorted(fields, key=lambda field: (
        field.page_index,
        min((rect.y0 for rect in field.regions), default=field.table_cells[0][0].y0
            if field.table_cells and field.table_cells[0][0] else 0),
    ))


def inspect_template(kind: str, data: bytes) -> list[str]:
    """Only explicit text fields or intact HWPX markers are fillable."""
    try:
        if kind == "pdf":
            reader = PdfReader(BytesIO(data), strict=True)
            if reader.is_encrypted:
                raise BusinessPlanDocumentError("암호화된 PDF 양식은 사용할 수 없습니다.")
            fields = reader.get_fields() or {}
            names = [name for name, field in fields.items() if field.get("/FT") == "/Tx"]
            if not names:
                with pymupdf.open(stream=data, filetype="pdf") as document:
                    names = [field.name for field in _static_pdf_layout(document)]
                if len(names) > MAX_FIELDS:
                    raise BusinessPlanDocumentError(f"양식의 작성 항목은 {MAX_FIELDS}개 이하여야 합니다.")
                return names
            visible_fields = {
                str((annotation.get("/Parent") or annotation).get_object().get("/T", ""))
                for page in reader.pages
                for reference in page.get("/Annots", [])
                if (annotation := reference.get_object()).get("/Subtype") == "/Widget"
                and annotation.get("/Rect")
            }
            if not set(names).issubset(visible_fields):
                raise BusinessPlanDocumentError("일부 PDF 텍스트 필드의 입력 위치를 확인할 수 없습니다.")
        elif kind == "hwpx":
            with HwpxDocument.open(BytesIO(data)) as document:
                names = list(dict.fromkeys(
                    match.group(1).strip()
                    for run in _hwpx_runs(document)
                    for match in MARKER.finditer(run.text or "")
                ))
                names += [name for name, _ in _hwpx_paragraph_layout(document) if name not in names]
                names += [field.name for field in _hwpx_table_layout(document) if field.name not in names]
                if not names:
                    raise BusinessPlanDocumentError(
                        "HWPX에서 작성할 위치를 찾지 못했습니다. {{항목명}} 표시, 제목 뒤의 빈 문단 또는 열 제목과 빈 셀이 있는 표가 필요합니다."
                    )
        else:
            raise BusinessPlanDocumentError("지원하지 않는 양식입니다.")
    except BusinessPlanDocumentError:
        raise
    except Exception as exc:
        raise BusinessPlanDocumentError("양식을 읽거나 입력 위치를 확인할 수 없습니다.") from exc
    if len(names) > MAX_FIELDS or any(not name.strip() for name in names):
        raise BusinessPlanDocumentError(f"양식 항목은 1~{MAX_FIELDS}개여야 하며 이름이 비어 있으면 안 됩니다.")
    return names


def _static_pdf_font_path() -> str:
    for candidate in (os.getenv("BIZPLAN_PDF_FONT", ""),
                      "C:/Windows/Fonts/malgun.ttf",
                      "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"):
        if candidate and Path(candidate).is_file():
            return candidate
    raise BusinessPlanRendererUnavailable("한글 PDF 글꼴을 찾을 수 없습니다.")


def _wrap_static_text(text: str, font: pymupdf.Font, size: float, width: float) -> list[str]:
    result: list[str] = []
    for paragraph in text.splitlines() or [""]:
        remaining = paragraph
        while remaining:
            low, high = 1, len(remaining)
            while low < high:
                middle = (low + high + 1) // 2
                if font.text_length(remaining[:middle], fontsize=size) <= width:
                    low = middle
                else:
                    high = middle - 1
            if low < len(remaining):
                word_end = remaining.rfind(" ", 0, low + 1)
                if word_end >= low // 2:
                    low = word_end + 1
            result.append(remaining[:low].rstrip())
            remaining = remaining[low:].lstrip()
        if not paragraph:
            result.append("")
    return result


def _draw_static_value(page: pymupdf.Page, regions: list[pymupdf.Rect],
                       value: str, font_path: str, *, center_vertically: bool = False) -> str:
    if not value.strip():
        return ""
    font = pymupdf.Font(fontfile=font_path)
    font_name = "BizplanKorean"
    page.insert_font(fontname=font_name, fontfile=font_path)
    for size in (10.0, 9.0, 8.0):
        lines = _wrap_static_text(value.strip(), font, size,
                                  min(rect.width for rect in regions) - 8)
        capacities = [max(0, int((rect.height - 8) / (size * 1.45))) for rect in regions]
        if len(lines) <= sum(capacities) or size == 8.0:
            position = 0
            for rect, capacity in zip(regions, capacities):
                visible = lines[position:position + capacity]
                top = (max(3, (rect.height - (size + (len(visible) - 1) * size * 1.45)) / 2)
                       if center_vertically and visible else 3)
                for offset, line in enumerate(visible):
                    page.insert_text((rect.x0 + 3, rect.y0 + size + top + offset * size * 1.45),
                                     line, fontname=font_name, fontsize=size, color=(0, 0, 0))
                position += capacity
            return "\n".join(lines[position:]).strip()
    raise BusinessPlanDocumentError("PDF 글꼴 크기 설정이 올바르지 않습니다.")


def _static_bullet_layout(page: pymupdf.Page, field: StaticPdfField,
                          value: str, font_path: str) -> tuple[list[dict], list[tuple[pymupdf.Rect, list[str], float, dict]], str] | None:
    if field.kind != "multiline_text" or not field.regions:
        return None
    markers = sorted((line for line in _pdf_lines(page)
                      if line["text"] in {"○", "●", "•", "-", "–"}
                      and any(rect.y0 - 12 <= line["rect"].y0 < rect.y1
                              and line["rect"].x1 < rect.x0 + 25 for rect in field.regions)),
                     key=lambda line: line["rect"].y0)
    if not markers:
        return None
    fragments = [re.sub(r"^\s*[○●•\-–]\s*", "", line).strip()
                 for line in value.splitlines() if line.strip()]
    joined = " ".join(fragment for fragment in fragments if fragment)
    if re.search(r"[.!?。]", joined):
        items = [sentence.strip() for sentence in re.split(r"(?<=[.!?。])\s+(?=\S)", joined)
                 if sentence.strip()]
    else:
        items = fragments
    if not items:
        return markers, [], ""
    font = pymupdf.Font(fontfile=font_path)
    best_layout = (markers, [], "\n".join(items))
    for size in (10.0, 9.0, 8.0):
        drawn = []
        next_y = 0.0
        previous_region = None
        for index, item in enumerate(items[:len(markers)]):
            marker = markers[index]
            region = next(rect for rect in field.regions
                          if rect.y0 - 12 <= marker["rect"].y0 < rect.y1)
            start_y = max(marker["rect"].y0, next_y if region == previous_region else region.y0)
            left = max(region.x0, marker["rect"].x1 + 12)
            lines = _wrap_static_text(item, font, size, region.x1 - left - 8)
            bottom = start_y + size + 6 + (len(lines) - 1) * size * 1.45
            if bottom > region.y1:
                break
            drawn.append((pymupdf.Rect(left, start_y - 2, region.x1, bottom), lines, size, marker))
            next_y = bottom + 5
            previous_region = region
        overflow = "\n".join(items[len(drawn):]).strip()
        if not overflow:
            return markers, drawn, ""
        if len(overflow) < len(best_layout[2]):
            best_layout = (markers, drawn, overflow)
    return best_layout


def _expand_static_pages(document: pymupdf.Document, expansions: list[dict],
                         font_path: str) -> bytes:
    """Insert writable space below a field and move the following template content."""
    if not expansions:
        return document.tobytes(garbage=4, deflate=True)
    output = pymupdf.open()
    for page_index, source in enumerate(document):
        page_expansions = sorted((item for item in expansions if item["page"] == page_index),
                                 key=lambda item: item["y"])
        if not page_expansions:
            output.insert_pdf(document, from_page=page_index, to_page=page_index)
            continue
        target = output.new_page(width=source.rect.width,
                                 height=source.rect.height + sum(item["height"] for item in page_expansions))
        target.insert_font(fontname="BizplanKorean", fontfile=font_path)
        cursor = 0.0
        shift = 0.0
        for item in page_expansions:
            anchor = max(cursor, min(item["y"], source.rect.height))
            if anchor > cursor:
                clip = pymupdf.Rect(0, cursor, source.rect.width, anchor)
                target.show_pdf_page(clip + (0, shift, 0, shift), document, page_index, clip=clip)
            top = anchor + shift
            size = item["size"]
            leading = size * 1.45
            if "table_rows" in item:
                row_top = top
                for row in item["table_rows"]:
                    if row.get("top_border"):
                        target.draw_line((item["grid_x"][0], row_top),
                                         (item["grid_x"][-1], row_top), width=0.5)
                    for x, lines in row["cells"]:
                        for offset, line in enumerate(lines):
                            target.insert_text((x, row_top + size + 4 + offset * leading), line,
                                               fontname="BizplanKorean", fontsize=size)
                    row_top += row["height"]
                for x in item["grid_x"]:
                    target.draw_line((x, top), (x, top + item["height"]), width=0.5)
            else:
                y = top + size + 4
                for marker, lines in item["paragraphs"]:
                    if marker:
                        target.insert_text((item["marker_x"], y), marker,
                                           fontname="BizplanKorean", fontsize=size)
                    for line in lines:
                        target.insert_text((item["x"], y), line,
                                           fontname="BizplanKorean", fontsize=size)
                        y += leading
                    y += 5
                for x in item.get("grid_x", []):
                    target.draw_line((x, top), (x, top + item["height"]), width=0.5)
            shift += item["height"]
            cursor = anchor
        if cursor < source.rect.height:
            clip = pymupdf.Rect(0, cursor, source.rect.width, source.rect.height)
            target.show_pdf_page(clip + (0, shift, 0, shift), document, page_index, clip=clip)
    return output.tobytes(garbage=4, deflate=True)


def _numeric_footer(page: pymupdf.Page) -> dict | None:
    return next((line for line in _pdf_lines(page)
                 if re.fullmatch(r"\d+", line["text"])
                 and line["rect"].y0 > page.rect.height - 70
                 and abs((line["rect"].x0 + line["rect"].x1) / 2
                         - page.rect.width / 2) < 35), None)


def _page_body_end(page: pymupdf.Page, footer: dict | None) -> float:
    """Find the last visible body element, excluding the footer and blank margin."""
    footer_top = footer["rect"].y0 if footer else page.rect.height
    bottoms = [line["rect"].y1 for line in _pdf_lines(page)
               if line["rect"].y0 < footer_top - 5]
    bottoms.extend(rect.y1 for drawing in page.get_drawings()
                   if (rect := pymupdf.Rect(drawing["rect"])).y0 < footer_top - 5
                   and rect.height < page.rect.height * 0.85)
    bottoms.extend(rect.y1 for block in page.get_text("dict")["blocks"]
                   if block["type"] == 1
                   and (rect := pymupdf.Rect(block["bbox"])).y0 < footer_top - 5)
    return min(footer_top - 8, max(bottoms, default=0) + 10)


def _reflow_page_cut(page: pymupdf.Page, start: float, limit: float,
                     body_end: float, next_capacity: float) -> float:
    lines = sorted(_pdf_lines(page), key=lambda line: line["rect"].y0)
    headings = [line for line in lines if SECTION_HEADING.match(line["text"])
                or line["text"].startswith("□")]
    for index in range(len(headings) - 1, -1, -1):
        heading = headings[index]
        group_end = headings[index + 1]["rect"].y0 if index + 1 < len(headings) else body_end
        if (start + 60 < heading["rect"].y0 < limit < group_end
                and group_end - heading["rect"].y0 <= next_capacity):
            return heading["rect"].y0 - 10
    tables = [pymupdf.Rect(table.bbox) for table in page.find_tables().tables]
    for table in tables:
        if (start + 60 < table.y0 < limit < table.y1
                and table.height <= next_capacity):
            return table.y0 - 8
    gaps = [(left["rect"].y1 + right["rect"].y0) / 2
            for left, right in zip(lines, lines[1:])
            if left["rect"].y1 + 1 < right["rect"].y0
            and start + 50 < (left["rect"].y1 + right["rect"].y0) / 2 <= limit]
    safe_gaps = [gap for gap in gaps if not any(rect.y0 < gap < rect.y1
                                                and rect.height <= next_capacity for rect in tables)]
    return max(safe_gaps or gaps, default=limit)


def _paginate_expanded_pdf(data: bytes, page_sizes: list[tuple[float, float]]) -> tuple[bytes, list[int]]:
    """Flow enlarged template pages onto pages of their original fixed size."""
    with pymupdf.open(stream=data, filetype="pdf") as document:
        if all(page.rect.height <= page_sizes[index][1] + 0.5
               for index, page in enumerate(document)):
            return data, list(range(len(document)))
        output = pymupdf.open()
        page_starts = []
        numbered = any(_numeric_footer(page) for page in document)
        for index, source in enumerate(document):
            page_starts.append(len(output))
            width, height = page_sizes[index]
            if source.rect.height <= height + 0.5:
                output.insert_pdf(document, from_page=index, to_page=index)
                continue
            footer = _numeric_footer(source)
            body_end = _page_body_end(source, footer)
            start = 0.0
            first = True
            while start < body_end - 0.5:
                destination_top = 0 if first else 60
                capacity = height - 58 - destination_top
                limit = min(start + capacity, body_end)
                end = (body_end if limit >= body_end else
                       _reflow_page_cut(source, start, limit, body_end, height - 118))
                if end <= start + 40:
                    end = limit
                page = output.new_page(width=width, height=height)
                clip = pymupdf.Rect(0, start, width, end)
                page.show_pdf_page(pymupdf.Rect(0, destination_top, width,
                                                destination_top + end - start),
                                   document, index, clip=clip)
                start = end
                first = False
        if numbered:
            for index, page in enumerate(output):
                footer = _numeric_footer(page)
                if footer:
                    page.add_redact_annot(footer["rect"] + (-2, -2, 2, 2),
                                          fill=False, cross_out=False)
                    page.apply_redactions(images=0, graphics=0, text=0)
                number = str(index + 1)
                x = (page.rect.width - pymupdf.get_text_length(number, fontname="helv", fontsize=9)) / 2
                page.insert_text((x, page.rect.height - 29), number, fontname="helv", fontsize=9)
        return output.tobytes(garbage=4, deflate=True), page_starts


def _static_text_expansion(field: StaticPdfField, overflow: str,
                           font: pymupdf.Font, *, bullet_layout: tuple | None = None) -> dict:
    size = bullet_layout[1][-1][2] if bullet_layout and bullet_layout[1] else 8.0
    marker = bullet_layout[0][-1] if bullet_layout else None
    rect = (next(rect for rect in field.regions
                 if rect.y0 - 12 <= marker["rect"].y0 < rect.y1)
            if marker else field.regions[-1])
    x = max(rect.x0, marker["rect"].x1 + 12) + 3 if marker else rect.x0 + 3
    paragraphs = [(marker["text"] if marker else "",
                   _wrap_static_text(text, font, size, rect.x1 - x - 5))
                  for text in (overflow.splitlines() if marker else [overflow]) if text.strip()]
    height = sum(max(1, len(lines)) * size * 1.45 + 5 for _, lines in paragraphs) + 8
    return {"page": field.page_index, "y": rect.y1, "height": height,
            "x": x, "marker_x": marker["rect"].x0 if marker else 0,
            "size": size, "paragraphs": paragraphs}


def _static_row_grid(page: pymupdf.Page, region: pymupdf.Rect) -> list[float]:
    for table in page.find_tables().tables:
        for row in table.rows:
            cells = [pymupdf.Rect(cell) for cell in row.cells if cell]
            if any(cell.y0 <= region.y0 + 3 and region.y1 <= cell.y1
                   and cell.x0 <= region.x0 <= region.x1 <= cell.x1 for cell in cells):
                return sorted({x for cell in cells for x in (cell.x0, cell.x1)})
    return []


def _static_table_expansions(field: StaticPdfField,
                             overflow_cells: list[tuple[int, int, str]],
                             extra_rows: list[list[str]], font: pymupdf.Font) -> list[dict]:
    if not field.table_cells:
        return []
    expansions = []
    for row_index in sorted({row for row, _, _ in overflow_cells}):
        row = field.table_cells[row_index]
        cells = []
        for _, column, text in (item for item in overflow_cells if item[0] == row_index):
            rect = row[column]
            if rect:
                cells.append((rect.x0 + 4, _wrap_static_text(text, font, 8, rect.width - 8)))
        if not cells:
            continue
        height = max(len(lines) * 11.6 + 8 for _, lines in cells)
        grid_x = sorted({x for rect in row if rect for x in (rect.x0, rect.x1)})
        expansions.append({"page": field.page_index, "y": max(rect.y1 for rect in row if rect) - 2,
                           "height": height, "size": 8, "grid_x": grid_x,
                           "table_rows": [{"height": height, "cells": cells}]})
    if extra_rows:
        last_row = field.table_cells[-1]
        grid_x = sorted({x for rect in last_row if rect for x in (rect.x0, rect.x1)})
        table_rows = []
        for values in extra_rows:
            cells = []
            for column, text in enumerate(values):
                rect = last_row[column]
                if rect and text:
                    cells.append((rect.x0 + 4, _wrap_static_text(text, font, 8, rect.width - 8)))
            height = max(28, max((len(lines) * 11.6 + 8 for _, lines in cells), default=0))
            table_rows.append({"height": height, "cells": cells, "top_border": True})
        expansions.append({"page": field.page_index,
                           "y": max(rect.y1 for rect in last_row if rect) - 2,
                           "height": sum(row["height"] for row in table_rows), "size": 8,
                           "grid_x": grid_x, "table_rows": table_rows})
    return expansions


def _image_size(mime_type: str, raw: bytes) -> tuple[int, int]:
    if not raw or len(raw) > 2 * 1024 * 1024:
        raise BusinessPlanDocumentError("이미지는 파일당 2 MiB 이하여야 합니다.")
    signature = b"\x89PNG\r\n\x1a\n" if mime_type == "image/png" else b"\xff\xd8\xff"
    if mime_type not in {"image/png", "image/jpeg"} or not raw.startswith(signature):
        raise BusinessPlanDocumentError("PNG 또는 JPEG 이미지 파일만 첨부할 수 있습니다.")
    try:
        with Image.open(BytesIO(raw)) as image:
            if image.format != ("PNG" if mime_type == "image/png" else "JPEG"):
                raise ValueError("image format does not match its MIME type")
            width, height = image.size
            image.verify()
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise BusinessPlanDocumentError("이미지 파일을 읽을 수 없습니다.") from exc
    if not (0 < width <= 6000 and 0 < height <= 6000):
        raise BusinessPlanDocumentError("이미지 가로·세로 크기는 6000픽셀 이하여야 합니다.")
    return width, height


def _render_static_pdf(data: bytes, values: dict[str, str], title: str,
                       images: dict[str, tuple[str, bytes]] | None = None) -> bytes:
    with pymupdf.open(stream=data, filetype="pdf") as document:
        page_sizes = [(page.rect.width, page.rect.height) for page in document]
        fields = _static_pdf_layout(document)
        images = images or {}
        if set(images) - {field.name for field in fields if field.kind == "image"}:
            raise BusinessPlanDocumentError("이미지를 배치할 수 있는 PDF 입력 영역을 찾지 못했습니다.")
        font_path = _static_pdf_font_path()
        bullet_layouts = {field.name: layout
                          for field in fields if (layout := _static_bullet_layout(
                              document[field.page_index], field, values.get(field.name, ""), font_path))}
        expansions: list[dict] = []
        font = pymupdf.Font(fontfile=font_path)
        for page_index, page in enumerate(document):
            page_lines = _pdf_lines(page)
            guidance_continuations: set[int] = set()
            preceding_guidance = None
            for line in sorted(page_lines, key=lambda item: item["rect"].y0):
                if line["text"].startswith("※"):
                    preceding_guidance = line
                elif (preceding_guidance is not None
                      and 0 <= line["rect"].y0 - preceding_guidance["rect"].y1 <= 10
                      and abs(line["rect"].x0 - preceding_guidance["rect"].x0) <= 4):
                    guidance_continuations.add(id(line))
                    preceding_guidance = line
                else:
                    preceding_guidance = None
            page_regions = [rect for field in fields if field.page_index == page_index
                            for rect in field.regions]
            page_table_cells = [rect for field in fields if field.page_index == page_index
                                and field.table_cells for row in field.table_cells
                                for column, rect in enumerate(row)
                                if rect and not (field.fixed_row_labels and column == 0)]
            for line in page_lines:
                text = line["text"]
                if (text.startswith("※") or id(line) in guidance_continuations
                        or (text.startswith("<") and text.endswith(">"))):
                    page.add_redact_annot(line["rect"], fill=False, cross_out=False)
                    continue
                for span in line["spans"]:
                    span_rect = pymupdf.Rect(span["bbox"])
                    if _is_blue_guidance(span["color"]) or any(
                        region.intersects(span_rect) for region in page_regions
                    ) or any(
                        cell.contains(span_rect) for cell in page_table_cells
                    ):
                        page.add_redact_annot(span_rect, fill=False, cross_out=False)
            for field in fields:
                if field.page_index == page_index and field.name in bullet_layouts:
                    markers, _, _ = bullet_layouts[field.name]
                    for marker in markers:
                        page.add_redact_annot(marker["rect"], fill=False, cross_out=False)
            page.apply_redactions(images=0, graphics=0, text=0)

        # A single blank value cell next to a name label is the form's title slot.
        title_overflow: tuple[pymupdf.Rect, str] | None = None
        if title.strip():
            first_page = document[0]
            for table in first_page.find_tables().tables:
                for index, row in enumerate(table.extract()):
                    label = re.sub(r"\s+", " ", row[0] or "").strip() if row else ""
                    if re.search(r"사업명|아이템명|서비스명|제품명|business name|project name|item name",
                                 label, re.I) and all(
                        not value for value in row[1:]
                    ) and not any(
                        field.kind == "metadata" and field.page_index == 0
                        and field.name.split(" [", 1)[0] == label for field in fields
                    ):
                        first_cell = table.rows[index].cells[0]
                        if first_cell:
                            cell = pymupdf.Rect(first_cell)
                            target = pymupdf.Rect(cell.x1 + 4, cell.y0 + 3,
                                                  first_page.rect.width - 55, cell.y1 - 3)
                            overflow = _draw_static_value(
                                first_page, [target], title, font_path,
                            )
                            if overflow:
                                title_overflow = (target, overflow)
                            break
                else:
                    continue
                break

        for field in fields:
            value = values.get(field.name, "")
            if field.kind == "table":
                overflow_cells, extra_rows = _draw_static_table(
                    document[field.page_index], field, value, font_path)
                expansions.extend(_static_table_expansions(
                    field, overflow_cells, extra_rows, font))
            elif field.kind == "image" and field.name in images:
                mime_type, raw = images[field.name]
                _image_size(mime_type, raw)
                try:
                    document[field.page_index].insert_image(field.regions[0] + (3, 3, -3, -3),
                                                            stream=raw, keep_proportion=True, overlay=True)
                except (RuntimeError, ValueError) as exc:
                    raise BusinessPlanDocumentError("이미지를 PDF 양식에 배치하지 못했습니다.") from exc
            elif field.name in bullet_layouts:
                page = document[field.page_index]
                page.insert_font(fontname="BizplanKorean", fontfile=font_path)
                for slot, lines, size, marker in bullet_layouts[field.name][1]:
                    page.insert_text((marker["rect"].x0, slot.y0 + size + 2), marker["text"],
                                     fontname="BizplanKorean", fontsize=size, color=(0, 0, 0))
                    for offset, line in enumerate(lines):
                        page.insert_text((slot.x0 + 3, slot.y0 + size + 2 + offset * size * 1.45),
                                         line, fontname="BizplanKorean", fontsize=size, color=(0, 0, 0))
                overflow = bullet_layouts[field.name][2]
                if overflow:
                    expansions.append(_static_text_expansion(
                        field, overflow, font, bullet_layout=bullet_layouts[field.name]))
            elif field.kind != "image":
                overflow = _draw_static_value(
                    document[field.page_index], field.regions, value, font_path,
                    center_vertically=field.kind == "metadata",
                )
                if overflow:
                    expansion = _static_text_expansion(field, overflow, font)
                    if field.kind == "metadata":
                        expansion["grid_x"] = _static_row_grid(
                            document[field.page_index], field.regions[-1])
                    expansions.append(expansion)
        if title_overflow:
            rect, overflow = title_overflow
            expansion = _static_text_expansion(
                StaticPdfField("사업명", 0, [rect], "metadata"), overflow, font)
            expansion["grid_x"] = _static_row_grid(document[0], rect)
            expansions.append(expansion)
        expanded = _expand_static_pages(document, expansions, font_path)
        return _paginate_expanded_pdf(expanded, page_sizes)[0]


def _parse_table_value(value: str, columns: tuple[str, ...]) -> list[list[str]]:
    if value.lstrip().startswith("{"):
        try:
            data = json.loads(value)
            rows = data["rows"]
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                raise ValueError("rows must contain objects")
            return [[str(row[column]).strip() if row.get(column) is not None else ""
                     for column in columns] for row in rows]
        except (ValueError, TypeError, KeyError) as exc:
            raise BusinessPlanDocumentError("표의 행·열 데이터가 올바르지 않습니다.") from exc
    rows = []
    for line in value.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("\t" if "\t" in line else "|")]
        if not any(cells) or all(re.fullmatch(r":?-{2,}:?", cell) for cell in cells):
            continue
        if tuple(cells) == columns:
            continue
        if len(cells) != len(columns):
            raise BusinessPlanDocumentError("표 열 개수가 양식과 다릅니다.")
        rows.append(cells)
    return rows


def _draw_static_table(page: pymupdf.Page, field: StaticPdfField,
                       value: str, font_path: str) -> tuple[list[tuple[int, int, str]], list[list[str]]]:
    if not value.strip() or not field.table_cells:
        return [], []
    rows = _parse_table_value(value, field.columns)
    capacity = len(field.table_cells)
    if len(rows) > capacity and field.fixed_row_labels:
        raise BusinessPlanDocumentError(f"표의 입력 행이 부족합니다: {field.name}")
    fixed_row_indices: dict[str, int] = {}
    if field.fixed_row_labels:
        fixed_row_indices = {
            (page.get_textbox(cells[0]) if cells[0] else "").strip(): index
            for index, cells in enumerate(field.table_cells)
        }
    used_rows: set[int] = set()
    overflow_cells: list[tuple[int, int, str]] = []
    for position, row in enumerate(rows[:capacity]):
        row_index = fixed_row_indices.get(row[0], -1) if field.fixed_row_labels else position
        if row_index < 0 or row_index in used_rows:
            raise BusinessPlanDocumentError(f"표의 고정 행 이름이 양식과 다릅니다: {field.name}")
        used_rows.add(row_index)
        for column, cell_value in enumerate(row):
            if field.fixed_row_labels and column == 0:
                continue
            rect = field.table_cells[row_index][column]
            if rect and cell_value:
                overflow = _draw_static_value(
                    page, [rect + (2, 1, -2, -1)], cell_value, font_path,
                    center_vertically=True,
                )
                if overflow:
                    overflow_cells.append((row_index, column, overflow))
    return overflow_cells, rows[capacity:]


def render_pdf_form(data: bytes, values: dict[str, str], title: str = "",
                    images: dict[str, tuple[str, bytes]] | None = None) -> bytes:
    names = inspect_template("pdf", data)
    if not (PdfReader(BytesIO(data)).get_fields() or {}):
        return _render_static_pdf(data, values, title, images)
    if images:
        raise BusinessPlanDocumentError("PDF 텍스트 입력 필드에는 이미지를 배치할 수 없습니다.")
    writer = PdfWriter()
    writer.append(PdfReader(BytesIO(data)))
    page_sizes = [(float(page.mediabox.width), float(page.mediabox.height)) for page in writer.pages]
    filled_values = {name: values.get(name, "").strip() for name in names}
    font = _register_korean_font()
    drawn_names: set[str] = set()
    field_pages: dict[str, int] = {}
    overflow_fields: list[tuple[int, str, pymupdf.Rect, str]] = []
    for page_index, page in enumerate(writer.pages):
        writer.update_page_form_field_values(
            page,
            filled_values,
            auto_regenerate=False,
        )
        kept_annotations = ArrayObject()
        overlay = BytesIO()
        media_box = page.mediabox
        painter = pdf_canvas.Canvas(overlay, pagesize=(float(media_box.width), float(media_box.height)))
        drawn = False
        for reference in page.get("/Annots", []):
            annotation = reference.get_object()
            parent = annotation.get("/Parent")
            field = parent.get_object() if parent else annotation
            name = str(field.get("/T", ""))
            if name not in filled_values or annotation.get("/Subtype") != "/Widget":
                kept_annotations.append(reference)
                continue
            rect = annotation.get("/Rect")
            if not rect or len(rect) != 4:
                raise BusinessPlanDocumentError(f"PDF 입력 위치를 확인할 수 없습니다: {name}")
            x0, y0, x1, y1 = (float(value) for value in rect)
            width, height = x1 - x0, y1 - y0
            if width < 25 or height < 14:
                raise BusinessPlanDocumentError(f"PDF 입력칸이 너무 작습니다: {name}")
            lines = _wrap_pdf_field(filled_values[name], font, 9, width - 6)
            visible_lines = max(0, int((height - 4) // 12))
            if len(lines) > visible_lines and filled_values[name]:
                page_height = float(media_box.height)
                overflow_fields.append((page_index, name,
                                        pymupdf.Rect(x0, page_height - y1, x1, page_height - y0),
                                        "\n".join(lines[visible_lines:])))
            lines = lines[:visible_lines]
            painter.setStrokeColor(colors.HexColor("#777777"))
            painter.setLineWidth(0.5)
            painter.rect(x0, y0, width, height, stroke=1, fill=0)
            painter.setFillColor(colors.black)
            painter.setFont(font, 9)
            for index, line in enumerate(lines):
                painter.drawString(x0 + 3, y1 - 12 - index * 12, line)
            drawn = True
            drawn_names.add(name)
            field_pages[name] = page_index
        if drawn:
            painter.save()
            overlay.seek(0)
            page.merge_page(PdfReader(overlay).pages[0])
            page[NameObject("/Annots")] = kept_annotations
    if set(names) != drawn_names:
        raise BusinessPlanDocumentError("일부 PDF 텍스트 필드의 입력 위치를 확인할 수 없습니다.")
    output = BytesIO()
    writer.write(output)
    if overflow_fields:
        with pymupdf.open(stream=output.getvalue(), filetype="pdf") as document:
            font_path = _static_pdf_font_path()
            font = pymupdf.Font(fontfile=font_path)
            expansions = []
            for page_index, name, rect, value in overflow_fields:
                expansion = _static_text_expansion(
                    StaticPdfField(name, page_index, [rect]), value, font)
                expansion["y"] -= 2
                expansion["grid_x"] = [rect.x0, rect.x1]
                expansions.append(expansion)
            expanded = _expand_static_pages(document, expansions, font_path)
        paginated, page_starts = _paginate_expanded_pdf(expanded, page_sizes)
        with pymupdf.open(stream=paginated, filetype="pdf") as document:
            for name, value in filled_values.items():
                widget = pymupdf.Widget()
                widget.field_name = name
                widget.field_value = value
                widget.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
                widget.field_flags = pymupdf.PDF_FIELD_IS_READ_ONLY
                widget.rect = pymupdf.Rect(0, 0, 1, 1)
                widget.border_width = 0
                widget.text_fontsize = 1
                document[page_starts[field_pages[name]]].add_widget(widget)
            return document.tobytes(garbage=4, deflate=True)
    return output.getvalue()


def _wrap_pdf_field(value: str, font: str, font_size: int, width: float) -> list[str]:
    lines: list[str] = []
    for paragraph in value.splitlines() or [""]:
        current = ""
        for character in paragraph:
            candidate = current + character
            if current and pdfmetrics.stringWidth(candidate, font, font_size) > width:
                lines.append(current)
                current = character
            else:
                current = candidate
        lines.append(current)
    return lines


def _hwpx_runs(document: HwpxDocument):
    yield from document.text.runs()
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    yield from paragraph.runs


def _hwpx_table_layout(document: HwpxDocument) -> list[HwpxTableField]:
    fields = []
    for table_index, table in enumerate(document.tables):
        rows = [[re.sub(r"\s+", " ", cell.text or "").strip() for cell in row.cells]
                for row in table.rows]
        if any(MARKER.search(cell) for row in rows for cell in row):
            continue
        for header_index, columns in enumerate(rows[:2]):
            if len(columns) < 2 or any(not column for column in columns):
                continue
            body = rows[header_index + 1:]
            if not body or not any(sum(not cell for cell in row) >= 1 for row in body):
                continue
            if any(len(row) != len(columns) for row in body):
                continue
            fixed_labels = all(row[0] and any(not cell for cell in row[1:]) for row in body)
            name = f"작성 표 {table_index + 1} [표: {' | '.join(columns)}]"
            if fixed_labels:
                name += f" [행: {', '.join(row[0] for row in body)}]"
            name += f" [최대 행: {len(body)}]"
            if len(name) <= 200:
                fields.append(HwpxTableField(name, table_index, header_index,
                                             tuple(columns), [row[0] for row in body] if fixed_labels else []))
            break
    return fields


def _hwpx_paragraph_layout(document: HwpxDocument) -> list[tuple[str, int]]:
    fields = []
    seen: set[str] = set()
    paragraphs = document.paragraphs
    for index, paragraph in enumerate(paragraphs[:-1]):
        heading = re.sub(r"\s+", " ", paragraph.text or "").strip()
        following = paragraphs[index + 1]
        if not (SECTION_HEADING.match(heading) and not (following.text or "").strip()
                and not following.tables):
            continue
        name = heading
        if name in seen:
            name = f"{heading} [작성 칸 {len(fields) + 1}]"
        fields.append((name, index + 1))
        seen.add(name)
    return fields


def render_hwpx_form(data: bytes, values: dict[str, str],
                     images: dict[str, tuple[str, bytes]] | None = None) -> bytes:
    names = inspect_template("hwpx", data)
    with HwpxDocument.open(BytesIO(data)) as document:
        images = images or {}
        paragraph_fields = _hwpx_paragraph_layout(document)
        table_fields = _hwpx_table_layout(document)
        image_paragraphs = {}
        for paragraph in document.paragraphs:
            for marker in MARKER.finditer(paragraph.text or ""):
                image_paragraphs.setdefault(marker.group(1).strip(), (paragraph, 12000, 12000))
        for table in document.tables:
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        for marker in MARKER.finditer(paragraph.text or ""):
                            image_paragraphs[marker.group(1).strip()] = (
                                paragraph, min(12000, max(1000, cell.width - 1000)),
                                min(12000, max(1000, cell.height - 500)),
                            )
        image_paragraphs.update({name: (document.paragraphs[index], 12000, 12000) for name, index in paragraph_fields
                                 if re.search(r"이미지|사진|도면|로고|image|photo|logo", name, re.I)})
        if set(images) - set(image_paragraphs):
            raise BusinessPlanDocumentError("이미지를 배치할 수 있는 HWPX 입력 영역을 찾지 못했습니다.")
        for run in _hwpx_runs(document):
            run.text = MARKER.sub(
                lambda match: values.get(match.group(1).strip(), "").strip(), run.text or ""
            )
        for name, index in paragraph_fields:
            if values.get(name, "").strip():
                document.paragraphs[index].set_text_preserving_runs(values[name].strip())
        for name, (mime_type, raw) in images.items():
            width, height = _image_size(mime_type, raw)
            paragraph, max_width, max_height = image_paragraphs[name]
            scale = min(max_width / width, max_height / height)
            item = document.media.add_image(raw, "png" if mime_type == "image/png" else "jpg")
            paragraph.add_picture(str(item), width=round(width * scale), height=round(height * scale))
        tables = list(document.tables)
        for field in table_fields:
            rows = _parse_table_value(values.get(field.name, ""), field.columns)
            table = tables[field.table_index]
            capacity = table.row_count - field.header_index - 1
            if len(rows) > capacity:
                raise BusinessPlanDocumentError(f"표의 입력 행이 부족합니다: {field.name}")
            for position, row in enumerate(rows):
                row_index = field.row_labels.index(row[0]) if field.row_labels and row[0] in field.row_labels else position
                if field.row_labels and row[0] not in field.row_labels:
                    raise BusinessPlanDocumentError(f"표의 고정 행 이름이 양식과 다릅니다: {field.name}")
                for column, value in enumerate(row):
                    if field.row_labels and column == 0:
                        continue
                    cell = table.cell(field.header_index + 1 + row_index, column)
                    if value and not cell.text.strip():
                        cell.set_text(value)
        result = document.to_bytes()
    with HwpxDocument.open(BytesIO(result)) as check:
        if any(MARKER.search(run.text or "") for run in _hwpx_runs(check)):
            raise BusinessPlanDocumentError("양식의 일부 입력 위치를 채우지 못했습니다.")
    return result


def _default_section_values(sections: list[dict[str, str]]) -> dict[str, str]:
    by_key = {str(section.get("key") or "").strip(): section for section in sections}
    by_label = {str(section.get("label") or "").strip(): section for section in sections}
    values: dict[str, str] = {}
    fields = DEFAULT_OVERVIEW_FIELDS + [
        (key, heading)
        for _, items in DEFAULT_PLAN_GROUPS
        for key, heading, _ in items
    ]
    for key, label in fields:
        section = by_key.get(key) or by_label.get(label)
        values[key] = str((section or {}).get("content") or "").strip() or MISSING
    return values


def render_default_hwpx(title: str, sections: list[dict[str, str]]) -> bytes:
    document = HwpxDocument.new()
    document.page.setup(
        paper_size="A4",
        margin_left_mm=9,
        margin_right_mm=9,
        margin_top_mm=8,
        margin_bottom_mm=8,
        header_margin_mm=4,
        footer_margin_mm=4,
    )
    normal = document.styles.ensure_run(font="나눔고딕", size=8.5)
    bold = document.styles.ensure_run(font="나눔고딕", size=9, bold=True)
    group = document.styles.ensure_run(font="나눔고딕", size=10, bold=True)
    title_style = document.styles.ensure_run(font="나눔고딕", size=17, bold=True)
    values = _default_section_values(sections)

    title_table = document.add_table(1, 1, width=54000, height=5200)
    title_table.set_cell_shading(0, 0, "#D0D0D0")
    _set_hwpx_cell(
        document,
        title_table.cell(0, 0),
        f"창업사업화 지원사업 사업계획서 (예비단계)\n{title or '사업계획서'}",
        char_style=title_style,
        alignment="CENTER",
    )

    overview = document.add_table(4, 2, width=54000)
    overview.set_column_widths([17, 83])
    overview.set_cell_shading(0, 0, "#D0D0D0")
    overview.set_cell_shading(0, 1, "#D0D0D0")
    _set_hwpx_cell(document, overview.cell(0, 0), "항목", char_style=bold, alignment="CENTER")
    _set_hwpx_cell(document, overview.cell(0, 1), "세부항목", char_style=bold, alignment="CENTER")
    for row, (key, label) in enumerate(DEFAULT_OVERVIEW_FIELDS, 1):
        overview.set_cell_shading(row, 0, "#D0D0D0")
        _set_hwpx_cell(document, overview.cell(row, 0), f"□ {label}", char_style=bold, alignment="CENTER")
        _set_hwpx_cell(document, overview.cell(row, 1), values[key], char_style=normal)

    row_count = sum(len(items) for _, items in DEFAULT_PLAN_GROUPS)
    outline = document.add_table(row_count, 2, width=54000)
    outline.set_column_widths([17, 83])
    current_row = 0
    for group_label, items in DEFAULT_PLAN_GROUPS:
        start_row = current_row
        for key, heading, _ in items:
            text = heading + "\n" + values[key]
            _set_hwpx_cell(
                document,
                outline.cell(current_row, 1),
                text,
                char_style=normal,
                first_line_style=bold,
            )
            current_row += 1
        end_row = current_row - 1
        if end_row > start_row:
            left = outline.merge_cells(start_row, 0, end_row, 0)
        else:
            left = outline.cell(start_row, 0)
        outline.set_cell_shading(start_row, 0, "#D0D0D0")
        _set_hwpx_cell(document, left, group_label, char_style=group, alignment="CENTER")
    return document.to_bytes()


def _set_hwpx_cell(
    document: HwpxDocument,
    cell: Any,
    text: str,
    *,
    char_style: str,
    first_line_style: str | None = None,
    alignment: str = "LEFT",
) -> None:
    """Write styled multiline text into one authored HWPX table cell."""
    cell.set_text(text, split_paragraphs=True)
    para_style = document.parts.headers[0].ensure_paragraph_format(
        alignment=alignment,
        line_spacing_percent=112,
    )
    for index, paragraph in enumerate(cell.paragraphs):
        paragraph.element.set("paraPrIDRef", para_style)
        style = first_line_style if index == 0 and first_line_style else char_style
        for run in paragraph.runs:
            run.element.set("charPrIDRef", style)


def _register_korean_font() -> str:
    candidates = [
        os.getenv("BIZPLAN_PDF_FONT", ""),
        "C:/Windows/Fonts/malgun.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            if "BizplanKorean" not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont("BizplanKorean", candidate))
            return "BizplanKorean"
    raise BusinessPlanDocumentError("PDF 출력을 위한 한국어 글꼴을 찾지 못했습니다.")


def render_default_pdf(title: str, sections: list[dict[str, str]]) -> bytes:
    font = _register_korean_font()
    output = BytesIO()
    document = SimpleDocTemplate(
        output, pagesize=A4, leftMargin=24, rightMargin=24, topMargin=22, bottomMargin=22,
    )
    title_bar = ParagraphStyle("title_bar", fontName=font, fontSize=17, leading=22, alignment=1)
    table_head = ParagraphStyle("table_head", fontName=font, fontSize=9, leading=11, alignment=1)
    group_style = ParagraphStyle("group", fontName=font, fontSize=9, leading=11, alignment=1)
    detail_style = ParagraphStyle("detail", fontName=font, fontSize=8.5, leading=12, alignment=TA_LEFT)
    width = A4[0] - 48
    values = _default_section_values(sections)
    story = [
        Table([[Paragraph(
            "창업사업화 지원사업 사업계획서 <font color='#0000FF'>(예비단계)</font>"
            f"<br/><font size='11'>{escape(title or '사업계획서')}</font>",
            title_bar,
        )]],
              colWidths=[width], style=TableStyle([
                  ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#D0D0D0")),
                  ("BOX", (0, 0), (-1, -1), 0.7, colors.black),
                  ("TOPPADDING", (0, 0), (-1, -1), 10),
                  ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
              ])),
        Spacer(1, 10),
    ]
    overview_data = [
        [Paragraph("<b>항목</b>", table_head), Paragraph("<b>세부항목</b>", table_head)],
        *[
            [
                Paragraph(
                    "□ " + (escape(label).replace(" ", "<br/>", 1) if key == "itemOverview" else escape(label)),
                    table_head,
                ),
                Paragraph(escape(values[key]).replace("\n", "<br/>"), detail_style),
            ]
            for key, label in DEFAULT_OVERVIEW_FIELDS
        ],
    ]
    overview_table = Table(overview_data, colWidths=[95, width - 95])
    overview_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.55, colors.black),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D0D0D0")),
        ("BACKGROUND", (0, 1), (0, -1), colors.HexColor("#D0D0D0")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.extend([overview_table, Spacer(1, 10)])

    outline_data: list[list[Any]] = []
    outline_style = [
        ("GRID", (0, 0), (-1, -1), 0.55, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    current_row = 0
    for group_label, items in DEFAULT_PLAN_GROUPS:
        start_row = current_row
        for item_index, (key, item_heading, _) in enumerate(items):
            content = escape(values[key]).replace("\n", "<br/>")
            detail = Paragraph(f"<b>{escape(item_heading)}</b><br/>{content}", detail_style)
            left = Paragraph(escape(group_label).replace("\n", "<br/>"), group_style) if item_index == 0 else ""
            outline_data.append([left, detail])
            current_row += 1
        outline_style.extend([
            ("SPAN", (0, start_row), (0, current_row - 1)),
            ("BACKGROUND", (0, start_row), (0, current_row - 1), colors.HexColor("#D0D0D0")),
        ])
    outline_table = Table(outline_data, colWidths=[95, width - 95], repeatRows=0)
    outline_table.setStyle(TableStyle(outline_style))
    story.append(outline_table)
    document.build(story)
    return output.getvalue()


def convert_hwpx_to_pdf(data: bytes) -> bytes:
    executable = os.getenv("BIZPLAN_HWP_CLI") or shutil.which("hwp")
    if not executable:
        raise BusinessPlanRendererUnavailable("HWPX PDF 변환기가 설치되지 않았습니다.")
    with tempfile.TemporaryDirectory(prefix="bizplan-") as directory:
        source = Path(directory) / "draft.hwpx"
        target = Path(directory) / "draft.pdf"
        source.write_bytes(data)
        command = [executable, "convert", str(source), "--to", "pdf", "--output", str(target)]
        font_directory = os.getenv("BIZPLAN_HWP_FONT_DIR") or (
            "C:/Windows/Fonts" if os.name == "nt" else "/usr/share/fonts/truetype/nanum"
        )
        if Path(font_directory).is_dir():
            command.extend(["--font-dir", font_directory])
        try:
            result = subprocess.run(
                command,
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=45, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise BusinessPlanDocumentError("HWPX를 PDF로 변환하지 못했습니다.") from exc
        if result.returncode or not target.is_file() or not target.read_bytes().startswith(b"%PDF-"):
            raise BusinessPlanDocumentError("HWPX를 PDF로 변환하지 못했습니다.")
        return target.read_bytes()

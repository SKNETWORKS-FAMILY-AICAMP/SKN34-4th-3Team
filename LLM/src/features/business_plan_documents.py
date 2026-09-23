"""Inspect supported business-plan forms and render drafts without changing uploads."""

from __future__ import annotations

import base64
import binascii
import os
import re
import shutil
import subprocess
import tempfile
from html import escape
from io import BytesIO
from pathlib import Path
from typing import Any

from hwpx import HwpxDocument
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, NameObject
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.pdfgen import canvas as pdf_canvas


MAX_TEMPLATE_BYTES = 4 * 1024 * 1024
MAX_FIELDS = 20
MARKER = re.compile(r"\{\{\s*([^{}]{1,80}?)\s*\}\}")
MISSING = "정보 부족"

DEFAULT_PLAN_GROUPS = [
    (
        "1. 문제인식\n(Problem)",
        [
            ("1-1. 창업아이템의 개발 동기 / 개발 추진경과(이력)", [
                "제품·서비스를 개발하게 된 내·외적 동기",
                "사업 신청 전 기획·추진한 경과(이력)",
                "소셜벤처는 인식하고 있는 사회적 문제를 함께 기재",
            ]),
            ("1-2. 창업아이템의 개발 목적", [
                "발견한 문제점의 해결 방안과 제품·서비스의 개발 목적",
                "소셜벤처는 사회적 문제 해결방안과 사회적 성과를 함께 기재",
            ]),
            ("1-3. 창업아이템의 목표시장 분석", [
                "목표시장의 규모·상황·특성, 경쟁 강도와 고객 특성",
            ]),
        ],
    ),
    (
        "2. 실현가능성\n(Solution)",
        [
            ("2-1. 창업아이템의 개발 방안 / 진행(준비) 정도", [
                "협약기간 내 개발할 제품·서비스의 최종 산출물",
                "개발 방법, 신청 시점의 개발 단계와 진행(준비) 정도",
                "기술 유출 방지를 위한 기술 보호 계획",
            ]),
            ("2-2. 창업아이템의 차별화 방안", [
                "보유역량을 기반으로 경쟁 제품·서비스 대비 경쟁력을 확보할 방안",
            ]),
        ],
    ),
    (
        "3. 성장전략\n(Scale-up)",
        [
            ("3-1. 창업아이템의 사업화 방안", [
                "제품·서비스의 수익 모델(비즈니스 모델)",
                "생산·출시, 홍보·마케팅, 유통·판매 등 목표시장 진출 방안",
            ]),
            ("3-2. 사업 추진 일정", [
                "전체 사업 단계의 목표와 상세 추진 일정",
                "협약기간 내 달성 가능한 목표와 상세 추진 일정",
            ]),
            ("3-3. 자금소요 및 조달계획", [
                "정부지원금 사용계획과 구체적인 조달계획",
                "본인 부담금과 추가 자본금의 구체적인 조달계획",
            ]),
        ],
    ),
    (
        "4. 팀 구성\n(Team)",
        [
            ("4-1. 대표자 현황 및 보유역량", [
                "대표자가 보유한 창업아이템 구현·판매 관련 역량",
                "소셜벤처는 사회적 가치창출 관련 경력·교육·활동을 함께 기재",
            ]),
            ("4-2. 팀 현황 및 보유역량", [
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
                raise BusinessPlanDocumentError("입력 가능한 텍스트 필드가 없습니다. 스캔 문서나 일반 PDF는 사용할 수 없습니다.")
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
                    for run in document.text.runs()
                    for match in MARKER.finditer(run.text or "")
                ))
                if not names:
                    raise BusinessPlanDocumentError("채울 위치를 찾지 못했습니다. HWPX 양식에 {{항목명}} 표시가 필요합니다.")
        else:
            raise BusinessPlanDocumentError("지원하지 않는 양식입니다.")
    except BusinessPlanDocumentError:
        raise
    except Exception as exc:
        raise BusinessPlanDocumentError("양식을 읽거나 입력 위치를 확인할 수 없습니다.") from exc
    if len(names) > MAX_FIELDS or any(not name.strip() for name in names):
        raise BusinessPlanDocumentError("양식 항목은 1~20개여야 하며 이름이 비어 있으면 안 됩니다.")
    return names


def render_pdf_form(data: bytes, values: dict[str, str]) -> bytes:
    names = inspect_template("pdf", data)
    writer = PdfWriter()
    writer.append(PdfReader(BytesIO(data)))
    filled_values = {name: values.get(name, "").strip() or MISSING for name in names}
    font = _register_korean_font()
    drawn_names: set[str] = set()
    for page in writer.pages:
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
            if len(lines) * 12 + 4 > height:
                raise BusinessPlanDocumentError(f"PDF 입력칸에 초안 내용이 들어가지 않습니다: {name}")
            painter.setStrokeColor(colors.HexColor("#777777"))
            painter.setLineWidth(0.5)
            painter.rect(x0, y0, width, height, stroke=1, fill=0)
            painter.setFillColor(colors.black)
            painter.setFont(font, 9)
            for index, line in enumerate(lines):
                painter.drawString(x0 + 3, y1 - 12 - index * 12, line)
            drawn = True
            drawn_names.add(name)
        if drawn:
            painter.save()
            overlay.seek(0)
            page.merge_page(PdfReader(overlay).pages[0])
            page[NameObject("/Annots")] = kept_annotations
    if set(names) != drawn_names:
        raise BusinessPlanDocumentError("일부 PDF 텍스트 필드의 입력 위치를 확인할 수 없습니다.")
    output = BytesIO()
    writer.write(output)
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


def render_hwpx_form(data: bytes, values: dict[str, str]) -> bytes:
    names = inspect_template("hwpx", data)
    with HwpxDocument.open(BytesIO(data)) as document:
        for name in names:
            replacement = values.get(name, "").strip() or MISSING
            count = document.text.replace("{{" + name + "}}", replacement)
            if not count:
                # Whitespace inside a marker is legal; preserve the exact run text.
                for run in document.text.runs():
                    run.text = MARKER.sub(
                        lambda match: replacement if match.group(1).strip() == name else match.group(0),
                        run.text or "",
                    )
        result = document.to_bytes()
    with HwpxDocument.open(BytesIO(result)) as check:
        if any(MARKER.search(run.text or "") for run in check.text.runs()):
            raise BusinessPlanDocumentError("양식의 일부 입력 위치를 채우지 못했습니다.")
    return result


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
    small = document.styles.ensure_run(font="나눔고딕", size=7.5)
    bold = document.styles.ensure_run(font="나눔고딕", size=9, bold=True)
    group = document.styles.ensure_run(font="나눔고딕", size=10, bold=True)
    title_style = document.styles.ensure_run(font="나눔고딕", size=17, bold=True)
    blue = document.styles.ensure_run(font="나눔고딕", size=9, color="#0000FF")

    note = document.add_table(1, 1, width=54000, height=2300)
    _set_hwpx_cell(document, note.cell(0, 0),
                   "※ 사업 신청 시, 사업계획서 작성 목차 페이지는 삭제하여 제출",
                   char_style=blue)

    title_table = document.add_table(1, 1, width=54000, height=4700)
    title_table.set_cell_shading(0, 0, "#D0D0D0")
    _set_hwpx_cell(
        document,
        title_table.cell(0, 0),
        "창업사업화 지원사업 사업계획서 작성 목차 (예비단계)",
        char_style=title_style,
        alignment="CENTER",
    )

    overview = document.add_table(4, 2, width=54000, height=9100)
    overview.set_column_widths([17, 83])
    overview.set_cell_shading(0, 0, "#D0D0D0")
    overview.set_cell_shading(0, 1, "#D0D0D0")
    _set_hwpx_cell(document, overview.cell(0, 0), "항목", char_style=bold, alignment="CENTER")
    _set_hwpx_cell(document, overview.cell(0, 1), "세부항목", char_style=bold, alignment="CENTER")
    overview_rows = [
        ("□ 신청현황", "- 사업 관련 상세 신청현황"),
        ("□ 일반현황", "- 대표자의 일반현황"),
        ("□ 창업아이템 개요(요약)", "- 창업아이템의 명칭·범주 및 소개, 진출 목표시장, 경쟁사 대비 차별성 등을 요약"),
    ]
    for row, (label, detail) in enumerate(overview_rows, 1):
        overview.set_cell_shading(row, 0, "#D0D0D0")
        _set_hwpx_cell(document, overview.cell(row, 0), label, char_style=bold, alignment="CENTER")
        _set_hwpx_cell(document, overview.cell(row, 1), detail, char_style=normal)

    row_count = sum(len(items) for _, items in DEFAULT_PLAN_GROUPS)
    outline = document.add_table(row_count, 2, width=54000, height=42500)
    outline.set_column_widths([17, 83])
    current_row = 0
    for group_label, items in DEFAULT_PLAN_GROUPS:
        start_row = current_row
        for heading, guides in items:
            text = heading + "\n" + "\n".join(f"- {guide}" for guide in guides)
            _set_hwpx_cell(
                document,
                outline.cell(current_row, 1),
                text,
                char_style=small,
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

    body_section = document.add_section()
    document.page.setup(
        paper_size="A4",
        margin_left_mm=9,
        margin_right_mm=9,
        margin_top_mm=12,
        margin_bottom_mm=12,
        section=body_section,
    )
    body_heading = document.parts.headers[0].ensure_paragraph_format(
        alignment="CENTER",
        line_spacing_percent=120,
    )
    document.add_paragraph(
        title or "사업계획서",
        section=body_section,
        para_pr_id_ref=body_heading,
        char_pr_id_ref=title_style,
    )
    body = document.add_table(max(len(sections), 1), 2, section=body_section, width=54000)
    body.set_column_widths([22, 78])
    rendered_sections = sections or [{"label": "사업계획서", "content": MISSING}]
    for row, section in enumerate(rendered_sections):
        body.set_cell_shading(row, 0, "#D0D0D0")
        _set_hwpx_cell(document, body.cell(row, 0), section["label"], char_style=group, alignment="CENTER")
        _set_hwpx_cell(
            document,
            body.cell(row, 1),
            section["content"].strip() or MISSING,
            char_style=normal,
        )
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
    heading = ParagraphStyle("heading", fontName=font, fontSize=17, leading=23, spaceAfter=14, alignment=1)
    title_bar = ParagraphStyle("title_bar", fontName=font, fontSize=17, leading=22, alignment=1)
    note = ParagraphStyle("note", fontName=font, fontSize=8.5, leading=12, textColor=colors.blue)
    table_head = ParagraphStyle("table_head", fontName=font, fontSize=9, leading=11, alignment=1)
    group_style = ParagraphStyle("group", fontName=font, fontSize=9, leading=11, alignment=1)
    detail_style = ParagraphStyle("detail", fontName=font, fontSize=7.2, leading=9.2)
    body = ParagraphStyle("body", fontName=font, fontSize=10, leading=17, alignment=TA_LEFT)
    width = A4[0] - 48
    story = [
        Table([[Paragraph("※ 사업 신청 시, 사업계획서 작성 목차 페이지는 삭제하여 제출", note)]],
              colWidths=[width], style=TableStyle([
                  ("BOX", (0, 0), (-1, -1), 0.5, colors.black),
                  ("LEFTPADDING", (0, 0), (-1, -1), 6),
                  ("TOPPADDING", (0, 0), (-1, -1), 5),
                  ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
              ])),
        Spacer(1, 8),
        Table([[Paragraph("창업사업화 지원사업 사업계획서 작성 목차 <font color='#0000FF'>(예비단계)</font>", title_bar)]],
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
        [Paragraph("□ 신청현황", table_head), Paragraph("- 사업 관련 상세 신청현황", detail_style)],
        [Paragraph("□ 일반현황", table_head), Paragraph("- 대표자의 일반현황", detail_style)],
        [Paragraph("□ 창업아이템<br/>개요(요약)", table_head),
         Paragraph("- 창업아이템의 명칭·범주 및 소개, 진출 목표시장, 경쟁사 대비 차별성 등을 요약", detail_style)],
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
        for item_index, (item_heading, guides) in enumerate(items):
            guidance = "<br/>".join(f"- {escape(guide)}" for guide in guides)
            detail = Paragraph(f"<b>{escape(item_heading)}</b><br/>{guidance}", detail_style)
            left = Paragraph(escape(group_label).replace("\n", "<br/>"), group_style) if item_index == 0 else ""
            outline_data.append([left, detail])
            current_row += 1
        outline_style.extend([
            ("SPAN", (0, start_row), (0, current_row - 1)),
            ("BACKGROUND", (0, start_row), (0, current_row - 1), colors.HexColor("#D0D0D0")),
        ])
    outline_table = Table(outline_data, colWidths=[95, width - 95], repeatRows=0)
    outline_table.setStyle(TableStyle(outline_style))
    story.extend([outline_table, PageBreak(), Paragraph(escape(title or "사업계획서"), heading)])
    for section in sections or [{"label": "사업계획서", "content": MISSING}]:
        section_table = Table([
            [Paragraph(f"<b>{escape(section['label'])}</b>", group_style),
             Paragraph(escape(section["content"].strip() or MISSING).replace("\n", "<br/>"), body)],
        ], colWidths=[120, width - 120])
        section_table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.6, colors.black),
            ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#D0D0D0")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 9),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ]))
        story.extend([section_table, Spacer(1, 9)])
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

"""Business plan document formats and template rejection paths."""

from __future__ import annotations

import base64
import asyncio
import json
import re
from io import BytesIO

import pytest
from hwpx import HwpxDocument
from PIL import Image
import pymupdf
from pypdf import PdfReader
from reportlab.pdfgen import canvas

from src.features.business_plan_documents import (
    DEFAULT_OVERVIEW_FIELDS, DEFAULT_PLAN_GROUPS,
    BusinessPlanDocumentError, decode_template, inspect_template,
    render_default_hwpx, render_default_pdf, render_hwpx_form, render_pdf_form,
)
from src.features.business_plan_documents import _pdf_lines, _static_pdf_font_path
from tests.django_client import DjangoTestClient
from src.serving.rag_routes import adapter_business_plan_render
from src.serving.schemas import BusinessPlanRenderRequest


def _pdf_form(with_field: bool = True) -> bytes:
    output = BytesIO()
    page = canvas.Canvas(output)
    page.drawString(40, 790, "Original heading")
    if with_field:
        page.acroForm.textfield(name="Problem", x=40, y=680, width=300, height=60)
    page.save()
    return output.getvalue()


def _static_pdf_form(heading: str = "1-1. Problem") -> bytes:
    output = BytesIO()
    page = canvas.Canvas(output)
    page.setFont("Helvetica-Bold", 16)
    page.drawString(50, 740, heading)
    page.setFillColorRGB(0.14, 0.3, 1)
    page.setFont("Helvetica", 9)
    page.drawString(50, 710, "Sample guidance")
    page.setFillColorRGB(0, 0, 0)
    page.drawString(100, 670, "Temporary sample answer")
    page.save()
    return output.getvalue()


def _static_pdf_with_schedule_table() -> bytes:
    output = BytesIO()
    page = canvas.Canvas(output)
    page.setFont("Helvetica-Bold", 16)
    page.drawString(50, 745, "2-1. Development strategy")
    page.drawString(50, 450, "2-2. Market strategy")
    for x in (50, 200, 335, 550):
        page.line(x, 530, x, 650)
    for y in (530, 570, 610, 650):
        page.line(50, y, 550, y)
    page.setFont("Helvetica", 10)
    for x, heading in ((60, "Activity"), (210, "Period"), (345, "Details")):
        page.drawString(x, 625, heading)
    page.save()
    return output.getvalue()


def test_static_pdf_schedule_table_is_a_separate_fillable_field() -> None:
    data = _static_pdf_with_schedule_table()
    names = inspect_template("pdf", data)
    table = next(name for name in names if "[표: Activity | Period | Details]" in name)
    assert "2-1. Development strategy" in names
    filled = PdfReader(BytesIO(render_pdf_form(data, {
        "2-1. Development strategy": "Development text",
        table: "MVP build | October 2026 | Implement the product",
    })))
    text = filled.pages[0].extract_text().replace("\xa0", " ")
    assert "Development text" in text
    assert "MVP build" in text
    assert "October 2026" in text


def test_static_pdf_table_accepts_structured_rows_with_empty_cells() -> None:
    data = _static_pdf_with_schedule_table()
    table = next(name for name in inspect_template("pdf", data) if "[표: Activity" in name)
    value = json.dumps({"rows": [{
        "Activity": "MVP build", "Period": None, "Details": "Implement product",
    }]})
    filled = PdfReader(BytesIO(render_pdf_form(data, {table: value})))
    text = filled.pages[0].extract_text().replace("\xa0", " ")
    assert "MVP build" in text
    assert "Implement product" in text
    assert "None" not in text


def test_static_pdf_fills_profile_cells_and_removes_wrapped_guidance() -> None:
    document = pymupdf.open()
    page = document.new_page()
    font_path = _static_pdf_font_path()
    page.insert_font(fontname="Korean", fontfile=font_path)
    page.insert_text((50, 145), "※ 양식 안내", fontname="Korean", fontsize=10)
    page.insert_text((50, 160), "양식의 목차·표는 변경하지 않음", fontname="Korean", fontsize=10)
    for left, top, right, bottom in ((50, 200, 150, 245), (50, 245, 150, 290),
                                     (300, 245, 400, 290), (50, 290, 150, 335),
                                     (300, 290, 400, 335)):
        page.draw_rect(pymupdf.Rect(left, top, right, bottom), color=None, fill=(0.9, 0.9, 0.9))
    for x, top in ((50, 200), (150, 200), (550, 200), (300, 245), (400, 245)):
        page.draw_line((x, top), (x, 335))
    for y in (200, 245, 290, 335):
        page.draw_line((50, y), (550, y))
    for x, y, value in ((53, 226, "창업아이템명"), (53, 271, "신청자 성명"),
                        (303, 271, "생년월일"), (403, 271, "1900.00.00"),
                        (53, 316, "직업"), (153, 316, "교수 / 연구원"),
                        (303, 316, "기업명"), (403, 316, "○○○○")):
        page.insert_text((x, y), value, fontname="Korean", fontsize=9)
    raw = document.tobytes(garbage=4, deflate=True)
    fields = inspect_template("pdf", raw)
    for label in ("창업아이템명", "신청자 성명", "생년월일", "직업", "기업명"):
        assert f"{label} [유형: metadata]" in fields
    values = {f"{label} [유형: metadata]": value for label, value in {
        "창업아이템명": "재고관리 서비스", "신청자 성명": "신대호",
        "생년월일": "1990.01.02", "직업": "개발자", "기업명": "재고컴퍼니",
    }.items()}
    rendered = pymupdf.open(stream=render_pdf_form(raw, values, title="재고관리 서비스"), filetype="pdf")
    text = rendered[0].get_text().replace("\xa0", " ")
    assert all(value in text for value in values.values())
    assert text.count("재고관리 서비스") == 1
    assert "1900.00.00" not in text
    assert "교수 / 연구원" not in text
    assert "양식의 목차·표는 변경하지 않음" not in text


def test_static_pdf_detects_unshaded_fields_on_later_page_without_table_headers() -> None:
    document = pymupdf.open()
    document.new_page().insert_text((50, 100), "Application cover")
    page = document.new_page()
    for x in (50, 160, 310, 420, 550):
        page.draw_line((x, 180), (x, 260))
    for y in (180, 220, 260):
        page.draw_line((50, y), (550, y))
    page.insert_text((55, 195), "Company", fontsize=9)
    page.insert_text((55, 207), "name", fontsize=9)
    for x, y, label in ((315, 205, "Contact"),
                        (55, 245, "Office"), (315, 245, "Founded")):
        page.insert_text((x, y), label, fontsize=9)
    page.insert_text((165, 205), "Example Corp", fontsize=9)
    schedule = document.new_page()
    for x in (50, 200, 335, 550):
        schedule.draw_line((x, 100), (x, 220))
    for y in (100, 140, 180, 220):
        schedule.draw_line((50, y), (550, y))
    for left, right in ((50, 200), (200, 335), (335, 550)):
        schedule.draw_rect(pymupdf.Rect(left, 100, right, 140),
                           color=None, fill=(0.9, 0.9, 0.9))
    for x, label in ((55, "Activity"), (205, "Period"), (340, "Details")):
        schedule.insert_text((x, 125), label, fontsize=9)
    raw = document.tobytes(garbage=4, deflate=True)
    fields = inspect_template("pdf", raw)
    for label in ("Company name", "Contact", "Office", "Founded"):
        assert f"{label} [유형: metadata]" in fields
    assert not any("Activity [유형: metadata]" in field for field in fields)
    values = {"Company name [유형: metadata]": "Acme", "Contact [유형: metadata]": "Lee"}
    rendered = pymupdf.open(stream=render_pdf_form(raw, values), filetype="pdf")
    text = rendered[1].get_text()
    assert "Acme" in text and "Lee" in text
    assert "Example Corp" not in text


def test_static_pdf_uses_only_needed_bullet_markers() -> None:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((60, 145), "1-1. Problem", fontsize=16)
    page.insert_text((60, 420), "1-2. Purpose", fontsize=16)
    font_path = _static_pdf_font_path()
    page.insert_font(fontname="Korean", fontfile=font_path)
    for y, symbol, x in ((205, "○", 65), (236, "-", 82), (267, "-", 82),
                         (298, "○", 65), (329, "-", 82)):
        page.insert_text((x, y), symbol, fontname="Korean", fontsize=10)
    raw = document.tobytes(garbage=4, deflate=True)
    label = inspect_template("pdf", raw)[0]
    filled = pymupdf.open(stream=render_pdf_form(raw, {label: "A clear problem statement."}), filetype="pdf")
    lines = [line["text"] for line in _pdf_lines(filled[0])]
    assert lines.count("○") == 1
    assert "-" not in lines
    assert any("A clear problem statement." in line.replace("\xa0", " ") for line in lines)
    long_sentence = ("This plan helps local shops track inventory and plan orders " * 4).strip() + "."
    filled_long = pymupdf.open(stream=render_pdf_form(raw, {label: long_sentence}), filetype="pdf")
    long_lines = [line["text"] for line in _pdf_lines(filled_long[0])]
    assert sum(line in {"○", "-"} for line in long_lines) == 1
    assert "plan orders" in " ".join(page.get_text() for page in filled_long).replace("\xa0", " ")
    sentences = (
        "소상공인은 매장 운영과 고객 응대를 함께 처리하느라 재고를 지속적으로 확인하기 어렵다. "
        "이로 인해 필요한 물품이 부족해 판매 기회를 놓치거나 재고가 과도하게 남을 수 있다. "
        "이 서비스는 재고 부족을 알려 소상공인의 관리 부담을 줄인다."
    )
    grouped = pymupdf.open(stream=render_pdf_form(raw, {label: sentences}), filetype="pdf")
    grouped_lines = _pdf_lines(grouped[0])
    assert [line["text"] for line in grouped_lines if line["text"] in {"○", "-"}] == ["○", "-", "-"]
    first_text = next(line for line in grouped_lines if "소상공인은" in line["text"])
    first_end = next(line for line in grouped_lines if "어렵다." in line["text"].replace("\xa0", " "))
    second_text = next(line for line in grouped_lines if "이로 인해" in line["text"].replace("\xa0", " "))
    second_marker = next(line for line in grouped_lines if line["text"] == "-")
    assert first_text["rect"].y0 <= first_end["rect"].y0 < second_marker["rect"].y0
    assert second_marker["rect"].y0 <= second_text["rect"].y0
    overflowing = " ".join(f"detail{i}" for i in range(300))
    continued = pymupdf.open(stream=render_pdf_form(raw, {label: overflowing}), filetype="pdf")
    assert len(continued) > 1
    all_text = " ".join(page.get_text() for page in continued).replace("\xa0", " ")
    assert "detail0" in all_text and "detail299" in all_text
    assert "작성 내용 이어짐" in continued[1].get_text().replace("\xa0", " ")
    legacy_label = label.split(" [글머리표:", 1)[0]
    response = asyncio.run(adapter_business_plan_render(BusinessPlanRenderRequest(
        sections=[{"key": "section_1", "label": legacy_label,
                   "content": "A clear problem statement."},
                  {"key": "section_2", "label": inspect_template("pdf", raw)[1], "content": ""}],
        format="pdf", template={"fileName": "form.pdf",
                                "contentBase64": base64.b64encode(raw).decode()},
    ), None, None))
    assert response.fileName == "business-plan.pdf"


def test_static_pdf_image_slot_receives_uploaded_png() -> None:
    output = BytesIO()
    page = canvas.Canvas(output)
    for x in (50, 180, 550):
        page.line(x, 550, x, 680)
    for y in (550, 680):
        page.line(50, y, 550, y)
    page.drawString(60, 620, "Product image")
    page.save()
    raw = output.getvalue()
    label = next(name for name in inspect_template("pdf", raw) if "[유형: image]" in name)
    picture = BytesIO()
    Image.new("RGB", (40, 20), (200, 30, 30)).save(picture, format="PNG")
    filled = pymupdf.open(stream=render_pdf_form(raw, {}, images={
        label: ("image/png", picture.getvalue()),
    }), filetype="pdf")
    assert len(filled[0].get_images()) == 1


@pytest.mark.parametrize("heading", ["1-1. Problem", "Executive Summary"])
def test_static_pdf_uses_headings_and_removes_sample_text(heading: str) -> None:
    data = _static_pdf_form(heading)
    assert inspect_template("pdf", data) == [heading]
    filled = PdfReader(BytesIO(render_pdf_form(data, {heading: "Actual plan content"})))
    text = filled.pages[0].extract_text().replace("\xa0", " ")
    assert heading in text
    assert "Actual plan content" in text
    assert "Sample guidance" not in text
    assert "Temporary sample answer" not in text


def test_static_pdf_leaves_missing_section_empty() -> None:
    data = _static_pdf_form()
    filled = PdfReader(BytesIO(render_pdf_form(data, {})))
    text = filled.pages[0].extract_text()
    assert "1-1. Problem" in text
    assert "Temporary sample answer" not in text
    assert "정보 부족" not in text


def _hwpx_form() -> bytes:
    document = HwpxDocument.new()
    document.add_paragraph("Original heading")
    document.add_paragraph("{{Problem}}")
    return document.to_bytes()


def test_default_files_fill_each_form_cell_without_appended_body() -> None:
    fields = DEFAULT_OVERVIEW_FIELDS + [
        (key, label)
        for _, items in DEFAULT_PLAN_GROUPS
        for key, label, _ in items
    ]
    sections = [
        {"key": key, "label": label, "content": f"{label}에 맞춘 작성 내용"}
        for key, label in fields
    ]
    hwpx = render_default_hwpx("사업계획서", sections)
    with HwpxDocument.open(BytesIO(hwpx)) as document:
        text = document.text.plain()
        assert "창업사업화 지원사업 사업계획서" in text
        assert "창업아이템의 목표시장 분석" in text
        assert "자금소요 및 조달계획" in text
        assert "신청현황에 맞춘 작성 내용" in text
        assert "자금소요 및 조달계획에 맞춘 작성 내용" in text
        assert all(section["content"] in text for section in sections)
        assert "작성 목차 페이지는 삭제" not in text
        assert len(document.sections) == 1
    pdf = PdfReader(BytesIO(render_default_pdf("사업계획서", sections)))
    text = "\n".join(page.extract_text() for page in pdf.pages)
    compact_text = re.sub(r"\s+", "", text)
    assert "창업사업화 지원사업 사업계획서" in text
    assert "창업아이템의 목표시장 분석" in text
    assert "신청현황에 맞춘 작성 내용" in text
    assert "자금소요 및 조달계획에 맞춘 작성 내용" in text
    assert all(re.sub(r"\s+", "", section["content"]) in compact_text for section in sections)
    assert "작성 목차 페이지는 삭제" not in text


def test_pdf_form_keeps_original_page_and_fills_text_field() -> None:
    data = _pdf_form()
    assert inspect_template("pdf", data) == ["Problem"]
    filled = PdfReader(BytesIO(render_pdf_form(data, {"Problem": "Specific problem"})))
    assert "Original heading" in filled.pages[0].extract_text()
    assert filled.get_fields()["Problem"].get("/V") == "Specific problem"


def test_pdf_form_leaves_missing_field_empty() -> None:
    filled = PdfReader(BytesIO(render_pdf_form(_pdf_form(), {})))
    assert filled.get_fields()["Problem"].get("/V") == ""


def test_pdf_form_displays_korean_and_rejects_clipped_content() -> None:
    data = _pdf_form()
    filled = PdfReader(BytesIO(render_pdf_form(data, {"Problem": "고객의 재고 문제"})))
    assert "고객의 재고 문제" in filled.pages[0].extract_text()
    with pytest.raises(BusinessPlanDocumentError, match="들어가지"):
        render_pdf_form(data, {"Problem": "긴 사업 설명 " * 100})


def test_hwpx_form_keeps_original_content_and_leaves_missing_value_blank() -> None:
    data = _hwpx_form()
    assert inspect_template("hwpx", data) == ["Problem"]
    filled = render_hwpx_form(data, {"Problem": ""})
    with HwpxDocument.open(BytesIO(filled)) as document:
        text = " ".join(run.text for run in document.text.runs())
        assert "Original heading" in text
        assert "정보 부족" not in text
        assert "{{Problem}}" not in text


def test_hwpx_table_cell_markers_are_filled_independently() -> None:
    document = HwpxDocument.new()
    table = document.add_table(2, 3, width=54000)
    for column, label in enumerate(("추진내용", "추진기간", "세부내용")):
        table.cell(0, column).set_text(label)
        table.cell(1, column).set_text("{{" + label + "}}")
    data = document.to_bytes()
    assert inspect_template("hwpx", data) == ["추진내용", "추진기간", "세부내용"]
    filled = render_hwpx_form(data, {
        "추진내용": "MVP 개발", "추진기간": "2026년 10월", "세부내용": "핵심 기능 구현",
    })
    with HwpxDocument.open(BytesIO(filled)) as result:
        cells = next(iter(result.tables))
        assert [cells.cell(1, column).text for column in range(3)] == [
            "MVP 개발", "2026년 10월", "핵심 기능 구현",
        ]


def test_hwpx_image_marker_receives_uploaded_png_in_existing_cell() -> None:
    document = HwpxDocument.new()
    table = document.add_table(1, 2, width=54000)
    table.cell(0, 0).set_text("제품 사진")
    table.cell(0, 1).set_text("{{제품 사진}}")
    picture = BytesIO()
    Image.new("RGB", (40, 20), (200, 30, 30)).save(picture, format="PNG")
    filled = render_hwpx_form(document.to_bytes(), {"제품 사진": ""}, {
        "제품 사진": ("image/png", picture.getvalue()),
    })
    with HwpxDocument.open(BytesIO(filled)) as result:
        assert len(result.media.picture_references()) == 1
        assert "{{제품 사진}}" not in result.text.plain()


def test_render_api_passes_uploaded_image_to_hwpx_renderer() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("{{제품 사진}}")
    picture = BytesIO()
    Image.new("RGB", (40, 20), (200, 30, 30)).save(picture, format="PNG")
    response = asyncio.run(adapter_business_plan_render(BusinessPlanRenderRequest(
        sections=[{"key": "section_1", "label": "제품 사진", "content": ""}],
        format="hwpx", template={"fileName": "form.hwpx",
                                  "contentBase64": base64.b64encode(document.to_bytes()).decode()},
        images=[{"key": "section_1", "mimeType": "image/png",
                 "contentBase64": base64.b64encode(picture.getvalue()).decode()}],
    ), None, None))
    with HwpxDocument.open(BytesIO(base64.b64decode(response.contentBase64))) as result:
        assert len(result.media.picture_references()) == 1


def test_hwpx_blank_table_uses_columns_and_preserves_cell_positions() -> None:
    document = HwpxDocument.new()
    table = document.add_table(3, 3, width=54000)
    for column, label in enumerate(("추진내용", "추진기간", "세부내용")):
        table.cell(0, column).set_text(label)
    data = document.to_bytes()
    names = inspect_template("hwpx", data)
    assert len(names) == 1
    assert "[표: 추진내용 | 추진기간 | 세부내용]" in names[0]
    filled = render_hwpx_form(data, {names[0]: "MVP 개발 | 2026년 10월 | 핵심 기능 구현"})
    with HwpxDocument.open(BytesIO(filled)) as result:
        table = next(iter(result.tables))
        assert [table.cell(1, column).text for column in range(3)] == [
            "MVP 개발", "2026년 10월", "핵심 기능 구현",
        ]
        assert [table.cell(2, column).text for column in range(3)] == ["", "", ""]


def test_hwpx_heading_followed_by_blank_paragraph_is_fillable() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("1-1. Development strategy")
    document.add_paragraph("")
    data = document.to_bytes()
    assert inspect_template("hwpx", data) == ["1-1. Development strategy"]
    filled = render_hwpx_form(data, {"1-1. Development strategy": "MVP 개발 계획"})
    with HwpxDocument.open(BytesIO(filled)) as result:
        assert "MVP 개발 계획" in [paragraph.text for paragraph in result.paragraphs]


@pytest.mark.parametrize("kind,data", [
    ("pdf", _pdf_form(False)),
    ("hwpx", HwpxDocument.new().to_bytes()),
])
def test_unfillable_forms_are_rejected(kind: str, data: bytes) -> None:
    with pytest.raises(BusinessPlanDocumentError):
        inspect_template(kind, data)


def test_template_inspect_and_pdf_render_http_contract() -> None:
    client = DjangoTestClient()
    data = _pdf_form()
    template = {"fileName": "form.pdf", "contentBase64": base64.b64encode(data).decode()}
    inspected = client.post("/rag/business-plan-template-inspect", json=template)
    assert inspected.status_code == 200
    assert inspected.json()["fields"] == ["Problem"]
    assert inspected.json()["outputFormats"] == ["pdf"]

    rejected = client.post("/rag/business-plan-render", json={
        "title": "Plan", "sections": [{"key": "section_1", "label": "Problem", "content": "Text"}],
        "format": "hwpx", "template": template,
    })
    assert rejected.status_code == 422

    rendered = client.post("/rag/business-plan-render", json={
        "title": "Plan", "sections": [{"key": "section_1", "label": "Problem", "content": "Text"}],
        "format": "pdf", "template": template,
    })
    assert rendered.status_code == 200
    output = base64.b64decode(rendered.json()["contentBase64"])
    assert PdfReader(BytesIO(output)).get_fields()["Problem"].get("/V") == "Text"


def test_wrong_file_type_is_rejected() -> None:
    with pytest.raises(BusinessPlanDocumentError):
        decode_template("form.pdf", base64.b64encode(b"not pdf").decode())

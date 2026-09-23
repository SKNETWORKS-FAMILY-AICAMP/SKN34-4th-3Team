"""Business plan document formats and template rejection paths."""

from __future__ import annotations

import base64
from io import BytesIO

import pytest
from hwpx import HwpxDocument
from pypdf import PdfReader
from reportlab.pdfgen import canvas

from src.features.business_plan_documents import (
    BusinessPlanDocumentError, decode_template, inspect_template,
    render_default_hwpx, render_default_pdf, render_hwpx_form, render_pdf_form,
)
from tests.django_client import DjangoTestClient


def _pdf_form(with_field: bool = True) -> bytes:
    output = BytesIO()
    page = canvas.Canvas(output)
    page.drawString(40, 790, "Original heading")
    if with_field:
        page.acroForm.textfield(name="Problem", x=40, y=680, width=300, height=60)
    page.save()
    return output.getvalue()


def _hwpx_form() -> bytes:
    document = HwpxDocument.new()
    document.add_paragraph("Original heading")
    document.add_paragraph("{{Problem}}")
    return document.to_bytes()


def test_default_files_open_and_contain_korean_text() -> None:
    sections = [{"label": "문제인식", "content": "정보 부족"}]
    hwpx = render_default_hwpx("사업계획서", sections)
    with HwpxDocument.open(BytesIO(hwpx)) as document:
        text = document.text.plain()
        assert "창업사업화 지원사업 사업계획서 작성 목차" in text
        assert "창업아이템의 목표시장 분석" in text
        assert "자금소요 및 조달계획" in text
        assert "정보 부족" in text
        assert len(document.sections) == 2
    pdf = PdfReader(BytesIO(render_default_pdf("사업계획서", sections)))
    assert len(pdf.pages) == 2
    first_page = pdf.pages[0].extract_text()
    assert "창업사업화 지원사업 사업계획서 작성 목차" in first_page
    assert "창업아이템의 목표시장 분석" in first_page
    assert "자금소요 및 조달계획" in first_page
    assert "정보 부족" in pdf.pages[1].extract_text()


def test_pdf_form_keeps_original_page_and_fills_text_field() -> None:
    data = _pdf_form()
    assert inspect_template("pdf", data) == ["Problem"]
    filled = PdfReader(BytesIO(render_pdf_form(data, {"Problem": "Specific problem"})))
    assert "Original heading" in filled.pages[0].extract_text()
    assert filled.get_fields()["Problem"].get("/V") == "Specific problem"


def test_pdf_form_displays_korean_and_rejects_clipped_content() -> None:
    data = _pdf_form()
    filled = PdfReader(BytesIO(render_pdf_form(data, {"Problem": "고객의 재고 문제"})))
    assert "고객의 재고 문제" in filled.pages[0].extract_text()
    with pytest.raises(BusinessPlanDocumentError, match="들어가지"):
        render_pdf_form(data, {"Problem": "긴 사업 설명 " * 100})


def test_hwpx_form_keeps_original_content_and_marks_missing_value() -> None:
    data = _hwpx_form()
    assert inspect_template("hwpx", data) == ["Problem"]
    filled = render_hwpx_form(data, {"Problem": ""})
    with HwpxDocument.open(BytesIO(filled)) as document:
        text = " ".join(run.text for run in document.text.runs())
        assert "Original heading" in text
        assert "정보 부족" in text
        assert "{{Problem}}" not in text


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

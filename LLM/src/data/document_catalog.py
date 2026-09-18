from pathlib import Path
import re

from src.data.contracts import DocumentCatalogEntry


SOURCE_PDF_DIR = Path(__file__).resolve().parent / "RAG_data"

# 기존 Mock Backend에서 사용 중인 1~5번 문서의 policy_id는 유지한다.
_EXISTING_POLICY_IDS = {1: 103, 2: 102, 3: 101, 4: 104, 5: 105}
_DOCUMENT_NUMBER_PATTERN = re.compile(r"^(\d+)_")


def get_document_catalog() -> list[DocumentCatalogEntry]:
    """RAG_data 폴더의 PDF를 탐색해 문서 catalog를 생성한다.

    Returns:
        PDF 파일명, 제목, 임시 policy_id를 담은 catalog 목록.

    Raises:
        ValueError: PDF 파일명이 ``숫자_제목.pdf`` 규칙을 따르지 않을 때.
    """
    catalog: list[DocumentCatalogEntry] = []

    for pdf_path in sorted(SOURCE_PDF_DIR.glob("*.pdf")):
        number_match = _DOCUMENT_NUMBER_PATTERN.match(pdf_path.name)
        if number_match is None:
            raise ValueError(
                f"PDF file name must follow '<number>_<title>.pdf': {pdf_path.name}"
            )

        document_number = int(number_match.group(1))
        title = pdf_path.stem.split("_", maxsplit=1)[1].replace("_", " ")
        title = title.removesuffix(" 실제공고문형")
        catalog.append(
            {
                "policy_id": _EXISTING_POLICY_IDS.get(
                    document_number,
                    100 + document_number,
                ),
                "title": title,
                "file_name": pdf_path.name,
            }
        )

    return catalog

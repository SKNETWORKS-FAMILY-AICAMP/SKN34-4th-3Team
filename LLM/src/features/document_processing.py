from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from src.data.contracts import DocumentCatalogEntry, RagChunk
from src.data.document_catalog import SOURCE_PDF_DIR


KOREAN_DOCUMENT_SEPARATORS = ["\n\n", "\n", "다. ", "요. ", ". ", " ", ""]


class PdfDocumentError(RuntimeError):
    """PDF를 RAG 문서로 변환할 수 없을 때 사용하는 기본 예외."""


class PdfDocumentNotFoundError(PdfDocumentError):
    """문서 catalog가 가리키는 PDF 파일이 없을 때 발생한다."""


class PdfTextNotFoundError(PdfDocumentError):
    """PDF에서 추출할 수 있는 텍스트가 없을 때 발생한다."""


def load_pdf_pages(
    entry: DocumentCatalogEntry,
    *,
    source_dir: Path = SOURCE_PDF_DIR,
) -> list[Document]:
    """PDF 한 개를 읽기 전용으로 열어 텍스트가 있는 페이지를 반환한다.

    Args:
        entry: PDF 파일명, 정책 ID와 제목이 정의된 문서 catalog 항목.
        source_dir: 원본 PDF가 위치한 읽기 전용 디렉터리.

    Returns:
        페이지 본문과 정책·출처 metadata를 담은 LangChain Document 목록.

    Raises:
        PdfDocumentNotFoundError: catalog에 지정된 PDF 파일이 없을 때.
        PdfTextNotFoundError: 모든 페이지에서 텍스트를 추출하지 못했을 때.
        PdfDocumentError: 경로가 잘못됐거나 PDF를 정상적으로 읽지 못했을 때.
    """
    file_name = entry["file_name"]
    if Path(file_name).name != file_name:
        raise PdfDocumentError("Catalog file_name must not contain a directory path")

    pdf_path = source_dir / file_name
    if not pdf_path.is_file():
        raise PdfDocumentNotFoundError(f"PDF not found: {file_name}")

    page_documents: list[Document] = []
    try:
        with pdf_path.open("rb") as pdf_stream:
            pdf_reader = PdfReader(pdf_stream)
            for page_number, pdf_page in enumerate(pdf_reader.pages, start=1):
                page_content = (pdf_page.extract_text() or "").strip()
                if not page_content:
                    continue
                page_documents.append(
                    Document(
                        page_content=page_content,
                        metadata={
                            "policy_id": entry["policy_id"],
                            "title": entry["title"],
                            "source": file_name,
                            "page": page_number,
                        },
                    )
                )
    except (OSError, PdfReadError) as exc:
        raise PdfDocumentError(f"Unable to read PDF: {file_name}") from exc

    if not page_documents:
        raise PdfTextNotFoundError(f"No extractable text in PDF: {file_name}")
    return page_documents


def split_pdf_pages(
    pages: list[Document],
    *,
    chunk_size: int,
    chunk_overlap: int,
) -> list[RagChunk]:
    """PDF 페이지를 출처 metadata가 보존된 RAG Chunk로 분할한다.

    Args:
        pages: PDF 페이지 본문과 정책·출처 metadata를 담은 Document 목록.
        chunk_size: Chunk 하나에 허용할 최대 문자 수.
        chunk_overlap: 인접한 Chunk가 공유할 문자 수.

    Returns:
        결정적인 chunk_id와 원본 페이지 metadata가 포함된 RAG Chunk 목록.

    Raises:
        ValueError: Chunk 설정이 잘못됐거나 페이지 필수 metadata가 없을 때.
    """
    rag_chunks: list[RagChunk] = []
    for page_document in pages:
        policy_id, title, source, page_number = _extract_page_metadata(page_document)
        chunk_contents = split_text(
            page_document.page_content,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        for chunk_number, chunk_content in enumerate(chunk_contents, start=1):
            rag_chunks.append(
                {
                    "chunk_id": (
                        f"policy-{policy_id}-page-{page_number}-chunk-{chunk_number}"
                    ),
                    "policy_id": policy_id,
                    "title": title,
                    "source": source,
                    "page": page_number,
                    "content": chunk_content,
                }
            )
    return rag_chunks


def split_text(
    content: str,
    *,
    chunk_size: int,
    chunk_overlap: int,
) -> list[str]:
    """일반 문서 본문을 한국어 구분자를 이용해 Chunk 문자열로 분할한다.

    Args:
        content: 분할할 원본 문서 본문.
        chunk_size: Chunk 하나에 허용할 최대 문자 수.
        chunk_overlap: 인접 Chunk가 공유할 문자 수.

    Returns:
        공백을 제거하고 빈 값을 제외한 Chunk 본문 목록.

    Raises:
        ValueError: Chunk 크기 또는 중첩 설정이 유효하지 않을 때.
    """
    _validate_chunk_settings(chunk_size, chunk_overlap)
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=KOREAN_DOCUMENT_SEPARATORS,
        length_function=len,
    )
    return [
        chunk_content.strip()
        for chunk_content in text_splitter.split_text(content)
        if chunk_content.strip()
    ]


def _validate_chunk_settings(chunk_size: int, chunk_overlap: int) -> None:
    """Chunk 크기와 중첩 범위가 유효한지 검사한다."""
    if chunk_size < 1:
        raise ValueError("chunk_size must be at least 1")
    if chunk_overlap < 0:
        raise ValueError("chunk_overlap must not be negative")
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size")


def _extract_page_metadata(document: Document) -> tuple[int, str, str, int]:
    """페이지 Document에서 필수 정책·출처 metadata를 추출한다."""
    required_fields = ("policy_id", "title", "source", "page")
    missing_fields = [
        field_name
        for field_name in required_fields
        if field_name not in document.metadata
    ]
    if missing_fields:
        raise ValueError(f"Missing page metadata: {', '.join(missing_fields)}")

    metadata = document.metadata
    return (
        int(metadata["policy_id"]),
        str(metadata["title"]),
        str(metadata["source"]),
        int(metadata["page"]),
    )

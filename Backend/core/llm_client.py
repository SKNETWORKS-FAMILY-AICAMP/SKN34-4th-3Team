"""HTTP client for the internal LLM service. Returns None when LLM is down.

LLM_API_SPEC_V1.md가 정한 공개 경로(`/rag/*`, `/ocr/receipt`)만 호출한다.
`/internal/*`은 LLM의 구현·진단용 비공개 경로라 fallback으로도 쓰지 않는다(V1 1절).
"""

from __future__ import annotations

import base64
import json
import logging
import uuid
import urllib.error
import urllib.request

from core.config import (
    LLM_API_URL,
    LLM_TIMEOUT_CHAT_POLICY,
    LLM_TIMEOUT_CHAT_TAX,
    LLM_TIMEOUT_DEDUCTIBILITY,
    LLM_TIMEOUT_LEGAL_BASIS,
    LLM_TIMEOUT_OCR,
    LLM_TIMEOUT_READY,
    LLM_TIMEOUT_REINDEX,
    LLM_TIMEOUT_SECONDS,
    LLM_TIMEOUT_SUMMARIZE,
)


logger = logging.getLogger(__name__)

# LLM은 tax·expense를 tax 멀티홉 route로 강제하므로 policy보다 오래 걸린다.
_CHAT_TIMEOUTS = {
    "policy": LLM_TIMEOUT_CHAT_POLICY,
    "roadmap": LLM_TIMEOUT_CHAT_POLICY,
    "tax": LLM_TIMEOUT_CHAT_TAX,
    "expense": LLM_TIMEOUT_CHAT_TAX,
    "saving": LLM_TIMEOUT_CHAT_TAX,
}


def llm_status() -> dict:
    health = _get("/health", timeout=LLM_TIMEOUT_READY)
    ready = _get("/rag/ready", timeout=LLM_TIMEOUT_READY)
    return {
        "url": LLM_API_URL,
        "reachable": health is not None,
        "health": health,
        "ragReady": bool(ready and ready.get("index_ready")),
        "llmConfigured": bool(ready and ready.get("llm_configured")),
    }


def reindex() -> dict | None:
    """관리자 재색인. 준비 상태와 무관하게 호출한다(V1 8절).

    `documentIds`의 의미가 아직 합의되지 않아 전체 재색인만 요청한다.
    `null`을 보내면 422이므로 빈 배열을 쓴다.
    """
    return _post("/rag/reindex", {"documentIds": []}, timeout=LLM_TIMEOUT_REINDEX)


def ensure_index_ready() -> bool:
    """기동 워밍업. 인덱스가 없을 때만 재색인한다.

    LLM은 기동 시 인덱스를 만들지 않는다(`create_app`이 빈 runtime을 만든다).
    누가 한 번 재색인해 주기 전까지 모든 질의가 `integration_unavailable`로 끝나므로
    Backend가 기동할 때 대신 깨워 준다.

    질의마다 준비 상태를 묻던 것(P0-2-1에서 제거)과는 다르다. 그건 챗 요청 경로에서
    매번 왕복하던 것이고 이건 기동 시 한 번 도는 워밍업이다.
    """
    ready = _get("/rag/ready", timeout=LLM_TIMEOUT_READY)
    if ready is None:
        logger.warning("LLM warm-up skipped: /rag/ready unreachable")
        return False
    if ready.get("index_ready"):
        logger.info("LLM warm-up skipped: index already ready (chunks=%s)", ready.get("chunk_count"))
        return True
    result = reindex()
    if result is None:
        logger.warning("LLM warm-up failed: reindex request did not succeed")
        return False
    logger.info(
        "LLM warm-up done: status=%s source=%s chunks=%s",
        result.get("status"),
        result.get("source"),
        result.get("chunk_count"),
    )
    return True


def rag_answer(
    question: str,
    *,
    category: str | None = None,
    user_context: dict | None = None,
    notice_results: list[dict] | None = None,
    conversation_history: list[dict] | None = None,
    roadmap_step: str | None = None,
) -> dict | None:
    """`POST /rag/chat`.

    인덱스 준비 여부를 미리 묻지 않는다. LLM은 인덱스가 없어도 409가 아니라
    200 + `status="integration_unavailable"`을 돌려주므로 판단은 응답에 맡긴다.
    """
    resolved = category or "tax"
    body: dict = {"category": resolved, "question": question}
    if user_context is not None:
        body["userContext"] = user_context
    if notice_results is not None:
        body["noticeResults"] = notice_results
    # 첫 질문 payload를 기존과 똑같이 유지하려고 빈 history는 필드째 생략한다.
    if conversation_history:
        body["conversationHistory"] = conversation_history
    if roadmap_step is not None:
        body["roadmapStep"] = roadmap_step
    return _post(
        "/rag/chat",
        body,
        timeout=_CHAT_TIMEOUTS.get(resolved, LLM_TIMEOUT_CHAT_TAX),
    )


def extract_receipt(
    filename: str,
    *,
    image_base64: str | None = None,
    mime_type: str = "image/jpeg",
) -> dict | None:
    if not image_base64:
        return None
    return _post_multipart(
        "/ocr/receipt",
        filename=filename,
        image_base64=image_base64,
        mime_type=mime_type,
        timeout=LLM_TIMEOUT_OCR,
    )


def explain_expense(
    category: str,
    vendor: str,
    amount: int,
    items: list[str] | None = None,
) -> dict | None:
    """`POST /rag/deductibility`. 인덱스 미준비 시 409가 오고 None으로 떨어진다."""
    normalized_category = (category or "").strip() or "미분류"
    normalized_vendor = (vendor or "").strip() or "상호 미상"
    normalized_items = [item.strip() for item in items or [] if item.strip()]
    spec = _post(
        "/rag/deductibility",
        {
            "category": normalized_category,
            "amount": amount,
            "vendor": normalized_vendor,
            "items": normalized_items,
        },
        timeout=LLM_TIMEOUT_DEDUCTIBILITY,
    )
    if not spec or not spec.get("basis"):
        return None
    return {
        "answer": spec["basis"],
        "deductible": spec.get("deductible"),
        "confidence": spec.get("confidence"),
        "sources": spec.get("sources") or [],
        "grounded": bool(spec.get("grounded")),
        "status": spec.get("status"),
        "llmUsed": bool(spec.get("llmUsed")),
    }


def summarize_announcement(raw_content: str, source: str | None = None) -> dict | None:
    normalized_content = (raw_content or "").strip()
    if not normalized_content:
        logger.info("Skipping LLM announcement summary because content is blank")
        return None
    return _post(
        "/rag/summarize-announcement",
        {"rawContent": normalized_content, "source": source or ""},
        timeout=LLM_TIMEOUT_SUMMARIZE,
    )


def explain_tax_reduction(
    eligible: bool,
    reasons: list[str],
    conditions: dict | None = None,
) -> dict | None:
    """`POST /rag/legal-basis`. 인덱스 미준비 시 409가 오고 None으로 떨어진다."""
    return _post(
        "/rag/legal-basis",
        {"eligible": eligible, "reasons": reasons, "conditions": conditions or {}},
        timeout=LLM_TIMEOUT_LEGAL_BASIS,
    )


def _get(path: str, *, timeout: float | None = None) -> dict | None:
    return _request("GET", path, timeout=timeout)


def _post(path: str, body: dict, *, timeout: float | None = None) -> dict | None:
    return _request("POST", path, body, timeout=timeout)


def _post_multipart(
    path: str,
    *,
    filename: str,
    image_base64: str,
    mime_type: str,
    timeout: float,
) -> dict | None:
    try:
        raw = base64.b64decode(image_base64)
    except (ValueError, TypeError):
        return None
    boundary = f"----skn34{uuid.uuid4().hex}"
    header = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="image"; filename="{filename}"\r\n'
        f"Content-Type: {mime_type or 'image/jpeg'}\r\n\r\n"
    ).encode("utf-8")
    footer = f"\r\n--{boundary}--\r\n".encode("ascii")
    data = header + raw + footer
    url = f"{LLM_API_URL}{path}"
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Accept": "application/json",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            payload = res.read().decode("utf-8")
            return json.loads(payload) if payload else {}
    except urllib.error.HTTPError as exc:
        _log_http_error("POST", path, exc)
        return None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        _log_transport_error("POST", path, exc)
        return None


def _request(
    method: str,
    path: str,
    body: dict | None = None,
    timeout: float | None = None,
) -> dict | None:
    url = f"{LLM_API_URL}{path}"
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout or LLM_TIMEOUT_SECONDS) as res:
            raw = res.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        _log_http_error(method, path, exc)
        return None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        _log_transport_error(method, path, exc)
        return None


def _log_http_error(
    method: str,
    path: str,
    exc: urllib.error.HTTPError,
) -> None:
    """LLM 오류 응답에서 비민감 코드만 추출해 기록한다."""
    error_code = "HTTP_ERROR"
    retryable = exc.code >= 500
    try:
        raw = exc.read().decode("utf-8")
        payload = json.loads(raw) if raw else {}
        error = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(error, dict):
            error_code = str(error.get("code") or error_code)
            retryable = bool(error.get("retryable", retryable))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        pass
    logger.warning(
        "LLM HTTP error: method=%s path=%s status=%s code=%s retryable=%s",
        method,
        path,
        exc.code,
        error_code,
        retryable,
    )


def _log_transport_error(method: str, path: str, exc: Exception) -> None:
    """URL·요청 본문·자격증명을 제외하고 전송 오류 종류만 기록한다."""
    logger.warning(
        "LLM transport error: method=%s path=%s type=%s",
        method,
        path,
        type(exc).__name__,
    )

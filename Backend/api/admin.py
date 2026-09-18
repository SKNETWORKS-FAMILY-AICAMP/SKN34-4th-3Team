from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import get_admin
from core import repo
from core.llm_client import llm_status, reindex
from core.postgres import postgres_status
from schemas.auth import LoginRequest, LoginResponse
from services import auth_service

router = APIRouter(prefix="/admin", tags=["관리자"])


def _parse_date(value) -> date | None:
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    return date.fromisoformat(str(value)[:10])


def _serialize_user(user: dict) -> dict:
    profile = repo.get_profile(user["id"]) or {}
    return {
        "id": user["id"],
        "email": user["email"],
        "name": user["name"],
        "age": user.get("age"),
        "region": user.get("region"),
        "status": user.get("status") or "active",
        "createdAt": user.get("created_at"),
        "business": {
            "businessType": profile.get("business_type"),
            "industry": profile.get("industry"),
            "foundedAt": profile.get("founded_at"),
        },
    }


@router.post("/auth/login", response_model=LoginResponse, summary="관리자 로그인")
def admin_login(body: LoginRequest):
    return auth_service.admin_login(body.email, body.password)


@router.get("/users", summary="사용자 목록")
def list_users(_: dict = Depends(get_admin), page: int = Query(default=1, ge=1)):
    rows = repo.list_users(offset=(page - 1) * 20, limit=20)
    return {"users": [_serialize_user(user) for user in rows]}


@router.get("/users/{user_id}", summary="사용자 상세")
def user_detail(user_id: int, _: dict = Depends(get_admin)):
    user = repo.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    return {
        "user": _serialize_user(user),
        "usage": {
            "chatMessages": len(repo.list_chats(user_id)),
            "expenses": len(repo.list_expenses(user_id)),
            "savedPolicies": len(repo.saved_policy_ids(user_id)),
        },
    }


@router.patch("/users/{user_id}", summary="사용자 상태 변경")
def update_user_status(user_id: int, body: dict, _: dict = Depends(get_admin)):
    user = repo.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    status = body.get("status")
    if status not in ("active", "suspended"):
        raise HTTPException(status_code=400, detail="status는 active 또는 suspended 입니다.")
    repo.update_user(user_id, {"status": status})
    return {"user": _serialize_user(repo.get_user(user_id))}


@router.get("/tax-documents", summary="세법 자료 목록")
def tax_documents(_: dict = Depends(get_admin)):
    return {"documents": repo.list_tax_documents()}


@router.post("/tax-documents", summary="세법 자료 등록")
def create_tax_document(body: dict, current: dict = Depends(get_admin)):
    doc_id = repo.insert_tax_document(current["id"], body)
    return {"documentId": doc_id}


@router.get("/policies", summary="정책 데이터 목록")
def admin_policies(
    _: dict = Depends(get_admin),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
):
    return {"policies": repo.list_policies(offset=(page - 1) * size, limit=size)}


@router.post("/policies", summary="정책 데이터 등록")
def create_policy(body: dict, current: dict = Depends(get_admin)):
    start = _parse_date(body.get("applyStartDate"))
    end = _parse_date(body.get("applyEndDate"))
    pid = repo.insert_policy(current["id"], body)
    policy = repo.get_policy(pid)
    aid = repo.insert_announcement(pid, {**body, "content": body.get("content") or body.get("benefit") or policy["title"]}, start, end)
    if end:
        repo.insert_event(
            "POLICY",
            f"{policy['title']} 신청 마감",
            end,
            f"{policy.get('source') or ''} · {policy['region']}",
            policy_id=pid,
        )
    return {"policyId": pid, "announcementId": aid}


@router.get("/announcements", summary="공고문 목록")
def admin_announcements(
    _: dict = Depends(get_admin),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
):
    return {"announcements": repo.list_announcements(offset=(page - 1) * size, limit=size)}


@router.post("/announcements", summary="공고문 등록")
def create_announcement(body: dict, _: dict = Depends(get_admin)):
    policy_id = body.get("policyId")
    if policy_id and not repo.get_policy(policy_id):
        raise HTTPException(status_code=404, detail="정책을 찾을 수 없습니다.")
    start = _parse_date(body.get("applyStartDate"))
    end = _parse_date(body.get("applyEndDate"))
    aid = repo.insert_announcement(policy_id, body, start, end)
    if policy_id and end:
        policy = repo.get_policy(policy_id)
        repo.insert_event(
            "POLICY",
            f"{policy['title']} 신청 마감",
            end,
            policy.get("source") or "",
            policy_id=policy_id,
        )
    return {"announcementId": aid}


@router.post("/rag-documents/reindex", summary="RAG 문서 재색인")
def reindex_documents(body: dict | None = None, _: dict = Depends(get_admin)):
    """인덱스 준비 여부와 무관하게 재색인을 요청합니다.

    `documentIds`의 의미가 합의되기 전이라 본문은 무시하고 전체 재색인만 호출합니다.
    """
    _ = body
    result = reindex()
    if result is None:
        raise HTTPException(status_code=502, detail="LLM 재색인 요청에 실패했습니다.")
    return {"status": result.get("status"), "llm": llm_status()}


@router.get("/monitoring", summary="시스템 모니터링")
def monitoring(_: dict = Depends(get_admin)):
    llm = llm_status()
    return {
        "metrics": {
            "users": repo.count("users"),
            "activeUsers": repo.count_users_by_status("active"),
            "suspendedUsers": repo.count_users_by_status("suspended"),
            "policies": repo.count("policies"),
            "announcements": repo.count("announcements"),
            "taxDocuments": repo.count("tax_documents"),
            "chatMessages": repo.count("chat_messages"),
            "expenses": repo.count("expenses"),
            "reminders": repo.count("reminders"),
            "ragReady": bool(llm.get("ragReady")),
            "llm": llm,
            "postgres": postgres_status(),
        }
    }

from datetime import date, timezone

from fastapi import HTTPException

from core import repo
from core.llm_client import explain_expense, extract_receipt

# 지출항목별 (경비 인정 여부, 신뢰도, 안내). 신뢰도 0.7 이상이고 증빙이 적격이면 '높음'으로 본다.
CATEGORY_RULES = {
    "사무용품": (True, 0.9, "사업용 소모품으로 경비 인정 가능성이 높습니다."),
    "통신비": (True, 0.8, "업무용 전화·인터넷 요금은 경비로 인정됩니다. 개인 사용분이 섞여 있으면 업무 사용분만 인정돼요."),
    "차량유지비": (True, 0.6, "업무용 차량의 주유·수리·보험료는 인정되지만, 업무용 승용차는 한도 등 별도 규정이 적용돼요."),
    "광고선전비": (True, 0.85, "사업 홍보를 위한 광고·판촉 비용은 경비로 인정됩니다."),
    "임차료": (True, 0.85, "사업장 임차료는 경비로 인정됩니다. 임대차계약서와 세금계산서 등 증빙을 보관해 두세요."),
    "복리후생비": (True, 0.55, "직원 복지 목적의 식대·간식 등은 인정될 수 있지만, 사업주 본인의 개인 식비는 인정되지 않는 경우가 많아요."),
    "접대비": (True, 0.5, "거래처 접대 비용은 한도 안에서만 인정되고, 건당 3만 원을 넘으면 카드·현금영수증·세금계산서 등 적격증빙이 필수예요."),
    "교육·도서": (True, 0.75, "업무와 관련된 교육훈련비·도서 구입비는 경비로 인정됩니다. 업무와 무관한 개인 학습은 제외돼요."),
    "기타": (True, 0.4, "항목을 특정하기 어려워 업무 관련성을 직접 확인해야 해요."),
}

# 예전 분류·표기를 새 지출항목으로 옮긴다.
LEGACY_CATEGORIES = {
    "식비": "복리후생비",
    "식대": "복리후생비",
    "교통": "차량유지비",
    "경조사비": "접대비",
    "접대": "접대비",
    "통신": "통신비",
    "광고": "광고선전비",
    "임대료": "임차료",
    "교육": "교육·도서",
    "도서": "교육·도서",
}

# 상호·품목 키워드로 지출항목을 짐작한다(OCR이 분류를 못 준 경우의 대비책).
CATEGORY_KEYWORDS = [
    ("통신비", ("통신", "텔레콤", "SKT", "KT", "유플러스", "인터넷")),
    ("차량유지비", ("주유", "정비", "카센터", "주차", "하이패스", "세차", "자동차")),
    ("광고선전비", ("광고", "마케팅", "인쇄", "현수막", "홍보")),
    ("임차료", ("임대", "월세", "임차", "부동산")),
    ("교육·도서", ("서점", "도서", "교보", "영풍", "예스24", "학원", "교육", "강의")),
    ("사무용품", ("문구", "오피스", "전자", "사무")),
    ("복리후생비", ("카페", "커피", "식당", "치킨", "분식", "김밥", "마트", "편의점", "베이커리")),
]

# 적격증빙(소득세법 제160조의2 등): 세금계산서·계산서·신용카드매출전표·현금영수증은
# 금액과 무관하게 인정되고, 간이영수증(영수증)은 건당 3만 원까지만 인정된다.
# 3만 원을 넘겨 간이영수증만 받으면 손금 자체는 인정돼도 증빙불비가산세(2%) 대상이다.
QUALIFIED_PROOF_TYPES = {"tax_invoice", "card_receipt", "cash_receipt"}
SIMPLE_RECEIPT_LIMIT = 30000

PROOF_LABELS = {
    "tax_invoice": "세금계산서",
    "card_receipt": "신용카드 매출전표",
    "cash_receipt": "현금영수증",
    "simple_receipt": "간이영수증",
    "unknown": "확인 불가",
}

TIER_LABELS = {
    "high": "인정 가능성 높음",
    "ambiguous": "애매함 (확인 필요)",
    "low": "인정 어려움",
}


def _check_proof(proof_type: str | None, amount: int | None) -> bool | None:
    """증빙이 적격인지 판정한다. None이면 증빙 종류를 몰라 판단할 수 없다는 뜻."""
    if proof_type in QUALIFIED_PROOF_TYPES:
        return True
    if proof_type == "simple_receipt":
        return amount is not None and amount <= SIMPLE_RECEIPT_LIMIT
    return None


def _missing_fields(vendor: str | None, spent, amount: int | None, proof_type: str | None) -> list[str]:
    missing = []
    if not vendor or vendor == "상호 미상":
        missing.append("상호")
    if not spent:
        missing.append("거래일")
    if not amount:
        missing.append("금액")
    if not proof_type or proof_type == "unknown":
        missing.append("증빙 유형(세금계산서·카드전표·현금영수증 표시)")
    return missing


def _tier(deductible: bool, confidence: float, proof_valid: bool | None) -> str:
    if not deductible:
        return "low"
    if confidence >= 0.7 and proof_valid is True:
        return "high"
    return "ambiguous"


def _proof_note(proof_valid: bool | None, amount: int, proof_type: str | None) -> str | None:
    if proof_valid is False:
        return (
            f"{amount:,}원 지출인데 {PROOF_LABELS.get(proof_type, '간이영수증')}만 있어 "
            f"적격증빙 요건(3만 원 초과 시 세금계산서·카드전표·현금영수증 필요)을 충족하지 "
            "못했습니다. 이대로 경비 처리하면 증빙불비가산세(2%) 대상이 될 수 있어요."
        )
    if proof_valid is None:
        return "증빙 종류를 이미지에서 확인하지 못해 적격 여부를 판단할 수 없습니다."
    return None


def _normalize_category(category: str | None) -> str | None:
    if category in CATEGORY_RULES:
        return category
    return LEGACY_CATEGORIES.get(category or "", category)


def _classify(vendor: str, amount: int, hinted: str | None = None, items: list[str] | None = None) -> str:
    hinted = _normalize_category(hinted)
    if hinted in CATEGORY_RULES:
        return hinted
    text = f"{vendor} {' '.join(items or [])}"
    lowered = text.lower()
    for category, words in CATEGORY_KEYWORDS:
        if any(w.lower() in lowered for w in words):
            return category
    return "기타"


def _apply_rule(expense: dict, category: str) -> None:
    category = _normalize_category(category) or "기타"
    deductible, confidence, basis = CATEGORY_RULES.get(category, CATEGORY_RULES["기타"])
    expense["category"] = category
    expense["deductible"] = deductible
    expense["deductible_confidence"] = confidence
    expense["deductible_basis"] = basis


def _migrate_legacy(expense: dict) -> dict:
    """예전 분류(식비·교통·경조사비 등)로 저장된 지출을 새 지출항목 규칙으로 다시 계산해 저장한다."""
    if expense["category"] in CATEGORY_RULES:
        return expense
    extraction = repo.get_extraction(expense["receipt_id"]) or {}
    # 옛 "교통"·"경조사비"는 분류에 실패했을 때의 기본값이기도 해서, 상호·품목 키워드를 먼저 본다.
    category = _classify(
        extraction.get("vendor") or "", expense["amount"], None, list(extraction.get("items") or [])
    )
    if category == "기타":
        category = _normalize_category(expense["category"])
        if category not in CATEGORY_RULES:
            category = "기타"
    deductible, confidence, basis = CATEGORY_RULES[category]
    proof_type = extraction.get("proof_type") or "unknown"
    proof_valid = _check_proof(proof_type, expense["amount"])
    missing = _missing_fields(extraction.get("vendor"), extraction.get("date"), expense["amount"], proof_type)
    note = _proof_note(proof_valid, expense["amount"], proof_type)
    repo.update_expense(
        expense["id"],
        category,
        deductible,
        confidence,
        f"{basis} {note}" if note else basis,
        _tier(deductible, confidence, proof_valid),
        proof_valid,
        missing,
    )
    return repo.get_expense(expense["id"]) or expense


def _law_url(law: str, article: str) -> str:
    return f"https://www.law.go.kr/법령/{law}/{article}"


def _law(law: str, article: str, title: str, point: str, who: str | None = None) -> dict:
    return {"law": law, "article": article, "title": title, "point": point, "who": who,
            "url": _law_url(law.replace(" ", ""), article)}


# 조문 번호·제목은 국가법령정보 원문으로 확인한 것만 넣었다. 요지는 이해를 돕는 요약이므로 원문 링크로 확인하도록 한다.
LAW_GENERAL = _law(
    "소득세법", "제27조", "사업소득의 필요경비의 계산",
    "총수입금액에 대응하는 비용으로서 일반적으로 용인되는 통상적인 것만 필요경비로 인정돼요.", "개인사업자",
)
LAW_PROOF = _law(
    "소득세법", "제160조의2", "경비 등의 지출증명 수취 및 보관",
    "필요경비를 인정받으려면 지출 증명서류를 받아 확정신고기간 종료일부터 5년간 보관해야 해요. "
    "사업자에게서 재화·용역을 공급받으면 세금계산서·카드전표·현금영수증 같은 정규증빙을 받아야 하고, 거래 건당 3만 원 이하는 예외예요.",
    "개인사업자",
)
LAW_PENALTY = _law(
    "소득세법", "제81조의6", "증명서류 수취 불성실 가산세",
    "정규증빙을 받지 않으면 그 금액의 2%를 가산세로 내요. 소규모사업자 등은 대상에서 제외돼요.", "개인사업자",
)
LAW_PENALTY_CORP = _law(
    "법인세법", "제75조의5", "증명서류 수취 불성실 가산세",
    "법인도 정규증빙을 받지 않으면 손금으로 인정되는 금액의 2%를 가산세로 내요.", "법인",
)
LAWS_BY_CATEGORY = {
    "접대비": [
        _law("소득세법", "제35조", "기업업무추진비의 필요경비 불산입",
             "접대·교제 명목의 비용은 한도 안에서만 필요경비로 인정돼요. 한 번에 일정 금액(3만 원)을 넘으면 신용카드·현금영수증·세금계산서 등을 써야 인정돼요. (예전 이름: 접대비)", "개인사업자"),
        _law("법인세법", "제25조", "기업업무추진비의 손금불산입",
             "법인의 접대비도 같은 방식으로 한도와 적격증빙 요건을 넘으면 손금에 산입되지 않아요.", "법인"),
    ],
    "차량유지비": [
        _law("소득세법", "제33조의2", "업무용승용차 관련 비용 등의 필요경비 불산입 특례",
             "복식부기의무자가 업무용 승용차의 감가상각비·임차료·유류비 등을 경비로 처리할 때 적용돼요. 감가상각비 등은 한도(1대당 연 800만 원)를 넘으면 초과분이 그 해 경비로 인정되지 않고 이월돼요.", "복식부기의무자"),
    ],
    "복리후생비": [
        _law("소득세법 시행령", "제55조", "사업소득의 필요경비의 계산",
             "직원을 위한 직장체육비·직장문화비·직원회식비 등이 필요경비 항목으로 열거돼 있어요. 사업주 본인의 개인 식비는 보통 대상이 아니에요.", "개인사업자"),
    ],
    "광고선전비": [
        _law("소득세법 시행령", "제55조", "사업소득의 필요경비의 계산",
             "광고·선전을 목적으로 견본품·달력·수첩 등을 불특정 다수에게 기증하는 비용이 필요경비 항목으로 열거돼 있어요. 그 밖의 광고 비용은 제27조의 일반 원칙으로 판단해요.", "개인사업자"),
    ],
}
# 별도 개별 조문보다 일반 원칙(제27조)으로 판단하는 항목의 안내.
LAW_NOTES = {
    "사무용품": "사무용품은 별도 개별 조문보다 제27조의 일반 원칙(사업과 관련된 통상적인 비용)으로 판단해요.",
    "통신비": "통신비는 별도 개별 조문보다 제27조의 일반 원칙으로 판단해요. 개인용과 섞이면 업무 사용분만 인정돼요.",
    "임차료": "사업장 임차료는 별도 개별 조문보다 제27조의 일반 원칙으로 판단해요. 임대차계약서와 세금계산서를 보관하세요.",
    "교육·도서": "교육·도서비는 별도 개별 조문보다 제27조의 일반 원칙(업무 관련성)으로 판단해요.",
    "기타": "항목이 분명하지 않으면 제27조의 일반 원칙(사업과의 관련성)으로 판단하므로, 지출 내용을 직접 확인해 주세요.",
}


def _legal_refs(category: str, proof_valid: bool | None) -> tuple[list[dict], str | None]:
    laws = [dict(x) for x in LAWS_BY_CATEGORY.get(category, [])]
    laws.append(dict(LAW_GENERAL))
    laws.append(dict(LAW_PROOF))
    if proof_valid is not True:
        laws.append(dict(LAW_PENALTY))
        laws.append(dict(LAW_PENALTY_CORP))
    return laws, LAW_NOTES.get(category)


def create_receipt(
    user_id: int,
    filename: str,
    *,
    image_base64: str | None = None,
    mime_type: str = "image/jpeg",
    image_bytes: bytes | None = None,
) -> dict:
    llm = extract_receipt(filename, image_base64=image_base64, mime_type=mime_type)
    if llm:
        vendor = llm.get("vendor") or "상호 미상"
        amount = int(llm.get("amount") or 0)
        items = llm.get("items") or []
        spent = date.fromisoformat(str(llm.get("date") or date.today())[:10])
        proof_type = llm.get("proofType") or "unknown"
        category = _classify(vendor, amount, llm.get("category"), items)
        source = llm.get("source") or "heuristic"
        # 못 읽은 값은 아래에서 기본값으로 채워지므로, 실제로 읽은 것인지 따로 기록해 둔다.
        read_meta = {
            "source": source,
            "read": {
                "date": bool(llm.get("date")),
                "vendor": bool(llm.get("vendor")),
                "amount": bool(llm.get("amount")),
                "items": bool(items),
                "proof": proof_type != "unknown",
            },
            "evidence": {
                "date": llm.get("dateText"),
                "vendor": llm.get("vendorText"),
                "amount": llm.get("amountText"),
                "proof": llm.get("proofEvidence"),
            },
        }
    else:
        vendor = "샘플문구점" if "office" in filename.lower() else "강남카페"
        amount = 18000
        items = ["아이스 아메리카노", "크루아상"] if "카페" in vendor else ["노트", "펜"]
        spent = date.today()
        proof_type = "unknown"
        category = _classify(vendor, amount, None, items)
        source = "mock"
        read_meta = {
            "source": source,
            "read": {"date": False, "vendor": False, "amount": False, "items": False, "proof": False},
            "evidence": {},
        }

    rid = repo.insert_receipt(user_id, filename, image_bytes=image_bytes, mime_type=mime_type)
    repo.insert_extraction(rid, spent, vendor, amount, items, proof_type, read_meta)

    deductible, confidence, basis = CATEGORY_RULES.get(category, CATEGORY_RULES["기타"])
    proof_valid = _check_proof(proof_type, amount)
    missing = _missing_fields(vendor, spent, amount, proof_type)
    tier = _tier(deductible, confidence, proof_valid)
    note = _proof_note(proof_valid, amount, proof_type)
    basis = f"{basis} {note}" if note else basis
    basis = f"{basis} (추출: {source})"

    repo.insert_expense(
        rid, user_id, category, amount, spent, deductible, confidence, basis, tier, proof_valid, missing
    )
    return {
        "receiptId": rid,
        "status": "done",
        "ocrSource": source,
        "proofType": proof_type,
        "proofTypeLabel": PROOF_LABELS.get(proof_type, proof_type),
    }


def get_extraction(receipt_id: int, user_id: int) -> dict:
    receipt = repo.get_receipt(receipt_id)
    if not receipt or receipt["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="영수증을 찾을 수 없습니다.")
    extraction = repo.get_extraction(receipt_id) or {}
    proof_type = extraction.get("proof_type") or "unknown"
    return {
        "date": extraction.get("date"),
        "vendor": extraction.get("vendor"),
        "amount": extraction.get("amount"),
        "items": extraction.get("items") or [],
        "proofType": proof_type,
        "proofTypeLabel": PROOF_LABELS.get(proof_type, proof_type),
        "ocrSource": "heuristic",
    }


def list_expenses(
    user_id: int,
    category: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[dict]:
    rows = [_migrate_legacy(e) for e in repo.list_expenses(user_id)]
    if category:
        category = _normalize_category(category)
        rows = [e for e in rows if e["category"] == category]
    if from_date:
        rows = [e for e in rows if e["date"] >= from_date]
    if to_date:
        rows = [e for e in rows if e["date"] <= to_date]
    result = []
    for e in rows:
        extraction = repo.get_extraction(e["receipt_id"]) or {}
        uploaded_at = (repo.get_receipt_meta(e["receipt_id"]) or {}).get("created_at")
        if uploaded_at is not None and uploaded_at.tzinfo is None:
            uploaded_at = uploaded_at.replace(tzinfo=timezone.utc)
        proof_type = extraction.get("proof_type") or "unknown"
        tier = e.get("deductible_tier") or _tier(
            e["deductible"], e.get("deductible_confidence") or 0.0, e.get("proof_valid")
        )
        result.append(
            {
                "expenseId": e["id"],
                "receiptId": e["receipt_id"],
                "vendor": extraction.get("vendor") or "상호 미상",
                "category": _normalize_category(e["category"]) or e["category"],
                "amount": e["amount"],
                "date": e["date"],
                "uploadedAt": uploaded_at,
                "deductible": e["deductible"],
                "tier": tier,
                "tierLabel": TIER_LABELS.get(tier, tier),
                "proofType": proof_type,
                "proofTypeLabel": PROOF_LABELS.get(proof_type, proof_type),
                "proofValid": e.get("proof_valid"),
                "missingFields": e.get("missing_fields") or [],
                "items": extraction.get("items") or [],
            }
        )
    return result


def update_category(expense_id: int, user_id: int, category: str) -> dict:
    expense = repo.get_expense(expense_id)
    if not expense or expense["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="지출을 찾을 수 없습니다.")
    if category not in CATEGORY_RULES:
        raise HTTPException(status_code=400, detail="지원하지 않는 지출항목입니다.")
    deductible, confidence, basis = CATEGORY_RULES[category]

    extraction = repo.get_extraction(expense["receipt_id"]) or {}
    proof_type = extraction.get("proof_type") or "unknown"
    proof_valid = _check_proof(proof_type, expense["amount"])
    missing = _missing_fields(extraction.get("vendor"), extraction.get("date"), expense["amount"], proof_type)
    tier = _tier(deductible, confidence, proof_valid)
    note = _proof_note(proof_valid, expense["amount"], proof_type)
    basis = f"{basis} {note}" if note else basis

    repo.update_expense(expense_id, category, deductible, confidence, basis, tier, proof_valid, missing)
    return deductibility(expense_id, user_id)


def deductibility(expense_id: int, user_id: int) -> dict:
    expense = repo.get_expense(expense_id)
    if not expense or expense["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="지출을 찾을 수 없습니다.")
    expense = _migrate_legacy(expense)
    extraction = repo.get_extraction(expense["receipt_id"]) or {}
    vendor = extraction.get("vendor") or "상호 미상"
    proof_type = extraction.get("proof_type") or "unknown"
    rag = explain_expense(
        expense["category"],
        vendor,
        expense["amount"],
        items=list(extraction.get("items") or []),
    )
    basis = expense["deductible_basis"]
    llm_used = False
    sources: list[str] = []
    deductible = expense["deductible"]
    confidence = expense["deductible_confidence"]
    if rag and (rag.get("answer") or rag.get("basis")):
        basis = rag.get("answer") or rag.get("basis")
        # 근거를 못 찾으면 LLM이 llmUsed=false로 알려준다. 응답값을 그대로 쓴다.
        llm_used = bool(rag.get("llmUsed"))
        # 세법 자료로 뒷받침되지 않은 응답("판단할 수 없음")은 안내 문구로만 쓰고, 규칙 판정을 덮어쓰지 않는다.
        if llm_used:
            if rag.get("deductible") is not None:
                deductible = bool(rag["deductible"])
            if rag.get("confidence") is not None:
                confidence = float(rag["confidence"])
        sources = [
            item.get("title") or item.get("source") or "세법 자료"
            for item in (rag.get("sources") or [])
            if item
        ]

    proof_valid = _check_proof(proof_type, expense["amount"])
    missing = _missing_fields(vendor, extraction.get("date"), expense["amount"], proof_type)
    tier = _tier(deductible, confidence, proof_valid)
    note = _proof_note(proof_valid, expense["amount"], proof_type)
    if note and note not in basis:
        basis = f"{basis} {note}"

    repo.update_expense(expense_id, expense["category"], deductible, confidence, basis, tier, proof_valid, missing)
    return {
        "deductible": deductible,
        "confidence": confidence,
        "basis": basis,
        "llmUsed": llm_used,
        "sources": sources,
        "tier": tier,
        "tierLabel": TIER_LABELS.get(tier, tier),
        "proofType": proof_type,
        "proofTypeLabel": PROOF_LABELS.get(proof_type, proof_type),
        "proofValid": proof_valid,
        "missingFields": missing,
    }


def analysis(expense_id: int, user_id: int) -> dict:
    """OCR이 영수증에서 무엇을 읽었고 그것으로 어떻게 판정했는지 단계별로 설명한다. LLM 호출 없이 저장값과 규칙만 쓴다."""
    expense = repo.get_expense(expense_id)
    if not expense or expense["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="지출을 찾을 수 없습니다.")
    expense = _migrate_legacy(expense)
    extraction = repo.get_extraction(expense["receipt_id"]) or {}
    meta = extraction.get("read_meta") or {}
    evidence = meta.get("evidence") or {}

    vendor = extraction.get("vendor") or "상호 미상"
    items = list(extraction.get("items") or [])
    amount = int(expense["amount"] or 0)
    proof_type = extraction.get("proof_type") or "unknown"
    proof_label = PROOF_LABELS.get(proof_type, proof_type)
    category = expense["category"]

    if meta.get("read"):
        read = meta["read"]
    else:
        # 읽음 여부를 기록하기 전에 올린 영수증: 값으로 짐작할 수 있는 것만 판단하고 날짜는 알 수 없다.
        read = {
            "vendor": vendor != "상호 미상",
            "amount": amount > 0,
            "items": bool(items),
            "proof": proof_type != "unknown",
            "date": None,
        }

    fields = [
        {"key": "vendor", "label": "상호", "value": vendor if read.get("vendor") else None,
         "read": read.get("vendor"), "evidence": evidence.get("vendor")},
        {"key": "date", "label": "거래일", "value": str(extraction.get("date") or expense["date"]) if read.get("date") is not False else None,
         "read": read.get("date"), "evidence": evidence.get("date")},
        {"key": "amount", "label": "금액", "value": f"{amount:,}원" if read.get("amount") else None,
         "read": read.get("amount"), "evidence": evidence.get("amount")},
        {"key": "items", "label": "품목", "value": ", ".join(items) if items else None,
         "read": read.get("items"), "evidence": None},
        {"key": "proof", "label": "증빙 종류", "value": proof_label if read.get("proof") else None,
         "read": read.get("proof"), "evidence": evidence.get("proof")},
    ]

    proof_valid = _check_proof(proof_type, amount)
    deductible = bool(expense["deductible"])
    confidence = float(expense["deductible_confidence"] or 0.0)
    tier = _tier(deductible, confidence, proof_valid)
    pct = round(confidence * 100)

    seen = ", ".join(items) if items else (vendor if read.get("vendor") else None)
    rule_deductible, _, rule_basis = CATEGORY_RULES.get(category, CATEGORY_RULES["기타"])

    if proof_type == "unknown":
        step_proof = {"result": "unknown", "detail": "세금계산서·카드전표·현금영수증임을 알 수 있는 표시를 찾지 못했어요."}
    elif evidence.get("proof"):
        step_proof = {"result": "pass", "detail": f"영수증의 '{evidence['proof']}' 문구를 확인 → 증빙 종류: {proof_label}"}
    else:
        step_proof = {"result": "pass", "detail": f"증빙 종류: {proof_label}"}

    if proof_valid is True and proof_type in QUALIFIED_PROOF_TYPES:
        step_valid = {"result": "pass", "detail": "세금계산서·카드전표·현금영수증은 금액과 상관없이 인정되는 적격증빙이에요."}
    elif proof_valid is True:
        step_valid = {"result": "pass", "detail": f"간이영수증은 건당 3만 원까지 인정돼요. {amount:,}원이라 범위 안이에요."}
    elif proof_valid is False:
        step_valid = {"result": "fail", "detail": f"{amount:,}원으로 3만 원을 넘는데 간이영수증뿐이라 적격증빙이 아니에요. 증빙불비가산세(2%) 대상이 될 수 있어요."}
    else:
        step_valid = {"result": "unknown", "detail": "증빙 종류를 알 수 없어 적격 여부를 판단하지 못했어요."}

    adjusted = deductible != rule_deductible
    step_category = {
        "result": "pass" if deductible and confidence >= 0.7 else "warn" if deductible else "fail",
        "detail": (f"읽은 내용: {seen}. " if seen else "") + f"분류: {category}. {rule_basis}"
        + (" 세법 자료를 검색한 결과를 반영해 판정이 조정됐어요." if adjusted else ""),
    }

    if tier == "high":
        overall = f"경비로 인정될 가능성이 높고(신뢰도 {pct}%) 증빙도 적격이라 '높음'으로 판정했어요."
    elif tier == "low":
        overall = "이 분류는 경비 인정이 어렵다고 보아 '어려움'으로 판정했어요."
    else:
        reasons = []
        if confidence < 0.7:
            reasons.append(f"분류 신뢰도가 {pct}%로 낮고")
        if proof_valid is not True:
            reasons.append("증빙이 적격인지 확실하지 않아")
        overall = " ".join(reasons) + " '애매함'으로 판정했어요. 빠진 정보를 채워 다시 확인해 보세요."

    steps = [
        {"key": "proof", "title": "증빙 종류 확인", **step_proof},
        {"key": "valid", "title": "적격증빙 여부", **step_valid},
        {"key": "category", "title": "지출 분류 · 업무 관련성", **step_category},
        {"key": "overall", "title": "종합 판정",
         "result": {"high": "pass", "ambiguous": "warn", "low": "fail"}[tier], "detail": overall},
    ]
    laws, law_note = _legal_refs(category, proof_valid)
    return {
        "fields": fields,
        "steps": steps,
        "laws": laws,
        "lawNote": law_note,
        "tier": tier,
        "tierLabel": TIER_LABELS[tier],
        "ocrSource": meta.get("source") or "legacy",
    }


def get_receipt_image(receipt_id: int, user_id: int) -> tuple[bytes, str]:
    row = repo.get_receipt_image(receipt_id)
    image_data = row.get("image_data") if row else None
    if not row or row["user_id"] != user_id or not image_data:
        raise HTTPException(status_code=404, detail="영수증 이미지를 찾을 수 없습니다.")
    return bytes(image_data), row.get("mime_type") or "image/jpeg"


def delete_expense(expense_id: int, user_id: int) -> None:
    expense = repo.get_expense(expense_id)
    if not expense or expense["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="지출을 찾을 수 없습니다.")
    repo.delete_expense(expense_id, expense["receipt_id"])

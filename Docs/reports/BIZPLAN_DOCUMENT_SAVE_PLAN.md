# 사업계획서 파일 저장 · 마이페이지 서류 탭 계획

> 작성일 2026-09-29, `feature/docu_save` `e51be47` 기준. 사업계획서 페이지에서 만든 HWPX/PDF 파일을 DB에 저장하고 마이페이지 '서류' 탭에서 목록·다운로드·삭제하는 기능의 계획. 코드 변경 전 설계 단계 문서.
>
> 2026-09-29 보관 제한 결정: 사용자당 8개·파일당 50MiB, 8개 도달 시 저장 거부, 동일 파일 중복 저장 허용(2절·8절).

## 1. 배경과 목표

현황
- 파일 출력: `renderPlan`(`Frontend/src/pages/BusinessPlanPage.jsx:946`) → `POST /bizplan/render` → `bizplan_service.render`(`Backend/services/bizplan_service.py:119`). 생성 파일을 base64로 반환만 하고 DB 기록 없음. 프론트는 `downloadBase64File`(`BusinessPlanPage.jsx:220`)로 브라우저 다운로드만 수행
- 임시저장: `PUT /bizplan/draft` → `bizplan_drafts`(`DB/app_extras.sql:100`). 작성 화면 상태(JSON)를 유저당 1건 덮어쓰기. 파일 저장과 별개
- 서류 탭: 메뉴 정의(`Frontend/src/constants.js:279`)만 존재. `MyPage.jsx:840`에서 "서류 화면은 준비 중입니다." 스텁 렌더
- 사업계획서 파일용 테이블·조회 API 없음

| 목표 | 내용 |
|---|---|
| 파일 보관 | '재평가 및 저장' 단계에서 '마이페이지에 저장' 버튼으로 생성 파일을 DB에 저장 |
| 서류 탭 | 저장한 파일 목록(파일명·형식·크기·저장일), 다시 다운로드, 삭제 |

범위 밖
- 저장 파일의 버전 관리·이름 변경·공유
- 사업계획서 외 서류(영수증 등) 통합 목록
- S3 등 외부 스토리지 이관(`Docs/reports/AWS_MIGRATION_PLAN.md` 범위)

## 2. 설계 결정

| 항목 | 결정 | 이유 |
|---|---|---|
| 저장 시점 | 다운로드와 분리된 '마이페이지에 저장' 버튼 | 사용자가 명시적으로 보관할 파일만 저장 |
| 저장 방식 | 서버가 직접 렌더링 후 저장 | 클라이언트가 보낸 base64를 그대로 받지 않아 임의 파일 업로드 차단. 기존 `render()` 검증(양식·이미지 크기·형식) 재사용 |
| 저장소 | PostgreSQL `BYTEA` | 영수증 원본(`receipts.image_data`, `DB/app_extras.sql:20`)과 같은 방식. 새 인프라 불필요 |
| 버튼 노출 | 다운로드 버튼과 같은 조건 | 양식이 있으면 그 형식 1개, 없으면 HWPX/PDF 각각 (`BusinessPlanPage.jsx:1413-1422`) |
| 보관 개수 | 사용자당 8개. 8개 보유 시 저장 거부(409), 자동 삭제 없음 | 사용자 모르게 기존 파일이 사라지지 않게 함. 서류 탭에서 직접 삭제 후 재저장 |
| 파일 크기 | 파일당 50MiB. 초과 시 저장 거부(413) | 사용자당 DB 사용량 상한 400MiB(8 × 50MiB) |
| 중복 저장 | 같은 내용 여러 번 저장 허용 | 개수 제한으로 증가량이 제한되므로 중복 검사 생략 |

## 3. DB

`DB/app_extras.sql`에 추가.

```sql
-- 사업계획서 페이지에서 '마이페이지에 저장'한 파일. 마이페이지 서류 탭에서 조회한다.
CREATE TABLE IF NOT EXISTS bizplan_documents (
    id         SERIAL PRIMARY KEY,
    user_id    INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title      VARCHAR(200) NOT NULL,
    file_name  VARCHAR(255) NOT NULL,
    format     VARCHAR(10)  NOT NULL,   -- 'hwpx' | 'pdf'
    mime_type  VARCHAR(100) NOT NULL,
    file_data  BYTEA        NOT NULL,
    size_bytes INT          NOT NULL,
    created_at TIMESTAMP DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_bizplan_documents_user
    ON bizplan_documents(user_id, created_at DESC);
```

## 4. Backend

| Method | Path | 인증 | 설명 |
|---|---|---|---|
| POST | `/bizplan/documents` | Bearer | body = `BusinessPlanRenderRequest` 재사용. 렌더 후 저장, 메타 반환 |
| GET | `/bizplan/documents` | Bearer | 내 서류 목록(파일 본문 제외, 최신순) |
| GET | `/bizplan/documents/{id}/file` | Bearer | 원본 파일(`HttpResponse` + `Content-Disposition`) |
| DELETE | `/bizplan/documents/{id}` | Bearer | 삭제 |

| 파일 | 변경 |
|---|---|
| `Backend/api/bizplan.py` | 라우트 4개. 기존 `user_auth` router 사용. 파일 응답은 `api/expenses.py:68` `receipt_image` 패턴 |
| `Backend/services/bizplan_service.py` | `save_document`: 보유 개수 확인(8개 이상 409) → 기존 `render()` 호출 → base64 디코드 → 크기 확인(50MiB 초과 413) → repo insert. 개수 확인을 렌더 앞에 두어 거부될 요청의 문서 API 호출 방지. `list_documents`, `get_document_file`, `delete_document`. 소유자 불일치·없음은 404(`expense_service.get_receipt_image` 패턴). 상수 `MAX_DOCUMENTS_PER_USER = 8`, `MAX_DOCUMENT_BYTES = 50 * 1024 * 1024`는 기존 `MAX_DRAFT_BYTES`(:23) 옆에 정의 |
| `Backend/core/repo.py` | `insert_bizplan_document`, `count_bizplan_documents`, `list_bizplan_documents`, `get_bizplan_document`, `delete_bizplan_document`. `upsert_bizplan_draft`(:679) 옆, `db.insert/fetchall/fetchone/execute` 사용 |
| `Backend/schemas/bizplan.py` | `BizplanDocumentItem`(id, title, fileName, format, sizeBytes, createdAt), `BizplanDocumentListResponse` |

## 5. Frontend

| 파일 | 변경 |
|---|---|
| `Frontend/src/api.js` | `saveBizplanDocument`(apiPost, timeout 70000 — `renderBusinessPlan`과 동일), `bizplanDocuments`(apiGet), `bizplanDocumentFile`(apiGetBlob, `receiptImage` 패턴), `deleteBizplanDocument`(apiDelete) |
| `Frontend/src/pages/BusinessPlanPage.jsx` | `renderPlan`의 payload 구성부를 함수로 분리해 다운로드·저장이 공유. `bp-actions`(:1412)에 '마이페이지에 저장' 버튼, 결과 안내는 기존 `savedNote` 방식. 401은 `onRequireLogin`, 409는 "서류는 8개까지 저장할 수 있습니다. 마이페이지 서류 탭에서 삭제한 뒤 다시 시도해 주세요.", 413은 "파일이 50MiB를 넘어 저장하지 못했습니다." |
| `Frontend/src/pages/MyPage.jsx` | `DocsList` 컴포넌트 추가, `menu === 'docs'` 분기 연결(:840 앞). 제목 옆에 보유 개수 `n/8` 표시. 빈 목록이면 사업계획서 페이지 이동 안내. 다운로드는 Blob → `<a download>`, 삭제는 확인 후 목록 갱신 |

스타일은 기존 `tool__panel`, `gov__empty`, `mp-*` 클래스 재사용.

## 6. 테스트·검증

- `Backend/tests/test_bizplan_api.py`: 저장 → 목록 → 파일 조회 → 삭제, 다른 사용자 접근 404, 비로그인 401, 8개 보유 시 9번째 저장 409(렌더 미호출), 렌더 결과 50MiB 초과 413, 동일 요청 2회 저장 시 2건 생성
- DB: `DB/app_extras.sql` 재적용 후 `bizplan_documents` 생성 확인
- 수동: 사업계획서 작성 → '마이페이지에 저장' → 마이페이지 서류 탭에서 목록 표시·다운로드 파일 열림·삭제 확인

## 7. 후속 문서 갱신 (구현 시)

- `Docs/Design/ERD.md`: `bizplan_documents` 추가
- `Docs/Design/API_SPEC.md`, `Backend/README.md`: 4개 엔드포인트 추가

## 8. 리스크

| 항목 | 내용 |
|---|---|
| DB 용량 | BYTEA 저장으로 DB 증가. 사용자당 상한 400MiB(8개 × 50MiB)로 제한(2절) |
| 렌더 중복 | 다운로드 후 저장하면 문서 API를 2회 호출. 개수 제한이 있으므로 허용, 최근 렌더 결과 재사용은 하지 않음 |
| 동시 저장 | 개수 확인과 insert 사이에 같은 사용자가 동시에 저장하면 8개를 넘을 수 있음. 버튼 중복 클릭은 저장 중 비활성화로 막고, 서버는 초과분을 허용 오차로 둠 |

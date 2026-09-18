# LLM 내부 API 명세서

Backend가 LLM 서비스를 호출할 때 쓰는 내부 계약이다. `Docs/Design/API_SPEC.md`가 Frontend↔Backend용이라면, 이 문서는 `Backend↔LLM`용이다. `Docs/Design/SEQUENCE.md`의 `SVC->>LLM` 호출부와 `Docs/Design/CLASS.md`의 `LLMServiceClient`를 실제 엔드포인트 단위로 구체화한 것이다.

> ⚠️ **폐기된 초안입니다. 계약이 아닙니다.**
>
> 확정 계약은 `Docs/Design/LLM_API_SPEC_V1.md`다. 이 문서가 TBD로 남겼던 공통 오류 코드와 타임아웃·재시도 정책은 V1에서 확정됐고, 구현된 엔드포인트도 V1이 정본이다. 두 문서가 충돌하면 V1을 따른다.
>
> 초기 설계 기록으로만 보존한다. Backend 구현 시 참고 문서는 V1과 `Docs/Design/BACKEND_LLM_INTEGRATION_HANDOFF.md`다.

- **Base URL**: `http://llm:8001` — Docker 내부 네트워크에서 서비스명으로 호출, 외부에 노출하지 않는다 (`Docs/Design/ARCHITECTURE.md` §4). Backend가 `http://localhost:8000`을 쓰기로 하면서 LLM은 8001로 정리함
- **인증**: 없음(무인증) — Docker 내부망 신뢰 기반으로 확정. 외부에 노출되지 않는 내부 통신이라 별도 인증 없이 진행한다
- **공통 에러 응답**: `{ "error": { "code": string, "message": string } }` — 4xx/5xx 공통 형식. `Docs/Design/API_SPEC.md`에도 아직 에러 포맷이 없으니, 여기서 먼저 정하고 그쪽에도 맞추는 걸 권장한다
- **동기/비동기**: 전부 동기 REST 호출로 시작한다 (`ARCHITECTURE.md` §4의 MVP 원칙과 동일). OCR·재색인처럼 오래 걸리는 작업은 필요해지면 별도로 재검토

## 1. RAG 질의응답 (FS-05, FS-06, FS-07)

| 항목 | 내용 |
| --- | --- |
| Endpoint | `POST /rag/chat` |
| Request | `{ category, question }` — `category`: `tax` / `expense` / `saving` / `policy` |
| Response | `{ answer, sources: [{ title, url, excerpt }] }` |
| 호출 시점 | `ChatService.sendMessage` 내부. 응답을 `chat_messages`, `answer_sources`에 저장 |
| 비고 | 근거 문서를 못 찾으면 `sources: []`로 반환 — Backend는 이 경우 "확인 필요" 안내로 대체 (FS-05 환각 방지 조건) |

## 2. 세액감면 판정 근거 설명 (FS-13)

| 항목 | 내용 |
| --- | --- |
| Endpoint | `POST /rag/legal-basis` |
| Request | `{ eligible, conditions: { age, region, industry, businessRegisteredAt, foundedAt } }` |
| Response | `{ reasons, legalBasis }` |
| 호출 시점 | `TaxService.checkTaxReduction`. **판정 자체(eligible 여부)는 Backend의 Rule 기반 로직이 수행**하고, LLM은 그 결과에 대한 근거 설명·법령 인용만 생성한다 (`SEQUENCE.md` #1과 동일한 역할 분담) |

## 3. 영수증 OCR 추출 (FS-15)

| 항목 | 내용 |
| --- | --- |
| Endpoint | `POST /ocr/receipt` |
| Request | `multipart/form-data` (`image`) |
| Response | `{ date, vendor, amount, items }` |
| 호출 시점 | `ExpenseService.registerReceipt`에서 이미지 업로드 직후 |
| 비고 | 인식 실패 시 필드를 `null`로 반환 — Backend는 수동 입력으로 보완 (FS-15 예외 규칙) |

## 4. 경비처리 가능성 분석 (FS-17)

| 항목 | 내용 |
| --- | --- |
| Endpoint | `POST /rag/deductibility` |
| Request | `{ category, amount, vendor, items }` |
| Response | `{ deductible, confidence, basis }` |
| 호출 시점 | `ExpenseService.getDeductibility`. 세법 기준과 RAG로 비교한 결과 (FS-17) |

## 5. 공고문 AI 요약 (FS-22)

| 항목 | 내용 |
| --- | --- |
| Endpoint | `POST /rag/summarize-announcement` |
| Request | `{ rawContent }` |
| Response | `{ target, benefit, period, documents, notes, source }` |
| 호출 시점 | `PolicyService.getAnnouncementSummary` |
| 비고 | 응답을 `announcement_summaries`에 캐싱해두고, 이미 요약이 있으면 재호출하지 않는 걸 권장 (매 조회마다 LLM 재호출 방지) |

## 6. RAG 문서 재색인 (FS-27)

| 항목 | 내용 |
| --- | --- |
| Endpoint | `POST /rag/reindex` |
| Request | `{ documentIds }` (선택 — 없으면 전체 대상) |
| Response | `{ status }` |
| 호출 시점 | `AdminService.reindexRagDocuments`. LLM이 내부적으로 임베딩을 생성/갱신하고 `rag_documents.embedding_status`를 갱신 |

## 미확정 사항 (Backend·LLM 팀 합의 필요)

- 공통 에러 코드 목록 (지금은 형식만 정의, 실제 `code` 값 목록 없음)
- 타임아웃·재시도 정책

## 관련 문서

- 호출 흐름: `Docs/Design/SEQUENCE.md`
- 클래스 설계: `Docs/Design/CLASS.md` (`LLMServiceClient`)
- 외부 API(Frontend↔Backend): `Docs/Design/API_SPEC.md`
- 데이터 구조: `Docs/Design/ERD.md`
- 시스템 구성: `Docs/Design/ARCHITECTURE.md`

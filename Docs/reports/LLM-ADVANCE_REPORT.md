# 비동기 상담·스트리밍·사업계획서 변경 보고서

작성일: 2026-09-29  
기준 브랜치: `feature/LLM-advance` (`9fde848` 기준)

## 병합 요약

| 영역 | 현재 동작 | 주요 코드 |
| --- | --- | --- |
| 상담 비동기 처리 | Backend 채팅 요청이 비동기 HTTP로 LLM을 호출한다. 동기 DB 작업은 `sync_to_async`, LLM의 동기 검색 작업은 `asyncio.to_thread`로 분리한다. | [Backend 상담 API](../../Backend/api/chat.py), [상담 서비스](../../Backend/services/chat_service.py), [LLM 그래프](../../LLM/src/rag/graph.py) |
| 최종 답변 스트리밍 | LLM의 최종 구조화 답변에서 생성 중인 `answer`를 `draft` 이벤트로 보내고, 검증된 최종 결과를 `done` 이벤트로 보낸다. Backend는 최종 결과를 저장한 후 프런트엔드에 `done`을 보낸다. | [LLM 답변 생성](../../LLM/src/rag/answer.py), [LLM 스트림](../../LLM/src/serving/rag_routes.py), [Backend 스트림](../../Backend/core/llm_client.py), [프런트엔드 파서](../../Frontend/src/api.js) |
| 상담 화면 | 응답 중에는 답변을 조금씩 표시한다. 최종 응답으로 화면을 한 번에 교체하지 않고 표시를 마친 뒤 메시지를 확정한다. 추가 정보·확인 자료 상자도 나타나는 효과를 적용했다. | [AiConsult](../../Frontend/src/components/AiConsult.jsx), [상담 CSS](../../Frontend/src/styles/04-ai-chat.css) |
| 사업계획서 | 작성 단계의 가로폭을 통일하고 Markdown 다운로드를 제거했다. PDF 양식을 넣으면 PDF만, HWPX 양식을 넣으면 HWPX만, 양식이 없으면 두 형식을 다운로드할 수 있다. | [사업계획서 화면](../../Frontend/src/pages/BusinessPlanPage.jsx), [페이지 폭](../../Frontend/src/styles/06-page-shell.css), [LLM 문서 API](../../LLM/src/serving/rag_routes.py) |
| 이탈 경고 | 임시저장 이후 달라진 작성 내용이 있으면 홈·메뉴 이동·로그아웃 시 확인창을 한 번 띄운다. 새로고침·탭 닫기는 브라우저 기본 경고를 사용한다. 저장 성공 시 경고 상태를 해제하고 저장 실패 시 유지한다. | [App 이동 처리](../../Frontend/src/App.jsx), [초안 상태 비교](../../Frontend/src/pages/BusinessPlanPage.jsx), [페이지 연결](../../Frontend/src/pages/SubPage.jsx) |

## 상담 요청 흐름과 계약

`POST /chat/messages/stream` → Backend `async_rag_answer_stream()` → LLM `POST /rag/chat/stream` → LangGraph → 최종 답변 생성 → Backend 저장 → 브라우저 순서다. 전송 형식은 줄바꿈으로 구분한 JSON(`application/x-ndjson`)이며, 이벤트는 `draft`(현재까지의 답변 문자열), `done`(완성된 결과), `error`를 사용한다. 양쪽 스트리밍 응답에 `X-Accel-Buffering: no`가 설정돼 있다. 기존 비스트리밍 채팅 경로도 남아 있다.

`draft.answer`는 **누적 문자열**이며 생성 중인 임시 표시다. 최종 `status`와 인용 번호는 구조화 출력이 끝난 뒤 검증한다. 따라서 프런트엔드는 `done.result`를 최종 답변과 저장된 메시지의 기준으로 삼는다. LLM 스트림 실패 시 Backend는 기존 대체 답변 경로로 내려갈 수 있으므로, 화면에서 보였던 임시 문장과 `done` 결과가 다를 수 있다. 프런트엔드는 그 차이를 점진적으로 반영해 갑작스러운 전체 교체를 줄인다.

화면 표시 속도는 `AiConsult.jsx`의 `ANSWER_REVEAL_MS`(현재 12ms)와 `ANSWER_REVEAL_CHARS`(현재 1)로 조정한다. 이는 **화면 표시 속도**이며 모델 토큰 생성 속도는 아니다. 다른 대화방으로 이동해도 진행 중인 요청을 해당 방에 연결하고, 답변 완료 후 방 목록과 근거 자료를 갱신한다.

## 사업계획서에서 병합 시 확인할 사항

- [사업계획서 화면](../../Frontend/src/pages/BusinessPlanPage.jsx)의 「보완 내용으로 초안 다시 생성하기」 버튼은 입력칸의 포커스 이동이 첫 클릭을 끊지 않도록 `onMouseDown`에서 기본 포커스 이동을 막는다. 생성 요청은 `onClick` 한 번으로 시작한다.
- PDF/HWPX 양식 검사 응답의 `outputFormats`는 첨부 형식 하나만 돌려준다. 저장된 예전 초안에 `outputFormats: ["hwpx", "pdf"]`가 남아 있어도 화면은 `templateInfo.kind`로 버튼을 결정한다. [LLM 문서 API](../../LLM/src/serving/rag_routes.py)는 양식과 다른 출력 형식을 요청하면 거부한다.
- 양식이 없을 때는 기본 HWPX와 PDF 출력이 모두 가능하다. PDF 양식에서 HWPX를 만들거나 HWPX 양식에서 PDF를 변환하는 경로는 현재 노출하지 않는다.
- 저장 여부는 화면의 작성 데이터와 마지막 로드/저장 시점의 값을 비교한다. 단계 이동·보완 입력 페이지 이동 자체는 저장되지 않은 내용으로 세지 않는다. 저장된 초안을 불러오기만 한 경우에는 경고하지 않는다.
- [이전 사업계획서 보고서](BUSINESS_PLAN_WORKFLOW_SESSION_REPORT_20260924.md)의 Markdown 다운로드 설명은 현재 코드와 다르다. 다운로드 형식은 이 보고서와 현행 코드 기준으로 병합한다.

## 관련 커밋과 확인 범위

| 커밋 | 내용 |
| --- | --- |
| `cd37983` | Backend·LLM 채팅 비동기 처리와 관련 테스트 추가 |
| `eb743c0` | LLM → Backend → Frontend 답변 스트리밍 경로 추가 |
| `8809895` | 스트리밍 표시 방식 조정 및 LLM 모델 요청 옵션 수정 |
| `ccd5303` | 사업계획서 폭과 다운로드 형식 정리 |
| `9fde848` | 초안 재생성 버튼과 저장되지 않은 내용 이탈 경고 |

기능 작업 과정에서 프런트엔드 `npm run build`가 통과했다. 이 보고서 작성 과정에서는 테스트나 브라우저 수동 검증을 추가로 실행하지 않았다. 병합 후에는 **상담 답변의 `draft` → `done` 순서**, **세 가지 양식 조건별 다운로드 버튼**, **초안 수정 후 첫 클릭 생성**, **미저장 상태에서 이동 취소/확인과 저장 후 재이동**을 실제 화면에서 확인하면 된다.

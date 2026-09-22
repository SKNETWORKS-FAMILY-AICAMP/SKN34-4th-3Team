# LLM FastAPI → Django 전환 변경 보고서

- 작성일: 2026-09-22 (Asia/Seoul)
- 이번 작업 범위: LLM HTTP API의 FastAPI → Django 전환 (`33ca80f`)
- 선행 이력: Backend는 별도 커밋 `26404b9`에서 이미 Django Ninja로 전환됐고 이후 `51c2a49`에 병합됐다.
- **이번 LLM 전환 커밋에서 `Backend/` 파일 변경은 0개다. Backend 수정 없이 기존 `Backend/core/llm_client.py`의 HTTP 호출 계약을 유지해 전환했다.**
- 이 보고서는 변경 사실과 검증 범위를 정리한다. 현재 로컬 서버 실행 상태는 아래 검증 기록과 별개다.

## 1. 결과 요약

| 서비스 | 현재 HTTP 프레임워크 | ASGI 서버 | 포트 | 핵심 경로 |
| --- | --- | --- | --- | --- |
| Backend | Django + Django Ninja | Uvicorn | 8000 | `/auth/*`, `/chat/*`, `/announcements`, `/expenses/*`, `/health`, `/docs` |
| LLM | Django ASGI 뷰 | Uvicorn | 8001 | `/rag/*`, `/ocr/receipt`, `/internal/rag/*`, `/health`, `/docs` |

Uvicorn은 ASGI 서버이므로 계속 사용한다. **운영 HTTP 라우팅과 오류 처리는 Django가 담당한다.** LLM의 FastAPI 애플리케이션 파일과 FastAPI·Starlette·`python-multipart` 의존성은 제거됐다. LangGraph, 검색기, PostgreSQL/pgvector 데이터 계층은 프레임워크 교체 대상이 아니어서 유지됐다.

이 표는 전환 후 **전체 시스템의 현재 상태**를 보여준다. 이번에 새로 구현한 것은 LLM 행이다. Backend 행은 이미 완료된 선행 변경을 이해하기 위한 배경이다.

요청 흐름은 다음과 같다.

```text
브라우저 /api/* → Frontend nginx 또는 Vite 프록시 → Backend Django Ninja :8000
                                                     └→ LLM Django ASGI :8001 /rag/*, /ocr/receipt
LLM Django 뷰 → Pydantic 요청 검증 → RAG 함수/LangGraph → JSON 응답
```

프론트 요청의 상대 경로와 개발 프록시는 [`Frontend/src/api.js`](../../Frontend/src/api.js), [`Frontend/vite.config.js`](../../Frontend/vite.config.js)에 정의돼 있다. Backend의 LLM 호출 경로는 [`Backend/core/llm_client.py`](../../Backend/core/llm_client.py)에 남아 있으며, Compose에서 `LLM_API_URL=http://llm:8001`을 주입한다.

## 2. 선행 완료된 Backend 전환: 이번 작업에서 수정하지 않음

| 파일 | 변경된 역할 |
| --- | --- |
| [`Backend/config/api.py`](../../Backend/config/api.py) | `NinjaAPI`를 만들고 기존 기능별 라우터를 등록한다. `/health`, `/docs`를 제공한다. |
| [`Backend/api/`](../../Backend/api/) | 인증, 사용자, 대화, 캘린더, 세금, 지출, 공고, 관리자 등의 HTTP 핸들러를 Django Ninja `Router`로 전환했다. 인증은 `Backend/api/deps.py`의 `HttpBearer`를 사용한다. |
| [`Backend/config/settings.py`](../../Backend/config/settings.py) | Django 설정, CORS, 업로드 크기 여유, Swagger 템플릿을 정의한다. 업무 DB 접근은 Django ORM이 아니라 기존 raw SQL 경로를 사용하므로 `DATABASES={}`다. |
| [`Backend/config/urls.py`](../../Backend/config/urls.py), [`Backend/config/asgi.py`](../../Backend/config/asgi.py) | URL 설정과 ASGI 진입점이다. ASGI 진입 시 DB 초기화와 LLM 인덱스 준비를 시작한다. |
| [`Backend/Dockerfile`](../../Backend/Dockerfile), [`Backend/pyproject.toml`](../../Backend/pyproject.toml) | `config.asgi:application` 실행 및 Django·Django Ninja 의존성을 반영했다. |
| [`Backend/tests/test_api_smoke.py`](../../Backend/tests/test_api_smoke.py) | 인증, 권한, 요청 검증, 공개 공고 API, 영수증 업로드 계약을 Django Ninja 경로로 확인한다. |

위 표는 선행 커밋 `26404b9`의 내용을 요약한 것이다. **`33ca80f`에 포함된 Backend 코드 변경은 아니다.** Backend의 기존 `startup()`은 DB를 초기화하고 별도 스레드에서 LLM `/rag/ready`를 확인한다. 인덱스가 준비되지 않았으면 `/rag/reindex`를 요청한다. `/health`는 Postgres·pgvector·LLM 연결 및 `ragReady`를 함께 반환한다.

## 3. LLM 변경 내역

| 파일 | 변경된 역할 |
| --- | --- |
| [`LLM/src/serving/django_config/settings.py`](../../LLM/src/serving/django_config/settings.py) | Django 설정, 허용 호스트, CORS, 업로드 제한을 정의한다. RAG 데이터 접근은 별도 계층이라 Django ORM을 쓰지 않는다. |
| [`LLM/src/serving/django_config/urls.py`](../../LLM/src/serving/django_config/urls.py) | 이전 공개·내부 API 경로를 Django URL로 등록하고 JSON 404·500 핸들러를 지정한다. |
| [`LLM/src/serving/django_config/asgi.py`](../../LLM/src/serving/django_config/asgi.py) | ASGI 진입점. 첫 HTTP 요청 때 동일 이벤트 루프에서 인덱스 준비 작업을 한 번 시작한다. 준비 중 `/rag/ready`는 `index_ready=false`일 수 있다. |
| [`LLM/src/serving/django_views.py`](../../LLM/src/serving/django_views.py) | HTTP 메서드, JSON 본문, Pydantic 검증, 멀티파트 영수증 업로드, 응답 직렬화, 공통 JSON 오류를 처리한다. 기존 RAG 함수를 호출한다. |
| [`LLM/src/serving/rag_routes.py`](../../LLM/src/serving/rag_routes.py) | FastAPI 라우터 데코레이터·`Depends`·`UploadFile`을 제거하고 프레임워크와 무관한 비동기 처리 함수 및 `RagRuntime`으로 유지했다. |
| [`LLM/src/serving/errors.py`](../../LLM/src/serving/errors.py) | FastAPI 예외 대신 `ApiError`와 오류 응답 형식을 제공한다. 모델 공급자 연결 실패·시간 초과·속도 제한도 해당 형식으로 변환한다. |
| [`LLM/src/serving/api_schema.py`](../../LLM/src/serving/api_schema.py) | Django API의 OpenAPI 3.1 문서를 생성한다. `/openapi.json`과 `/docs`가 복구됐다. `/docs`는 오프라인에서도 경로 표와 JSON 링크를 보여준다. 대화형 Swagger UI 자산은 외부 CDN을 사용한다. |
| [`LLM/main.py`](../../LLM/main.py), [`LLM/manage.py`](../../LLM/manage.py), [`LLM/Dockerfile`](../../LLM/Dockerfile) | 개발 실행, Django 관리 명령, 컨테이너 실행을 Django ASGI 진입점으로 연결한다. Uvicorn은 `--lifespan off`로 실행한다. |
| [`LLM/pyproject.toml`](../../LLM/pyproject.toml), [`LLM/uv.lock`](../../LLM/uv.lock) | Django·`django-cors-headers`를 추가하고 FastAPI·Starlette·`python-multipart`를 제거했다. |
| [`LLM/tests/django_client.py`](../../LLM/tests/django_client.py), [`LLM/tests/test_django_serving.py`](../../LLM/tests/test_django_serving.py) | 기존 API·계약 테스트를 실제 Django URL 경로로 옮기고, 404/405, 문서, CORS, 업로드, 인덱스 준비 등을 검증한다. |
| `LLM/src/serving/app.py` | 이전 FastAPI 애플리케이션 파일을 삭제했다. |

유지되는 주요 공개 경로는 `GET /health`, `GET /rag/ready`, `POST /rag/reindex`, `POST /rag/chat`, `POST /rag/legal-basis`, `POST /rag/deductibility`, `POST /rag/summarize-announcement`, `POST /ocr/receipt`이다. 내부 경로는 `GET /internal/rag/ready`, `POST /internal/rag/index`, `POST /internal/rag/answer`, `POST /internal/rag/recommendations`이다.

이전 검수에서 발견한 **미등록 URL의 HTML 404**와 **잘못된 메서드의 빈 405**는 `{ "error": { "code", "message", "retryable" } }` JSON 응답으로 맞췄다. `405`는 `Allow` 헤더도 반환한다. 요청 검증 실패는 `422`, 잘못된 미디어 타입은 `415`, 과대 영수증 이미지는 `413`을 유지한다.

## 4. 문서와 발표자료

- [`Docs/README.md`](../README.md), [`LLM/README.md`](../../LLM/README.md), [`LLM/RUN_GUIDE.md`](../../LLM/RUN_GUIDE.md)에 Django 실행 명령, `/docs`, `/health`, 첫 요청의 인덱스 준비 동작을 반영했다.
- [`Presentation/slides.md`](../../Presentation/slides.md)의 Backend 기술 표기를 현재 상태인 Django Ninja로 수정했다. 발표자료 표기 변경이며 Backend 코드는 수정하지 않았다.
- 과거 개발 기록의 FastAPI 언급은 당시 상태를 설명하는 이력이라 그대로 남아 있다.

## 5. 검증 기록과 해석

| 검증 | 결과 |
| --- | --- |
| `Backend/.venv/Scripts/python.exe -m unittest discover -s tests -p 'test_*.py' -q` | **42개 통과** (2026-09-22 보고서 작성 시 재실행). Backend 코드 수정에 따른 테스트가 아니라 선행 서비스 연동 확인이다. |
| `LLM/.venv/Scripts/python.exe manage.py check` | Django 시스템 검사 **문제 없음** (보고서 작성 시 재실행) |
| `LLM/.venv/Scripts/python.exe -m pytest tests/test_django_serving.py tests/test_backend_api_contract.py tests/test_health.py -q -p no:cacheprovider` | Django HTTP·계약 테스트 **34개 통과** (보고서 작성 시 재실행) |
| LLM 주요 테스트 전체 실행 (평가용 ML 테스트 4개 제외) | **380개 통과, 8개 실패**. 실패는 저장소에 없는 초기 PDF 20개를 전제로 한 테스트다. |
| 평가용 ML 테스트 4개 포함 전체 수집 | 현재 환경에 `ML` 모듈과 `pandas`가 없어 수집 단계에서 중단된다. 프레임워크 경로 실패는 아니다. |
| 이전 Docker 빌드·실행 확인 | 새 LLM 이미지 빌드 성공. 실행 환경에서 `fastapi: None`, `django: True` 확인. `/docs` 200, 없는 URL 404 JSON, 잘못된 메서드 405 JSON 확인. |
| 이전 실서비스 연동 확인 | LLM `/rag/ready`에서 `index_ready=true`, 12,613개 청크. Backend `/health`에서 `ragReady=true`. 프론트 프록시의 공고 API 200. 실제 `/rag/chat` 요청은 HTTP 200으로 처리됐고 답변 상태는 `insufficient_evidence`였다. |

8개 실패는 `test_document_indexing.py` 2개, `test_index_cache.py` 1개, `test_pdf_loader.py` 2개, `test_rag_api.py` 3개다. 모두 초기 `RAG_data` PDF를 직접 읽거나 해당 PDF로 만든 인덱스에 근거가 있다고 가정한다. 수집 단계에서 막힌 4개는 `test_judge_ml_pipeline.py`, `test_judge_text_features.py`, `test_tfidf_judge_experiment.py`, `test_tune_judge_models.py`다. 전체 테스트 수치는 이 네 파일을 제외한 실행 결과이며, 운영 PostgreSQL 인덱스 성능이나 답변 정확도를 평가한 수치는 아니다.

**현재 로컬 상태:** 보고서 작성 시점에는 `localhost:8000`과 `localhost:8001`에 접속할 수 없었다. 따라서 위 Docker·HTTP 확인은 전환 직후 실행했을 때의 기록이며, 현재 컨테이너가 계속 실행 중이라는 주장은 아니다. 재확인하려면 저장소 루트에서 `docker compose ps -a`, `docker compose up -d --build`, `http://localhost:8000/health`, `http://localhost:8001/rag/ready` 순으로 확인한다.

## 6. 남겨 둔 이전 PDF mock 경로

[`LLM/src/data/document_catalog.py`](../../LLM/src/data/document_catalog.py)와 `in_memory` 검색 경로에는 초기 `RAG_data` PDF catalog 처리가 남아 있다. **현재 Compose는 `VECTOR_STORE_BACKEND=postgres`로 고정**되어 운영 인덱스는 PostgreSQL의 정책·공고·세법 원천 데이터에서 준비된다. 초기 PDF 20개는 저장소에 없으며 운영 그래프의 입력이 아니다.

2026-09-22 후속 정리에서 저장소에 없는 초기 PDF 20개를 전제로 한 테스트를 제거했다. 이전에 실패하던 테스트는 8개였고, 같은 원본 PDF에 의존하던 캐시 테스트도 함께 제거했다. `test_index_cache.py`는 전체가 해당 PDF에 의존하여 삭제했고, `test_document_indexing.py`, `test_pdf_loader.py`, `test_rag_api.py`에서는 해당 테스트만 제거했다. 임시 파일로 PDF 처리의 오류 경로를 확인하는 테스트와 PostgreSQL 운영 검색 코드는 유지했다. 과거의 테스트 실패 기록은 위 5절에 당시 검증 결과로 남아 있다.

## 7. 다음 작업자가 주의할 점

1. 새 HTTP 기능은 Backend에서는 Django Ninja 라우터, LLM에서는 Django URL·뷰에 등록한다. 삭제된 `LLM/src/serving/app.py`나 FastAPI 데코레이터를 다시 사용하지 않는다.
2. LLM 요청·응답 경로를 추가하면 `LLM/src/serving/django_config/urls.py`와 `LLM/src/serving/api_schema.py`를 함께 갱신하고 Django 계약 테스트를 추가한다.
3. LLM `/health` 200은 프로세스 생존 신호이고, RAG 준비 여부는 `/rag/ready`의 `index_ready`로 판단한다. 첫 요청의 백그라운드 준비 중에는 잠시 `false`일 수 있다.
4. 초기 PDF 20개를 전제로 한 테스트는 제거했다. `in_memory` 개발 경로는 운영 Compose의 `postgres` 경로와 분리되어 있으며 이번 정리에서 운영 검색 코드는 수정하지 않았다.
5. 새 환경의 Elasticsearch 초기 적재와 alias·문서 수 확인 절차는 [`LLM/RUN_GUIDE.md` 5절](../../LLM/RUN_GUIDE.md#5-검색기-준비)을 따른다. 이후 서빙·재색인 문제 4건의 원인, 수정 결과와 제한은 [별도 보고서](ELASTICSEARCH_SERVING_CONSISTENCY_FIX_REPORT_20260922.md)에 정리했다.

후속 검증: PDF 처리·RAG API·Elasticsearch 색인 관련 테스트 35개 통과, Django HTTP 테스트 8개 통과(각각 별도 실행). 두 묶음을 한 프로세스에서 연속 실행하면 기존 전역 RAG 런타임 상태가 남아 `test_health_ready_and_cors`가 실패하는 테스트 격리 문제가 확인되었다. 이번 정리는 운영 런타임 코드를 변경하지 않았다.

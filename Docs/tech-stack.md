# 기술 스택
Docker Compose 기반의 컨테이너형 서비스로 구성한다.
각 서비스의 역할 및 통신 구조는 `Docs/Design/ARCHITECTURE.md`를 참고한다.

## Backend
* **Language:** Python 3.13
* **Framework:** Django + Django Ninja (ASGI, uvicorn). ORM은 쓰지 않고 raw SQL(`Backend/core/repo.py`)
* **Architecture:** Controller–Service–Model
* **Directory:** `Backend/api`, `Backend/services`, `Backend/schemas`
* **Communication:** REST API

## LLM
* **Language:** Python 3.13
* **Framework:** LangChain + LangGraph
* **LLM Model:** OpenAI. `LLM/src/models/factory.py`가 `ChatOpenAI`(temperature 0)와 `OpenAIEmbeddings`만 생성하며, 모델명은 `LLM_MODEL`·`EMBEDDING_MODEL` 환경변수로 주입
* **RAG:** LangGraph 그래프로 질문을 policy·notice·tax(범위 밖은 `out_of_scope`) 경로에 배분하고 `category=roadmap`은 전용 코치 노드로 처리. tax는 근거가 충분해질 때까지 검색·재질의를 반복하는 멀티홉(`TAX_MAX_HOPS`, 기본 3)
* **Semantic Cache:** 세금 질문의 검색 근거와 근거 판정을 PostgreSQL `tax_rag_cache`에 저장해 유사 질문에 재사용(`LLM/src/rag/tax_cache.py`, `TAX_CACHE_ENABLED` 기본 true)
* **검색:** dense(pgvector) + BM25를 RRF로 융합하는 hybrid가 기본. Postgres 모드의 BM25는 Elasticsearch 9 + Nori 형태소 분석기(`LLM/src/vectorstores/nori_hybrid.py`, `elasticsearch/Dockerfile`), in-memory 모드는 메모리 BM25. `RETRIEVAL_MODE=dense`는 정책 추천(`/internal/rag/recommendations`)에만 적용되고 그래프 경로는 항상 hybrid
* **Rerank:** Cohere. 기본 모델 `rerank-v4.0-fast`. 실패하면 RRF 순서로 폴백
* **Guardrail:** 범위 밖 질문 차단, 근거 없는 생성·인용 검증
* **OCR / Vision:** Tesseract OCR(`kor+eng`, LLM 이미지에 `tesseract-ocr-kor` 설치, `LLM/src/features/receipt_ocr.py`)로 글자를 읽고 LLM이 필드를 정리. Tesseract 실패·글자 부족 시 OpenAI Vision으로 대체. 지출관리 화면(`ExpenseTracker.jsx`)이 `POST /expenses/receipts`로 호출
* **사업계획서 문서 처리:** 제출 양식(PDF·HWPX) 검사와 PDF·HWPX 출력(`LLM/src/features/business_plan_documents.py`)
* **스트리밍:** 채팅 답변을 NDJSON으로 흘려보내는 `/rag/chat/stream`(Backend는 `httpx.AsyncClient`로 중계)
* **Tracing:** LangSmith. 기본 비활성이며 `LANGSMITH_TRACING`으로 켬
* **DB 연결:** `psycopg_pool` 커넥션 풀(1~16). 컴파일된 그래프·LLM·Cohere 클라이언트는 프로세스 안에서 재사용
* **Dependencies:** `LLM/pyproject.toml` 기준으로 관리

세액감면 **Rule Engine은 LLM이 아니라 Backend에 있다**(`Backend/services/tax_service.py`). LLM은 그 판정 결과에 대한 근거 설명·법령 인용만 생성하며 판정값을 바꾸지 않는다. 역할 경계는 `Docs/Design/LLM_API_SPEC_V1.md` 10절 참고.

## Database
* **RDBMS:** PostgreSQL 16 (`pgvector/pgvector:pg16` 이미지)
* **Vector Store:** pgvector (PostgreSQL extension). 키워드 검색 인덱스는 Elasticsearch(아래 Infrastructure). `rag_documents.embedding`은 `VECTOR(1536)`이며 HNSW + `vector_cosine_ops` 인덱스를 둠
* 관계형 데이터와 벡터 데이터 통합 관리
* LLM 세금 질문 Semantic Cache도 같은 DB의 `tax_rag_cache` 테이블(`DB/app_extras.sql`)에 저장
* Backend는 Postgres 전용이다. 기동 시 연결에 실패하면 RuntimeError로 기동을 중단한다

## Frontend
* **Framework:** React 18.3 + Vite 5.4
* **Styling:** `Frontend/src/styles.css`가 `src/styles/*.css` 13개를 순서대로 import. CSS 변수 기반 라이트·다크 토큰과 반응형. **CSS 프레임워크를 쓰지 않는다**
* **Routing:** 라우터 라이브러리 없음. `App.jsx`의 상태로 뷰를 전환(`home` / `page` / `mypage`). `page` 안의 `roadmap` / `tax` / `expenses` / `bizplan` / `gov`는 `pages/SubPage.jsx`가 선택
* **Dependencies:** 런타임 의존성은 `react`·`react-dom`·`exceljs`(지출 엑셀 보고서) 세 개, 빌드 의존성에 `vite-plugin-pwa`(PWA 설치·Service Worker) (`Frontend/package.json`)
* **API 호출:** `Frontend/src/api.js`. 기본 base는 `/api`이고 접두사를 벗겨 Backend로 넘기는 프록시가 앞단에 있음. 개발에서는 Vite(`vite.config.js`), 배포에서는 nginx(`Frontend/nginx.conf`, AWS는 HTTPS용 `nginx.https.conf`)가 같은 일을 함. `useApi`로 부르는 일부 GET만 실패 시 목데이터로 폴백하고, 로그인·AI 상담·추천 등 나머지는 오류를 안내

## Infrastructure
* **Container:** Docker
* **Orchestration:** Docker Compose
* **Services (`docker-compose.yml`):** `backend`(:8000), `llm`(:8001), `db`(:5432), `db-migrate`(스키마 적용 one-shot), `elasticsearch`(:9200, Nori), 그리고 프로필 서비스 `frontend`(:80, `frontend` 프로필)·`presentation`(발표자료, `presentation` 프로필). 로컬 개발은 호스트 Vite(:5173) 또는 `docker-compose.dev.yml`의 `frontend-dev`
* **AWS:** App EC2(`docker-compose.app.yml`: backend·llm·frontend nginx :80/:443·presentation, `run --rm` 전용 `db-migrate`·`collector`)와 Data EC2(`docker-compose.data.yml`: db·elasticsearch). 절차는 `Docs/AWS_DEPLOY_GUIDE.md`
* **CI/CD:** GitHub Actions. `deploy.yml`(PR·main 테스트 → main 병합 시 App EC2 배포), `collect.yml`(주간 수집 → 재색인), `collect-retry.yml`(3시간마다 일시 장애 재시도)
* **Network:** Docker 내부 네트워크 기반 서비스 간 통신
* **API Communication:** REST API
* 예: Backend → LLM `http://llm:8001/...`
* **로컬 실행:** `setup.sh`(bash) / `setup.bat`(cmd.exe)이 `.env` 검사부터 빌드·기동·헬스체크·Frontend 실행까지 처리. `.env`는 스크립트가 만들지 않으며 팀에서 받아 루트에 둔다
* **요구 버전:** Docker Compose v2.1.1 이상. 기동 대기를 `compose up --wait`와 `curl --retry`에 맡긴다

## Dependency & Environment Management
* **Python Version:** 3.13 (Backend·LLM). DB 수집 스크립트는 3.12(`DB/.python-version`)
* **Package Manager:** uv
* Python 프로젝트의 의존성 및 가상환경을 `uv`로 관리
* 프로젝트별 `pyproject.toml` 및 `uv.lock`을 통해 의존성 버전을 고정

## Test
* **LLM:** pytest. `LLM/tests/` 아래 테스트 파일 46개(테스트 함수 412개, 2026-10-01 기준). `ML` 패키지를 import하는 judge 실험 테스트 4개는 수집 실패하므로 제외하고 실행(`LLM/README.md` 테스트 절). `LLM/pyproject.toml`의 `testpaths = ["tests"]`
* **Backend:** 표준 `unittest`. `Backend/tests/` 아래 16개 파일(테스트 함수 134개). `uv run python -m unittest discover tests`. CI(`deploy.yml`)에서 실행
* **Frontend:** Node 내장 테스트 러너. `Frontend/tests/*.test.mjs` 2개 파일, `node --test "tests/*.test.mjs"`. CI에서 `npm run build`와 함께 실행
* **Lint / Formatter:** 설정된 것 없음

## Version Control
* **Git:** 소스 코드 버전 관리
* **GitHub:** 원격 저장소 및 협업 관리
* **Branch Strategy:** `main` / `develop` / `feature/*`

## 관련 문서
* **시스템 구성:** `Docs/Design/ARCHITECTURE.md`
* **데이터 구조:** `Docs/Design/ERD.md`

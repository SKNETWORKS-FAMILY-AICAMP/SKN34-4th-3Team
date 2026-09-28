# Elasticsearch 서빙·재색인 일관성 수정 보고서

- 작성일: 2026-09-22
- 범위: LLM의 PostgreSQL Dense + Elasticsearch Nori BM25 검색, 준비 상태, 재색인 경로
- 실행 절차: [`LLM/RUN_GUIDE.md` 5절](../../LLM/RUN_GUIDE.md#5-검색기-준비)

## 1. 결론과 적용 범위

개발 환경에서 진행한 Elasticsearch 성능 평가가 잘못된 것은 아니다. 당시에는 PostgreSQL 원본 10,892건을 Elasticsearch에 적재하고 `rag-documents` alias를 연결한 기록이 있다. 기존 ES 볼륨이 있는 환경에서 정상 검색이 된 것과 새 볼륨에서 초기 색인이 필요한 것은 양립한다. [당시 작업 기록](../../LLM/work_log/WORK_LOG_0920_NORI_RETRIEVAL_HANDOFF.md)과 [성능 비교 보고서](ELASTICSEARCH_REPORT/ELASTICSEARCH_COMPARISON_REPORT.md)는 이미 색인된 환경의 결과다.

이번 수정은 다음 네 지적 중 **2~4번의 서빙 동작을 직접 수정**했고, **1번은 Backend가 사용하는 `/rag/reindex` 경로에서 ES 적재가 실행되도록 연결**했다. LLM만 단독 실행하거나 `/internal/rag/index`만 호출하는 경우에는 ES 전체 적재가 자동으로 수행되지 않는다. 새 환경에서의 수동 명령과 확인 절차는 실행 가이드에 있다.

| 번호 | 기존 문제 | 수정 후 |
| --- | --- | --- |
| 1. ES 색인이 서빙 경로에 연결되지 않음 | ES 재색인 함수는 CLI에서만 호출됐다. pgvector 준비와 `/rag/reindex`가 ES 문서를 만들지 않았다. | `/rag/reindex`가 pgvector 갱신 뒤 ES 전체 재색인을 호출한다. Backend는 `/rag/ready=false`일 때 기존 워밍업 절차에서 `/rag/reindex`를 요청한다. LLM 단독 실행의 명시적 적재 명령은 실행 가이드에 둔다. |
| 2. ES 장애 시 Dense 근거 소실 | Dense 검색 성공 후 ES 검색이 예외를 던지면 전체 검색이 실패했다. 정책 그래프는 `retrieval_error`로 종료할 수 있었고 세금 API는 5xx가 될 수 있었다. | ES 연결·API 오류 또는 해당 프로세스가 감지한 재색인 불일치 시 ES 결과를 제외하고 Dense 결과로 계속 검색한다. 오류는 LLM 서버 로그에 남긴다. |
| 3. 준비 상태가 ES를 무시 | `/rag/ready`의 `index_ready`는 프로세스의 pgvector 검색기만 확인했다. | PostgreSQL 운영 경로에서는 ES alias 존재, 문서 수 1건 이상, 해당 프로세스의 재색인 성공 상태까지 확인한다. ES가 응답하지 않으면 `false`다. |
| 4. 부분 재색인의 불일치 | `documentIds`가 지정되면 `rag_documents`의 해당 행만 다시 임베딩했고 ES는 갱신하지 않았다. | 선택한 행을 처리한 뒤 DB 원본 기준 pgvector 전체 동기화와 ES 전체 재색인을 실행한다. ES 갱신이 실패하면 API가 오류를 반환하고 해당 프로세스는 이전 ES 결과를 검색에 사용하지 않는다. |

## 2. 요청별 실행 흐름

### 처음 컨테이너를 실행할 때

Compose는 `elasticsearch_data` 볼륨을 생성하지만, 빈 볼륨에 인덱스나 alias를 복사하지 않는다. ES 클러스터 healthcheck는 서버 응답만 보므로 문서가 없어도 통과한다. LLM의 첫 HTTP 요청에서 시작하는 ASGI 워밍업과 `/internal/rag/index`는 pgvector를 준비한다. 그 상태에서 `/rag/ready`는 ES alias와 문서가 없음을 확인해 `index_ready=false`를 반환한다. Backend가 함께 실행 중이면 기존 워밍업이 `/rag/reindex`를 호출하고, 이 경로가 PostgreSQL 원본으로 pgvector와 ES를 갱신한다.

Backend가 없거나 ES 적재를 별도로 실행해야 할 때는 [`LLM/RUN_GUIDE.md`의 명령](../../LLM/RUN_GUIDE.md#elasticsearch-최초-적재-및-확인)을 따른다. **PostgreSQL 연결과 정책·공고·세법 원본 데이터가 준비된 상태**가 전제다. 원본 문서가 0건이면 ES 적재 함수는 실패한다.

### 검색 중 ES가 실패할 때

[`NoriHybridSearch.search_stages()`](../../LLM/src/vectorstores/nori_hybrid.py)은 Dense 검색 뒤 ES를 조회한다. ES가 `ApiError` 또는 `TransportError`를 내면 오류와 traceback을 LLM 프로세스 로그에 출력하고 해당 요청의 BM25 결과를 비운다. 정책 그래프는 빈 결과 목록을 RRF의 분모에 넣지 않아 Dense 근거를 유지한다. 세금 근거 검색도 같은 검색기를 사용하므로 해당 ES 오류 때문에 Dense 근거를 잃지 않는다.

이는 **오류 시 자동 재색인**이 아니다. 해당 요청에서 Dense 검색으로 계속 진행하는 동작이다. 사용자 화면이나 정상 API 응답에 Elasticsearch traceback을 노출하지 않는다. 사용자는 Dense 근거만으로 만들어진 답변 또는 근거가 부족할 때의 일반 응답을 받을 수 있다. 운영자는 `docker compose logs --tail=100 llm`에서 로그를 확인한다. 별도의 로그 파일이나 DB 저장 기능은 추가하지 않았다.

### `/rag/ready`와 재색인

[`ready()`](../../LLM/src/serving/rag_routes.py)은 pgvector 검색기가 준비돼 있고, 해당 프로세스가 ES 재색인 실패 상태가 아니며, ES `rag-documents` alias에 문서가 있을 때 `index_ready=true`를 반환한다. Backend의 `ragReady`도 이 값을 따른다. 검색 API는 ES가 일시적으로 실패하면 Dense로 계속 시도하므로 **`index_ready=false`와 Dense fallback은 동시에 가능**하다. `ready`는 구성 요소의 정상 상태를 나타내고 fallback은 사용자 요청의 근거를 보존한다.

`POST /rag/reindex`는 전체 요청과 `documentIds` 요청 모두 ES 전체 재색인을 수행한다. 이 요청이 들어오기 전의 개별 검색 오류가 재색인을 직접 시작하지는 않는다. Backend가 시작할 때 `index_ready=false`를 보고 `/rag/reindex`를 보내는 경우는 별개다. `/internal/rag/index`는 ES 적재를 하지 않는다.

## 3. `documentIds`, 전체 재색인, 원본 DB의 의미

`documentIds`는 [`rag_documents.id`](../../LLM/src/vectorstores/postgres.py) 값이다. 정책 ID나 ES 문서 ID가 아니다. 예를 들어 `{"documentIds":[9,7]}`은 먼저 `rag_documents`의 9번·7번 청크를 선택한다. 그 뒤 원본 테이블 기준으로 pgvector를 동기화하고 ES를 **전체** 재색인한다. ES 문서는 원본 정책·공고·세법 레코드 단위이고 선택 ID는 pgvector 청크 행 단위라, 두 ID 집합을 같은 것으로 취급할 수 없다.

현재 [Backend 재색인 호출](../../Backend/core/llm_client.py)은 `documentIds: []`를 보낸다. 따라서 특정 ID를 지정하는 경로는 LLM API를 직접 호출할 때에만 사용된다. `force=true`는 pgvector의 기존 청크도 다시 임베딩하도록 하는 값이다. ES 전체 재색인 여부와는 별개다. 부분 요청도 ES 전체 색인을 생성하므로 데이터가 많으면 실행 시간과 자원을 사용한다.

원본 테이블 `policies`, `announcements`, `tax_documents`에는 `SELECT`만 수행한다. PostgreSQL에서 변경되는 것은 검색용 파생 테이블 `rag_documents`의 청크·임베딩이며, 동기화 과정에서 사라진 청크가 정리될 수 있다. Elasticsearch에서는 새 물리 인덱스에 전체 문서를 적재한 다음 `rag-documents` alias를 전환한다. 적재 실패 시 기존 alias를 새 인덱스로 옮기지 않는다. 원본 정책·공고·세법 행을 수정하는 작업은 아니다.

## 4. 수정 파일과 검증

| 파일 | 변경 내용 |
| --- | --- |
| [`LLM/src/vectorstores/nori_hybrid.py`](../../LLM/src/vectorstores/nori_hybrid.py) | ES 연결·API 오류 시 Dense 결과 유지, 재색인 실패 상태에서 ES 검색 건너뜀 |
| [`LLM/src/rag/graph.py`](../../LLM/src/rag/graph.py) | 빈 검색 결과를 RRF 순위 목록에서 제외해 Dense 근거 점수 유지 |
| [`LLM/src/serving/rag_routes.py`](../../LLM/src/serving/rag_routes.py) | ES 준비 상태 확인, `/rag/reindex`의 pgvector·ES 동기화, 실패 상태 관리 |
| [`LLM/tests/test_nori_hybrid_live.py`](../../LLM/tests/test_nori_hybrid_live.py), [`LLM/tests/test_rag_api.py`](../../LLM/tests/test_rag_api.py) | ES 장애 시 Dense fallback, 준비 상태, 부분·전체 재색인 및 실패 경로 검증 |
| [`LLM/RUN_GUIDE.md`](../../LLM/RUN_GUIDE.md) | 통합 환경 명령과 변경된 운영 동작 안내 |

LLM의 Nori 검색·RAG API·Django HTTP·정책/세금 그래프·계약·ES 색인 관련 테스트 **183개 통과**와 `python manage.py check` 통과를 확인했다. 마지막 추가 정책 그래프 fallback 테스트는 대상 파일 단독 실행 **10개 통과**로 확인했다. `git diff --check`도 통과했다. 이 수치는 외부 PostgreSQL·Elasticsearch를 띄운 통합 시험 결과가 아니다. 현재 환경에서는 Docker 데몬에 연결할 수 없어 실제 컨테이너에서의 초기 적재와 장애 전환을 재현하지 못했다.

## 5. 남아 있는 제한

- `/rag/ready`는 ES alias의 존재와 문서 수를 확인한다. ES 내용이 DB 원본과 완전히 같은지까지 매 요청마다 대조하지 않는다. DB 원본을 외부 작업자가 변경했다면 `/rag/reindex` 또는 실행 가이드의 ES 적재 명령을 실행해야 한다.
- pgvector와 ES는 별도 저장소라 하나의 DB 트랜잭션으로 함께 커밋할 수 없다. 재색인 도중 실패하면 API가 오류를 반환하고 **그 LLM 프로세스**는 ES 검색을 비활성화하지만, 다른 프로세스나 재시작 이후까지 이 메모리 상태가 영구 공유되지는 않는다. 실패 후 ES 상태를 확인하고 `/rag/reindex`를 다시 실행해야 한다.
- ES 연결 오류 시 Dense fallback은 답변 경로를 보존한다. ES가 제공하던 어휘 검색 근거와 검색 품질을 그대로 보장하지는 않는다. 정확도는 별도 통합 평가가 필요하다.

## 6. 후속 수정: Elasticsearch 인덱스 디스크 누적 방지

기존 전체 ES 재색인은 매번 새 물리 인덱스를 만들고 alias만 이전했다. 이전 물리 인덱스는 남았으며, `/rag/reindex`의 부분 요청도 ES 전체 색인을 만들게 바뀐 뒤에는 호출 횟수에 따라 디스크 사용량이 더 빨리 늘 수 있었다.

후속 수정에서 [`elasticsearch_indexing.py`](../../LLM/src/features/elasticsearch_indexing.py)는 새 인덱스 적재와 alias 전환이 성공한 **다음** 직전 alias 대상을 삭제한다. 새 색인을 만들기 전과 전환한 뒤에는 이 함수가 생성한 `rag-documents-nori-v3-xsv-xsa-<시각>` 형식의 미사용 인덱스 중 하루 이상 지난 것도 정리한다. 현재 검색 alias 대상, 다른 alias가 붙은 인덱스, 이름 규칙이 다른 인덱스는 건드리지 않는다. 최근에 생성됐지만 alias가 없는 인덱스는 진행 중인 별도 색인일 수 있어 하루 동안 보존한다.

ES 적재 또는 alias 전환이 실패하면 기존 alias 대상을 삭제하지 않고, 실패한 신규 인덱스만 삭제한다. alias 전환에 성공했지만 옛 인덱스 삭제가 실패하면 새 색인 성공을 실패로 바꾸지 않고 LLM 로그에 남긴다. 이 경우 디스크 공간을 확보한 뒤 다음 재색인에서 다시 정리를 시도하거나 운영자가 ES 인덱스 상태를 확인해야 한다. 이미 디스크가 꽉 차 새 인덱스를 만들 수 없는 경우에도 재색인 전 오래된 미사용 인덱스를 먼저 정리하도록 했다. 이전 Nori 버전 또는 다른 서비스 인덱스는 자동 삭제 대상이 아니다.

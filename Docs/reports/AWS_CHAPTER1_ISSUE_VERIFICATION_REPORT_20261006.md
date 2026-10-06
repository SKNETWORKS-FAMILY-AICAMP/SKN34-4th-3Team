# AWS 챕터 1 운영 검증 결과 보고서

작성일: 2026-10-06  
대상: 챕터 1 운영 검증 — ID 3 → ID 4 → ID 1 → ID 2  
기준 문서: `AWS_CHAPTER1_OPERATIONAL_VERIFICATION_20261006.md`

---

## 1. 최종 요약

이번 검증에서는 `develop → main` 병합 이후 실제 GitHub Actions 배포와 App EC2 운영 상태, LLM 메모리 한도, 재색인 중 RAG 가용성, 수집 작업 직렬화, Data EC2 백업/복원 가능성을 확인했다.

현재 상태는 다음과 같다.

| 항목 | 상태 | 요약 |
|---|---|---|
| main 배포 | 완료 | main push 후 테스트, 이미지 빌드, deploy 성공 |
| ID 1 — App EC2 메모리/OOM | 완료 | 상담/OCR/수집/재색인 부하에서 OOM·재시작 없음 |
| ID 2 — 재색인 중 기존 RAG 유지 | 핵심 경로 완료 | 재색인 중 `index_ready=true` 유지, 실제 상담 정상 |
| ID 3 — 운영 작업 직렬화 | 부분 완료 | 수집 + 재시도 직렬화와 서버 lock 확인. deploy/PR 동시성은 이번 세션에서 별도 재현하지 않음 |
| ID 4 — 백업/복원 | 부분 완료 | 수동 백업·freshness·S3 다운로드·실제 복원·내용 확인 완료. cron 자동 실행은 다음 예정 시각 후 확인 필요 |
| SNS 실패 알림 | 제외 | 운영 요구사항에서 제외하기로 결정 |

따라서 **챕터 1 운영 검증은 대부분 완료되었으나, 최종 완료 처리 전 `cron 자동 실행 확인`이 남아 있다.** 또한 원 기준 문서의 ID 3 전체 시나리오를 엄격히 충족하려면 수집 중 deploy 대기와 PR 테스트 독립 실행도 별도로 확인해야 한다.

---

## 2. main 병합 및 자동 배포 검증

### 2.1 main PR

main 대상 PR에서 다음 상태를 확인했다.

- Backend/Frontend 테스트 성공
- PR 단계의 `build-images`는 Skipped
- PR 단계의 `deploy`는 Skipped
- 전체 required check 통과

이후 main에 병합했다.

### 2.2 main push Actions

main 병합 후 workflow에서 다음을 확인했다.

- test 성공
- Backend 이미지 빌드 성공
- Frontend 이미지 빌드 성공
- LLM 이미지 빌드 성공
- Presentation 이미지 빌드 성공
- 최초 deploy는 `LLM_MEM_LIMIT` 미설정으로 실패

실패 로그:

```text
error while interpolating services.llm.mem_limit:
required variable LLM_MEM_LIMIT is missing a value
```

App EC2의 현재 사용량을 기준으로 초기 운영 검증값을 다음과 같이 설정했다.

```env
LLM_MEM_LIMIT=2560m
```

설정 후 deploy를 재실행했고 정상 성공했다.

---

## 3. 실제 배포 상태 확인

최종 배포 SHA:

```text
645eb09a811b7803f85db3cc4d6238a541bf7ff0
```

App EC2에서 `git rev-parse HEAD` 결과와 backend/frontend/llm 실행 이미지 태그가 모두 동일한 SHA임을 확인했다.

컨테이너 상태:

- backend: healthy
- llm: healthy
- frontend: running

LLM 컨테이너 inspect 결과:

```text
limit=2684354560
oom=false
restarts=0
```

`2684354560 bytes`는 설정한 `2560m`과 일치한다.

Backend `/health` 응답 핵심 값:

```json
{
  "status": "ok",
  "postgres": "connected",
  "pgvector": "ready",
  "ragChunks": 18481,
  "policies": 3756,
  "llm": "connected",
  "ragReady": true
}
```

따라서 배포 SHA, 컨테이너 기동, 메모리 제한, DB/LLM/RAG 준비 상태를 모두 확인했다.

---

## 4. ID 1 — App EC2 메모리/OOM 검증

LLM 메모리 한도는 `2560m`으로 설정했다.

실제 기능 사용 중 관찰한 LLM 메모리 최대 사용률은 다음과 같다.

| 작업 | LLM 최대 메모리 사용률 |
|---|---:|
| 일반 정책/세무 상담 | 약 65% |
| OCR | 약 70% |
| 수집 | 약 74% |
| 재색인 | 약 85% |

가장 높은 값은 재색인 중 약 85%였다. 한도 초과 및 컨테이너 종료는 발생하지 않았다.

부하 검증 종료 후 다음을 확인했다.

```text
oom=false
restarts=0
```

커널 OOM 로그 조회에서도 관련 기록이 발견되지 않았다.

### ID 1 판정

**완료**

확인된 사항:

- LLM 메모리 제한 실제 적용
- 상담/OCR/수집/재색인 실제 처리 성공
- OOM 없음
- 예기치 않은 LLM 재시작 없음
- 최대 관찰 사용률 약 85%

주의: 이번 세션에서 개별 작업별 `free`/`vmstat` 원시 로그를 별도 보관하지는 않았으므로, 장기적인 host memory/swap 추이는 별도 모니터링 항목으로 남길 수 있다.

---

## 5. ID 2 — 재색인 중 기존 RAG 검색 유지

재색인 시작 전 `/rag/ready` 결과:

```json
{
  "status": "ready",
  "index_ready": true,
  "llm_configured": true,
  "embedding_configured": true,
  "langsmith_tracing": true,
  "document_count": 14550,
  "chunk_count": 18481,
  "index_source": "cache"
}
```

재색인 중 다음을 확인했다.

- `index_ready=true` 유지
- 재색인 진행 중 실제 정책/세무 상담 정상
- 근거/출처 정상 표시
- 503 또는 RAG 미준비 오류 없음
- 재색인 중 LLM 최대 메모리 약 85%

### ID 2 판정

**핵심 성공 경로 완료**

이번 운영 세션에서 별도로 확인하지 않은 항목:

- 신규/변경 문서가 실제 검색 결과에 반영되었는지에 대한 별도 표본 증거
- 운영 환경에서 의도적으로 재색인 실패를 유발하는 실패 경로

실패 경로는 기준 문서상 로컬 회귀 테스트 범위로 구분되어 있으며, 운영 DB를 중지하거나 삭제하는 방식의 실패 유도는 수행하지 않았다.

---

## 6. ID 3 — 배포·수집 작업 직렬화 및 서버 잠금

### 6.1 collect-data 수동 실행

GitHub Actions에서 `collect-data`를 수동 실행했다.

- 실행 시간: 약 3분 27초
- 결과: 성공
- 수집 중 LLM 메모리 최대 약 74%

### 6.2 App EC2 lock 확인

수집이 실제 서버 작업 중일 때:

```bash
flock -n "$HOME/.ec2-app.lock" -c 'echo lock-free'
echo "lock check exit=$?"
```

결과:

```text
lock check exit=1
```

따라서 수집 중 공통 lock이 실제로 잡혀 있음을 확인했다.

모든 운영 작업 종료 후 동일 명령 결과:

```text
lock-free
lock check exit=0
```

따라서 작업 종료 후 lock이 정상 해제됨도 확인했다.

### 6.3 collect-data-retry 직렬화

`collect-data` 실행 중 `collect-data-retry`를 추가 실행했다.

확인 결과:

- 기존 `collect-data`는 취소되지 않고 계속 실행
- 후속 `collect-data-retry`는 Queued 상태로 대기
- 첫 작업 종료 후 retry가 실제 실행
- 재시도 대상이 없어 정상 성공 종료

### ID 3 판정

**부분 완료**

이번 세션에서 확인한 핵심 항목:

- 새 작업 요청으로 기존 수집이 Canceled되지 않음
- 후속 운영 작업이 대기 후 실행
- 서버 공통 lock 동작

원 기준 문서의 전체 시나리오 중 이번 세션에서 동시 재현하지 않은 항목:

- 수집 실행 중 main deploy job이 대기 후 실행되는지
- 수집 실행 중 신규 PR test가 운영 concurrency와 무관하게 독립 실행되는지

따라서 운영 작업 직렬화의 핵심 동작은 검증했으나, ID 3 전체 완료 기준을 엄격히 적용한다면 위 2개 항목은 추가 증거가 필요하다.

---

## 7. ID 4 — Data EC2 백업 및 복원 검증

### 7.1 접속 이슈 정리

검증 중 Data EC2의 프라이빗 주소 변경으로 인해 초기 일부 명령이 App EC2에서 실행되었다.

App EC2에서 확인된 다음 결과는 Data 검증 증거에서 제외했다.

- `BACKUP_BUCKET=MISSING`
- `aws sts get-caller-identity → NoCredentials`
- Data 컨테이너 미실행처럼 보였던 결과

이후 변경된 Data EC2 주소로 정상 접속한 뒤 재검증했다.

### 7.2 AWS CLI 및 IAM

Data EC2에서 다음을 확인했다.

- AWS CLI 설치 정상
- IAM Role: `startup-on-data-role`
- STS 호출 성공
- S3 백업 버킷 접근 권한 정책 존재

SNS는 운영 요구사항에서 제외하기로 결정하여 설정하지 않았다.

### 7.3 제한 PATH 수동 백업

최초 제한 환경 실행에서는 Data EC2의 `backup_db.sh`가 최신 코드가 아니어서 `/snap/bin/aws`를 찾지 못했다.

Data EC2에 최신 main을 반영한 뒤 재실행했다.

```bash
env -i HOME="$HOME" PATH=/usr/bin:/bin bash scripts/backup_db.sh
echo "backup exit=$?"
```

최종 결과:

```text
backup exit=0
```

따라서 cron과 유사한 제한 환경에서도 백업 성공을 확인했다.

### 7.4 freshness

```bash
bash scripts/backup_db.sh --check-freshness
echo "freshness exit=$?"
```

정상 출력 및 `freshness exit=0`을 확인했다.

### 7.5 S3 백업 파일 다운로드

검증 대상 백업:

```text
daily/startup_platform_20261006_063645.dump
```

S3에서 테스트용 임시 디렉터리로 다운로드했다.

- 다운로드 성공
- 파일 크기: 약 133MB

### 7.6 실제 복원

운영 DB와 분리된 임시 `pgvector/pgvector:pg16` 컨테이너를 생성하고 `ch1_verify` DB를 생성했다.

다음 옵션으로 실제 복원했다.

```text
pg_restore --exit-on-error --no-owner --no-privileges
```

결과:

```text
restore exit=0
```

이후 복원된 테이블, 행 수, 실제 데이터 내용을 확인했고 정상임을 확인했다.

### 7.7 cron

수동 검증을 수행한 시점에는 당일 cron 예정 시각이 이미 지나 있었으므로 자동 실행 여부는 같은 날 확인할 수 없었다.

다음 예정 실행 이후 아래 두 가지를 확인한다.

```bash
tail -n 50 ~/backup_db.log
aws s3 ls "s3://startup-on-fifo-backup/daily/" | tail
```

완료 기준:

- 예정 시각 이후 `backup verified` 로그 존재
- 동일 시각대 신규 S3 dump 생성
- freshness cron 로그 정상

### ID 4 판정

**부분 완료 — cron 확인 대기**

완료:

- 제한 PATH 수동 백업
- freshness
- S3 업로드 결과 다운로드
- 별도 DB 실제 복원
- 복원 데이터 확인

남음:

- cron 자동 실행 확인

제외:

- SNS 실패 알림은 운영 요구사항에서 제외하기로 결정

---

## 8. 검증 중 발견된 문제 및 조치

| 문제 | 원인 | 조치 | 결과 |
|---|---|---|---|
| 첫 main deploy 실패 | `LLM_MEM_LIMIT` 미설정 | App `.env`에 `LLM_MEM_LIMIT=2560m` 설정 | deploy 성공 |
| Data 검증 중 App EC2 결과 혼입 | Data EC2 프라이빗 주소 변경 | 실제 Data EC2 주소로 재접속 | Data 기준 재검증 |
| 제한 PATH 백업에서 `aws: command not found` | Data EC2의 `backup_db.sh`가 최신 main 미반영 | 최신 main 반영 | `backup exit=0` |
| SNS 미설정 | 운영 요구사항에서 제외 결정 | 추가 구성하지 않음 | 문서상 예외로 기록 |

---

## 9. 최종 상태

| ID | 현재 판정 | 남은 항목 |
|---|---|---|
| ID 1 | 완료 | 없음 |
| ID 2 | 핵심 성공 경로 완료 | 변경 문서 반영 표본/운영 실패 경로는 별도 증거 없음 |
| ID 3 | 부분 완료 | deploy 대기 및 PR test 독립 실행 동시 시나리오 미재현 |
| ID 4 | 부분 완료 | cron 자동 실행 확인 |

### 전체 판정

**운영 핵심 기능 검증은 대부분 완료되었고, 즉시 해결이 필요한 장애는 확인되지 않았다.**

최종 종료 조건은 다음과 같다.

1. 다음 cron 예정 실행 후 자동 백업 파일과 로그 확인
2. 필요 시 ID 3의 미실시 동시성 시나리오(deploy/PR)를 추가 확인
3. SNS 알림 제외 결정을 운영 문서의 완료 기준에도 반영

이 3가지를 정리하면 챕터 1 운영 검증을 최종 완료 상태로 전환할 수 있다.

---

## 10. 다음 확인용 명령

cron 실행 이후 Data EC2에서:

```bash
tail -n 50 ~/backup_db.log
aws s3 ls "s3://startup-on-fifo-backup/daily/" | tail
```

자동 백업 파일과 `backup verified` 로그가 예정 시각 이후 생성되었으면 ID 4의 남은 cron 항목을 완료 처리한다.

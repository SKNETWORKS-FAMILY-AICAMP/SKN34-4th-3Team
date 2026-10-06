ALTER TABLE users ADD COLUMN IF NOT EXISTS phone VARCHAR(20);
ALTER TABLE users ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'active';

ALTER TABLE calendar_events ADD COLUMN IF NOT EXISTS user_id INT REFERENCES users(id);

ALTER TABLE reminders ADD COLUMN IF NOT EXISTS dispatched BOOLEAN DEFAULT false;

ALTER TABLE expenses ADD COLUMN IF NOT EXISTS user_id INT REFERENCES users(id);

-- 영수증 경비 인정 판정: 증빙 유형(세금계산서/카드전표/현금영수증/간이영수증), 적격 여부, 3단계 판정, 빠진 정보
ALTER TABLE receipt_extractions ADD COLUMN IF NOT EXISTS proof_type VARCHAR(30);
ALTER TABLE expenses ADD COLUMN IF NOT EXISTS deductible_tier VARCHAR(20);
ALTER TABLE expenses ADD COLUMN IF NOT EXISTS proof_valid BOOLEAN;
ALTER TABLE expenses ADD COLUMN IF NOT EXISTS missing_fields TEXT;

-- OCR이 실제로 읽은 항목(기본값으로 채운 것과 구분)과 영수증 원문 근거. JSON 문자열.
ALTER TABLE receipt_extractions ADD COLUMN IF NOT EXISTS read_meta TEXT;

-- 올린 영수증 원본 이미지를 나중에 다시 볼 수 있게 저장한다.
ALTER TABLE receipts ADD COLUMN IF NOT EXISTS image_data BYTEA;
ALTER TABLE receipts ADD COLUMN IF NOT EXISTS mime_type VARCHAR(50);

ALTER TABLE announcements ADD COLUMN IF NOT EXISTS apply_method VARCHAR(255);

ALTER TABLE announcement_summaries ADD COLUMN IF NOT EXISTS llm_used BOOLEAN DEFAULT false;

CREATE TABLE IF NOT EXISTS notifications (
    id         SERIAL PRIMARY KEY,
    user_id    INT REFERENCES users(id),
    kind       VARCHAR(50),
    title      VARCHAR(255),
    body       TEXT,
    channel    VARCHAR(50),
    status     VARCHAR(50),
    read_flag  BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT now()
);

-- 재실행 가능해야 한다. ADD CONSTRAINT 는 IF NOT EXISTS 를 지원하지 않아 직접 확인한다.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_users_region'
    ) THEN
        ALTER TABLE users ADD CONSTRAINT chk_users_region
        CHECK (region IS NULL OR region IN (
            '서울', '부산', '대구', '인천', '광주', '대전', '울산', '세종',
            '경기', '강원', '충북', '충남', '전북', '전남', '경북', '경남', '제주'
        )) NOT VALID;
    END IF;
END $$;

-- LLM 세금 질문 캐시(LLM/src/rag/tax_cache.py). 데이터는 환경별로 새로 채운다.
CREATE TABLE IF NOT EXISTS tax_rag_cache (
    id                 BIGSERIAL PRIMARY KEY,
    cache_key          TEXT NOT NULL UNIQUE,
    question           TEXT NOT NULL,
    question_embedding vector(1536) NOT NULL,
    cached_result      JSONB NOT NULL,
    created_at         TIMESTAMPTZ DEFAULT now()
);
-- 유사 질문 조회(ORDER BY question_embedding <=> ...)가 캐시 전체를 훑지 않게 한다.
CREATE INDEX IF NOT EXISTS tax_rag_cache_question_embedding_hnsw
    ON tax_rag_cache USING hnsw (question_embedding vector_cosine_ops);
-- 캐시 유효성 판단(세법 청크 최신 갱신 시각) 조회용.
CREATE INDEX IF NOT EXISTS rag_documents_source_type_updated_at_idx
    ON rag_documents (source_type, updated_at);

-- 대화방
CREATE TABLE IF NOT EXISTS chat_rooms (
    id         SERIAL PRIMARY KEY,
    user_id    INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category   VARCHAR(50) NOT NULL,       -- tax | policy | roadmap
    title      VARCHAR(255),                -- NULL이면 첫 질문을 제목으로 표시
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()      -- 마지막 메시지 시각(목록 정렬)
);
CREATE INDEX IF NOT EXISTS idx_chat_rooms_user_cat ON chat_rooms (user_id, category, updated_at DESC);

ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS room_id INT REFERENCES chat_rooms(id) ON DELETE CASCADE;
CREATE INDEX IF NOT EXISTS idx_chat_messages_room ON chat_messages (room_id, id);

-- 기존 메시지 백필: (user_id, category)당 "이전 대화" 방 1개.
-- room_id IS NULL 행만 대상이라 재실행해도 방이 중복 생성되지 않는다.
INSERT INTO chat_rooms (user_id, category, title, created_at, updated_at)
SELECT user_id, category, '이전 대화', MIN(created_at), MAX(created_at)
FROM chat_messages
WHERE room_id IS NULL AND user_id IS NOT NULL AND category IS NOT NULL
GROUP BY user_id, category;

UPDATE chat_messages m SET room_id = r.id
FROM chat_rooms r
WHERE m.room_id IS NULL AND r.user_id = m.user_id AND r.category = m.category
  AND r.title = '이전 대화';

-- 창업 로드맵 체크: 완료한 항목만 행으로 둔다(해제하면 DELETE)
CREATE TABLE IF NOT EXISTS user_roadmap_progress (
    user_id  INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    version  SMALLINT NOT NULL DEFAULT 2,   -- 프론트 ROADMAP_KEY의 v2와 같은 의미
    task_key VARCHAR(20) NOT NULL,          -- "A:0" (단계:항목 인덱스), 현재 키 형식 그대로
    done_at  TIMESTAMP DEFAULT now(),
    PRIMARY KEY (user_id, version, task_key)
);

-- 사업계획서 임시저장: 유저당 1건(현재 동작과 같음)
CREATE TABLE IF NOT EXISTS bizplan_drafts (
    user_id     INT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    form        JSONB NOT NULL DEFAULT '{}'::jsonb,
    plan        JSONB,                       -- 공고 양식에 따라 sections 개수·키가 달라 JSONB
    eval_result JSONB,
    updated_at  TIMESTAMP DEFAULT now()
);

-- 대화방 삭제는 행을 지우지 않고 표시만 한다(관리자 통계 보존). NULL이면 활성 방.
ALTER TABLE chat_rooms ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP;

-- Backend가 항상 room_id를 넣으므로 백필 뒤 NULL이 없으면 NOT NULL로 고정한다.
-- user_id·category가 NULL이라 백필되지 못한 행이 있으면 건너뛴다.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM chat_messages WHERE room_id IS NULL) THEN
        ALTER TABLE chat_messages ALTER COLUMN room_id SET NOT NULL;
    END IF;
END $$;

-- 사업계획서 임시저장 본문: 필드가 자주 늘어나 화면 상태 전체를 JSONB 한 덩어리로 둔다.
-- 위 form/plan/eval_result 컬럼은 쓰지 않는다(삭제는 팀 합의 뒤).
ALTER TABLE bizplan_drafts ADD COLUMN IF NOT EXISTS data JSONB NOT NULL DEFAULT '{}'::jsonb;

-- 사업계획서 보관함: 사용자가 만든 사업계획서를 여러 건 보관한다(마이페이지에서 관리).
-- 작성 화면(bizplan_drafts)은 지금 열어 둔 한 건이고, 임시저장할 때 여기에도 같은 내용을 저장한다.
-- 제목·진행 단계·점수는 목록을 가볍게 보여주려고 data에서 뽑아 따로 둔다.
CREATE TABLE IF NOT EXISTS bizplans (
    id          SERIAL PRIMARY KEY,
    user_id     INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title       VARCHAR(200) NOT NULL DEFAULT '',
    status      VARCHAR(20) NOT NULL DEFAULT 'writing',
    score       INT,
    data        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMP DEFAULT now(),
    updated_at  TIMESTAMP DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_bizplans_user ON bizplans(user_id, updated_at DESC);

-- 국세청 법령해석례 제목("[국세청 법령해석] 안건명 (안건번호)")이 255자를 넘을 수 있다.
ALTER TABLE tax_documents ALTER COLUMN title TYPE VARCHAR(500);

-- '마이페이지에 저장'한 사업계획서 원본. 임시저장 상태와 별도로 보관한다.
CREATE TABLE IF NOT EXISTS bizplan_documents (
    id         SERIAL PRIMARY KEY,
    user_id    INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title      VARCHAR(200) NOT NULL,
    file_name  VARCHAR(255) NOT NULL,
    format     VARCHAR(10) NOT NULL,
    mime_type  VARCHAR(100) NOT NULL,
    file_data  BYTEA NOT NULL,
    size_bytes INT NOT NULL,
    created_at TIMESTAMP DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_bizplan_documents_user
    ON bizplan_documents(user_id, created_at DESC);

-- 같은 저장 문서의 추가 출력 형식. 두 형식을 보관해도 문서 수는 1건이다.
CREATE TABLE IF NOT EXISTS bizplan_document_files (
    document_id INT NOT NULL REFERENCES bizplan_documents(id) ON DELETE CASCADE,
    format      VARCHAR(10) NOT NULL,
    file_name   VARCHAR(255) NOT NULL,
    mime_type   VARCHAR(100) NOT NULL,
    file_data   BYTEA NOT NULL,
    size_bytes  INT NOT NULL,
    PRIMARY KEY (document_id, format)
);

-- 유저별 구독 플랜. 행이 없으면 무료 플랜. 결제는 목업이라 결제 내역은 두지 않는다.
CREATE TABLE IF NOT EXISTS user_subscriptions (
    user_id    INT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    plan       VARCHAR(20) NOT NULL DEFAULT 'free' CHECK (plan IN ('free','basic','pro')),
    started_at TIMESTAMP NOT NULL DEFAULT now(),
    renews_at  TIMESTAMP
);

-- 수집 실패 단위 기록(DB/scripts/collect_common.py). 스크립트가 다시 실행되면 이전 미해결 행은 resolved_at 으로 닫는다.
-- transient 는 run_collection.py --retry 가 next_retry_at 이후 자동 재실행, permanent 는 담당자 조치 대상.
CREATE TABLE IF NOT EXISTS collection_failures (
    id            BIGSERIAL PRIMARY KEY,
    script        VARCHAR(100) NOT NULL,          -- 04_collect_kstartup.py
    unit          VARCHAR(255) NOT NULL,          -- page=3 / keyword=창업,page=2 / mst=280409 / ntstDcmId=..
    kind          VARCHAR(20)  NOT NULL CHECK (kind IN ('transient','permanent')),
    reason        TEXT,
    attempt       INT NOT NULL DEFAULT 0,         -- 지연 재실행 회차(정기 실행은 0)
    next_retry_at TIMESTAMPTZ,
    resolved_at   TIMESTAMPTZ,
    created_at    TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_collection_failures_open
    ON collection_failures (script) WHERE resolved_at IS NULL;

-- TIMESTAMP 컬럼의 now() 기본값을 앱 컨테이너(TZ=Asia/Seoul)와 같은 한국 시간으로 기록한다. 새 연결부터 적용된다.
DO $$
BEGIN
    EXECUTE format('ALTER DATABASE %I SET timezone TO %L', current_database(), 'Asia/Seoul');
END $$;

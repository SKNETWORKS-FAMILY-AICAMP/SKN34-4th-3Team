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

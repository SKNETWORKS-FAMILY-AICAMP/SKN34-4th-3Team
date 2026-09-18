ALTER TABLE users ADD COLUMN IF NOT EXISTS phone VARCHAR(20);
ALTER TABLE users ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'active';

ALTER TABLE calendar_events ADD COLUMN IF NOT EXISTS user_id INT REFERENCES users(id);

ALTER TABLE reminders ADD COLUMN IF NOT EXISTS dispatched BOOLEAN DEFAULT false;

ALTER TABLE expenses ADD COLUMN IF NOT EXISTS user_id INT REFERENCES users(id);

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

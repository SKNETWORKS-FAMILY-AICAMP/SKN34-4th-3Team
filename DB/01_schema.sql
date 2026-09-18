-- 전체 초기화 후 재생성
-- DROP TABLE IF EXISTS rag_documents, tax_documents, saved_policies, announcement_summaries, announcements, expenses, receipt_extractions, receipts, tax_reduction_results, reminders, calendar_events, policies, tax_info, answer_sources, chat_messages, business_profiles, users, admin_users CASCADE;

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE admin_users (
    id            SERIAL PRIMARY KEY,
    email         VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role          VARCHAR(50),
    created_at    TIMESTAMP DEFAULT now()
);

CREATE TABLE users (
    id            SERIAL PRIMARY KEY,
    email         VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    name          VARCHAR(100),
    age           INT,
    region        VARCHAR(100),
    created_at    TIMESTAMP DEFAULT now()
);

CREATE TABLE business_profiles (
    id                       SERIAL PRIMARY KEY,
    user_id                  INT UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    business_type            VARCHAR(50),
    industry                 VARCHAR(100),
    business_registered_at   DATE,
    founded_at               DATE
);

CREATE TABLE chat_messages (
    id         SERIAL PRIMARY KEY,
    user_id    INT REFERENCES users(id) ON DELETE CASCADE,
    category   VARCHAR(50), 
    question   TEXT,
    answer     TEXT,
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE answer_sources (
    id         SERIAL PRIMARY KEY,
    message_id INT REFERENCES chat_messages(id) ON DELETE CASCADE,
    title      VARCHAR(255),
    url        VARCHAR(500),
    excerpt    TEXT
);

CREATE TABLE tax_info (
    id         SERIAL PRIMARY KEY,
    user_id    INT REFERENCES users(id) ON DELETE CASCADE,
    tax_type   VARCHAR(100),
    details    TEXT,
    updated_at TIMESTAMP DEFAULT now()
);

CREATE TABLE policies (
    id               SERIAL PRIMARY KEY,
    admin_id         INT REFERENCES admin_users(id),
    title            VARCHAR(255) NOT NULL,
    region           VARCHAR(2000),
    industry         VARCHAR(100),
    target           TEXT,
    benefit          TEXT,
    eligibility_rule TEXT,
    source           VARCHAR(500),
    created_at       TIMESTAMP DEFAULT now()
);

CREATE TABLE calendar_events (
    id            SERIAL PRIMARY KEY,
    event_type    VARCHAR(20) NOT NULL, 
    business_type VARCHAR(50),  
    policy_id     INT REFERENCES policies(id), 
    title         VARCHAR(255),
    due_date      DATE,
    description   TEXT
);

CREATE TABLE reminders (
    id         SERIAL PRIMARY KEY,
    user_id    INT REFERENCES users(id) ON DELETE CASCADE,
    event_id   INT REFERENCES calendar_events(id) ON DELETE CASCADE,
    notify_at  TIMESTAMP,
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE tax_reduction_results (
    id          SERIAL PRIMARY KEY,
    user_id     INT REFERENCES users(id) ON DELETE CASCADE,
    eligible    BOOLEAN,
    reasons     TEXT,
    legal_basis TEXT,
    judged_at   TIMESTAMP DEFAULT now()
);

CREATE TABLE receipts (
    id         SERIAL PRIMARY KEY,
    user_id    INT REFERENCES users(id) ON DELETE CASCADE,
    image_url  VARCHAR(500),
    status     VARCHAR(50) DEFAULT 'pending',  
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE receipt_extractions (
    id         SERIAL PRIMARY KEY,
    receipt_id INT UNIQUE REFERENCES receipts(id) ON DELETE CASCADE,
    date       DATE,
    vendor     VARCHAR(255),
    amount     INT,
    items      TEXT
);

CREATE TABLE expenses (
    id                     SERIAL PRIMARY KEY,
    receipt_id             INT REFERENCES receipts(id) ON DELETE CASCADE,
    category               VARCHAR(100),
    amount                 INT,
    date                   DATE,
    deductible             BOOLEAN,
    deductible_confidence  FLOAT,
    deductible_basis       TEXT
);

CREATE TABLE announcements (
    id               SERIAL PRIMARY KEY,
    policy_id        INT REFERENCES policies(id) ON DELETE CASCADE,
    raw_content      TEXT,
    source_url       VARCHAR(500),
    apply_start_date DATE,
    apply_end_date   DATE,
    created_at       TIMESTAMP DEFAULT now()
);

CREATE TABLE announcement_summaries (
    id               SERIAL PRIMARY KEY,
    announcement_id  INT UNIQUE REFERENCES announcements(id) ON DELETE CASCADE,
    target           TEXT,
    benefit          TEXT,
    period           TEXT,  
    documents        TEXT,
    notes            TEXT,
    source           VARCHAR(500)
);

CREATE TABLE saved_policies (
    id        SERIAL PRIMARY KEY,
    user_id   INT REFERENCES users(id) ON DELETE CASCADE,
    policy_id INT REFERENCES policies(id) ON DELETE CASCADE,
    saved_at  TIMESTAMP DEFAULT now(),
    UNIQUE (user_id, policy_id) 
);

CREATE TABLE tax_documents (
    id         SERIAL PRIMARY KEY,
    admin_id   INT REFERENCES admin_users(id),
    title      VARCHAR(255),
    law_name   VARCHAR(100),
    content    TEXT,
    source     VARCHAR(500),
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE rag_documents (
    id                SERIAL PRIMARY KEY,
    source_type       VARCHAR(50),
    source_id         INT,
    chunk_id          VARCHAR(100) UNIQUE,
    policy_id         INT REFERENCES policies(id),
    content           TEXT,
    embedding_status  VARCHAR(50),
    embedding         VECTOR(1536),
    updated_at        TIMESTAMP DEFAULT now()
);

CREATE INDEX ON rag_documents USING hnsw (embedding vector_cosine_ops);

-- ERD와 다른 사항
-- 1. 테이블명 전부 소문자 + 단수를 복수로 (user같은 경우 예약어인 이슈)
-- 2. ON DELETE CASCADE를 일부 키에 걸어둠. (유저 탈퇴 시 데이터 삭제. but 관리자가 올린 정책 등 중요데이터는 미해당)
-- 3. pgvector 이용해 벡터데이터 저장 통합 위해 임베딩컬럼 추가
-- 4. saved_policies에 UNIQUE제약 추가해서 같은유저가 같은정책 여러번 저장할 수 없도록
-- 5. 일부 컬럼에 NOT NULL제약 추가
-- 6. 영수증 상태값 디폴트 설정 (receipts.status DEFAULT 'pending')
-- 7. tax_documents에 law_name 컬럼 추가 (법령 종류 구분용, 예: '조세특례제한법', '조세특례제한법 시행령')
-- 8. policies 테이블의 지역 코드 담는 region 컬럼 크기 수정 (100에서 2000으로)
-- 9. rag_documents 컬럼에 chunk_id, policy_id, content 컬럼 추가
-- 10. rag_documents 테이블의 embedding 컬럼에 검색을 빠르게 해주는 인덱스를 하나 추가함. (hnsw 방식)
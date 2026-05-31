-- Query history
CREATE TABLE IF NOT EXISTS query_logs (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    query_text  TEXT NOT NULL,
    answer      TEXT,
    sources     JSONB,
    latency_ms  INTEGER,
    trace_id    TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- User feedback
CREATE TABLE IF NOT EXISTS feedback (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    query_id    UUID REFERENCES query_logs(id),
    rating      SMALLINT CHECK (rating IN (1, -1)),  -- 1=thumbs up, -1=thumbs down
    comment     TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Indexed documents
CREATE TABLE IF NOT EXISTS documents (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filename    TEXT NOT NULL,
    source      TEXT,                          -- FATF / BOT / SEC
    page_count  INTEGER,
    chunk_count INTEGER,
    status      TEXT DEFAULT 'indexed',        -- indexed / deleted
    indexed_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_query_logs_created_at ON query_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_feedback_query_id ON feedback(query_id);
CREATE INDEX IF NOT EXISTS idx_documents_source ON documents(source);

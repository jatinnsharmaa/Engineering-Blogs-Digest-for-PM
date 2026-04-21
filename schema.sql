CREATE TABLE IF NOT EXISTS rss_articles (
    guid TEXT PRIMARY KEY,
    company TEXT NOT NULL,
    url TEXT NOT NULL,
    processed_at TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_processed_at ON rss_articles(processed_at);

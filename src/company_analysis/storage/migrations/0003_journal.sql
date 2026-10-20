-- Analysts' journal: investment theses and notes. Append-only: a correction is a new entry.

CREATE TABLE journal_entries (
    entry_id   VARCHAR PRIMARY KEY,
    issuer_id  VARCHAR NOT NULL,
    entry_date DATE NOT NULL,       -- date the note refers to (chosen by the analyst)
    author     VARCHAR NOT NULL,
    text       VARCHAR NOT NULL,
    decision   VARCHAR NOT NULL,    -- the analyst's decision, never the tool's
    created_at TIMESTAMP NOT NULL   -- when it was recorded (UTC)
);

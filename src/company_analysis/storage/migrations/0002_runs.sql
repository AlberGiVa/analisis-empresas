-- Analysis runs and their outputs. Append-only: every run adds its own rows (keyed by run_id)
-- and nothing is ever updated, so earlier results remain available for comparison.

CREATE TABLE runs (
    run_id          VARCHAR PRIMARY KEY,
    started_at      TIMESTAMP NOT NULL,
    finished_at     TIMESTAMP NOT NULL,
    as_of_date      DATE NOT NULL,       -- analysis date (no data published later is used)
    data_cutoff     TIMESTAMP NOT NULL,  -- only batches loaded up to this moment are used
    load_ids        VARCHAR NOT NULL,    -- JSON list of the load batches visible to the run
    config_version  VARCHAR NOT NULL,
    config_hash     VARCHAR NOT NULL,
    config_snapshot VARCHAR NOT NULL,    -- the configuration file exactly as used
    code_version    VARCHAR NOT NULL,
    git_commit      VARCHAR,
    triggered_by    VARCHAR NOT NULL,
    status          VARCHAR NOT NULL,    -- completed | failed
    error           VARCHAR
);

CREATE TABLE metric_values (
    run_id    VARCHAR NOT NULL,
    metric_id VARCHAR NOT NULL,
    issuer_id VARCHAR NOT NULL,
    level     VARCHAR NOT NULL,  -- issuer | bond
    entity_id VARCHAR NOT NULL,  -- issuer id or bond ISIN
    status    VARCHAR NOT NULL,
    value     DOUBLE,
    detail    VARCHAR,
    inputs    VARCHAR NOT NULL,  -- JSON: label -> value of every input used
    PRIMARY KEY (run_id, metric_id, level, entity_id)
);

CREATE TABLE scores (
    run_id            VARCHAR NOT NULL,
    issuer_id         VARCHAR NOT NULL,
    score_type        VARCHAR NOT NULL,  -- equity | credit
    value             DOUBLE,            -- NULL when the score is not shown
    coverage          DOUBLE NOT NULL,
    factors_with_data INTEGER NOT NULL,
    displayed         BOOLEAN NOT NULL,
    reason            VARCHAR,
    PRIMARY KEY (run_id, issuer_id, score_type)
);

CREATE TABLE score_components (
    run_id          VARCHAR NOT NULL,
    issuer_id       VARCHAR NOT NULL,
    score_type      VARCHAR NOT NULL,
    metric_id       VARCHAR NOT NULL,
    weight          DOUBLE NOT NULL,
    status          VARCHAR NOT NULL,
    value           DOUBLE,
    detail          VARCHAR,
    reference_group VARCHAR,  -- sector | universe
    peer_count      INTEGER,
    percentile      DOUBLE,
    contribution    DOUBLE,
    PRIMARY KEY (run_id, issuer_id, score_type, metric_id)
);

CREATE TABLE screen_results (
    run_id     VARCHAR NOT NULL,
    issuer_id  VARCHAR NOT NULL,
    screen_id  VARCHAR NOT NULL,
    outcome    VARCHAR NOT NULL,  -- pass | fail | indeterminate
    conditions VARCHAR NOT NULL,  -- JSON: description, outcome and detail of each condition
    PRIMARY KEY (run_id, issuer_id, screen_id)
);

CREATE TABLE alerts (
    run_id    VARCHAR NOT NULL,
    alert_id  INTEGER NOT NULL,
    rule      VARCHAR NOT NULL,
    issuer_id VARCHAR NOT NULL,
    entity_id VARCHAR,
    message   VARCHAR NOT NULL,
    details   VARCHAR NOT NULL,  -- JSON
    PRIMARY KEY (run_id, alert_id)
);

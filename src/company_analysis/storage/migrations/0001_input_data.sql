-- Input data. Append-only: rows are never updated or deleted. Every row points to the load batch
-- that brought it, and a correction arrives as a new row in a later batch. Readers pick, for each
-- key, the latest version published by the analysis date and loaded before the run started.
-- Timestamps are UTC.

CREATE TABLE load_batches (
    load_id      VARCHAR PRIMARY KEY,
    loaded_at    TIMESTAMP NOT NULL,
    provider     VARCHAR NOT NULL,
    content_hash VARCHAR NOT NULL,  -- SHA-256 of the loaded content (idempotent loads)
    row_counts   VARCHAR NOT NULL   -- JSON: records per collection
);

CREATE TABLE issuers (
    load_id               VARCHAR NOT NULL,
    issuer_id             VARCHAR NOT NULL,
    name                  VARCHAR NOT NULL,
    lei                   VARCHAR,
    country               VARCHAR NOT NULL,
    sector                VARCHAR NOT NULL,
    industry              VARCHAR NOT NULL,
    reporting_currency    VARCHAR NOT NULL,
    fiscal_year_end_month INTEGER NOT NULL,
    PRIMARY KEY (load_id, issuer_id)
);

CREATE TABLE equities (
    load_id   VARCHAR NOT NULL,
    isin      VARCHAR NOT NULL,
    issuer_id VARCHAR NOT NULL,
    ticker    VARCHAR NOT NULL,
    exchange  VARCHAR NOT NULL,
    currency  VARCHAR NOT NULL,
    PRIMARY KEY (load_id, isin)
);

CREATE TABLE bonds (
    load_id               VARCHAR NOT NULL,
    isin                  VARCHAR NOT NULL,
    issuer_id             VARCHAR NOT NULL,
    currency              VARCHAR NOT NULL,
    coupon_pct            DOUBLE NOT NULL,
    coupon_frequency      INTEGER NOT NULL,
    issue_date            DATE NOT NULL,
    maturity_date         DATE NOT NULL,
    seniority             VARCHAR NOT NULL,
    amount_outstanding_mn DOUBLE NOT NULL,
    PRIMARY KEY (load_id, isin)
);

CREATE TABLE financial_facts (
    load_id       VARCHAR NOT NULL,
    issuer_id     VARCHAR NOT NULL,
    fiscal_period VARCHAR NOT NULL,
    period_end    DATE NOT NULL,  -- closing date of the period
    item          VARCHAR NOT NULL,
    value         DOUBLE NOT NULL,
    currency      VARCHAR,
    published_at  DATE NOT NULL,  -- date the value became public
    PRIMARY KEY (load_id, issuer_id, fiscal_period, period_end, item, published_at)
);

CREATE TABLE equity_prices (
    load_id    VARCHAR NOT NULL,
    isin       VARCHAR NOT NULL,
    price_date DATE NOT NULL,
    close      DOUBLE NOT NULL,
    currency   VARCHAR NOT NULL,
    PRIMARY KEY (load_id, isin, price_date)
);

CREATE TABLE bond_quotes (
    load_id     VARCHAR NOT NULL,
    isin        VARCHAR NOT NULL,
    quote_date  DATE NOT NULL,
    yield_pct   DOUBLE NOT NULL,
    spread_bp   DOUBLE NOT NULL,
    spread_type VARCHAR NOT NULL,
    PRIMARY KEY (load_id, isin, quote_date)
);

CREATE TABLE ratings (
    load_id     VARCHAR NOT NULL,
    isin        VARCHAR NOT NULL,
    agency      VARCHAR NOT NULL,
    rating      VARCHAR NOT NULL,
    rating_date DATE NOT NULL,
    PRIMARY KEY (load_id, isin, agency, rating_date)
);

CREATE TABLE fx_rates (
    load_id       VARCHAR NOT NULL,
    currency      VARCHAR NOT NULL,
    rate_date     DATE NOT NULL,
    units_per_eur DOUBLE NOT NULL,
    PRIMARY KEY (load_id, currency, rate_date)
);

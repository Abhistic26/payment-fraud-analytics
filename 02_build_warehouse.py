"""
=============================================================================
 STAGE 02 : Load Star Schema into a SQL Warehouse (SQLite)
=============================================================================
 SQLite is used so the entire warehouse ships as a single portable file in
 the repo -- any reviewer can open fraud_warehouse.db and run every query in
 /sql without provisioning a server. The DDL, indexing strategy and query
 patterns are standard ANSI SQL and port directly to Postgres / Fabric SQL.
=============================================================================
"""

import pandas as pd
import sqlite3
import os

BASE = os.path.join(os.path.dirname(__file__), "..")
SRC = os.path.join(BASE, "data", "star_schema")
DB = os.path.join(BASE, "data", "fraud_warehouse.db")

if os.path.exists(DB):
    os.remove(DB)

con = sqlite3.connect(DB)
cur = con.cursor()

# ---------------------------------------------------------------------------
# DDL -- explicit typing rather than pandas' inferred schema
# ---------------------------------------------------------------------------
cur.executescript("""
CREATE TABLE dim_date (
    date_key      INTEGER PRIMARY KEY,
    date          TEXT    NOT NULL,
    year          INTEGER,
    month_no      INTEGER,
    month_name    TEXT,
    week_no       INTEGER,
    day_name      TEXT,
    day_of_week   INTEGER,
    is_weekend    TEXT
);

CREATE TABLE dim_customer (
    customer_id           INTEGER PRIMARY KEY,
    total_txns            INTEGER,
    total_spend           REAL,
    avg_txn_amount        REAL,
    max_txn_amount        REAL,
    first_seen            TEXT,
    last_seen             TEXT,
    fraud_txns            INTEGER,
    fraud_rate_pct        REAL,
    active_days           INTEGER,
    txns_per_day          REAL,
    value_segment         TEXT,
    ever_compromised      TEXT
);

CREATE TABLE dim_terminal (
    terminal_id       INTEGER PRIMARY KEY,
    total_txns        INTEGER,
    total_volume      REAL,
    avg_txn_amount    REAL,
    unique_customers  INTEGER,
    fraud_txns        INTEGER,
    fraud_volume      REAL,
    fraud_rate_pct    REAL,
    risk_tier         TEXT
);

CREATE TABLE dim_amount_band (
    amount_band     TEXT PRIMARY KEY,
    txns            INTEGER,
    fraud_txns      INTEGER,
    total_value     REAL,
    fraud_rate_pct  REAL,
    pct_of_all_txns REAL
);

CREATE TABLE fact_transactions (
    transaction_id          INTEGER PRIMARY KEY,
    txn_datetime            TEXT    NOT NULL,
    date_key                INTEGER NOT NULL,
    customer_id             INTEGER NOT NULL,
    terminal_id             INTEGER NOT NULL,
    amount                  REAL    NOT NULL,
    amount_band             TEXT,
    txn_hour                INTEGER,
    part_of_day             TEXT,
    is_fraud                INTEGER NOT NULL,
    fraud_scenario          INTEGER,
    fraud_type              TEXT,
    cust_txn_seq            INTEGER,
    mins_since_prev_txn     REAL,
    cust_avg_amount_todate  REAL,
    amount_vs_cust_avg      REAL,
    terminal_txn_seq        INTEGER,
    FOREIGN KEY (date_key)    REFERENCES dim_date(date_key),
    FOREIGN KEY (customer_id) REFERENCES dim_customer(customer_id),
    FOREIGN KEY (terminal_id) REFERENCES dim_terminal(terminal_id)
);
""")
con.commit()

# ---------------------------------------------------------------------------
# LOAD
# ---------------------------------------------------------------------------
loads = [
    ("dim_date", "dim_date.csv"),
    ("dim_customer", "dim_customer.csv"),
    ("dim_terminal", "dim_terminal.csv"),
    ("dim_amount_band", "dim_amount_band.csv"),
    ("fact_transactions", "fact_transactions.csv"),
]

for table, fname in loads:
    df = pd.read_csv(os.path.join(SRC, fname))
    df.to_sql(table, con, if_exists="append", index=False)
    print(f"[LOAD] {table:<20} {len(df):>9,} rows")

# ---------------------------------------------------------------------------
# INDEXES -- fact table is ~880k rows; without these the analytical
# queries below do full scans. Indexing the foreign keys and the fraud flag
# takes the heaviest query from ~1.4s to ~0.05s.
# ---------------------------------------------------------------------------
cur.executescript("""
CREATE INDEX idx_fact_date     ON fact_transactions(date_key);
CREATE INDEX idx_fact_cust     ON fact_transactions(customer_id);
CREATE INDEX idx_fact_term     ON fact_transactions(terminal_id);
CREATE INDEX idx_fact_fraud    ON fact_transactions(is_fraud);
CREATE INDEX idx_fact_band     ON fact_transactions(amount_band);
CREATE INDEX idx_fact_hour     ON fact_transactions(txn_hour);
CREATE INDEX idx_fact_dt       ON fact_transactions(txn_datetime);
""")
con.commit()
cur.execute("ANALYZE;")
con.commit()

# ---------------------------------------------------------------------------
# REUSABLE VIEW -- denormalised layer for BI tools that cannot join well
# ---------------------------------------------------------------------------
cur.executescript("""
CREATE VIEW vw_txn_enriched AS
SELECT
    f.transaction_id,
    f.txn_datetime,
    d.date,
    d.month_name,
    d.day_name,
    d.is_weekend,
    f.customer_id,
    c.value_segment,
    f.terminal_id,
    t.risk_tier          AS terminal_risk_tier,
    f.amount,
    f.amount_band,
    f.txn_hour,
    f.part_of_day,
    f.amount_vs_cust_avg,
    f.mins_since_prev_txn,
    f.is_fraud,
    f.fraud_type
FROM fact_transactions f
JOIN dim_date     d ON f.date_key    = d.date_key
JOIN dim_customer c ON f.customer_id = c.customer_id
JOIN dim_terminal t ON f.terminal_id = t.terminal_id;
""")
con.commit()

size_mb = os.path.getsize(DB) / 1024 / 1024
print(f"\n[OK] warehouse built -> {DB}  ({size_mb:.1f} MB)")
print("[OK] 5 tables + 7 indexes + 1 view")
con.close()

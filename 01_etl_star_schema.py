"""
=============================================================================
 PROJECT   : Payment Fraud Analytics - Risk & Cost Optimisation
 STAGE 01  : ETL  ->  Star Schema Build
 AUTHOR    : Abhishek Singh
=============================================================================
 PURPOSE
 -------
 Raw transaction logs arrive as one flat file per day. This script:
   1. Consolidates 92 daily files into a single transaction fact table
   2. Engineers analyst-grade features (time buckets, amount bands, velocity)
   3. Builds conformed dimensions (Date, Customer, Terminal, Amount Band)
   4. Emits a clean star schema for SQL / Power BI / Microsoft Fabric

 WHY A STAR SCHEMA?
 ------------------
 Flat files do not scale in BI tools. A star schema (one fact, many dims)
 is the standard model for Power BI and Fabric Lakehouse because it keeps
 relationships one-to-many and lets DAX measures filter cleanly.
=============================================================================
"""

import pandas as pd
import numpy as np
import glob
import os
import warnings

warnings.filterwarnings("ignore")

DATA = os.path.join(os.path.dirname(__file__), "..", "data")
OUT = os.path.join(DATA, "star_schema")
os.makedirs(OUT, exist_ok=True)


# ---------------------------------------------------------------------------
# 1. EXTRACT
# ---------------------------------------------------------------------------
def extract():
    files = sorted(glob.glob(os.path.join(DATA, "hb_*.pkl")))
    print(f"[EXTRACT] reading {len(files)} daily transaction files ...")
    df = pd.concat([pd.read_pickle(f) for f in files], ignore_index=True)
    print(f"[EXTRACT] {len(df):,} raw transactions loaded")
    return df


# ---------------------------------------------------------------------------
# 2. TRANSFORM
# ---------------------------------------------------------------------------
def transform(df):
    print("[TRANSFORM] cleaning + feature engineering ...")

    df = df.rename(
        columns={
            "TRANSACTION_ID": "transaction_id",
            "TX_DATETIME": "txn_datetime",
            "CUSTOMER_ID": "customer_id",
            "TERMINAL_ID": "terminal_id",
            "TX_AMOUNT": "amount",
            "TX_FRAUD": "is_fraud",
            "TX_FRAUD_SCENARIO": "fraud_scenario",
        }
    )[
        [
            "transaction_id",
            "txn_datetime",
            "customer_id",
            "terminal_id",
            "amount",
            "is_fraud",
            "fraud_scenario",
        ]
    ]

    # --- type discipline -------------------------------------------------
    df["txn_datetime"] = pd.to_datetime(df["txn_datetime"])
    for c in ["customer_id", "terminal_id", "transaction_id"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("int64")
    df["amount"] = df["amount"].astype(float).round(2)
    df["is_fraud"] = df["is_fraud"].astype(int)
    df["fraud_scenario"] = df["fraud_scenario"].astype(int)

    # --- data quality audit ---------------------------------------------
    dq = {
        "duplicate_txn_ids": int(df.transaction_id.duplicated().sum()),
        "null_rows": int(df.isnull().any(axis=1).sum()),
        "zero_amount_txns": int((df.amount <= 0).sum()),
        "negative_amounts": int((df.amount < 0).sum()),
    }
    print(f"[DQ AUDIT] {dq}")

    df = df.drop_duplicates(subset="transaction_id").dropna()
    df = df[df.amount > 0].copy()

    # --- time features ---------------------------------------------------
    df["txn_date"] = df.txn_datetime.dt.date
    df["date_key"] = df.txn_datetime.dt.strftime("%Y%m%d").astype(int)
    df["txn_hour"] = df.txn_datetime.dt.hour

    def part_of_day(h):
        if h < 6:
            return "01 Night (00-06)"
        if h < 12:
            return "02 Morning (06-12)"
        if h < 18:
            return "03 Afternoon (12-18)"
        return "04 Evening (18-24)"

    df["part_of_day"] = df.txn_hour.map(part_of_day)

    # --- amount banding (business-readable risk buckets) ------------------
    bins = [0, 25, 50, 100, 200, 220, 500, np.inf]
    labels = [
        "01 Micro (0-25)",
        "02 Small (25-50)",
        "03 Medium (50-100)",
        "04 Large (100-200)",
        "05 High (200-220)",
        "06 Very High (220-500)",
        "07 Extreme (500+)",
    ]
    df["amount_band"] = pd.cut(df.amount, bins=bins, labels=labels, right=True)

    # --- behavioural features (customer velocity) -------------------------
    df = df.sort_values(["customer_id", "txn_datetime"]).reset_index(drop=True)
    g = df.groupby("customer_id")
    df["cust_txn_seq"] = g.cumcount() + 1
    df["mins_since_prev_txn"] = (
        g["txn_datetime"].diff().dt.total_seconds().div(60).round(1)
    )
    # expanding mean EXCLUDES current row -> no target leakage
    df["cust_avg_amount_todate"] = (
        g["amount"].apply(lambda s: s.shift().expanding().mean()).reset_index(drop=True)
    ).round(2)
    df["amount_vs_cust_avg"] = (
        df.amount / df.cust_avg_amount_todate.replace(0, np.nan)
    ).round(2)

    # --- terminal exposure ------------------------------------------------
    df["terminal_txn_seq"] = df.groupby("terminal_id").cumcount() + 1

    # --- fraud typology labels -------------------------------------------
    scen = {
        0: "Legitimate",
        1: "S1 - High Value Anomaly",
        2: "S2 - Terminal Compromise",
        3: "S3 - Account Takeover",
    }
    df["fraud_type"] = df.fraud_scenario.map(scen)

    df = df.sort_values("txn_datetime").reset_index(drop=True)
    print(f"[TRANSFORM] {len(df):,} clean transactions | fraud rate "
          f"{df.is_fraud.mean()*100:.3f}%")
    return df, dq


# ---------------------------------------------------------------------------
# 3. DIMENSIONS
# ---------------------------------------------------------------------------
def build_dim_date(df):
    d = pd.DataFrame({"txn_date": sorted(df.txn_date.unique())})
    d["date"] = pd.to_datetime(d.txn_date)
    d["date_key"] = d.date.dt.strftime("%Y%m%d").astype(int)
    d["year"] = d.date.dt.year
    d["month_no"] = d.date.dt.month
    d["month_name"] = d.date.dt.strftime("%b %Y")
    d["week_no"] = d.date.dt.isocalendar().week.astype(int)
    d["day_name"] = d.date.dt.day_name()
    d["day_of_week"] = d.date.dt.dayofweek + 1
    d["is_weekend"] = d.day_of_week.isin([6, 7]).map({True: "Weekend", False: "Weekday"})
    return d[
        ["date_key", "date", "year", "month_no", "month_name", "week_no",
         "day_name", "day_of_week", "is_weekend"]
    ]


def build_dim_customer(df):
    c = df.groupby("customer_id").agg(
        total_txns=("transaction_id", "count"),
        total_spend=("amount", "sum"),
        avg_txn_amount=("amount", "mean"),
        max_txn_amount=("amount", "max"),
        first_seen=("txn_datetime", "min"),
        last_seen=("txn_datetime", "max"),
        fraud_txns=("is_fraud", "sum"),
    ).reset_index()

    c["total_spend"] = c.total_spend.round(2)
    c["avg_txn_amount"] = c.avg_txn_amount.round(2)
    c["fraud_rate_pct"] = (c.fraud_txns / c.total_txns * 100).round(3)
    c["active_days"] = (c.last_seen - c.first_seen).dt.days + 1
    c["txns_per_day"] = (c.total_txns / c.active_days).round(2)

    # value segmentation by spend quartile
    c["value_segment"] = pd.qcut(
        c.total_spend, 4,
        labels=["D - Low Value", "C - Mid Value", "B - High Value", "A - Premium"],
    ).astype(str)

    c["ever_compromised"] = (c.fraud_txns > 0).map({True: "Yes", False: "No"})
    return c


def build_dim_terminal(df):
    t = df.groupby("terminal_id").agg(
        total_txns=("transaction_id", "count"),
        total_volume=("amount", "sum"),
        avg_txn_amount=("amount", "mean"),
        unique_customers=("customer_id", "nunique"),
        fraud_txns=("is_fraud", "sum"),
        fraud_volume=("amount", lambda s: s[df.loc[s.index, "is_fraud"] == 1].sum()),
    ).reset_index()

    t["total_volume"] = t.total_volume.round(2)
    t["avg_txn_amount"] = t.avg_txn_amount.round(2)
    t["fraud_volume"] = t.fraud_volume.round(2)
    t["fraud_rate_pct"] = (t.fraud_txns / t.total_txns * 100).round(3)

    # operational risk tiering -> drives manual review routing
    def tier(r):
        if r >= 5:
            return "1 - Critical"
        if r >= 2:
            return "2 - High"
        if r > 0:
            return "3 - Watch"
        return "4 - Clean"

    t["risk_tier"] = t.fraud_rate_pct.map(tier)
    return t


def build_dim_amount_band(df):
    b = df.groupby("amount_band", observed=True).agg(
        txns=("transaction_id", "count"),
        fraud_txns=("is_fraud", "sum"),
        total_value=("amount", "sum"),
    ).reset_index()
    b["fraud_rate_pct"] = (b.fraud_txns / b.txns * 100).round(3)
    b["total_value"] = b.total_value.round(2)
    b["pct_of_all_txns"] = (b.txns / b.txns.sum() * 100).round(2)
    b["amount_band"] = b.amount_band.astype(str)
    return b


# ---------------------------------------------------------------------------
# 4. LOAD
# ---------------------------------------------------------------------------
def main():
    raw = extract()
    fact, dq = transform(raw)

    dim_date = build_dim_date(fact)
    dim_cust = build_dim_customer(fact)
    dim_term = build_dim_terminal(fact)
    dim_band = build_dim_amount_band(fact)

    fact_out = fact[
        ["transaction_id", "txn_datetime", "date_key", "customer_id", "terminal_id",
         "amount", "amount_band", "txn_hour", "part_of_day", "is_fraud",
         "fraud_scenario", "fraud_type", "cust_txn_seq", "mins_since_prev_txn",
         "cust_avg_amount_todate", "amount_vs_cust_avg", "terminal_txn_seq"]
    ].copy()
    fact_out["amount_band"] = fact_out.amount_band.astype(str)

    fact_out.to_parquet(os.path.join(OUT, "fact_transactions.parquet"), index=False)
    fact_out.to_csv(os.path.join(OUT, "fact_transactions.csv"), index=False)
    dim_date.to_csv(os.path.join(OUT, "dim_date.csv"), index=False)
    dim_cust.to_csv(os.path.join(OUT, "dim_customer.csv"), index=False)
    dim_term.to_csv(os.path.join(OUT, "dim_terminal.csv"), index=False)
    dim_band.to_csv(os.path.join(OUT, "dim_amount_band.csv"), index=False)

    pd.DataFrame([dq]).to_csv(os.path.join(OUT, "data_quality_audit.csv"), index=False)

    print("\n" + "=" * 62)
    print(" STAR SCHEMA BUILT")
    print("=" * 62)
    print(f" fact_transactions : {len(fact_out):>9,} rows x {fact_out.shape[1]} cols")
    print(f" dim_date          : {len(dim_date):>9,} rows")
    print(f" dim_customer      : {len(dim_cust):>9,} rows")
    print(f" dim_terminal      : {len(dim_term):>9,} rows")
    print(f" dim_amount_band   : {len(dim_band):>9,} rows")
    print("=" * 62)


if __name__ == "__main__":
    main()

"""
=============================================================================
 STAGE 04 : Excel Deliverable
=============================================================================
 Fraud-operations teams live in Excel. This builds the workbook they would
 actually receive: a KPI summary, native Excel charts, conditional
 formatting for triage, and a raw sheet formatted as a Table so the
 recipient can build their own PivotTables without asking for help.
=============================================================================
"""

import pandas as pd
import numpy as np
import sqlite3
import json
import os

BASE = os.path.join(os.path.dirname(__file__), "..")
DB = os.path.join(BASE, "data", "fraud_warehouse.db")
OUT = os.path.join(BASE, "excel")
os.makedirs(OUT, exist_ok=True)
XL = os.path.join(OUT, "Fraud_Analytics_Workbook.xlsx")

con = sqlite3.connect(DB)
q = lambda s: pd.read_sql(s, con)
stats_json = json.load(open(os.path.join(BASE, "reports", "statistical_results.json")))

# ---------------------------------------------------------------------------
# Pull the analysis layers
# ---------------------------------------------------------------------------
kpi_src = q("""
    SELECT COUNT(*) txns, COUNT(DISTINCT customer_id) customers,
           COUNT(DISTINCT terminal_id) terminals, SUM(amount) value,
           SUM(is_fraud) frauds,
           SUM(CASE WHEN is_fraud=1 THEN amount ELSE 0 END) fraud_value
    FROM fact_transactions""").iloc[0]

by_band = q("""
    SELECT amount_band, COUNT(*) txns, SUM(is_fraud) fraud_txns,
           ROUND(100.0*SUM(is_fraud)/COUNT(*),3) fraud_rate_pct,
           ROUND(SUM(CASE WHEN is_fraud=1 THEN amount ELSE 0 END),2) fraud_value
    FROM fact_transactions GROUP BY amount_band ORDER BY amount_band""")

by_type = q("""
    SELECT fraud_type, COUNT(*) incidents,
           ROUND(SUM(amount),2) loss_value, ROUND(AVG(amount),2) avg_loss,
           COUNT(DISTINCT customer_id) customers_hit
    FROM fact_transactions WHERE is_fraud=1
    GROUP BY fraud_type ORDER BY loss_value DESC""")

daily = q("""
    SELECT DATE(txn_datetime) txn_date, COUNT(*) txns, SUM(is_fraud) fraud_txns,
           ROUND(100.0*SUM(is_fraud)/COUNT(*),3) fraud_rate_pct,
           ROUND(SUM(CASE WHEN is_fraud=1 THEN amount ELSE 0 END),2) fraud_value
    FROM fact_transactions GROUP BY DATE(txn_datetime) ORDER BY txn_date""")
daily["fraud_rate_7d_ma"] = daily.fraud_rate_pct.rolling(7, min_periods=1).mean().round(3)

hourly = q("""
    SELECT txn_hour, COUNT(*) txns, SUM(is_fraud) fraud_txns,
           ROUND(100.0*SUM(is_fraud)/COUNT(*),3) fraud_rate_pct
    FROM fact_transactions GROUP BY txn_hour ORDER BY txn_hour""")

terminals = q("""
    SELECT terminal_id, total_txns, fraud_txns, fraud_rate_pct,
           ROUND(fraud_volume,2) fraud_volume, unique_customers, risk_tier
    FROM dim_terminal WHERE fraud_txns > 0
    ORDER BY fraud_volume DESC LIMIT 250""")

segments = q("""
    SELECT value_segment, COUNT(*) customers, SUM(total_txns) txns,
           ROUND(SUM(total_spend),2) spend, SUM(fraud_txns) fraud_txns,
           ROUND(100.0*SUM(fraud_txns)/SUM(total_txns),3) fraud_rate_pct,
           SUM(CASE WHEN ever_compromised='Yes' THEN 1 ELSE 0 END) customers_hit
    FROM dim_customer GROUP BY value_segment ORDER BY value_segment""")

thresholds = pd.read_csv(os.path.join(BASE, "reports", "threshold_optimisation.csv"))
thr_view = thresholds[thresholds.threshold.between(100, 400)].copy()

# A pivot-ready extract. 880k rows will not open comfortably, so a
# stratified sample keeps every segment represented at a usable file size.
rng = np.random.default_rng(42)
raw = q("SELECT * FROM vw_txn_enriched")
fr = raw[raw.is_fraud == 1]
lg = raw[raw.is_fraud == 0].sample(n=40000, random_state=42)
pivot_data = pd.concat([fr, lg]).sort_values("txn_datetime").reset_index(drop=True)

# ---------------------------------------------------------------------------
# Write workbook
# ---------------------------------------------------------------------------
wb = pd.ExcelWriter(XL, engine="xlsxwriter")
book = wb.book

# --- house style ---
F = dict(
    title=book.add_format({"bold": True, "font_size": 18, "font_color": "#1F2A44"}),
    sub=book.add_format({"font_size": 10, "font_color": "#6B7280", "italic": True}),
    h=book.add_format({"bold": True, "font_size": 11, "bg_color": "#1F2A44",
                       "font_color": "white", "border": 1, "align": "center",
                       "valign": "vcenter", "text_wrap": True}),
    sect=book.add_format({"bold": True, "font_size": 12, "font_color": "#1F2A44",
                          "bottom": 2, "border_color": "#C8A951"}),
    num=book.add_format({"num_format": "#,##0", "border": 1}),
    cur=book.add_format({"num_format": "#,##0.00", "border": 1}),
    pct=book.add_format({"num_format": "0.000", "border": 1}),
    txt=book.add_format({"border": 1}),
    kpi_l=book.add_format({"font_size": 10, "font_color": "#6B7280",
                           "align": "center", "top": 1, "left": 1, "right": 1,
                           "border_color": "#D1D5DB"}),
    kpi_v=book.add_format({"font_size": 20, "bold": True, "align": "center",
                           "font_color": "#1F2A44", "bottom": 1, "left": 1,
                           "right": 1, "border_color": "#D1D5DB"}),
    note=book.add_format({"font_size": 10, "text_wrap": True, "valign": "top",
                          "font_color": "#374151"}),
    good=book.add_format({"bg_color": "#D1FAE5", "font_color": "#065F46"}),
    bad=book.add_format({"bg_color": "#FEE2E2", "font_color": "#991B1B"}),
)


def write_table(sheet, df, row0, col0, fmts=None):
    for j, c in enumerate(df.columns):
        sheet.write(row0, col0 + j, c.replace("_", " ").title(), F["h"])
    for i in range(len(df)):
        for j, c in enumerate(df.columns):
            v = df.iloc[i, j]
            f = (fmts or {}).get(c, F["txt"])
            if pd.isna(v):
                sheet.write_blank(row0 + 1 + i, col0 + j, None, f)
            elif isinstance(v, (int, np.integer, float, np.floating)):
                sheet.write_number(row0 + 1 + i, col0 + j, float(v), f)
            else:
                sheet.write(row0 + 1 + i, col0 + j, str(v), f)


# ===================== SHEET 1 : DASHBOARD =====================
ws = book.add_worksheet("1. Dashboard")
ws.hide_gridlines(2)
ws.set_column("A:A", 2)
ws.set_column("B:J", 15)

ws.write("B2", "PAYMENT FRAUD ANALYTICS", F["title"])
ws.write("B3", f"{int(kpi_src.txns):,} transactions  |  "
               f"{int(kpi_src.customers):,} customers  |  "
               f"{int(kpi_src.terminals):,} terminals  |  92 days", F["sub"])

fr_rate = 100 * kpi_src.frauds / kpi_src.txns
var_pct = 100 * kpi_src.fraud_value / kpi_src.value
kpis = [
    ("TRANSACTIONS", f"{int(kpi_src.txns):,}"),
    ("VALUE PROCESSED", f"{kpi_src.value/1e6:.1f}M"),
    ("FRAUD CASES", f"{int(kpi_src.frauds):,}"),
    ("FRAUD RATE", f"{fr_rate:.3f}%"),
    ("GROSS LOSS", f"{kpi_src.fraud_value/1000:.0f}K"),
    ("VALUE AT RISK", f"{var_pct:.2f}%"),
]
for i, (lab, val) in enumerate(kpis):
    c = 1 + i * 1
    ws.write(4, c, lab, F["kpi_l"])
    ws.write(5, c, val, F["kpi_v"])
ws.set_row(5, 30)

ws.write("B8", "RISK BY TRANSACTION SIZE", F["sect"])
write_table(ws, by_band, 9, 1,
            {"txns": F["num"], "fraud_txns": F["num"],
             "fraud_rate_pct": F["pct"], "fraud_value": F["cur"]})

ch1 = book.add_chart({"type": "column"})
ch1.add_series({
    "name": "Fraud rate %",
    "categories": ["1. Dashboard", 10, 1, 9 + len(by_band), 1],
    "values": ["1. Dashboard", 10, 4, 9 + len(by_band), 4],
    "fill": {"color": "#C0392B"},
})
ch1.set_title({"name": "Fraud rate by amount band (%)"})
ch1.set_legend({"none": True})
ch1.set_size({"width": 460, "height": 260})
ws.insert_chart("H9", ch1)

r = 11 + len(by_band)
ws.write(r, 1, "LOSS BY FRAUD TYPOLOGY", F["sect"])
write_table(ws, by_type, r + 1, 1,
            {"incidents": F["num"], "loss_value": F["cur"],
             "avg_loss": F["cur"], "customers_hit": F["num"]})

ch2 = book.add_chart({"type": "pie"})
ch2.add_series({
    "name": "Loss by typology",
    "categories": ["1. Dashboard", r + 2, 1, r + 1 + len(by_type), 1],
    "values": ["1. Dashboard", r + 2, 3, r + 1 + len(by_type), 3],
    "points": [{"fill": {"color": c}} for c in ["#C0392B", "#E67E22", "#C8A951"]],
})
ch2.set_title({"name": "Share of total loss"})
ch2.set_size({"width": 460, "height": 260})
ws.insert_chart(f"H{r+2}", ch2)

r2 = r + 3 + len(by_type)
ws.write(r2, 1, "KEY FINDING", F["sect"])
bs = stats_json["test7_blind_spot"]
t5 = stats_json["test5_threshold"]
ws.merge_range(
    r2 + 1, 1, r2 + 4, 6,
    f"An amount-only review rule set at the cost-optimal cut-off of "
    f"{t5['optimal_threshold']} catches {t5['recall_pct']:.1f}% of fraud at "
    f"{t5['precision_pct']:.1f}% precision. The remaining "
    f"{bs['pct_of_all_fraud_missed']:.1f}% of cases -- worth "
    f"{bs['unprevented_loss']:,.0f} -- sit below the cut-off and are invisible "
    f"to any amount rule. Closing that gap requires behavioural signals "
    f"(deviation from a customer's own baseline, terminal reputation), not a "
    f"lower threshold: lowering it multiplies false positives without touching "
    f"these cases.",
    F["note"])

# ===================== SHEET 2 : TREND =====================
ws2 = book.add_worksheet("2. Daily Trend")
ws2.hide_gridlines(2)
ws2.set_column("A:A", 2)
ws2.set_column("B:B", 13)
ws2.set_column("C:G", 15)
ws2.write("B2", "DAILY FRAUD TREND", F["title"])
ws2.write("B3", "7-day moving average smooths weekday noise so a real shift is visible",
          F["sub"])
write_table(ws2, daily, 5, 1,
            {"txns": F["num"], "fraud_txns": F["num"],
             "fraud_rate_pct": F["pct"], "fraud_value": F["cur"],
             "fraud_rate_7d_ma": F["pct"]})

ch3 = book.add_chart({"type": "line"})
ch3.add_series({"name": "Daily fraud rate %",
                "categories": ["2. Daily Trend", 6, 1, 5 + len(daily), 1],
                "values": ["2. Daily Trend", 6, 4, 5 + len(daily), 4],
                "line": {"color": "#D1D5DB", "width": 1.25}})
ch3.add_series({"name": "7-day moving avg",
                "categories": ["2. Daily Trend", 6, 1, 5 + len(daily), 1],
                "values": ["2. Daily Trend", 6, 6, 5 + len(daily), 6],
                "line": {"color": "#C0392B", "width": 2.25}})
ch3.set_title({"name": "Fraud rate over time (%)"})
ch3.set_size({"width": 720, "height": 320})
ws2.insert_chart("I6", ch3)

ch4 = book.add_chart({"type": "column"})
ch4.add_series({"name": "Daily fraud loss",
                "categories": ["2. Daily Trend", 6, 1, 5 + len(daily), 1],
                "values": ["2. Daily Trend", 6, 5, 5 + len(daily), 5],
                "fill": {"color": "#1F2A44"}})
ch4.set_title({"name": "Daily fraud loss (value)"})
ch4.set_legend({"none": True})
ch4.set_size({"width": 720, "height": 300})
ws2.insert_chart("I24", ch4)

# ===================== SHEET 3 : TERMINAL WATCHLIST =====================
ws3 = book.add_worksheet("3. Terminal Watchlist")
ws3.hide_gridlines(2)
ws3.set_column("A:A", 2)
ws3.set_column("B:H", 16)
ws3.write("B2", "TERMINAL RISK WATCHLIST", F["title"])
ws3.write("B3", "Top 250 terminals by fraud loss -- the manual review worklist. "
                "Conditional formatting flags the review queue.", F["sub"])
write_table(ws3, terminals, 5, 1,
            {"total_txns": F["num"], "fraud_txns": F["num"],
             "fraud_rate_pct": F["pct"], "fraud_volume": F["cur"],
             "unique_customers": F["num"]})

last = 5 + len(terminals)
ws3.conditional_format(6, 4, last, 4,
                       {"type": "3_color_scale", "min_color": "#FFFFFF",
                        "mid_color": "#FDE68A", "max_color": "#DC2626"})
ws3.conditional_format(6, 5, last, 5,
                       {"type": "data_bar", "bar_color": "#1F2A44"})
ws3.conditional_format(6, 7, last, 7,
                       {"type": "text", "criteria": "containing",
                        "value": "Critical", "format": F["bad"]})
ws3.conditional_format(6, 7, last, 7,
                       {"type": "text", "criteria": "containing",
                        "value": "Watch", "format": F["good"]})
ws3.freeze_panes(6, 0)
ws3.autofilter(5, 1, last, 7)

# ===================== SHEET 4 : THRESHOLD MODEL =====================
ws4 = book.add_worksheet("4. Threshold Model")
ws4.hide_gridlines(2)
ws4.set_column("A:A", 2)
ws4.set_column("B:K", 16)
ws4.write("B2", "REVIEW THRESHOLD -- COST/BENEFIT MODEL", F["title"])
a = stats_json["test5_threshold"]["assumptions"]
ws4.write("B3", f"Assumptions: review cost {a['cost_per_review']} per case | "
                f"false-decline cost {a['cost_false_decline']} | "
                f"recovery rate {a['recovery_rate']:.0%}. "
                f"Change these and the optimum moves -- see sensitivity below.",
          F["sub"])
write_table(ws4, thr_view, 5, 1,
            {"threshold": F["num"], "txns_flagged": F["num"],
             "frauds_caught": F["num"], "false_positives": F["num"],
             "recall_pct": F["pct"], "precision_pct": F["pct"],
             "loss_prevented": F["cur"], "operating_cost": F["cur"],
             "residual_loss": F["cur"], "net_benefit": F["cur"]})
lastr = 5 + len(thr_view)
ws4.conditional_format(6, 10, lastr, 10,
                       {"type": "3_color_scale", "min_color": "#FEE2E2",
                        "mid_color": "#FEF3C7", "max_color": "#D1FAE5"})

ch5 = book.add_chart({"type": "line"})
ch5.add_series({"name": "Net benefit",
                "categories": ["4. Threshold Model", 6, 1, lastr, 1],
                "values": ["4. Threshold Model", 6, 10, lastr, 10],
                "line": {"color": "#065F46", "width": 2.25}})
ch5.set_title({"name": "Net benefit by review threshold"})
ch5.set_x_axis({"name": "Review transactions above"})
ch5.set_size({"width": 620, "height": 300})
ws4.insert_chart("M6", ch5)

ch6 = book.add_chart({"type": "line"})
ch6.add_series({"name": "Recall %",
                "categories": ["4. Threshold Model", 6, 1, lastr, 1],
                "values": ["4. Threshold Model", 6, 5, lastr, 5],
                "line": {"color": "#C0392B", "width": 2}})
ch6.add_series({"name": "Precision %",
                "categories": ["4. Threshold Model", 6, 1, lastr, 1],
                "values": ["4. Threshold Model", 6, 6, lastr, 6],
                "line": {"color": "#1F2A44", "width": 2}})
ch6.set_title({"name": "Precision / recall trade-off"})
ch6.set_size({"width": 620, "height": 300})
ws4.insert_chart("M22", ch6)

sens = pd.read_csv(os.path.join(BASE, "reports", "sensitivity_analysis.csv"))
rr = lastr + 3
ws4.write(rr, 1, "SENSITIVITY -- does the recommendation survive other costs?", F["sect"])
write_table(ws4, sens, rr + 1, 1,
            {"review_cost": F["cur"], "false_decline_cost": F["cur"],
             "optimal_threshold": F["num"], "net_benefit": F["cur"]})

# ===================== SHEET 5 : SEGMENTS & HOURS =====================
ws5 = book.add_worksheet("5. Segments")
ws5.hide_gridlines(2)
ws5.set_column("A:A", 2)
ws5.set_column("B:H", 16)
ws5.write("B2", "CUSTOMER SEGMENTS & TIME PATTERNS", F["title"])
ws5.write("B4", "FRAUD BY CUSTOMER VALUE SEGMENT", F["sect"])
write_table(ws5, segments, 5, 1,
            {"customers": F["num"], "txns": F["num"], "spend": F["cur"],
             "fraud_txns": F["num"], "fraud_rate_pct": F["pct"],
             "customers_hit": F["num"]})

r5 = 7 + len(segments)
ws5.write(r5, 1, "FRAUD RATE BY HOUR OF DAY", F["sect"])
write_table(ws5, hourly, r5 + 1, 1,
            {"txn_hour": F["num"], "txns": F["num"],
             "fraud_txns": F["num"], "fraud_rate_pct": F["pct"]})

t2 = stats_json["test2_timing"]
ws5.merge_range(r5 + 3 + len(hourly), 1, r5 + 6 + len(hourly), 7,
                f"STATISTICAL NOTE: a chi-square test of independence returns "
                f"Cramer's V = {t2['cramers_v']:.4f} for time-of-day, versus "
                f"{stats_json['test3_amount_band']['cramers_v']:.4f} for amount "
                f"band. Time-of-day variation is not a usable signal here -- the "
                f"hourly differences are noise, not pattern. Rostering analysts by "
                f"hour would spend budget against a non-effect.", F["note"])

ch7 = book.add_chart({"type": "column"})
ch7.add_series({"name": "Fraud rate % by hour",
                "categories": ["5. Segments", r5 + 2, 1, r5 + 1 + len(hourly), 1],
                "values": ["5. Segments", r5 + 2, 4, r5 + 1 + len(hourly), 4],
                "fill": {"color": "#1F2A44"}})
ch7.set_title({"name": "Fraud rate by hour (%) -- note the flat profile"})
ch7.set_legend({"none": True})
ch7.set_size({"width": 620, "height": 280})
ws5.insert_chart(f"J{r5+2}", ch7)

# ===================== SHEET 6 : PIVOT DATA =====================
pivot_data.to_excel(wb, sheet_name="6. Pivot Data", index=False, startrow=0)
ws6 = wb.sheets["6. Pivot Data"]
ws6.add_table(0, 0, len(pivot_data), len(pivot_data.columns) - 1,
              {"name": "TxnData", "style": "Table Style Medium 2",
               "columns": [{"header": c} for c in pivot_data.columns]})
ws6.freeze_panes(1, 0)
ws6.set_column("A:S", 15)

# ===================== SHEET 7 : README =====================
ws7 = book.add_worksheet("7. Notes")
ws7.hide_gridlines(2)
ws7.set_column("A:A", 2)
ws7.set_column("B:B", 105)
ws7.write("B2", "HOW TO USE THIS WORKBOOK", F["title"])
notes = [
    ("Purpose", "Fraud exposure review for a card portfolio of "
                f"{int(kpi_src.txns):,} transactions over 92 days."),
    ("1. Dashboard", "Headline KPIs, risk by amount band, loss by typology."),
    ("2. Daily Trend", "Daily series with a 7-day moving average and loss bars."),
    ("3. Terminal Watchlist", "Top 250 terminals by loss. Filter Risk Tier to "
                              "'1 - Critical' for today's review queue."),
    ("4. Threshold Model", "Cost/benefit of each review cut-off, plus a "
                           "sensitivity grid. Edit the assumptions in the "
                           "Python script and re-run to model your own costs."),
    ("5. Segments", "Customer value segments and hour-of-day profile, with the "
                    "statistical note on why timing is not actionable."),
    ("6. Pivot Data", "Formatted as an Excel Table named 'TxnData'. "
                      "Insert > PivotTable > select TxnData to build your own "
                      "views. All fraud cases plus a 40,000-row random sample "
                      "of legitimate transactions, so fraud rates on this sheet "
                      "are deliberately higher than the portfolio rate -- use "
                      "it for composition, not for rate."),
    ("Data source", "ULB Machine Learning Group transaction simulator, from the "
                    "open handbook 'Reproducible Machine Learning for Credit "
                    "Card Fraud Detection'. 92 daily files, Apr-Jul 2018."),
    ("Rebuild", "python notebooks/01_etl_star_schema.py -> 02 -> 03 -> 04"),
]
rowi = 4
for k, v in notes:
    ws7.write(rowi, 1, k, F["sect"])
    ws7.merge_range(rowi + 1, 1, rowi + 2, 1, v, F["note"])
    rowi += 4

wb.close()
con.close()

print(f"[OK] workbook written -> {XL}")
print(f"     size: {os.path.getsize(XL)/1024/1024:.2f} MB")
print(f"     sheets: 7 | native charts: 7 | pivot rows: {len(pivot_data):,}")

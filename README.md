# Payment Fraud Analytics — Risk Concentration & Review-Threshold Optimisation

**Live dashboard:** _add your Streamlit URL here after deploying_

An end-to-end analytics project on **882,468 card transactions** over 92 days,
answering one operational question: *where should a fraud team point its
limited review capacity, and what does that rule cost versus save?*

Built with **Python · SQL · Excel · Power BI · Streamlit**.

---

## The headline finding

A manual-review rule based on transaction amount — the control most fraud
teams start with — is **cost-optimal at a cut-off of 200**, where it returns a
net benefit of **103,239** per 92-day window.

At that setting it catches **24.6% of fraud cases**.

The other **75.4% — 5,230 cases worth 326,213** — sits *below* the cut-off and
is structurally invisible to any amount rule. Lowering the threshold does not
help: at 100 the same rule swings to a **net loss of 1.38M**, because false
positives grow far faster than detections.

Closing that gap requires a different kind of signal, and the analysis
identifies which one.

---

## What the analysis established

| Question | Answer | Evidence |
|---|---|---|
| Are fraudulent transactions larger? | Yes — 6.7× by mean value | Mann-Whitney U, p < 0.001, rank-biserial 0.55 |
| Which dimension carries real risk signal? | Amount, not timing | Cramér's V **0.4837** vs **0.0007** — a 686× difference |
| How concentrated is the loss? | Worst **5%** of terminals hold **52%** of it | Pareto over 10,000 terminals |
| What is the cost-optimal review threshold? | **200** | Expected-cost model, stable across 9 cost scenarios |
| What does that rule miss? | 75.4% of cases, worth 326,213 | Residual analysis by fraud typology |

### The negative result worth reading

Fraud rate by hour of day looks like it varies — 0.778% to 0.795% across the
four periods. It doesn't. A chi-square test returns **Cramér's V = 0.0007**,
against **0.4837** for amount band.

The hourly variation is noise. A staffing model built on it would spend real
budget against a non-effect. Reporting that clearly mattered more than
reporting a pattern that wasn't there.

---

## Recommendations delivered

1. **Set the review threshold at 200, not lower.** Maximises net benefit and
   holds across every cost scenario tested (optimum moves only 180–210).
2. **Build a terminal watchlist covering the worst 5% of the estate** — those
   terminals carry 52% of loss, reachable without touching every transaction.
3. **Add a behavioural rule on deviation from each customer's own baseline.**
   Account-takeover cases run above 3× a customer's normal spend while staying
   unremarkable in absolute terms — the signal an amount rule cannot use.
4. **Do not roster reviewers by hour of day.** See the negative result above.

Each recommendation ships with the metric that tells you whether it worked.

---

## Repository

```
├── notebooks/
│   ├── 00_download_data.py        Parallel, resumable data fetch
│   ├── 01_etl_star_schema.py      ETL, feature engineering, DQ audit
│   ├── 02_build_warehouse.py      SQL warehouse: 5 tables, 7 indexes, 1 view
│   ├── 03_statistical_analysis.py 7 hypothesis tests + cost optimisation
│   └── 04_build_excel.py          7-sheet workbook with native charts
├── sql/
│   └── 01_business_analysis.sql   25 analyst queries, all validated
├── dashboard/
│   ├── app.py                     6-tab Streamlit dashboard
│   └── data/                      Pre-aggregated slices (~120 KB)
├── powerbi/
│   ├── measures.dax               40+ DAX measures
│   └── BUILD_GUIDE.md             Step-by-step report build
├── excel/
│   └── Fraud_Analytics_Workbook.xlsx
└── reports/
    ├── statistical_results.json
    ├── threshold_optimisation.csv
    └── sensitivity_analysis.csv
```

---

## Technical notes

**Star schema, not a flat file.** One fact table (882,468 rows) against four
conformed dimensions. Flat extracts don't scale in BI tools; a star schema
keeps every relationship many-to-one so DAX measures filter predictably.

**Indexing.** Seven indexes on the fact table take the heaviest analytical
query from ~1.4s to ~0.05s.

**No target leakage.** The `cust_avg_amount_todate` feature uses an expanding
mean that excludes the current row — a customer's baseline must not be
computed from the transaction being scored.

**A window-function bug worth documenting.** The Pareto query originally
placed its running total in the outer `SELECT` alongside a `WHERE rn IN (...)`
filter. SQL applies `WHERE` *before* SELECT-level window functions, so the
running sum accumulated over only the surviving rows and understated every
cumulative figure — silently, with no error. The fix materialises the
cumulative sum in a CTE before filtering. The corrected query is annotated in
`sql/01_business_analysis.sql`.

**Effect size over p-value.** At n = 882,468 almost any difference reaches
significance. Cramér's V and rank-biserial correlation are reported alongside
every p-value, because the p-value alone would have made time-of-day look
important.

**Wilson interval, not normal approximation.** At a proportion below 1% the
normal approximation is unreliable and can return a negative lower bound.

**Pre-aggregation for deployment.** The dashboard reads ~120 KB of
pre-computed slices rather than holding the fact table in memory, so it stays
responsive on a free-tier container.

---

## Data source and provenance

Transaction data comes from the **Université Libre de Bruxelles Machine
Learning Group**, published alongside the open handbook *Reproducible Machine
Learning for Credit Card Fraud Detection — Practical Handbook* (Le Borgne,
Siblini, Lebichot & Bontempi, 2022).

**This is simulated data, and that is stated plainly rather than implied.**
Production card data is never publicly released. This is the reference dataset
the fraud-detection research community uses precisely because it reproduces the
structural properties that matter — extreme class imbalance (0.786%),
entity-level attack patterns, and time-dependent behaviour — while remaining
freely redistributable. The same research group released the widely-cited
anonymised real-transaction dataset; this simulator was built to mirror it.

Every analytical method here — the schema design, the significance testing, the
cost model, the SQL — transfers unchanged to production data.

**Known limitations**, also stated in the dashboard:

- Labels are treated as ground truth. In production, confirmed-fraud labels
  arrive weeks late via chargebacks, so recent periods are always
  under-labelled and need a maturity window.
- Cost parameters are illustrative. The sensitivity grid exists so the
  recommendation can be re-checked against real figures.
- No merchant category or geography in the source, so segment-level risk could
  not be tested — usually the next most useful dimension after amount.
- These are transparent threshold rules, not a model. A supervised model would
  likely lift recall, at the cost of the explainability that makes a rule
  defensible to a regulator.

---

## Reproducing

```bash
pip install -r requirements.txt

python notebooks/00_download_data.py        # ~130 MB, 92 files, parallel
python notebooks/01_etl_star_schema.py
python notebooks/02_build_warehouse.py
python notebooks/03_statistical_analysis.py
python notebooks/04_build_excel.py

# SQL
sqlite3 data/fraud_warehouse.db < sql/01_business_analysis.sql

# Dashboard
streamlit run dashboard/app.py
```

Raw files, the 109 MB fact CSV and the 206 MB SQLite database are gitignored —
they exceed GitHub's 100 MB file limit and are fully regenerated by the
pipeline above. The Parquet fact table (21 MB) and all dimensions are
committed, so Power BI can be built without re-running anything.

---

**Abhishek Singh** · M.Sc Data Science, DA-IICT
[GitHub](https://github.com/Abhistic26) · [LinkedIn](https://linkedin.com/in/abhishek-singh-701405215) · abhiabhishek2615@gmail.com

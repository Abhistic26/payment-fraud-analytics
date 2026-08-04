# Power BI — Build Guide

Everything needed to reproduce the report from the files in this repo.
Estimated time: **45–60 minutes** the first time.

> **Prerequisite:** run the pipeline first so `data/star_schema/` exists.
> ```
> python notebooks/00_download_data.py
> python notebooks/01_etl_star_schema.py
> python notebooks/02_build_warehouse.py
> python notebooks/03_statistical_analysis.py
> ```

---

## 1. Load the data

**Home → Get data → Text/CSV** and load these four:

| File | Table | Rows |
|---|---|---|
| `data/star_schema/dim_date.csv` | `dim_date` | 92 |
| `data/star_schema/dim_customer.csv` | `dim_customer` | 4,983 |
| `data/star_schema/dim_terminal.csv` | `dim_terminal` | 10,000 |
| `data/star_schema/dim_amount_band.csv` | `dim_amount_band` | 7 |

For the fact table use the Parquet file — it loads roughly 5× faster than the
CSV and preserves data types, so you skip a round of manual type-fixing:

**Home → Get data → More → Parquet →** `data/star_schema/fact_transactions.parquet`
→ rename the query to `fact_transactions`.

### Type check in Power Query
Before **Close & Apply**, confirm in the Power Query editor:

- `txn_datetime` → Date/Time
- `amount`, `amount_vs_cust_avg`, `cust_avg_amount_todate` → Decimal Number
- `date_key`, `customer_id`, `terminal_id`, `txn_hour`, `is_fraud` → Whole Number
- `amount_band`, `part_of_day`, `fraud_type` → Text

Getting this right here avoids blank measures later. A numeric column silently
imported as Text is the single most common cause of a DAX measure returning
blank for no obvious reason.

---

## 2. Build the model

Go to **Model view**. Power BI will auto-detect some relationships — delete
them all and create these four explicitly, so you know exactly what the model
contains:

| From (many) | To (one) | Cardinality | Cross-filter |
|---|---|---|---|
| `fact_transactions[date_key]` | `dim_date[date_key]` | Many-to-one | Single |
| `fact_transactions[customer_id]` | `dim_customer[customer_id]` | Many-to-one | Single |
| `fact_transactions[terminal_id]` | `dim_terminal[terminal_id]` | Many-to-one | Single |
| `fact_transactions[amount_band]` | `dim_amount_band[amount_band]` | Many-to-one | Single |

All four should be **active** (solid line). Keep cross-filter direction
**Single** — bidirectional filtering on a star schema creates ambiguous filter
paths and is the usual cause of wrong totals.

### Mark the date table
Select `dim_date` → **Table tools → Mark as Date Table** → choose `date`.
Time-intelligence measures (`Fraud Loss PM`, `Fraud Rate 7D MA`) will not work
without this.

### Sort columns properly
Select `dim_date[month_name]` → **Column tools → Sort by column** → `month_no`.
Otherwise months sort alphabetically (Apr, Jul, Jun, May).

Do the same for `dim_date[day_name]` → sort by `day_of_week`.

---

## 3. Add the measures

1. **Home → Enter data**, name the table `_Measures`, click **Load**, then
   delete its blank `Column1` in the Data pane.
2. Open `powerbi/measures.dax`. For each measure: **Modeling → New measure**,
   paste, press Enter.
3. In the Data pane, drag every new measure into `_Measures`.
4. Set formats — this is what makes the report look finished rather than raw:
   - `Fraud Rate %`, `Value at Risk %`, `Recall %`, `Precision %` → Decimal, 2–3 dp
   - `Fraud Loss`, `Total Value`, `Net Benefit` → Whole number, thousands separator
   - `Risk Lift` → Decimal, 1 dp

### Create the threshold parameter
**Modeling → New parameter → Numeric range**

- Name: `Review Threshold`
- Minimum `20`, Maximum `600`, Increment `10`, Default `200`
- Tick **Add slicer to this page**

This creates the table the simulator measures reference.

---

## 4. Report pages

### Page 1 — Executive Summary

**KPI cards** (six across the top), each a Card visual:
`Total Transactions` · `Total Value` · `Fraud Transactions` · `Fraud Rate %` ·
`Fraud Loss` · `Value at Risk %`

**Fraud rate by amount band** — Clustered column chart
X: `dim_amount_band[amount_band]` · Y: `Fraud Rate %`
Add `Risk Lift` to Tooltips.

**Loss by typology** — Donut chart
Legend: `fact_transactions[fraud_type]` · Values: `Fraud Loss`
Filter out `Legitimate` in the Filters pane.

**Fraud trend** — Line chart
X: `dim_date[date]` · Y: `Fraud Rate %` and `Fraud Rate 7D MA`
Set the raw line to thin grey and the moving average to a bold accent colour.

**Slicers:** `dim_date[date]` (Between), `dim_customer[value_segment]`,
`dim_terminal[risk_tier]`.

### Page 2 — Terminal Watchlist

**Table visual** with `dim_terminal[terminal_id]`, `Total Transactions`,
`Fraud Transactions`, `Fraud Rate %`, `Fraud Loss`, `Risk Lift Label`,
`dim_terminal[risk_tier]`.

Conditional formatting: select the `Fraud Rate %` column →
**Format → Cell elements → Background colour → Format style: Field value →
based on `Risk Colour`**.

**Pareto chart** — Line and clustered column
X: `dim_terminal[terminal_id]` · Column: `Fraud Loss` · Line: `Cumulative Loss %`
Set Top N filter to 100 by `Fraud Loss`. This is the visual that shows a
small share of terminals carries most of the loss.

### Page 3 — Threshold Simulator

**Threshold slicer** at the top (created in step 3).

**Cards:** `Txns Flagged` · `Frauds Caught` · `Frauds Missed` · `Recall %` ·
`Precision %` · `Net Benefit`

**Narrative:** a Card (or Text box bound to a measure) showing
`Threshold Recommendation` — it rewrites itself as the slider moves.

**Trade-off chart** — Line chart
X: `'Review Threshold'[Review Threshold]` · Y: `Recall %` and `Precision %`

Format `Net Benefit` with **Cell elements → Font colour → Field value →
`Net Benefit Colour`** so it turns red when the rule stops paying for itself.

### Page 4 — Customer Segments

Matrix: rows `dim_customer[value_segment]`, values `Customers Affected`,
`Customer Impact Rate %`, `Fraud Rate %`, `Risk Lift`.

Heat map matrix: rows `fact_transactions[part_of_day]`,
columns `dim_amount_band[amount_band]`, values `Fraud Rate %`, with a
background colour scale.

---

## 5. Finishing

- **View → Page background** — set a light neutral (`#FAFAF9`) on every page.
- Give each visual a title that states the finding, not the field names.
  "Fraud concentrates above 200" beats "Fraud Rate % by amount_band".
- **File → Options → Current file → Report settings** — turn on
  *Change default visual interaction to cross-filter*.
- Publish: **Home → Publish → My workspace**, then **Share → Copy link** and
  set access to "Anyone with the link" so the URL works from a CV.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Measures return blank | `amount` imported as Text | Power Query → change type to Decimal |
| Time-intelligence errors | Date table not marked | Mark `dim_date` as Date Table |
| Months sort Apr, Jul, Jun | Sort-by-column not set | Sort `month_name` by `month_no` |
| Totals look wrong | Bidirectional filtering | Set all relationships to Single |
| Threshold slicer does nothing | Parameter table missing | Recreate via New parameter → Numeric range |
| Parquet option missing | Older Power BI build | Update, or load `fact_transactions.csv` instead |

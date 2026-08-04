/* ==========================================================================
   PAYMENT FRAUD ANALYTICS  --  BUSINESS ANALYSIS QUERY PACK
   --------------------------------------------------------------------------
   Author  : Abhishek Singh
   Engine  : SQLite 3  (ANSI-compatible; ports to Postgres / Fabric SQL)
   Dataset : 882,468 transactions | 4,983 customers | 10,000 terminals

   HOW TO RUN
     sqlite3 data/fraud_warehouse.db  < sql/01_business_analysis.sql

   Every query below answers a question a fraud-operations manager would
   actually ask in a review meeting. The question is stated first; the SQL
   is the answer.
   ========================================================================== */

.headers on
.mode column
.width 28 14 14 14 14


/* ==========================================================================
   SECTION A -- PORTFOLIO HEALTH
   ========================================================================== */

/* --------------------------------------------------------------------------
   Q1. What is the overall size and fraud exposure of the portfolio?
        -- the single slide an exec wants before anything else
   -------------------------------------------------------------------------- */
SELECT
    COUNT(*)                                              AS total_txns,
    COUNT(DISTINCT customer_id)                           AS customers,
    COUNT(DISTINCT terminal_id)                           AS terminals,
    ROUND(SUM(amount), 2)                                 AS total_value,
    SUM(is_fraud)                                         AS fraud_txns,
    ROUND(100.0 * SUM(is_fraud) / COUNT(*), 3)            AS fraud_rate_pct,
    ROUND(SUM(CASE WHEN is_fraud = 1 THEN amount END), 2) AS fraud_value,
    ROUND(100.0 * SUM(CASE WHEN is_fraud = 1 THEN amount ELSE 0 END)
                / SUM(amount), 3)                         AS value_at_risk_pct
FROM fact_transactions;


/* --------------------------------------------------------------------------
   Q2. Fraud costs more per incident than a normal sale earns.
        How much more?  -- justifies the whole investigation budget
   -------------------------------------------------------------------------- */
SELECT
    CASE is_fraud WHEN 1 THEN 'Fraudulent' ELSE 'Legitimate' END AS txn_class,
    COUNT(*)                                    AS txns,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 3) AS pct_of_txns,
    ROUND(AVG(amount), 2)                       AS avg_amount,
    ROUND(MIN(amount), 2)                       AS min_amount,
    ROUND(MAX(amount), 2)                       AS max_amount,
    ROUND(SUM(amount), 2)                       AS total_value,
    ROUND(100.0 * SUM(amount) / SUM(SUM(amount)) OVER (), 3) AS pct_of_value
FROM fact_transactions
GROUP BY is_fraud;


/* --------------------------------------------------------------------------
   Q3. Which fraud typology drives the most loss?
        -- tells the ops team where to build controls first
   -------------------------------------------------------------------------- */
SELECT
    fraud_type,
    COUNT(*)                                     AS incidents,
    ROUND(SUM(amount), 2)                        AS loss_value,
    ROUND(AVG(amount), 2)                        AS avg_loss,
    COUNT(DISTINCT customer_id)                  AS customers_hit,
    COUNT(DISTINCT terminal_id)                  AS terminals_involved,
    ROUND(100.0 * SUM(amount)
          / SUM(SUM(amount)) OVER (), 2)         AS pct_of_total_loss
FROM fact_transactions
WHERE is_fraud = 1
GROUP BY fraud_type
ORDER BY loss_value DESC;


/* ==========================================================================
   SECTION B -- WHERE THE RISK CONCENTRATES
   ========================================================================== */

/* --------------------------------------------------------------------------
   Q4. Does fraud rate rise with ticket size?
        -- the core input to any amount-based review threshold
   -------------------------------------------------------------------------- */
SELECT
    amount_band,
    COUNT(*)                                        AS txns,
    SUM(is_fraud)                                   AS fraud_txns,
    ROUND(100.0 * SUM(is_fraud) / COUNT(*), 3)      AS fraud_rate_pct,
    ROUND(SUM(CASE WHEN is_fraud=1 THEN amount ELSE 0 END), 2) AS fraud_value,
    -- lift vs the portfolio baseline: >1 means this band is riskier
    ROUND( (1.0 * SUM(is_fraud) / COUNT(*))
         / (SELECT 1.0 * SUM(is_fraud) / COUNT(*) FROM fact_transactions), 2
         )                                          AS risk_lift
FROM fact_transactions
GROUP BY amount_band
ORDER BY amount_band;


/* --------------------------------------------------------------------------
   Q5. What share of total fraud loss sits above each amount cut-off?
        -- running totals answer "if we review everything above X,
           how much loss do we cover?"
   -------------------------------------------------------------------------- */
WITH banded AS (
    SELECT
        amount_band,
        SUM(CASE WHEN is_fraud=1 THEN amount ELSE 0 END) AS fraud_value,
        COUNT(*)                                          AS txns
    FROM fact_transactions
    GROUP BY amount_band
)
SELECT
    amount_band,
    txns,
    ROUND(fraud_value, 2)                                        AS fraud_value,
    ROUND(SUM(fraud_value) OVER (ORDER BY amount_band DESC), 2)  AS cum_fraud_value,
    ROUND(100.0 * SUM(fraud_value) OVER (ORDER BY amount_band DESC)
          / SUM(fraud_value) OVER (), 2)                         AS cum_pct_of_loss,
    ROUND(100.0 * SUM(txns) OVER (ORDER BY amount_band DESC)
          / SUM(txns) OVER (), 2)                                AS cum_pct_of_txns
FROM banded
ORDER BY amount_band DESC;


/* --------------------------------------------------------------------------
   Q6. When during the day does fraud spike?
        -- drives analyst shift rostering
   -------------------------------------------------------------------------- */
SELECT
    txn_hour,
    COUNT(*)                                    AS txns,
    SUM(is_fraud)                               AS fraud_txns,
    ROUND(100.0 * SUM(is_fraud) / COUNT(*), 3)  AS fraud_rate_pct,
    ROUND(AVG(CASE WHEN is_fraud=1 THEN amount END), 2) AS avg_fraud_amount,
    -- flag hours running above the daily average fraud rate
    CASE WHEN 1.0 * SUM(is_fraud) / COUNT(*)
              > (SELECT 1.0 * SUM(is_fraud) / COUNT(*) FROM fact_transactions)
         THEN 'ABOVE BASELINE' ELSE 'normal' END AS status
FROM fact_transactions
GROUP BY txn_hour
ORDER BY fraud_rate_pct DESC;


/* --------------------------------------------------------------------------
   Q7. Weekday vs weekend -- is staffing aligned to actual risk?
   -------------------------------------------------------------------------- */
SELECT
    d.is_weekend,
    d.day_name,
    COUNT(*)                                        AS txns,
    SUM(f.is_fraud)                                 AS fraud_txns,
    ROUND(100.0 * SUM(f.is_fraud) / COUNT(*), 3)    AS fraud_rate_pct,
    ROUND(SUM(CASE WHEN f.is_fraud=1 THEN f.amount ELSE 0 END), 2) AS fraud_value
FROM fact_transactions f
JOIN dim_date d ON f.date_key = d.date_key
GROUP BY d.is_weekend, d.day_name, d.day_of_week
ORDER BY d.day_of_week;


/* ==========================================================================
   SECTION C -- TERMINAL (MERCHANT) RISK
   ========================================================================== */

/* --------------------------------------------------------------------------
   Q8. Top 20 highest-loss terminals -- the manual review worklist
   -------------------------------------------------------------------------- */
SELECT
    t.terminal_id,
    t.total_txns,
    t.fraud_txns,
    t.fraud_rate_pct,
    ROUND(t.fraud_volume, 2)    AS fraud_volume,
    t.unique_customers,
    t.risk_tier,
    RANK() OVER (ORDER BY t.fraud_volume DESC) AS loss_rank
FROM dim_terminal t
WHERE t.fraud_txns > 0
ORDER BY t.fraud_volume DESC
LIMIT 20;


/* --------------------------------------------------------------------------
   Q9. Pareto check -- do a small number of terminals carry most of the loss?
        -- if yes, targeted intervention beats blanket rules
   -------------------------------------------------------------------------- */
/* NOTE ON CORRECTNESS
   The running total MUST be materialised in a CTE before the WHERE clause
   picks out sample rows. SQL applies WHERE *before* the SELECT-level window
   functions, so filtering first would make the running SUM accumulate over
   only the surviving rows and silently understate every cumulative figure. */
WITH ranked AS (
    SELECT
        terminal_id,
        fraud_volume,
        ROW_NUMBER() OVER (ORDER BY fraud_volume DESC) AS rn
    FROM dim_terminal
    WHERE fraud_volume > 0
),
cumulative AS (
    SELECT
        rn,
        fraud_volume,
        SUM(fraud_volume) OVER (ORDER BY rn
              ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cum_fraud,
        SUM(fraud_volume) OVER ()                               AS total_fraud
    FROM ranked
)
SELECT
    rn                                                       AS terminals_reviewed,
    ROUND(100.0 * rn / (SELECT COUNT(*) FROM dim_terminal), 2)
                                                             AS pct_of_all_terminals,
    ROUND(cum_fraud, 2)                                      AS cum_fraud_recovered,
    ROUND(100.0 * cum_fraud / total_fraud, 2)                AS cum_pct_of_loss
FROM cumulative
WHERE rn IN (10, 25, 50, 100, 200, 300, 500, 750, 1000, 1500, 2000)
ORDER BY rn;


/* --------------------------------------------------------------------------
   Q10. Terminal risk tier summary -- how big is each review queue?
   -------------------------------------------------------------------------- */
SELECT
    risk_tier,
    COUNT(*)                                    AS terminals,
    SUM(total_txns)                             AS txns_covered,
    SUM(fraud_txns)                             AS fraud_txns,
    ROUND(SUM(fraud_volume), 2)                 AS fraud_volume,
    ROUND(100.0 * SUM(fraud_volume)
          / SUM(SUM(fraud_volume)) OVER (), 2)  AS pct_of_loss
FROM dim_terminal
GROUP BY risk_tier
ORDER BY risk_tier;


/* --------------------------------------------------------------------------
   Q11. Compromised-terminal attack windows.
         Scenario 2 fraud = a terminal is skimmed and abused for a period.
         How long does each attack run before it stops?
         -- directly sizes the detection-latency problem
   -------------------------------------------------------------------------- */
WITH attacks AS (
    SELECT
        terminal_id,
        MIN(DATE(txn_datetime)) AS first_fraud_day,
        MAX(DATE(txn_datetime)) AS last_fraud_day,
        COUNT(*)                AS fraud_txns,
        ROUND(SUM(amount), 2)   AS fraud_value
    FROM fact_transactions
    WHERE fraud_scenario = 2
    GROUP BY terminal_id
)
SELECT
    terminal_id,
    first_fraud_day,
    last_fraud_day,
    CAST(JULIANDAY(last_fraud_day) - JULIANDAY(first_fraud_day) AS INT) + 1
                                    AS attack_window_days,
    fraud_txns,
    fraud_value,
    ROUND(fraud_value / (CAST(JULIANDAY(last_fraud_day)
          - JULIANDAY(first_fraud_day) AS INT) + 1), 2) AS loss_per_day
FROM attacks
ORDER BY fraud_value DESC
LIMIT 15;


/* ==========================================================================
   SECTION D -- CUSTOMER RISK
   ========================================================================== */

/* --------------------------------------------------------------------------
   Q12. Are premium customers disproportionately targeted?
         -- if yes, retention risk, not just fraud loss
   -------------------------------------------------------------------------- */
SELECT
    c.value_segment,
    COUNT(DISTINCT c.customer_id)                       AS customers,
    SUM(c.total_txns)                                   AS txns,
    ROUND(SUM(c.total_spend), 2)                        AS spend,
    SUM(c.fraud_txns)                                   AS fraud_txns,
    ROUND(100.0 * SUM(c.fraud_txns) / SUM(c.total_txns), 3) AS fraud_rate_pct,
    SUM(CASE WHEN c.ever_compromised = 'Yes' THEN 1 ELSE 0 END) AS customers_hit,
    ROUND(100.0 * SUM(CASE WHEN c.ever_compromised='Yes' THEN 1 ELSE 0 END)
          / COUNT(*), 2)                                AS pct_customers_hit
FROM dim_customer c
GROUP BY c.value_segment
ORDER BY c.value_segment;


/* --------------------------------------------------------------------------
   Q13. Account-takeover signature: on a compromised account, how far above
         the customer's own normal spend does a fraudulent txn sit?
         -- this ratio is the strongest single behavioural rule available
   -------------------------------------------------------------------------- */
SELECT
    CASE is_fraud WHEN 1 THEN 'Fraudulent' ELSE 'Legitimate' END AS txn_class,
    COUNT(*)                                AS txns,
    ROUND(AVG(amount_vs_cust_avg), 2)       AS avg_ratio_to_own_baseline,
    ROUND(MAX(amount_vs_cust_avg), 2)       AS max_ratio,
    SUM(CASE WHEN amount_vs_cust_avg > 3 THEN 1 ELSE 0 END)  AS over_3x_baseline,
    ROUND(100.0 * SUM(CASE WHEN amount_vs_cust_avg > 3 THEN 1 ELSE 0 END)
          / COUNT(*), 2)                    AS pct_over_3x
FROM fact_transactions
WHERE amount_vs_cust_avg IS NOT NULL
GROUP BY is_fraud;


/* --------------------------------------------------------------------------
   Q14. Repeat victims -- customers hit more than once.
         -- a repeat victim is a churn risk and a process failure
   -------------------------------------------------------------------------- */
SELECT
    fraud_txns              AS times_defrauded,
    COUNT(*)                AS customers,
    ROUND(AVG(total_spend), 2) AS avg_lifetime_spend,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct_of_victims
FROM dim_customer
WHERE fraud_txns > 0
GROUP BY fraud_txns
ORDER BY times_defrauded DESC;


/* --------------------------------------------------------------------------
   Q15. Velocity signal -- do fraudulent txns cluster in rapid bursts?
   -------------------------------------------------------------------------- */
SELECT
    CASE
        WHEN mins_since_prev_txn <    60 THEN 'a. under 1 hour'
        WHEN mins_since_prev_txn <   360 THEN 'b. 1-6 hours'
        WHEN mins_since_prev_txn <  1440 THEN 'c. 6-24 hours'
        WHEN mins_since_prev_txn <  4320 THEN 'd. 1-3 days'
        ELSE                                  'e. over 3 days'
    END                                         AS gap_since_prev_txn,
    COUNT(*)                                    AS txns,
    SUM(is_fraud)                               AS fraud_txns,
    ROUND(100.0 * SUM(is_fraud) / COUNT(*), 3)  AS fraud_rate_pct
FROM fact_transactions
WHERE mins_since_prev_txn IS NOT NULL
GROUP BY gap_since_prev_txn
ORDER BY gap_since_prev_txn;


/* ==========================================================================
   SECTION E -- TREND & COHORT
   ========================================================================== */

/* --------------------------------------------------------------------------
   Q16. Daily fraud trend with a 7-day moving average.
         -- moving average strips weekday noise so a real shift is visible
   -------------------------------------------------------------------------- */
WITH daily AS (
    SELECT
        DATE(txn_datetime)                         AS txn_date,
        COUNT(*)                                   AS txns,
        SUM(is_fraud)                              AS fraud_txns,
        ROUND(SUM(CASE WHEN is_fraud=1 THEN amount ELSE 0 END), 2) AS fraud_value
    FROM fact_transactions
    GROUP BY DATE(txn_datetime)
)
SELECT
    txn_date,
    txns,
    fraud_txns,
    fraud_value,
    ROUND(100.0 * fraud_txns / txns, 3)                    AS fraud_rate_pct,
    ROUND(AVG(100.0 * fraud_txns / txns)
          OVER (ORDER BY txn_date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW), 3)
                                                           AS fraud_rate_7d_ma,
    ROUND(AVG(fraud_value)
          OVER (ORDER BY txn_date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW), 2)
                                                           AS fraud_value_7d_ma
FROM daily
ORDER BY txn_date;


/* --------------------------------------------------------------------------
   Q17. Week-over-week movement -- is the problem growing or contained?
   -------------------------------------------------------------------------- */
WITH weekly AS (
    SELECT
        d.week_no,
        MIN(d.date)                                 AS week_start,
        COUNT(*)                                    AS txns,
        SUM(f.is_fraud)                             AS fraud_txns,
        SUM(CASE WHEN f.is_fraud=1 THEN f.amount ELSE 0 END) AS fraud_value
    FROM fact_transactions f
    JOIN dim_date d ON f.date_key = d.date_key
    GROUP BY d.week_no
)
SELECT
    week_no,
    week_start,
    txns,
    fraud_txns,
    ROUND(fraud_value, 2)                                       AS fraud_value,
    LAG(fraud_txns) OVER (ORDER BY week_no)                     AS prev_week_fraud,
    ROUND(100.0 * (fraud_txns - LAG(fraud_txns) OVER (ORDER BY week_no))
          / NULLIF(LAG(fraud_txns) OVER (ORDER BY week_no), 0), 2)
                                                                AS wow_change_pct
FROM weekly
ORDER BY week_no;


/* --------------------------------------------------------------------------
   Q18. Days where fraud value breached the alert threshold
         (mean + 2 standard deviations) -- an auditable incident log.
         SQLite has no STDDEV, so it is computed from raw moments.
   -------------------------------------------------------------------------- */
WITH daily AS (
    SELECT DATE(txn_datetime) AS txn_date,
           SUM(CASE WHEN is_fraud=1 THEN amount ELSE 0 END) AS fraud_value
    FROM fact_transactions
    GROUP BY DATE(txn_datetime)
),
stats AS (
    SELECT
        AVG(fraud_value) AS mu,
        SQRT(AVG(fraud_value * fraud_value) - AVG(fraud_value) * AVG(fraud_value))
                         AS sigma
    FROM daily
)
SELECT
    d.txn_date,
    ROUND(d.fraud_value, 2)                     AS fraud_value,
    ROUND(s.mu, 2)                              AS mean_daily_loss,
    ROUND(s.mu + 2 * s.sigma, 2)                AS alert_threshold,
    ROUND((d.fraud_value - s.mu) / s.sigma, 2)  AS z_score
FROM daily d CROSS JOIN stats s
WHERE d.fraud_value > s.mu + 2 * s.sigma
ORDER BY d.fraud_value DESC;


/* ==========================================================================
   SECTION F -- DECISION SUPPORT
   ========================================================================== */

/* --------------------------------------------------------------------------
   Q19. Rule simulation: "review every transaction above X".
         For each candidate threshold, how much loss is caught and how many
         good customers get stopped?  -- the precision/recall trade-off,
         expressed in operational language.
   -------------------------------------------------------------------------- */
WITH thresholds(cutoff) AS (
    VALUES (100), (150), (200), (220), (250), (300), (400), (500)
),
sim AS (
    SELECT
        th.cutoff,
        SUM(CASE WHEN f.amount >= th.cutoff THEN 1 ELSE 0 END)     AS flagged,
        SUM(CASE WHEN f.amount >= th.cutoff AND f.is_fraud=1
                 THEN 1 ELSE 0 END)                                AS true_pos,
        SUM(CASE WHEN f.amount >= th.cutoff AND f.is_fraud=0
                 THEN 1 ELSE 0 END)                                AS false_pos,
        SUM(CASE WHEN f.amount <  th.cutoff AND f.is_fraud=1
                 THEN 1 ELSE 0 END)                                AS missed,
        SUM(CASE WHEN f.amount >= th.cutoff AND f.is_fraud=1
                 THEN f.amount ELSE 0 END)                         AS loss_prevented
    FROM fact_transactions f CROSS JOIN thresholds th
    GROUP BY th.cutoff
)
SELECT
    cutoff                                                   AS review_above,
    flagged                                                  AS txns_for_review,
    ROUND(100.0 * flagged
          / (SELECT COUNT(*) FROM fact_transactions), 2)     AS pct_txns_reviewed,
    true_pos                                                 AS frauds_caught,
    missed                                                   AS frauds_missed,
    ROUND(100.0 * true_pos / (true_pos + missed), 2)         AS recall_pct,
    ROUND(100.0 * true_pos / NULLIF(flagged, 0), 2)          AS precision_pct,
    ROUND(loss_prevented, 2)                                 AS loss_prevented,
    false_pos                                                AS good_customers_stopped
FROM sim
ORDER BY cutoff;


/* --------------------------------------------------------------------------
   Q20. Layered rule: high amount OR spend far above the customer's own
         baseline. Does combining signals beat a single amount cut-off?
   -------------------------------------------------------------------------- */
WITH tagged AS (
    SELECT
        is_fraud,
        amount,
        CASE
            WHEN amount >= 220                      THEN 'R1 high amount'
            WHEN amount_vs_cust_avg >= 4            THEN 'R2 vs own baseline'
            WHEN mins_since_prev_txn < 60
                 AND amount >= 100                  THEN 'R3 rapid + sizeable'
            ELSE                                         'not flagged'
        END AS rule_hit
    FROM fact_transactions
)
SELECT
    rule_hit,
    COUNT(*)                                        AS txns_flagged,
    SUM(is_fraud)                                   AS frauds_caught,
    ROUND(100.0 * SUM(is_fraud) / COUNT(*), 2)      AS precision_pct,
    ROUND(SUM(CASE WHEN is_fraud=1 THEN amount ELSE 0 END), 2) AS loss_prevented,
    ROUND(100.0 * SUM(is_fraud)
          / (SELECT SUM(is_fraud) FROM fact_transactions), 2)  AS pct_of_all_fraud
FROM tagged
GROUP BY rule_hit
ORDER BY frauds_caught DESC;


/* --------------------------------------------------------------------------
   Q21. Blind spot: what does a pure amount rule at 220 completely miss?
         -- every missed fraud here is a case for behavioural rules
   -------------------------------------------------------------------------- */
SELECT
    fraud_type,
    COUNT(*)                                AS frauds_missed,
    ROUND(SUM(amount), 2)                   AS loss_not_prevented,
    ROUND(AVG(amount), 2)                   AS avg_missed_amount,
    ROUND(AVG(amount_vs_cust_avg), 2)       AS avg_ratio_to_baseline
FROM fact_transactions
WHERE is_fraud = 1 AND amount < 220
GROUP BY fraud_type
ORDER BY loss_not_prevented DESC;


/* --------------------------------------------------------------------------
   Q22. Customer-level risk scorecard -- a ranked triage list ops can work
         top-down. Combines value at stake with incident history.
   -------------------------------------------------------------------------- */
WITH scored AS (
    SELECT
        c.customer_id,
        c.value_segment,
        c.total_txns,
        c.total_spend,
        c.fraud_txns,
        c.fraud_rate_pct,
        NTILE(5) OVER (ORDER BY c.total_spend)     AS spend_quintile,
        NTILE(5) OVER (ORDER BY c.fraud_rate_pct)  AS risk_quintile
    FROM dim_customer c
    WHERE c.fraud_txns > 0
)
SELECT
    customer_id,
    value_segment,
    total_txns,
    ROUND(total_spend, 2)   AS total_spend,
    fraud_txns,
    fraud_rate_pct,
    spend_quintile + risk_quintile                  AS priority_score,
    CASE WHEN spend_quintile + risk_quintile >= 9 THEN 'P1 - call today'
         WHEN spend_quintile + risk_quintile >= 7 THEN 'P2 - this week'
         ELSE                                          'P3 - monitor'
    END                                             AS action
FROM scored
ORDER BY priority_score DESC, total_spend DESC
LIMIT 25;


/* --------------------------------------------------------------------------
   Q23. Detection latency: on a compromised terminal, how many good
         transactions pass before the FIRST fraud appears?
         -- baseline for measuring any future detection system
   -------------------------------------------------------------------------- */
WITH first_fraud AS (
    SELECT terminal_id, MIN(txn_datetime) AS first_fraud_at
    FROM fact_transactions
    WHERE is_fraud = 1
    GROUP BY terminal_id
)
SELECT
    ff.terminal_id,
    ff.first_fraud_at,
    COUNT(f.transaction_id)          AS clean_txns_before_first_fraud,
    ROUND(SUM(f.amount), 2)          AS clean_value_before,
    t.fraud_txns                     AS total_frauds_on_terminal,
    ROUND(t.fraud_volume, 2)         AS total_fraud_loss
FROM first_fraud ff
JOIN fact_transactions f
      ON f.terminal_id  = ff.terminal_id
     AND f.txn_datetime < ff.first_fraud_at
JOIN dim_terminal t ON t.terminal_id = ff.terminal_id
GROUP BY ff.terminal_id, ff.first_fraud_at, t.fraud_txns, t.fraud_volume
ORDER BY total_fraud_loss DESC
LIMIT 15;


/* --------------------------------------------------------------------------
   Q24. Heat map source: fraud rate by hour band x amount band.
         -- feeds the Power BI matrix visual
   -------------------------------------------------------------------------- */
SELECT
    part_of_day,
    amount_band,
    COUNT(*)                                    AS txns,
    SUM(is_fraud)                               AS fraud_txns,
    ROUND(100.0 * SUM(is_fraud) / COUNT(*), 3)  AS fraud_rate_pct
FROM fact_transactions
GROUP BY part_of_day, amount_band
HAVING COUNT(*) > 100
ORDER BY fraud_rate_pct DESC
LIMIT 25;


/* --------------------------------------------------------------------------
   Q25. Executive one-pager: every headline number in a single result set.
         -- this is the query that backs the top row of the dashboard
   -------------------------------------------------------------------------- */
WITH base AS (
    SELECT COUNT(*) AS txns,
           SUM(is_fraud) AS frauds,
           SUM(amount) AS value,
           SUM(CASE WHEN is_fraud=1 THEN amount ELSE 0 END) AS fraud_value
    FROM fact_transactions
),
terms AS (
    SELECT COUNT(*) AS bad_terminals
    FROM dim_terminal WHERE risk_tier IN ('1 - Critical', '2 - High')
),
custs AS (
    SELECT COUNT(*) AS victims FROM dim_customer WHERE fraud_txns > 0
)
SELECT 'Total transactions'        AS metric, PRINTF('%,d', b.txns)                    AS value FROM base b
UNION ALL SELECT 'Total value processed',     PRINTF('%.2f', b.value)                  FROM base b
UNION ALL SELECT 'Fraudulent transactions',   PRINTF('%,d', b.frauds)                  FROM base b
UNION ALL SELECT 'Fraud rate (%)',            PRINTF('%.3f', 100.0*b.frauds/b.txns)    FROM base b
UNION ALL SELECT 'Gross fraud loss',          PRINTF('%.2f', b.fraud_value)            FROM base b
UNION ALL SELECT 'Value at risk (%)',         PRINTF('%.3f', 100.0*b.fraud_value/b.value) FROM base b
UNION ALL SELECT 'Avg loss per incident',     PRINTF('%.2f', b.fraud_value/b.frauds)   FROM base b
UNION ALL SELECT 'High-risk terminals',       PRINTF('%,d', t.bad_terminals)           FROM terms t
UNION ALL SELECT 'Customers impacted',        PRINTF('%,d', c.victims)                 FROM custs c;

/* ====================== END OF QUERY PACK ============================== */

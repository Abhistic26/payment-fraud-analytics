"""
Payment Fraud Analytics -- interactive dashboard
Author: Abhishek Singh

Reads pre-aggregated slices (~120 KB total). Aggregation happens once in the
pipeline rather than on every page load, so the deployed app stays responsive
on a free-tier container instead of holding an 880k-row frame in memory.
"""

import os
import json

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(
    page_title="Payment Fraud Analytics",
    page_icon="*",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Design tokens
# ---------------------------------------------------------------------------
INK = "#12192B"
INK_SOFT = "#5A6478"
GOLD = "#B8934A"
RISK = "#C0392B"
SAFE = "#0F766E"
LINE = "#E3E0D8"
PAPER = "#FAF9F6"

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@500&display=swap');

.stApp { background: PAPER_C; }
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 2.2rem; max-width: 1400px; }

h1, h2, h3 { font-family: 'Fraunces', Georgia, serif !important;
             color: INK_C !important; letter-spacing: -0.015em; }

.masthead { border-bottom: 2px solid INK_C; padding-bottom: 1rem;
            margin-bottom: 1.6rem; }
.masthead .eyebrow { font-size: .68rem; letter-spacing: .18em;
            text-transform: uppercase; color: GOLD_C; font-weight: 600; }
.masthead h1 { font-size: 2.3rem; margin: .25rem 0 .3rem 0; font-weight: 600; }
.masthead .meta { font-size: .82rem; color: SOFT_C; }

.kpi { background: #fff; border: 1px solid LINE_C; border-top: 3px solid INK_C;
       padding: .95rem 1.05rem; height: 100%; }
.kpi .lab { font-size: .62rem; letter-spacing: .12em; text-transform: uppercase;
       color: SOFT_C; font-weight: 600; }
.kpi .val { font-family: 'Fraunces', serif; font-size: 1.85rem; font-weight: 600;
       color: INK_C; line-height: 1.15; margin-top: .3rem; }
.kpi .sub { font-size: .72rem; color: SOFT_C; margin-top: .15rem; }
.kpi.alert { border-top-color: RISK_C; }
.kpi.alert .val { color: RISK_C; }

.finding { background: #fff; border-left: 3px solid GOLD_C; padding: 1.1rem 1.3rem;
       margin: .6rem 0 1.1rem 0; border-top: 1px solid LINE_C;
       border-right: 1px solid LINE_C; border-bottom: 1px solid LINE_C; }
.finding .tag { font-size: .62rem; letter-spacing: .14em; text-transform: uppercase;
       color: GOLD_C; font-weight: 600; }
.finding p { margin: .45rem 0 0 0; color: #2B3244; font-size: .93rem;
       line-height: 1.62; }

.rec { background: #fff; border: 1px solid LINE_C; border-left: 3px solid SAFE_C;
       padding: 1rem 1.2rem; margin-bottom: .8rem; }
.rec .n { font-family: 'JetBrains Mono', monospace; font-size: .72rem;
       color: SAFE_C; font-weight: 600; }
.rec .t { font-weight: 600; color: INK_C; margin-top: .2rem; font-size: .95rem; }
.rec .d { color: SOFT_C; font-size: .87rem; margin-top: .3rem; line-height: 1.6; }

.sec { font-family: 'Fraunces', serif; font-size: 1.15rem; font-weight: 600;
       color: INK_C; border-bottom: 1px solid LINE_C; padding-bottom: .4rem;
       margin: 1.6rem 0 .9rem 0; }

.stTabs [data-baseweb="tab-list"] { gap: 1.6rem; border-bottom: 1px solid LINE_C; }
.stTabs [data-baseweb="tab"] { font-size: .85rem; font-weight: 500;
       color: SOFT_C; padding: .5rem 0; }
.stTabs [aria-selected="true"] { color: INK_C !important; font-weight: 600; }

[data-testid="stSidebar"] { background: #fff; border-right: 1px solid LINE_C; }
.stDataFrame { border: 1px solid LINE_C; }
</style>
"""

CSS = (CSS.replace("PAPER_C", PAPER).replace("INK_C", INK)
          .replace("SOFT_C", INK_SOFT).replace("GOLD_C", GOLD)
          .replace("RISK_C", RISK).replace("SAFE_C", SAFE)
          .replace("LINE_C", LINE))

st.markdown(CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Data loading
#   Files are looked for in dashboard/data/ first, then the repo root, so the
#   app works whether or not the data folder survived upload.
# ---------------------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
CANDIDATES = [
    os.path.join(HERE, "data"),
    os.path.join(HERE, ".."),
    HERE,
]

FILES = ["agg_band", "agg_daily", "agg_type", "agg_hour", "agg_heatmap",
         "agg_segment", "top_terminals", "pareto", "thresholds",
         "sensitivity", "amount_hist"]


def _find(name, ext):
    for base in CANDIDATES:
        p = os.path.join(base, name + ext)
        if os.path.exists(p):
            return p
    return None


@st.cache_data
def load():
    out = {}
    missing = []
    for n in FILES:
        p = _find(n, ".csv")
        if p is None:
            missing.append(n + ".csv")
        else:
            out[n] = pd.read_csv(p)
    p = _find("stats", ".json")
    if p is None:
        missing.append("stats.json")
    else:
        with open(p) as fh:
            out["stats"] = json.load(fh)
    if missing:
        return None, missing
    out["agg_daily"]["txn_date"] = pd.to_datetime(out["agg_daily"]["txn_date"])
    return out, []


data, missing = load()

if data is None:
    st.error("Data files not found.")
    st.write("Missing:", ", ".join(missing))
    st.write("Looked in:", " | ".join(CANDIDATES))
    st.stop()

S = data["stats"]
daily = data["agg_daily"]
band = data["agg_band"]
typ = data["agg_type"]

TOT_TXN = int(daily["txns"].sum())
TOT_FRAUD = int(daily["fraud_txns"].sum())
TOT_VAL = float(daily["total_value"].sum())
FRAUD_VAL = float(daily["fraud_value"].sum())
FRAUD_RATE = 100.0 * TOT_FRAUD / TOT_TXN
VAR_PCT = 100.0 * FRAUD_VAL / TOT_VAL


# ---------------------------------------------------------------------------
# Chart layout helper
#   Returns a fresh layout dict each call. Building the dict first and passing
#   it as a single ** argument avoids any ordering or duplicate-key issues
#   across plotly versions.
# ---------------------------------------------------------------------------
def L(**overrides):
    base = {
        "paper_bgcolor": "white",
        "plot_bgcolor": "white",
        "font": {"family": "Inter, sans-serif", "size": 12, "color": INK},
        "margin": {"l": 10, "r": 10, "t": 46, "b": 10},
        "xaxis": {"gridcolor": "#F0EEE8", "linecolor": LINE, "zeroline": False},
        "yaxis": {"gridcolor": "#F0EEE8", "linecolor": LINE, "zeroline": False},
        "hoverlabel": {"bgcolor": "white", "bordercolor": LINE,
                       "font": {"family": "Inter", "size": 12, "color": INK}},
        "title": {"font": {"family": "Fraunces, serif", "size": 15,
                           "color": INK}, "x": 0},
    }
    for k, v in overrides.items():
        base[k] = v
    return base


def kpi_html(label, value, sub="", alert=False):
    cls = "kpi alert" if alert else "kpi"
    return ('<div class="' + cls + '">'
            '<div class="lab">' + str(label) + '</div>'
            '<div class="val">' + str(value) + '</div>'
            '<div class="sub">' + str(sub) + '</div></div>')


def finding(tag, text):
    st.markdown('<div class="finding"><div class="tag">' + tag + '</div><p>'
                + text + '</p></div>', unsafe_allow_html=True)


def section(title):
    st.markdown('<div class="sec">' + title + '</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Masthead
# ---------------------------------------------------------------------------
d_min = daily["txn_date"].min()
d_max = daily["txn_date"].max()

st.markdown(
    '<div class="masthead">'
    '<div class="eyebrow">Fraud Risk &middot; Portfolio Review</div>'
    '<h1>Payment Fraud Analytics</h1>'
    '<div class="meta">' + format(TOT_TXN, ",") + ' transactions &nbsp;&middot;&nbsp; '
    '4,983 customers &nbsp;&middot;&nbsp; 10,000 terminals &nbsp;&middot;&nbsp; '
    + d_min.strftime("%d %b") + ' &ndash; ' + d_max.strftime("%d %b %Y") +
    '</div></div>',
    unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### Review policy")
    st.caption("Set the manual-review rule and the cost of running it. "
               "Every figure on the Decision tab responds.")

    thr = st.select_slider("Review transactions above",
                           options=list(range(20, 601, 10)), value=200)
    st.markdown("---")
    st.markdown("**Cost assumptions**")
    c_rev = st.number_input("Cost per manual review", 0.5, 20.0, 3.0, 0.5)
    c_fd = st.number_input("Cost of a false decline", 1.0, 60.0, 12.0, 1.0)
    recov = st.slider("Recovery rate on caught fraud", 0.0, 1.0, 0.75, 0.05)

    st.markdown("---")
    st.caption("**Data** - ULB Machine Learning Group transaction simulator, "
               "published with *Reproducible Machine Learning for Credit Card "
               "Fraud Detection* (Le Borgne et al., 2022). 92 daily files.")

# ---------------------------------------------------------------------------
# KPI strip
# ---------------------------------------------------------------------------
ci_lo = S["test4_fraud_rate_ci"]["ci_lower_pct"]
ci_hi = S["test4_fraud_rate_ci"]["ci_upper_pct"]

kpis = [
    ("Transactions", format(round(TOT_TXN / 1000), ",") + "K", "92 days", False),
    ("Value processed", "{:.1f}M".format(TOT_VAL / 1e6), "gross", False),
    ("Fraud cases", format(TOT_FRAUD, ","), "confirmed", True),
    ("Fraud rate", "{:.3f}%".format(FRAUD_RATE),
     "CI {:.3f}-{:.3f}%".format(ci_lo, ci_hi), True),
    ("Gross loss", "{:.0f}K".format(FRAUD_VAL / 1000), "before recovery", True),
    ("Value at risk", "{:.2f}%".format(VAR_PCT), "of throughput", True),
]

cols = st.columns(6)
for col, item in zip(cols, kpis):
    col.markdown(kpi_html(item[0], item[1], item[2], item[3]),
                 unsafe_allow_html=True)

st.markdown("")

tabs = st.tabs(["Overview", "Where risk sits", "Terminals",
                "Decision model", "Statistical basis", "Recommendations"])

# ===========================================================================
# TAB 1 -- OVERVIEW
# ===========================================================================
with tabs[0]:
    ratio = S["test1_amount"]["mean_fraud"] / S["test1_amount"]["mean_legit"]
    top_type = typ.iloc[0]
    finding(
        "Headline",
        "Fraud runs at <b>{:.3f}%</b> of transactions but <b>{:.2f}%</b> of "
        "value - fraudulent transactions are {:.1f}x larger than legitimate "
        "ones on average. Loss concentrates in <b>{}</b>, which accounts for "
        "{:.0f}% of total loss from {:.0f}% of incidents.".format(
            FRAUD_RATE, VAR_PCT, ratio, top_type["fraud_type"],
            100.0 * top_type["loss_value"] / FRAUD_VAL,
            100.0 * top_type["incidents"] / TOT_FRAUD))

    c1, c2 = st.columns([1.65, 1])

    with c1:
        fig = go.Figure()
        fig.add_bar(x=daily["txn_date"], y=daily["fraud_value"],
                    name="Daily loss", marker_color="#DCD8CE",
                    hovertemplate="%{x|%d %b}<br>Loss %{y:,.0f}<extra></extra>")
        fig.add_scatter(x=daily["txn_date"], y=daily["fraud_rate_7d_ma"],
                        name="Fraud rate 7d avg (%)", yaxis="y2",
                        line={"color": RISK, "width": 2.2},
                        hovertemplate="%{x|%d %b}<br>%{y:.3f}%<extra></extra>")
        fig.update_layout(**L(
            height=330,
            title={"text": "Daily loss and smoothed fraud rate",
                   "font": {"family": "Fraunces, serif", "size": 15,
                            "color": INK}, "x": 0},
            yaxis2={"overlaying": "y", "side": "right", "showgrid": False,
                    "tickformat": ".2f"},
            legend={"orientation": "h", "y": 1.08, "x": 0,
                    "bgcolor": "rgba(0,0,0,0)"}))
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        fig = go.Figure(go.Pie(
            labels=typ["fraud_type"], values=typ["loss_value"], hole=0.58,
            marker={"colors": [RISK, "#D98C5F", GOLD],
                    "line": {"color": "white", "width": 2}},
            textinfo="percent", textfont={"size": 12, "color": "white"},
            hovertemplate="%{label}<br>%{value:,.0f}<extra></extra>"))
        fig.update_layout(**L(
            height=330,
            title={"text": "Share of loss by typology",
                   "font": {"family": "Fraunces, serif", "size": 15,
                            "color": INK}, "x": 0},
            legend={"orientation": "h", "y": -0.12, "x": 0,
                    "font": {"size": 10}}))
        st.plotly_chart(fig, use_container_width=True)

    section("Fraud typologies")
    tbl = typ.copy()
    tbl["share_of_loss_pct"] = (100.0 * tbl["loss_value"] / FRAUD_VAL).round(1)
    tbl = tbl.rename(columns={
        "fraud_type": "Typology", "incidents": "Incidents",
        "loss_value": "Loss value", "avg_loss": "Avg loss",
        "customers_hit": "Customers hit", "terminals": "Terminals",
        "share_of_loss_pct": "Share of loss %"})
    st.dataframe(tbl, use_container_width=True, hide_index=True)

    st.caption("**Reading this:** Terminal Compromise produces the most "
               "incidents but the smallest average loss - it is a volume "
               "problem. Account Takeover is the reverse: fewer cases, far "
               "larger each. They need different controls, and a single "
               "blanket rule will handle neither well.")

# ===========================================================================
# TAB 2 -- WHERE RISK SITS
# ===========================================================================
with tabs[1]:
    base_rate = FRAUD_RATE
    b = band.copy()
    b["lift"] = (b["fraud_rate_pct"] / base_rate).round(1)

    c1, c2 = st.columns(2)

    with c1:
        colours = []
        for v in b["fraud_rate_pct"]:
            if v > base_rate * 2:
                colours.append(RISK)
            elif v > base_rate:
                colours.append(GOLD)
            else:
                colours.append("#C9CEDB")

        fig = go.Figure(go.Bar(
            x=b["amount_band"], y=b["fraud_rate_pct"],
            marker_color=colours,
            text=["{:.2f}%".format(v) for v in b["fraud_rate_pct"]],
            textposition="outside",
            hovertemplate="%{x}<br>%{y:.3f}%<extra></extra>"))
        fig.add_hline(y=base_rate,
                      line={"color": INK_SOFT, "width": 1, "dash": "dot"},
                      annotation_text="portfolio {:.3f}%".format(base_rate))
        fig.update_layout(**L(
            height=360, showlegend=False,
            title={"text": "Fraud rate by amount band",
                   "font": {"family": "Fraunces, serif", "size": 15,
                            "color": INK}, "x": 0},
            xaxis={"gridcolor": "#F0EEE8", "linecolor": LINE,
                   "zeroline": False, "tickangle": -35,
                   "tickfont": {"size": 10}}))
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        hist = data["amount_hist"]
        fig = go.Figure()
        for flag, nm, colr in [(0, "Legitimate", "#C9CEDB"),
                               (1, "Fraudulent", RISK)]:
            sub = hist[hist["is_fraud"] == flag]
            tot = sub["n"].sum()
            pct = sub["n"] / tot * 100.0 if tot else sub["n"]
            fig.add_bar(x=sub["bin"], y=pct, name=nm, marker_color=colr,
                        opacity=0.85,
                        hovertemplate=nm + "<br>%{x}<br>%{y:.2f}%<extra></extra>")
        fig.update_layout(**L(
            height=360, barmode="overlay",
            title={"text": "Amount distribution (% within class)",
                   "font": {"family": "Fraunces, serif", "size": 15,
                            "color": INK}, "x": 0},
            legend={"orientation": "h", "y": 1.08, "x": 0,
                    "bgcolor": "rgba(0,0,0,0)"}))
        st.plotly_chart(fig, use_container_width=True)

    low3_txns = int(b.iloc[:3]["txns"].sum())
    low3_fraud = int(b.iloc[:3]["fraud_txns"].sum())
    hi_band = b.iloc[-2]
    finding(
        "Where the risk actually is",
        "Risk rises sharply with ticket size: the <b>{}</b> band carries "
        "<b>{:.0f}x</b> the portfolio rate. But volume sits at the other end "
        "- the three lowest bands hold <b>{:.0f}%</b> of all transactions and "
        "still contribute <b>{}</b> fraud cases. High rate and high volume are "
        "in different places, which is exactly why a single cut-off cannot "
        "solve this.".format(
            hi_band["amount_band"], hi_band["lift"],
            100.0 * low3_txns / int(b["txns"].sum()), format(low3_fraud, ",")))

    section("Timing - and why it is not a lever")
    c1, c2 = st.columns([1.5, 1])

    with c1:
        hr = data["agg_hour"]
        fig = go.Figure(go.Scatter(
            x=hr["txn_hour"], y=hr["fraud_rate_pct"], mode="lines+markers",
            line={"color": INK, "width": 2}, marker={"size": 6, "color": INK},
            hovertemplate="%{x}:00<br>%{y:.3f}%<extra></extra>"))
        fig.add_hline(y=base_rate,
                      line={"color": RISK, "width": 1, "dash": "dot"})
        fig.update_layout(**L(
            height=300,
            title={"text": "Fraud rate by hour of day (%)",
                   "font": {"family": "Fraunces, serif", "size": 15,
                            "color": INK}, "x": 0},
            yaxis={"gridcolor": "#F0EEE8", "linecolor": LINE,
                   "zeroline": False,
                   "range": [base_rate * 0.8, base_rate * 1.2]}))
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        v_time = S["test2_timing"]["cramers_v"]
        v_amt = S["test3_amount_band"]["cramers_v"]
        st.markdown(
            '<div class="finding" style="margin-top:2.4rem">'
            '<div class="tag">Negative result</div>'
            '<p>Chi-square gives Cramer\'s V of <b>{:.4f}</b> for time-of-day '
            'against <b>{:.4f}</b> for amount band - a <b>{:.0f}x</b> '
            'difference in association strength. Note the y-axis is zoomed to '
            '&plusmn;20% of the mean; on a full scale the line is flat.</p>'
            '<p>The hourly variation here is noise. Rostering reviewers by '
            'hour would spend real budget against a non-effect.</p>'
            '</div>'.format(v_time, v_amt, v_amt / v_time),
            unsafe_allow_html=True)

    section("Fraud rate by period and ticket size")
    hm = data["agg_heatmap"].pivot(index="part_of_day", columns="amount_band",
                                   values="fraud_rate_pct")
    fig = px.imshow(hm, color_continuous_scale=["#FFFFFF", "#F5D7A8", RISK],
                    aspect="auto", labels={"color": "Fraud %"})
    fig.update_layout(**L(
        height=290,
        xaxis={"tickangle": -30, "tickfont": {"size": 10}, "side": "bottom"}))
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Colour varies almost entirely left-to-right (amount) and "
               "barely top-to-bottom (time) - the same conclusion the "
               "significance tests reach, shown visually.")

# ===========================================================================
# TAB 3 -- TERMINALS
# ===========================================================================
with tabs[2]:
    par = data["pareto"]
    tt = data["top_terminals"]

    at5 = float(par[par["pct_terminals"] <= 5]["cum_pct"].max())
    at10 = float(par[par["pct_terminals"] <= 10]["cum_pct"].max())

    c1, c2 = st.columns([1.5, 1])

    with c1:
        fig = go.Figure(go.Scatter(
            x=par["pct_terminals"], y=par["cum_pct"], mode="lines",
            line={"color": INK, "width": 2.4}, fill="tozeroy",
            fillcolor="rgba(18,25,43,0.06)",
            hovertemplate="Top %{x:.1f}% of terminals<br>"
                          "%{y:.1f}% of loss<extra></extra>"))
        for xv, yv in [(5, at5), (10, at10)]:
            fig.add_scatter(x=[xv], y=[yv], mode="markers+text",
                            marker={"size": 9, "color": RISK},
                            text=["  {:.0f}%".format(yv)],
                            textposition="middle right",
                            textfont={"size": 11, "color": RISK},
                            showlegend=False, hoverinfo="skip")
        fig.update_layout(**L(
            height=360, showlegend=False,
            title={"text": "Loss concentration across the terminal estate",
                   "font": {"family": "Fraunces, serif", "size": 15,
                            "color": INK}, "x": 0},
            xaxis={"gridcolor": "#F0EEE8", "linecolor": LINE,
                   "zeroline": False, "range": [0, 25],
                   "title": "% of terminals, worst first"},
            yaxis={"gridcolor": "#F0EEE8", "linecolor": LINE,
                   "zeroline": False, "title": "% of total loss"}))
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        st.markdown(
            '<div class="finding" style="margin-top:2.4rem">'
            '<div class="tag">Concentration</div>'
            '<p>The worst <b>5%</b> of terminals carry <b>{:.0f}%</b> of all '
            'fraud loss. The worst <b>10%</b> carry <b>{:.0f}%</b>.</p>'
            '<p>This is what makes targeted review viable. A watchlist of a '
            'few hundred terminals reaches most of the exposure - a blanket '
            'amount rule touches every transaction in the portfolio to reach '
            'the same place.</p></div>'.format(at5, at10),
            unsafe_allow_html=True)

    section("Watchlist - highest loss terminals")
    tiers = sorted(tt["risk_tier"].unique().tolist())
    chosen = st.multiselect("Risk tier", tiers, default=tiers)
    if not chosen:
        chosen = tiers

    view = tt[tt["risk_tier"].isin(chosen)].head(60).copy()
    view = view.rename(columns={
        "terminal_id": "Terminal", "total_txns": "Txns",
        "fraud_txns": "Fraud txns", "fraud_rate_pct": "Fraud rate %",
        "fraud_volume": "Fraud loss", "unique_customers": "Customers",
        "risk_tier": "Risk tier"})
    st.dataframe(view, use_container_width=True, hide_index=True, height=380)

# ===========================================================================
# TAB 4 -- DECISION MODEL
# ===========================================================================
with tabs[3]:
    th = data["thresholds"].copy()

    # Recompute economics live against the sidebar assumptions.
    # frauds_missed is derived here rather than read from file -- the
    # threshold table stores only what was caught.
    th["frauds_missed"] = TOT_FRAUD - th["frauds_caught"]
    th["op_cost_live"] = th["txns_flagged"] * c_rev + th["false_positives"] * c_fd
    th["prevented_live"] = th["loss_prevented"] / 0.75 * recov
    th["net_live"] = th["prevented_live"] - th["op_cost_live"] - th["residual_loss"]

    idx = (th["threshold"] - thr).abs().idxmin()
    cur = th.loc[idx]
    opt = th.loc[th["net_live"].idxmax()]

    cells = [
        ("Flagged for review", format(int(cur["txns_flagged"]), ","),
         "{:.2f}% of volume".format(100.0 * cur["txns_flagged"] / TOT_TXN), False),
        ("Fraud caught", format(int(cur["frauds_caught"]), ","),
         "recall {:.1f}%".format(cur["recall_pct"]), False),
        ("Precision", "{:.1f}%".format(cur["precision_pct"]),
         format(int(cur["false_positives"]), ",") + " false alarms", False),
        ("Fraud missed", format(int(cur["frauds_missed"]), ","),
         "{:,.0f} residual".format(cur["residual_loss"]), True),
        ("Net benefit", "{:,.0f}".format(cur["net_live"]),
         "at your assumptions", bool(cur["net_live"] < 0)),
    ]
    cs = st.columns(5)
    for col, item in zip(cs, cells):
        col.markdown(kpi_html(item[0], item[1], item[2], item[3]),
                     unsafe_allow_html=True)

    st.markdown("")
    c1, c2 = st.columns(2)

    with c1:
        fig = go.Figure(go.Scatter(
            x=th["threshold"], y=th["net_live"], mode="lines",
            line={"color": SAFE, "width": 2.4},
            hovertemplate="Above %{x}<br>Net %{y:,.0f}<extra></extra>"))
        fig.add_hline(y=0, line={"color": INK_SOFT, "width": 1})
        fig.add_vline(x=float(opt["threshold"]),
                      line={"color": GOLD, "width": 1.5, "dash": "dash"},
                      annotation_text="optimum {}".format(int(opt["threshold"])))
        fig.add_vline(x=thr, line={"color": RISK, "width": 1.5},
                      annotation_text="your setting",
                      annotation_position="top left")
        fig.update_layout(**L(
            height=340, showlegend=False,
            title={"text": "Net benefit by review threshold",
                   "font": {"family": "Fraunces, serif", "size": 15,
                            "color": INK}, "x": 0}))
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        fig = go.Figure()
        fig.add_scatter(x=th["threshold"], y=th["recall_pct"], name="Recall",
                        line={"color": RISK, "width": 2.2})
        fig.add_scatter(x=th["threshold"], y=th["precision_pct"],
                        name="Precision", line={"color": INK, "width": 2.2})
        fig.add_vline(x=thr, line={"color": GOLD, "width": 1.5, "dash": "dot"})
        fig.update_layout(**L(
            height=340,
            title={"text": "Precision / recall trade-off",
                   "font": {"family": "Fraunces, serif", "size": 15,
                            "color": INK}, "x": 0},
            legend={"orientation": "h", "y": 1.08, "x": 0,
                    "bgcolor": "rgba(0,0,0,0)"}))
        st.plotly_chart(fig, use_container_width=True)

    gap = thr - int(opt["threshold"])
    if abs(gap) <= 10:
        verdict = "matches"
    elif gap < 0:
        verdict = "sits below"
    else:
        verdict = "sits above"

    finding(
        "Reading the model",
        "At a cut-off of <b>{}</b> the rule flags {} transactions and returns "
        "a net benefit of <b>{:,.0f}</b>. That {} the optimum of <b>{}</b> "
        "({:,.0f}). The curve is steep on the left: lowering the cut-off pulls "
        "in false positives far faster than fraud, and the rule stops paying "
        "for itself well before it catches most of the loss.".format(
            thr, format(int(cur["txns_flagged"]), ","), cur["net_live"],
            verdict, int(opt["threshold"]), opt["net_live"]))

    section("Does the answer survive different costs?")
    c1, c2 = st.columns([1, 1.2])

    with c1:
        sv = data["sensitivity"].pivot(index="review_cost",
                                       columns="false_decline_cost",
                                       values="optimal_threshold")
        fig = px.imshow(sv, text_auto=True, aspect="auto",
                        color_continuous_scale=["#EEF2F7", "#9FB0C9"],
                        labels={"x": "False-decline cost",
                                "y": "Review cost", "color": "Optimal"})
        fig.update_layout(**L(
            height=280, coloraxis_showscale=False,
            title={"text": "Optimal threshold across cost scenarios",
                   "font": {"family": "Fraunces, serif", "size": 15,
                            "color": INK}, "x": 0}))
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        rng = S["test6_sensitivity"]["threshold_range"]
        st.markdown(
            '<div class="finding" style="margin-top:2rem">'
            '<div class="tag">Robustness</div>'
            '<p>Re-solving across nine cost scenarios - review cost from 1.5 '
            'to 6, false-decline cost from 6 to 24 - moves the optimum only '
            'between <b>{}</b> and <b>{}</b>.</p>'
            '<p>A recommendation that flips when an assumption moves 20% is '
            'not a recommendation. This one holds, so it is safe to act on '
            'before the exact cost figures are agreed.</p>'
            '</div>'.format(rng[0], rng[1]), unsafe_allow_html=True)

# ===========================================================================
# TAB 5 -- STATISTICAL BASIS
# ===========================================================================
with tabs[4]:
    st.markdown("Every claim on the preceding tabs traces to one of these "
                "tests. Assumptions were checked before each test was chosen "
                "- a test applied without checking its assumptions gives a "
                "confident wrong answer.")

    t1 = S["test1_amount"]
    section("1 &nbsp; Are fraudulent transactions larger?")
    cs = st.columns(4)
    cs[0].metric("Test", "Mann-Whitney U")
    cs[1].metric("p-value", "{:.2e}".format(t1["p_value"]))
    cs[2].metric("Effect size",
                 "{:.3f}".format(t1["effect_size_rank_biserial"]))
    cs[3].metric("Median fraud / legit",
                 "{:.0f} / {:.0f}".format(t1["median_fraud"],
                                          t1["median_legit"]))
    st.caption("Amounts are heavily right-skewed, so normality fails and a "
               "t-test would be invalid. Mann-Whitney compares ranks and makes "
               "no distributional assumption. At n=882,468 the p-value is near "
               "certain to be small, so the rank-biserial effect size is the "
               "figure that actually matters.")

    t2 = S["test2_timing"]
    t3 = S["test3_amount_band"]
    section("2 &nbsp; Which dimensions carry real signal?")
    cmp_tbl = pd.DataFrame({
        "Dimension": ["Amount band", "Time of day"],
        "Chi-square": ["{:,.0f}".format(t3["chi2"]),
                       "{:,.1f}".format(t2["chi2"])],
        "p-value": ["{:.2e}".format(t3["p_value"]),
                    "{:.3f}".format(t2["p_value"])],
        "Cramers V": ["{:.4f}".format(t3["cramers_v"]),
                      "{:.4f}".format(t2["cramers_v"])],
        "Strength": ["Strong - build controls here",
                     "Negligible - not actionable"],
    })
    st.dataframe(cmp_tbl, use_container_width=True, hide_index=True)
    st.caption("Cramer's V rescales chi-square to 0-1 so the two dimensions "
               "can be compared directly. Reporting the p-value alone would "
               "make both look important; the effect sizes differ by roughly "
               "{:.0f}x.".format(t3["cramers_v"] / t2["cramers_v"]))

    t4 = S["test4_fraud_rate_ci"]
    section("3 &nbsp; What counts as a real shift?")
    cs = st.columns(3)
    cs[0].metric("Fraud rate", "{:.4f}%".format(t4["point_estimate_pct"]))
    cs[1].metric("95% CI", "{:.4f}-{:.4f}%".format(t4["ci_lower_pct"],
                                                   t4["ci_upper_pct"]))
    cs[2].metric("Sample", format(int(t4["n"]), ","))
    st.caption("Wilson interval rather than the normal approximation - at a "
               "proportion below 1% the normal approximation is unreliable and "
               "can return a negative lower bound. Use this band as the control "
               "limit: a future period landing outside it is a genuine shift, "
               "not routine variation.")

    t7 = S["test7_blind_spot"]
    section("4 &nbsp; What the amount rule cannot see")
    bs = pd.DataFrame(t7["by_type"])
    bs = bs.rename(columns={
        "fraud_type": "Typology", "incidents": "Incidents missed",
        "loss": "Loss not prevented",
        "avg_ratio_to_baseline": "Avg ratio to customer baseline"})
    st.dataframe(bs, use_container_width=True, hide_index=True)
    st.caption("At the optimal threshold of {}, {:.1f}% of fraud cases "
               "({:,.0f} in value) fall below the cut-off. Terminal Compromise "
               "transactions sit at roughly 1.0x the customer's own normal "
               "spend - they look ordinary by construction, and no amount "
               "threshold will separate them.".format(
                   t7["threshold"], t7["pct_of_all_fraud_missed"],
                   t7["unprevented_loss"]))

# ===========================================================================
# TAB 6 -- RECOMMENDATIONS
# ===========================================================================
with tabs[5]:
    t5 = S["test5_threshold"]
    t7 = S["test7_blind_spot"]
    t6 = S["test6_sensitivity"]
    par = data["pareto"]
    at5 = float(par[par["pct_terminals"] <= 5]["cum_pct"].max())

    st.markdown("Four actions, ordered by benefit per unit of effort. Each "
                "states the evidence behind it and how to tell whether it "
                "worked.")
    st.markdown("")

    recs = [
        ("01",
         "Set the review threshold at {}, not lower".format(
             t5["optimal_threshold"]),
         "Maximises net benefit at {:,.0f} and stays optimal across every cost "
         "scenario tested ({}-{}). Dropping to 100 turns the rule sharply "
         "negative - false positives grow far faster than detections. "
         "<b>Measure:</b> net benefit per week, and analyst hours per fraud "
         "caught.".format(t5["net_benefit"], t6["threshold_range"][0],
                          t6["threshold_range"][1])),
        ("02",
         "Stand up a terminal watchlist covering the worst 5% of the estate",
         "Those terminals carry {:.0f}% of all loss. Reviewing by terminal "
         "reputation reaches most of the exposure without touching every "
         "transaction in the portfolio. <b>Measure:</b> share of new fraud "
         "appearing on already-listed terminals - rising means the list is "
         "working.".format(at5)),
        ("03",
         "Add a behavioural rule on deviation from each customer's own "
         "baseline",
         "{:.0f}% of fraud ({:,.0f}) sits below the amount cut-off and is "
         "invisible to it. Account Takeover cases run above 3x the customer's "
         "own normal spend while remaining unremarkable in absolute terms - "
         "that ratio is the signal an amount rule structurally cannot use. "
         "<b>Measure:</b> incremental catches attributable to the new rule, "
         "tracked separately from the amount rule.".format(
             t7["pct_of_all_fraud_missed"], t7["unprevented_loss"])),
        ("04",
         "Do not roster reviewers by hour of day",
         "Cramer's V of {:.4f} means the hourly pattern is noise. Any staffing "
         "model built on it spends real budget against a non-effect. Roster to "
         "transaction volume instead. <b>Measure:</b> queue wait time against "
         "volume, not against fraud rate.".format(
             S["test2_timing"]["cramers_v"])),
    ]

    for num, title, body in recs:
        st.markdown('<div class="rec"><div class="n">' + num + '</div>'
                    '<div class="t">' + title + '</div>'
                    '<div class="d">' + body + '</div></div>',
                    unsafe_allow_html=True)

    section("Limitations")
    st.markdown(
        "- **Labels are treated as ground truth.** In production, "
        "confirmed-fraud labels arrive weeks late through chargebacks, so "
        "recent periods are always under-labelled. Any live version of this "
        "analysis needs a maturity window before a month is called final.\n"
        "- **Cost parameters are illustrative.** Review cost, false-decline "
        "cost and recovery rate are placeholders; the sensitivity grid exists "
        "precisely so the recommendation can be checked against the "
        "business's real figures.\n"
        "- **No merchant category or geography.** The source data carries no "
        "MCC or location, so segment-level risk could not be tested. That is "
        "usually the next most useful dimension after amount.\n"
        "- **Rules, not a model.** Everything here is a transparent threshold "
        "rule. A supervised model would likely lift recall further, at the "
        "cost of the explainability that makes a rule defensible to a "
        "regulator.")

st.markdown("---")
st.caption("Abhishek Singh - Payment Fraud Analytics - Python, SQL, Power BI, "
           "Excel, Streamlit. Data: ULB Machine Learning Group transaction "
           "simulator (Le Borgne et al., 2022).")

"""
Payment Fraud Analytics -- interactive dashboard
Author: Abhishek Singh

Reads pre-aggregated slices from dashboard/data/ (~120 KB total). The
aggregation happens once in the pipeline rather than on every page load,
so the deployed app stays responsive on a free-tier container instead of
holding an 880k-row frame in memory.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import json
import os

st.set_page_config(
    page_title="Payment Fraud Analytics",
    page_icon="◈",
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

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@500&display=swap');

.stApp {{ background: {PAPER}; }}
html, body, [class*="css"] {{ font-family: 'Inter', sans-serif; }}
#MainMenu, footer, header {{ visibility: hidden; }}
.block-container {{ padding-top: 2.2rem; max-width: 1400px; }}

h1, h2, h3 {{ font-family: 'Fraunces', Georgia, serif !important;
             color: {INK} !important; letter-spacing: -0.015em; }}

.masthead {{ border-bottom: 2px solid {INK}; padding-bottom: 1rem;
             margin-bottom: 1.6rem; }}
.masthead .eyebrow {{ font-size: .68rem; letter-spacing: .18em;
             text-transform: uppercase; color: {GOLD}; font-weight: 600; }}
.masthead h1 {{ font-size: 2.3rem; margin: .25rem 0 .3rem 0; font-weight: 600; }}
.masthead .meta {{ font-size: .82rem; color: {INK_SOFT}; }}

.kpi {{ background: #fff; border: 1px solid {LINE}; border-top: 3px solid {INK};
        padding: .95rem 1.05rem; height: 100%; }}
.kpi .lab {{ font-size: .62rem; letter-spacing: .12em; text-transform: uppercase;
        color: {INK_SOFT}; font-weight: 600; }}
.kpi .val {{ font-family: 'Fraunces', serif; font-size: 1.85rem; font-weight: 600;
        color: {INK}; line-height: 1.15; margin-top: .3rem; }}
.kpi .sub {{ font-size: .72rem; color: {INK_SOFT}; margin-top: .15rem; }}
.kpi.alert {{ border-top-color: {RISK}; }}
.kpi.alert .val {{ color: {RISK}; }}

.finding {{ background: #fff; border-left: 3px solid {GOLD}; padding: 1.1rem 1.3rem;
        margin: .6rem 0 1.1rem 0; border-top: 1px solid {LINE};
        border-right: 1px solid {LINE}; border-bottom: 1px solid {LINE}; }}
.finding .tag {{ font-size: .62rem; letter-spacing: .14em; text-transform: uppercase;
        color: {GOLD}; font-weight: 600; }}
.finding p {{ margin: .45rem 0 0 0; color: #2B3244; font-size: .93rem;
        line-height: 1.62; }}

.rec {{ background: #fff; border: 1px solid {LINE}; border-left: 3px solid {SAFE};
        padding: 1rem 1.2rem; margin-bottom: .8rem; }}
.rec .n {{ font-family: 'JetBrains Mono', monospace; font-size: .72rem;
        color: {SAFE}; font-weight: 600; }}
.rec .t {{ font-weight: 600; color: {INK}; margin-top: .2rem; font-size: .95rem; }}
.rec .d {{ color: {INK_SOFT}; font-size: .87rem; margin-top: .3rem; line-height: 1.6; }}

.sec {{ font-family: 'Fraunces', serif; font-size: 1.15rem; font-weight: 600;
        color: {INK}; border-bottom: 1px solid {LINE}; padding-bottom: .4rem;
        margin: 1.6rem 0 .9rem 0; }}

.stTabs [data-baseweb="tab-list"] {{ gap: 1.6rem; border-bottom: 1px solid {LINE}; }}
.stTabs [data-baseweb="tab"] {{ font-size: .85rem; font-weight: 500;
        color: {INK_SOFT}; padding: .5rem 0; }}
.stTabs [aria-selected="true"] {{ color: {INK} !important; font-weight: 600; }}

[data-testid="stSidebar"] {{ background: #fff; border-right: 1px solid {LINE}; }}
.stDataFrame {{ border: 1px solid {LINE}; }}
</style>
""", unsafe_allow_html=True)

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


@st.cache_data
def load():
    r = {n: pd.read_csv(os.path.join(D, f"{n}.csv")) for n in [
        "agg_band", "agg_daily", "agg_type", "agg_hour", "agg_heatmap",
        "agg_segment", "top_terminals", "pareto", "thresholds",
        "sensitivity", "amount_hist"]}
    r["stats"] = json.load(open(os.path.join(D, "stats.json")))
    r["agg_daily"]["txn_date"] = pd.to_datetime(r["agg_daily"]["txn_date"])
    return r


d = load()
S = d["stats"]
daily, band, typ = d["agg_daily"], d["agg_band"], d["agg_type"]

TOT_TXN = int(daily.txns.sum())
TOT_FRAUD = int(daily.fraud_txns.sum())
TOT_VAL = float(daily.total_value.sum())
FRAUD_VAL = float(daily.fraud_value.sum())
FRAUD_RATE = 100 * TOT_FRAUD / TOT_TXN
VAR_PCT = 100 * FRAUD_VAL / TOT_VAL

PLOTLY = dict(
    paper_bgcolor="white", plot_bgcolor="white",
    font=dict(family="Inter, sans-serif", size=12, color=INK),
    margin=dict(l=10, r=10, t=44, b=10),
    xaxis=dict(gridcolor="#F0EEE8", linecolor=LINE, zeroline=False),
    yaxis=dict(gridcolor="#F0EEE8", linecolor=LINE, zeroline=False),
    hoverlabel=dict(bgcolor="white", bordercolor=LINE,
                    font=dict(family="Inter", size=12, color=INK)),
    title=dict(font=dict(family="Fraunces, serif", size=15, color=INK), x=0),
)


def kpi(label, value, sub="", alert=False):
    return (f'<div class="kpi{" alert" if alert else ""}">'
            f'<div class="lab">{label}</div><div class="val">{value}</div>'
            f'<div class="sub">{sub}</div></div>')


def finding(tag, text):
    st.markdown(f'<div class="finding"><div class="tag">{tag}</div>'
                f'<p>{text}</p></div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Masthead
# ---------------------------------------------------------------------------
st.markdown(f"""
<div class="masthead">
  <div class="eyebrow">Fraud Risk &middot; Portfolio Review</div>
  <h1>Payment Fraud Analytics</h1>
  <div class="meta">{TOT_TXN:,} transactions &nbsp;&middot;&nbsp; 4,983 customers
  &nbsp;&middot;&nbsp; 10,000 terminals &nbsp;&middot;&nbsp;
  {daily.txn_date.min():%d %b} &ndash; {daily.txn_date.max():%d %b %Y}</div>
</div>
""", unsafe_allow_html=True)

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
    rec = st.slider("Recovery rate on caught fraud", 0.0, 1.0, 0.75, 0.05)

    st.markdown("---")
    st.caption("**Data** — ULB Machine Learning Group transaction simulator, "
               "published with *Reproducible Machine Learning for Credit Card "
               "Fraud Detection* (Le Borgne et al., 2022). 92 daily files.")

# ---------------------------------------------------------------------------
# KPI strip
# ---------------------------------------------------------------------------
cols = st.columns(6)
vals = [
    ("Transactions", f"{TOT_TXN/1000:.0f}K", "92 days", False),
    ("Value processed", f"{TOT_VAL/1e6:.1f}M", "gross", False),
    ("Fraud cases", f"{TOT_FRAUD:,}", "confirmed", True),
    ("Fraud rate", f"{FRAUD_RATE:.3f}%",
     f"CI {S['test4_fraud_rate_ci']['ci_lower_pct']:.3f}"
     f"–{S['test4_fraud_rate_ci']['ci_upper_pct']:.3f}%", True),
    ("Gross loss", f"{FRAUD_VAL/1000:.0f}K", "before recovery", True),
    ("Value at risk", f"{VAR_PCT:.2f}%", "of throughput", True),
]
for c, (l, v, s, a) in zip(cols, vals):
    c.markdown(kpi(l, v, s, a), unsafe_allow_html=True)

st.markdown("")

tabs = st.tabs(["Overview", "Where risk sits", "Terminals",
                "Decision model", "Statistical basis", "Recommendations"])

# ===========================================================================
# TAB 1 -- OVERVIEW
# ===========================================================================
with tabs[0]:
    finding("Headline",
            f"Fraud runs at <b>{FRAUD_RATE:.3f}%</b> of transactions but "
            f"<b>{VAR_PCT:.2f}%</b> of value — fraudulent transactions are "
            f"{S['test1_amount']['mean_fraud']/S['test1_amount']['mean_legit']:.1f}× "
            f"larger than legitimate ones on average. Loss concentrates in "
            f"<b>{typ.iloc[0].fraud_type}</b>, which accounts for "
            f"{100*typ.iloc[0].loss_value/FRAUD_VAL:.0f}% of total loss from "
            f"{100*typ.iloc[0].incidents/TOT_FRAUD:.0f}% of incidents.")

    c1, c2 = st.columns([1.65, 1])

    with c1:
        f = go.Figure()
        f.add_bar(x=daily.txn_date, y=daily.fraud_value, name="Daily loss",
                  marker_color="#DCD8CE",
                  hovertemplate="%{x|%d %b}<br>Loss %{y:,.0f}<extra></extra>")
        f.add_scatter(x=daily.txn_date, y=daily.fraud_rate_7d_ma,
                      name="Fraud rate 7d avg %",
                      line=dict(color=RISK, width=2.2),
                      hovertemplate="%{x|%d %b}<br>%{y:.3f}%<extra></extra>",
                      yaxis="y2")
        layout = dict(**PLOTLY)
        layout.update(height=330, title="Daily loss and smoothed fraud rate",
                      yaxis2=dict(overlaying="y", side="right", showgrid=False,
                                  tickformat=".3f"),
                      legend=dict(orientation="h", y=1.06, x=0, bgcolor="rgba(0,0,0,0)"))
        f.update_layout(**layout)
        st.plotly_chart(f, use_container_width=True)

    with c2:
        f = go.Figure(go.Pie(
            labels=typ.fraud_type, values=typ.loss_value, hole=.58,
            marker=dict(colors=[RISK, "#D98C5F", GOLD],
                        line=dict(color="white", width=2)),
            textinfo="percent", textfont=dict(size=12, color="white"),
            hovertemplate="%{label}<br>%{value:,.0f}<extra></extra>"))
        f.update_layout(**PLOTLY, height=330, title="Share of loss by typology",
                        legend=dict(orientation="h", y=-.12, x=0, font=dict(size=10)))
        st.plotly_chart(f, use_container_width=True)

    st.markdown('<div class="sec">Fraud typologies</div>', unsafe_allow_html=True)
    t = typ.copy()
    t["share_of_loss"] = (100 * t.loss_value / FRAUD_VAL).round(1)
    t.columns = ["Typology", "Incidents", "Loss value", "Avg loss",
                 "Customers hit", "Terminals", "Share of loss %"]
    st.dataframe(t, use_container_width=True, hide_index=True)

    st.caption("**Reading this:** Terminal Compromise produces the most "
               "incidents but the smallest average loss — it is a volume "
               "problem. Account Takeover is the reverse: fewer cases, far "
               "larger each. They need different controls, and a single "
               "blanket rule will handle neither well.")

# ===========================================================================
# TAB 2 -- WHERE RISK SITS
# ===========================================================================
with tabs[1]:
    base = FRAUD_RATE
    b = band.copy()
    b["lift"] = (b.fraud_rate_pct / base).round(1)

    c1, c2 = st.columns(2)
    with c1:
        f = go.Figure(go.Bar(
            x=b.amount_band, y=b.fraud_rate_pct,
            marker_color=[RISK if v > base * 2 else GOLD if v > base else "#C9CEDB"
                          for v in b.fraud_rate_pct],
            text=[f"{v:.2f}%" for v in b.fraud_rate_pct], textposition="outside",
            hovertemplate="%{x}<br>%{y:.3f}%<extra></extra>"))
        f.add_hline(y=base, line=dict(color=INK_SOFT, width=1, dash="dot"),
                    annotation_text=f"portfolio {base:.3f}%",
                    annotation_font=dict(size=10, color=INK_SOFT))
        f.update_layout(**PLOTLY, height=350, title="Fraud rate by amount band",
                        showlegend=False)
        f.update_xaxes(tickangle=-35, tickfont=dict(size=10))
        st.plotly_chart(f, use_container_width=True)

    with c2:
        h = d["amount_hist"]
        f = go.Figure()
        for k, nm, col in [(0, "Legitimate", "#C9CEDB"), (1, "Fraudulent", RISK)]:
            s = h[h.is_fraud == k]
            f.add_bar(x=s.bin, y=s.n / s.n.sum() * 100, name=nm,
                      marker_color=col, opacity=.85,
                      hovertemplate=nm + "<br>%{x}–%{customdata}<br>%{y:.2f}%<extra></extra>",
                      customdata=s.bin + 10)
        f.update_layout(**PLOTLY, height=350, barmode="overlay",
                        title="Amount distribution (% within class)",
                        legend=dict(orientation="h", y=1.06, x=0,
                                    bgcolor="rgba(0,0,0,0)"))
        st.plotly_chart(f, use_container_width=True)

    finding("Where the risk actually is",
            f"Risk rises sharply with ticket size: the "
            f"<b>{b.iloc[-2].amount_band}</b> band carries "
            f"<b>{b.iloc[-2].lift:.0f}×</b> the portfolio rate. "
            f"But volume sits at the other end — the three lowest bands hold "
            f"<b>{100*b.iloc[:3].txns.sum()/b.txns.sum():.0f}%</b> of all "
            f"transactions and still contribute "
            f"<b>{b.iloc[:3].fraud_txns.sum():,}</b> fraud cases. "
            f"High rate and high volume are in different places, which is "
            f"exactly why a single cut-off cannot solve this.")

    st.markdown('<div class="sec">Timing — and why it is not a lever</div>',
                unsafe_allow_html=True)
    c1, c2 = st.columns([1.5, 1])
    with c1:
        hr = d["agg_hour"]
        f = go.Figure(go.Scatter(
            x=hr.txn_hour, y=hr.fraud_rate_pct, mode="lines+markers",
            line=dict(color=INK, width=2), marker=dict(size=6, color=INK),
            hovertemplate="%{x}:00<br>%{y:.3f}%<extra></extra>"))
        f.add_hline(y=base, line=dict(color=RISK, width=1, dash="dot"))
        f.update_layout(**PLOTLY, height=300,
                        title="Fraud rate by hour of day (%)")
        f.update_yaxes(range=[base * .8, base * 1.2])
        st.plotly_chart(f, use_container_width=True)

    with c2:
        t2, t3 = S["test2_timing"], S["test3_amount_band"]
        st.markdown(f"""
<div class="finding" style="margin-top:2.4rem">
<div class="tag">Negative result</div>
<p>Chi-square gives Cramér's V of <b>{t2['cramers_v']:.4f}</b> for time-of-day
against <b>{t3['cramers_v']:.4f}</b> for amount band — a
<b>{t3['cramers_v']/t2['cramers_v']:.0f}×</b> difference in association
strength. Note the y-axis above is zoomed to ±20% of the mean; on a full
scale the line is flat.</p>
<p>The hourly variation here is noise. Rostering reviewers by hour would
spend real budget against a non-effect.</p>
</div>""", unsafe_allow_html=True)

    st.markdown('<div class="sec">Fraud rate by period and ticket size</div>',
                unsafe_allow_html=True)
    hm = d["agg_heatmap"].pivot(index="part_of_day", columns="amount_band",
                                values="fraud_rate_pct")
    f = px.imshow(hm, color_continuous_scale=["#FFFFFF", "#F5D7A8", RISK],
                  aspect="auto", labels=dict(color="Fraud %"))
    f.update_layout(**PLOTLY, height=280)
    f.update_xaxes(tickangle=-30, tickfont=dict(size=10), side="bottom")
    st.plotly_chart(f, use_container_width=True)
    st.caption("Colour varies almost entirely left-to-right (amount) and "
               "barely top-to-bottom (time) — the same conclusion the "
               "significance tests reach, shown visually.")

# ===========================================================================
# TAB 3 -- TERMINALS
# ===========================================================================
with tabs[2]:
    par, tt = d["pareto"], d["top_terminals"]
    at5 = par[par.pct_terminals <= 5].cum_pct.max()
    at10 = par[par.pct_terminals <= 10].cum_pct.max()

    c1, c2 = st.columns([1.5, 1])
    with c1:
        f = go.Figure(go.Scatter(
            x=par.pct_terminals, y=par.cum_pct, mode="lines",
            line=dict(color=INK, width=2.4), fill="tozeroy",
            fillcolor="rgba(18,25,43,.06)",
            hovertemplate="Top %{x:.1f}% of terminals<br>"
                          "%{y:.1f}% of loss<extra></extra>"))
        for x, y in [(5, at5), (10, at10)]:
            f.add_scatter(x=[x], y=[y], mode="markers+text",
                          marker=dict(size=9, color=RISK),
                          text=[f"  {y:.0f}%"], textposition="middle right",
                          textfont=dict(size=11, color=RISK), showlegend=False,
                          hoverinfo="skip")
        f.update_layout(**PLOTLY, height=350, showlegend=False,
                        title="Loss concentration across the terminal estate")
        f.update_xaxes(title="% of terminals, worst first", range=[0, 25])
        f.update_yaxes(title="% of total loss")
        st.plotly_chart(f, use_container_width=True)

    with c2:
        st.markdown(f"""
<div class="finding" style="margin-top:2.4rem">
<div class="tag">Concentration</div>
<p>The worst <b>5%</b> of terminals carry <b>{at5:.0f}%</b> of all fraud loss.
The worst <b>10%</b> carry <b>{at10:.0f}%</b>.</p>
<p>This is what makes targeted review viable. A watchlist of a few hundred
terminals reaches most of the exposure — a blanket amount rule touches every
transaction in the portfolio to reach the same place.</p>
</div>""", unsafe_allow_html=True)

    st.markdown('<div class="sec">Watchlist — highest loss terminals</div>',
                unsafe_allow_html=True)
    tier = st.multiselect("Risk tier", sorted(tt.risk_tier.unique()),
                          default=sorted(tt.risk_tier.unique()))
    v = tt[tt.risk_tier.isin(tier)].head(60).copy()
    v.columns = ["Terminal", "Txns", "Fraud txns", "Fraud rate %",
                 "Fraud loss", "Customers", "Risk tier"]
    st.dataframe(
        v, use_container_width=True, hide_index=True, height=380,
        column_config={
            "Fraud loss": st.column_config.ProgressColumn(
                "Fraud loss", format="%.0f", min_value=0,
                max_value=float(tt.fraud_volume.max())),
            "Fraud rate %": st.column_config.NumberColumn(format="%.2f%%"),
        })

# ===========================================================================
# TAB 4 -- DECISION MODEL
# ===========================================================================
with tabs[3]:
    th = d["thresholds"].copy()
    # Recompute economics live against the sidebar assumptions
    th["operating_cost_live"] = (th.txns_flagged * c_rev
                                 + th.false_positives * c_fd)
    th["prevented_live"] = th.loss_prevented / 0.75 * rec
    th["net_live"] = (th.prevented_live - th.operating_cost_live
                      - th.residual_loss)

    cur = th.iloc[(th.threshold - thr).abs().argmin()]
    opt = th.loc[th.net_live.idxmax()]

    c = st.columns(5)
    c[0].markdown(kpi("Flagged for review", f"{int(cur.txns_flagged):,}",
                      f"{100*cur.txns_flagged/TOT_TXN:.2f}% of volume"),
                  unsafe_allow_html=True)
    c[1].markdown(kpi("Fraud caught", f"{int(cur.frauds_caught):,}",
                      f"recall {cur.recall_pct:.1f}%"), unsafe_allow_html=True)
    c[2].markdown(kpi("Precision", f"{cur.precision_pct:.1f}%",
                      f"{int(cur.false_positives):,} false alarms"),
                  unsafe_allow_html=True)
    c[3].markdown(kpi("Fraud missed", f"{int(cur.frauds_missed):,}",
                      f"{cur.residual_loss:,.0f} residual", alert=True),
                  unsafe_allow_html=True)
    c[4].markdown(kpi("Net benefit", f"{cur.net_live:,.0f}",
                      "at your assumptions", alert=cur.net_live < 0),
                  unsafe_allow_html=True)

    st.markdown("")
    c1, c2 = st.columns(2)
    with c1:
        f = go.Figure(go.Scatter(
            x=th.threshold, y=th.net_live, mode="lines",
            line=dict(color=SAFE, width=2.4),
            hovertemplate="Above %{x}<br>Net %{y:,.0f}<extra></extra>"))
        f.add_hline(y=0, line=dict(color=INK_SOFT, width=1))
        f.add_vline(x=opt.threshold, line=dict(color=GOLD, width=1.5, dash="dash"),
                    annotation_text=f"optimum {int(opt.threshold)}",
                    annotation_font=dict(size=10, color=GOLD))
        f.add_vline(x=thr, line=dict(color=RISK, width=1.5),
                    annotation_text="your setting", annotation_position="top left",
                    annotation_font=dict(size=10, color=RISK))
        f.update_layout(**PLOTLY, height=330, showlegend=False,
                        title="Net benefit by review threshold")
        st.plotly_chart(f, use_container_width=True)

    with c2:
        f = go.Figure()
        f.add_scatter(x=th.threshold, y=th.recall_pct, name="Recall",
                      line=dict(color=RISK, width=2.2))
        f.add_scatter(x=th.threshold, y=th.precision_pct, name="Precision",
                      line=dict(color=INK, width=2.2))
        f.add_vline(x=thr, line=dict(color=GOLD, width=1.5, dash="dot"))
        f.update_layout(**PLOTLY, height=330,
                        title="Precision / recall trade-off",
                        legend=dict(orientation="h", y=1.06, x=0,
                                    bgcolor="rgba(0,0,0,0)"))
        st.plotly_chart(f, use_container_width=True)

    verdict = ("matches" if abs(thr - opt.threshold) <= 10 else
               "sits below" if thr < opt.threshold else "sits above")
    finding("Reading the model",
            f"At a cut-off of <b>{thr}</b> the rule flags "
            f"{int(cur.txns_flagged):,} transactions and returns a net benefit "
            f"of <b>{cur.net_live:,.0f}</b>. That {verdict} the optimum of "
            f"<b>{int(opt.threshold)}</b> ({opt.net_live:,.0f}). "
            f"The curve is steep on the left: lowering the cut-off pulls in "
            f"false positives far faster than fraud, and the rule stops paying "
            f"for itself well before it catches most of the loss.")

    st.markdown('<div class="sec">Does the answer survive different costs?</div>',
                unsafe_allow_html=True)
    c1, c2 = st.columns([1, 1.2])
    with c1:
        sv = d["sensitivity"].pivot(index="review_cost",
                                    columns="false_decline_cost",
                                    values="optimal_threshold")
        f = px.imshow(sv, text_auto=True, aspect="auto",
                      color_continuous_scale=["#EEF2F7", "#9FB0C9"],
                      labels=dict(x="False-decline cost", y="Review cost",
                                  color="Optimal"))
        f.update_layout(**PLOTLY, height=270, coloraxis_showscale=False,
                        title="Optimal threshold across cost scenarios")
        st.plotly_chart(f, use_container_width=True)
    with c2:
        t6 = S["test6_sensitivity"]
        st.markdown(f"""
<div class="finding" style="margin-top:2rem">
<div class="tag">Robustness</div>
<p>Re-solving across nine cost scenarios — review cost from 1.5 to 6, false-decline
cost from 6 to 24 — moves the optimum only between
<b>{t6['threshold_range'][0]}</b> and <b>{t6['threshold_range'][1]}</b>.</p>
<p>A recommendation that flips when an assumption moves 20% is not a
recommendation. This one holds, so it is safe to act on before the exact
cost figures are agreed.</p>
</div>""", unsafe_allow_html=True)

# ===========================================================================
# TAB 5 -- STATISTICAL BASIS
# ===========================================================================
with tabs[4]:
    st.markdown("Every claim on the preceding tabs traces to one of these "
                "tests. Assumptions were checked before each test was chosen — "
                "a test applied without checking its assumptions gives a "
                "confident wrong answer.")

    t1 = S["test1_amount"]
    st.markdown('<div class="sec">1 &nbsp; Are fraudulent transactions larger?</div>',
                unsafe_allow_html=True)
    c = st.columns(4)
    c[0].metric("Test", "Mann-Whitney U")
    c[1].metric("p-value", f"{t1['p_value']:.2e}")
    c[2].metric("Effect size", f"{t1['effect_size_rank_biserial']:.3f}")
    c[3].metric("Median fraud vs legit",
                f"{t1['median_fraud']:.0f} / {t1['median_legit']:.0f}")
    st.caption("Amounts are heavily right-skewed, so normality fails and a "
               "t-test would be invalid. Mann-Whitney compares ranks and makes "
               "no distributional assumption. At n=882,468 the p-value is near "
               "certain to be small, so the rank-biserial effect size is the "
               "figure that actually matters.")

    t2, t3 = S["test2_timing"], S["test3_amount_band"]
    st.markdown('<div class="sec">2 &nbsp; Which dimensions carry real signal?</div>',
                unsafe_allow_html=True)
    cmp = pd.DataFrame({
        "Dimension": ["Amount band", "Time of day"],
        "Chi-square": [f"{t3['chi2']:,.0f}", f"{t2['chi2']:,.1f}"],
        "p-value": [f"{t3['p_value']:.2e}", f"{t2['p_value']:.3f}"],
        "Cramér's V": [f"{t3['cramers_v']:.4f}", f"{t2['cramers_v']:.4f}"],
        "Strength": ["Strong — build controls here", "Negligible — not actionable"],
    })
    st.dataframe(cmp, use_container_width=True, hide_index=True)
    st.caption("Cramér's V rescales chi-square to 0–1 so the two dimensions "
               "can be compared directly. Reporting the p-value alone would "
               "make both look important; the effect sizes differ by roughly "
               f"{t3['cramers_v']/t2['cramers_v']:.0f}×.")

    t4 = S["test4_fraud_rate_ci"]
    st.markdown('<div class="sec">3 &nbsp; What counts as a real shift?</div>',
                unsafe_allow_html=True)
    c = st.columns(3)
    c[0].metric("Fraud rate", f"{t4['point_estimate_pct']:.4f}%")
    c[1].metric("95% CI", f"{t4['ci_lower_pct']:.4f}–{t4['ci_upper_pct']:.4f}%")
    c[2].metric("Sample", f"{t4['n']:,}")
    st.caption("Wilson interval rather than the normal approximation — at a "
               "proportion below 1% the normal approximation is unreliable and "
               "can return a negative lower bound. Use this band as the control "
               "limit: a future period landing outside it is a genuine shift, "
               "not routine variation.")

    t7 = S["test7_blind_spot"]
    st.markdown('<div class="sec">4 &nbsp; What the amount rule cannot see</div>',
                unsafe_allow_html=True)
    bs = pd.DataFrame(t7["by_type"])
    bs.columns = ["Typology", "Incidents missed", "Loss not prevented",
                  "Avg ratio to customer baseline"]
    st.dataframe(bs, use_container_width=True, hide_index=True)
    st.caption(f"At the optimal threshold of {t7['threshold']}, "
               f"{t7['pct_of_all_fraud_missed']:.1f}% of fraud cases "
               f"({t7['unprevented_loss']:,.0f} in value) fall below the "
               f"cut-off. Terminal Compromise transactions sit at roughly 1.0× "
               f"the customer's own normal spend — they look ordinary by "
               f"construction, and no amount threshold will separate them.")

# ===========================================================================
# TAB 6 -- RECOMMENDATIONS
# ===========================================================================
with tabs[5]:
    t5, t7 = S["test5_threshold"], S["test7_blind_spot"]
    at5 = d["pareto"][d["pareto"].pct_terminals <= 5].cum_pct.max()

    st.markdown("Four actions, ordered by benefit per unit of effort. Each "
                "states the evidence behind it and how to tell whether it "
                "worked.")
    st.markdown("")

    recs = [
        ("01", f"Set the review threshold at {t5['optimal_threshold']}, not lower",
         f"Maximises net benefit at {t5['net_benefit']:,.0f} and stays optimal "
         f"across every cost scenario tested "
         f"({S['test6_sensitivity']['threshold_range'][0]}–"
         f"{S['test6_sensitivity']['threshold_range'][1]}). Dropping to 100 turns "
         f"the rule sharply negative — false positives grow far faster than "
         f"detections. <b>Measure:</b> net benefit per week, and analyst hours "
         f"per fraud caught."),
        ("02", f"Stand up a terminal watchlist covering the worst 5% of the estate",
         f"Those terminals carry {at5:.0f}% of all loss. Reviewing by terminal "
         f"reputation reaches most of the exposure without touching every "
         f"transaction in the portfolio. <b>Measure:</b> share of new fraud "
         f"appearing on already-listed terminals — rising means the list is "
         f"working."),
        ("03", "Add a behavioural rule on deviation from each customer's own baseline",
         f"{t7['pct_of_all_fraud_missed']:.0f}% of fraud "
         f"({t7['unprevented_loss']:,.0f}) sits below the amount cut-off and is "
         f"invisible to it. Account Takeover cases run above 3× the customer's "
         f"own normal spend while remaining unremarkable in absolute terms — "
         f"that ratio is the signal an amount rule structurally cannot use. "
         f"<b>Measure:</b> incremental catches attributable to the new rule, "
         f"tracked separately from the amount rule."),
        ("04", "Do not roster reviewers by hour of day",
         f"Cramér's V of {S['test2_timing']['cramers_v']:.4f} means the hourly "
         f"pattern is noise. Any staffing model built on it spends real budget "
         f"against a non-effect. Roster to transaction volume instead. "
         f"<b>Measure:</b> queue wait time against volume, not against fraud rate."),
    ]
    for n, t, dd in recs:
        st.markdown(f'<div class="rec"><div class="n">{n}</div>'
                    f'<div class="t">{t}</div><div class="d">{dd}</div></div>',
                    unsafe_allow_html=True)

    st.markdown('<div class="sec">Limitations</div>', unsafe_allow_html=True)
    st.markdown("""
- **Labels are treated as ground truth.** In production, confirmed-fraud labels
  arrive weeks late through chargebacks, so recent periods are always
  under-labelled. Any live version of this analysis needs a maturity window
  before a month is called final.
- **Cost parameters are illustrative.** Review cost, false-decline cost and
  recovery rate are placeholders; the sensitivity grid exists precisely so the
  recommendation can be checked against the business's real figures.
- **No merchant category or geography.** The source data carries no MCC or
  location, so segment-level risk could not be tested. That is usually the
  next most useful dimension after amount.
- **Rules, not a model.** Everything here is a transparent threshold rule. A
  supervised model would likely lift recall further, at the cost of the
  explainability that makes a rule defensible to a regulator.
""")

st.markdown("---")
st.caption("Abhishek Singh · Payment Fraud Analytics · Python · SQL · "
           "Power BI · Excel · Streamlit — data: ULB Machine Learning Group "
           "transaction simulator (Le Borgne et al., 2022)")

"""Shared helpers for the Phase 3 pages: warehouse, formatting, chart style, labels."""
from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from pulseiq_metrics.views import Warehouse, MIN_GROUP, OPEN_STATUSES  # noqa: E402
from pulseiq_metrics.loader import CUTOFF  # noqa: E402

# categorical slots 1-3 (validated all-pairs) + reserved status colours (always paired with icon + word)
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e3e2de"
GOOD, WARN, BAD, NONE = "#1a7f37", "#b7791f", "#cf222e", "#6b6a66"
AI_LABEL = "AI-generated, for human review"


@st.cache_resource(show_spinner="Loading PulseIQ warehouse…")
def get_wh() -> Warehouse:
    return Warehouse()


def inr(x, dp=2) -> str:
    if x is None or pd.isna(x):
        return "—"
    a = abs(x); sign = "-" if x < 0 else ""
    if a >= 1e7: return f"{sign}₹{a/1e7:,.{dp}f} Cr"
    if a >= 1e5: return f"{sign}₹{a/1e5:,.{dp}f} L"
    return f"{sign}₹{a:,.0f}"


def inr_full(x) -> str:
    return "—" if x is None or pd.isna(x) else f"₹{x:,.0f}"


def style():
    st.markdown("""
<style>
.block-container{padding-top:2.2rem;max-width:1250px}
h1{font-size:1.7rem!important;margin-bottom:.1rem}
.sub{color:#52514e;font-size:.92rem;margin-bottom:.8rem}
.ai-chip{display:inline-block;background:#f4ecff;color:#4b2fa8;border:1px solid #cdb9f5;border-radius:999px;
  padding:2px 10px;font-size:.78rem;font-weight:600;margin:0 0 4px 0}
.note{background:#f1f0ed;border-left:3px solid #2a78d6;padding:.5rem .8rem;border-radius:4px;font-size:.9rem;color:#2b2a28;margin:.3rem 0 .9rem}
.tie-ok{color:#1a7f37;font-weight:600}.tie-bad{color:#cf222e;font-weight:600}
table.pl{border-collapse:collapse;width:100%;font-size:.9rem}
table.pl td,table.pl th{padding:4px 10px;border-bottom:1px solid #e3e2de}
table.pl th{text-align:right;color:#52514e;font-weight:600}table.pl th:first-child{text-align:left}
table.pl td{text-align:right;font-variant-numeric:tabular-nums}table.pl td:first-child{text-align:left}
table.pl tr.h td{font-weight:700;background:#f1f0ed}table.pl tr.t td{font-weight:700;border-top:2px solid #0b0b0b}
table.pl td.neg{color:#cf222e}
</style>""", unsafe_allow_html=True)


def header(title, sub):
    style()
    st.title(title)
    st.markdown(f'<div class="sub">{sub}</div>', unsafe_allow_html=True)


def ai_chip():
    st.markdown(f'<span class="ai-chip">✦ {AI_LABEL}</span>', unsafe_allow_html=True)


def note(text):
    st.markdown(f'<div class="note">{text}</div>', unsafe_allow_html=True)


def base_fig(height=340, title=None, ai=False) -> go.Figure:
    fig = go.Figure()
    t = (title or "") + (f"  <span style='font-size:11px;color:#4b2fa8'>✦ {AI_LABEL}</span>" if ai else "")
    fig.update_layout(
        height=height, margin=dict(l=10, r=10, t=44 if t else 14, b=10),
        title=dict(text=t, x=0, font=dict(size=14, color=INK)),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=INK2, size=12), hovermode="x unified",
        legend=dict(orientation="h", y=1.02, yanchor="bottom", x=1, xanchor="right"),
        xaxis=dict(gridcolor=GRID, linecolor=GRID, zeroline=False),
        yaxis=dict(gridcolor=GRID, linecolor=GRID, zeroline=False))
    return fig


def month_label(ts) -> str:
    return pd.Timestamp(ts).strftime("%b %Y")


def pick_month(months, key, label="Month", default_last=True):
    months = list(months)
    return st.sidebar.selectbox(label, months, index=len(months) - 1 if default_last else 0,
                                format_func=month_label, key=key)


def html_table(df: pd.DataFrame, row_class: pd.Series | None = None, neg_cols=()) -> str:
    h = "<table class='pl'><tr>" + "".join(f"<th>{c}</th>" for c in df.columns) + "</tr>"
    for i, r in df.iterrows():
        cls = f" class='{row_class.loc[i]}'" if row_class is not None and row_class.loc[i] else ""
        h += f"<tr{cls}>"
        for c in df.columns:
            v = r[c]
            neg = " class='neg'" if c in neg_cols and isinstance(v, str) and v.startswith("-") else ""
            h += f"<td{neg}>{v}</td>"
        h += "</tr>"
    return h + "</table>"

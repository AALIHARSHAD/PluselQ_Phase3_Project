"""Task 15: Executive company-health scorecard. One A4 page, eight KPIs, every number from v_company_month."""
import pandas as pd
import streamlit as st
from p3.common import *
from pulseiq_metrics import scorecard as sc

w = get_wh()
cm = w.view("v_company_month")
months = list(cm.month)
sel = pick_month(months, "sc_month")
rows = sc.build(cm, sel)
colour = {sc.GREEN: GOOD, sc.AMBER: WARN, sc.RED: BAD, sc.GREY: NONE}

st.markdown("""
<style>
.block-container{padding-top:1.2rem;max-width:1250px}
.sc-head{display:flex;justify-content:space-between;align-items:baseline;border-bottom:2px solid #0b0b0b;padding-bottom:4px;margin-bottom:8px}
.sc-head h1{font-size:1.5rem!important;margin:0;padding:0}.sc-head .m{font-size:1.05rem;font-weight:600}
.sc-sum{font-size:.92rem;margin:2px 0 10px}
.card{border:1px solid #e3e2de;border-radius:8px;padding:9px 11px 6px;background:#fff;height:190px;position:relative;overflow:hidden}
.card .t{font-size:.82rem;color:#52514e;font-weight:600}.card .t span{color:#8a8985;font-weight:400}
.card .v{font-size:1.65rem;font-weight:700;line-height:1.2;font-variant-numeric:tabular-nums;color:#0b0b0b}
.pill{display:inline-block;border-radius:999px;padding:1px 9px;font-size:.74rem;font-weight:700;color:#fff;vertical-align:middle}
.card .s{font-size:.78rem;color:#52514e;margin-top:1px;line-height:1.35}
.card .why{font-size:.7rem;color:#6b6a66;margin-top:3px;line-height:1.25}
.card svg{position:absolute;right:8px;top:30px}
.bar{position:absolute;left:0;top:0;bottom:0;width:4px}
.sc-foot{font-size:.74rem;color:#6b6a66;margin-top:6px}
@media print{
 @page{size:A4 landscape;margin:8mm}
 header,[data-testid=stSidebar],[data-testid=stToolbar],[data-testid=stDecoration],[data-testid=stStatusWidget],footer,
 [data-testid=stExpander],[data-testid=stIFrame],.noprint{display:none!important}
 html,body,.stApp,[data-testid=stAppViewContainer],[data-testid=stMain],section.main,.block-container{overflow:visible!important;height:auto!important;min-height:0!important;padding-top:0!important;padding-bottom:0!important;max-width:none!important}
 [data-testid=stElementContainer]:has(iframe),[data-testid=stBottom]{display:none!important}
 .stApp{position:static!important}
 [data-testid=stHorizontalBlock]{flex-wrap:nowrap!important;gap:.5rem!important}
 *{-webkit-print-color-adjust:exact;print-color-adjust:exact}
}
</style>""", unsafe_allow_html=True)


def spark(vals, months_, good_up, colr, w_=96, h_=34):
    v = [x for x in vals if x is not None and not pd.isna(x)]
    if len(v) < 2:
        return ""
    lo, hi = min(v), max(v); span = (hi - lo) or 1
    pts = [(2 + i * (w_ - 4) / (len(vals) - 1), h_ - 3 - (x - lo) / span * (h_ - 6)) for i, x in enumerate(vals) if x is not None and not pd.isna(x)]
    path = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    lx, ly = pts[-1]
    return (f"<svg width='{w_}' height='{h_}' viewBox='0 0 {w_} {h_}' role='img' aria-label='trend, last {len(vals)} months'>"
            f"<polyline fill='none' stroke='#9a9993' stroke-width='1.6' points='{path}'/>"
            f"<circle cx='{lx:.1f}' cy='{ly:.1f}' r='3' fill='{colr}'/></svg>")


counts = {s: sum(r["status"] == s for r in rows) for s in (sc.GREEN, sc.AMBER, sc.RED, sc.GREY)}
hc = cm.loc[cm.month == sel, "headcount_end"].iloc[0]
st.markdown(f"<div class='sc-head'><h1>PulseIQ company health scorecard</h1><div class='m'>{month_label(sel)}</div></div>"
            f"<div class='sc-sum'>Zenith Nova Technologies (fictional) · {int(hc)} people at month end · "
            f"<b style='color:{GOOD}'>{counts[sc.GREEN]} on target</b> · <b style='color:{WARN}'>{counts[sc.AMBER]} watch</b> · "
            f"<b style='color:{BAD}'>{counts[sc.RED]} off target</b>"
            + (f" · <b style='color:{NONE}'>{counts[sc.GREY]} no target</b>" if counts[sc.GREY] else "") + "</div>", unsafe_allow_html=True)

for line in (rows[:4], rows[4:]):
    cols = st.columns(4)
    for col, r in zip(cols, line):
        k, c = r["kpi"], colour[r["status"]]
        good = sc.trend_is_good(k, r["delta"])
        arrow = "" if r["delta"] in (None, 0) else ("▲" if r["delta"] > 0 else "▼")
        dcol = NONE if good is None else (GOOD if good else BAD)
        with col:
            st.markdown(
                f"<div class='card'><div class='bar' style='background:{c}'></div>"
                f"<div class='t'>{k.name} <span>{k.metric_id}</span></div>"
                f"<div class='v'>{sc.fmt_value(k, r['value'])}</div>"
                f"<span class='pill' style='background:{c}'>{sc.STATUS_ICON[r['status']]} {sc.STATUS_WORD[r['status']]}</span>"
                f"{spark(r['series'], r['series_months'], k.higher_is_better, c)}"
                f"<div class='s'>Target {sc.fmt_target(k, r['target'])}<br>"
                f"vs last month <b style='color:{dcol}'>{arrow} {sc.fmt_delta(k, r['delta'])}</b></div>"
                f"<div class='why'>{k.why}</div></div>", unsafe_allow_html=True)
            st.page_link(k.page, label="Details", icon=":material/arrow_forward:")

st.markdown("<div class='sc-foot'>Status rule: green = on the good side of target; amber = within tolerance on the bad side; red = outside tolerance; "
            "open the table below for each KPI’s target source and tolerance. Revenue, margin and overdue receivables have no target in kpi_targets, "
            "so they are judged against the average of the previous 12 months and marked provisional. Fictional training data. Cut-off 30 Sep 2026.</div>", unsafe_allow_html=True)

PRINT_BTN = """<button onclick="window.parent.print()" style="font:600 13px sans-serif;padding:6px 14px;border:1px solid #2a78d6;background:#fff;color:#2a78d6;border-radius:6px;cursor:pointer">
Print / save as PDF (A4)</button>"""
if hasattr(st, "iframe"):            # newer Streamlit
    st.iframe(PRINT_BTN, height=44)
else:                                # Streamlit 1.39-1.5x
    import streamlit.components.v1 as components
    components.html(PRINT_BTN, height=44)

# ---------------------------------------------------------------- traceability
with st.expander("Traceability: where every number comes from, and how its status is decided"):
    t = pd.DataFrame([{
        "KPI": k.name, "Metric": k.metric_id, "Metric view": "v_company_month", "Column": k.key,
        "Target / reference": k.target_basis,
        "Amber band": (f"{k.tol_abs:g} {'pts' if k.unit != 'inr' else ''}" if k.tol_abs is not None else f"{k.tol_rel:.0%} of target"),
        "Good direction": "higher" if k.higher_is_better else "lower",
        "Why it is on the page": k.why} for k in sc.KPIS])
    st.markdown(html_table(t), unsafe_allow_html=True)
    st.caption("v_company_month is built from v_pl_monthly (M16/M18), v_payroll_dm + budget_payroll_dept_month (M09), v_ar_month_end (M21), "
               "v_attendance_dm (M13), v_headcount_dm (M04), v_payroll_dm (M11) and fact_task (M22); targets from kpi_targets, "
               "headcount-weighted across departments. See docs/metric_dictionary.md.")
    # tie the page to the detailed pages for the same month
    pl = w.view("v_pl_monthly").set_index("period").loc[f"{sel:%Y-%m}"]
    ar_ok = abs(rows[3]["value"] - w.view("v_overdue_month_end").overdue_receivables.iloc[0]) < .01 if sel == months[-1] else None
    chk = pd.DataFrame([
        ["Revenue", sc.fmt_value(sc.KPIS[0], rows[0]["value"]), f"{pl.revenue/1e7:,.2f} Cr on P&L page", "✔" if abs(rows[0]["value"] - pl.revenue) < .01 else "✖"],
        ["Operating margin", f"{rows[1]['value']:.2f}%", f"{pl.margin_pct:.2f}% on P&L page", "✔" if abs(rows[1]["value"] - pl.margin_pct) < 1e-6 else "✖"],
        ["Overdue receivables", sc.fmt_value(sc.KPIS[3], rows[3]["value"]),
         "Receivables page (cut-off month only)" if ar_ok is not None else "Receivables page shows the cut-off month only",
         "✔" if ar_ok else "—"]], columns=["KPI", "Scorecard", "Detail page", "Agree"])
    st.markdown(html_table(chk), unsafe_allow_html=True)

with st.expander("Think for yourself: you may only show 5 KPIs. Which 3 do you remove and why?"):
    st.markdown("""
**Keep:** Revenue (M16), Operating margin (M18), Overdue receivables (M21), Attrition (M04), Task completion (M22).
**Remove:** Payroll cost vs budget, Attendance, Overtime share.

- **Payroll vs budget** is already inside margin: payroll is over 80% of expenses, so an overspend shows up in margin a month later. It stays one click away on the Department page.
- **Overtime share** is a driver, not an outcome, and is tiny here (about 0.3% of payroll against a 1–3% target), so it almost never changes a decision.
- **Attendance** barely moves (92–96%) and mostly sits near its target; attrition and task completion already tell the founder if people capacity is a problem.

I keep **overdue receivables** over, say, headcount because it is the one number that warns of a *cash* problem while profit still looks fine. The test I used: if this KPI turned red, would the founder do something different this week?
""")

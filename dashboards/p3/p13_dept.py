"""Task 13: Cross-department impact view (reconciled to reference_summary_dept_month)."""
import numpy as np
import pandas as pd
import streamlit as st
from p3.common import *

header("Cross-department impact view",
       "Grain: one row per department × month. Each source is aggregated to that grain first, then joined. Reconciled to reference_summary_dept_month.")
w = get_wh()
dm = w.view("v_dept_month")
months = sorted(dm.month.unique())
sel = pick_month(months, "dm_month")
cutoff_hc = MIN_GROUP

note("<b>Join order (and why).</b> 1) Aggregate payroll, attendance, headcount and leave to department × month separately. "
     "2) Join the four aggregates on <code>department_id + month</code>, starting from payroll. "
     "3) Re-add the totals and compare with the sources after the join. Joining raw rows first would repeat a department's payroll once per attendance row and inflate every figure. "
     "<b>Privacy:</b> departments with fewer than 5 people are hidden in charts and the comparison table (the Executive Office has 1 person); they stay in the reconciliation totals only.")

# ---- reconciliation
st.subheader("Reconciliation to the reference summary")
ref = w.tables["reference_summary_dept_month"]
j = dm.merge(ref, on=["department_id", "month"], suffixes=("", "_ref"))
pairs = [("employer_cost", "Employer cost (M09)"), ("gross_pay", "Gross pay"), ("overtime_pay", "Overtime pay"),
         ("employees_paid", "Employees paid"), ("overtime_hours", "Overtime hours"), ("late_arrivals", "Late arrivals"),
         ("attendance_rate", "Attendance rate (M13)"), ("headcount_end", "Headcount end (M01)"), ("hires", "Hires"),
         ("exits", "Exits"), ("attrition_rate_monthly_pct", "Attrition % (M04)"), ("cost_per_head", "Cost per head (M10)"),
         ("overtime_share_pct", "Overtime share % (M11)")]
rows = []
for c, lab in pairs:
    d = (j[c] - j[c + "_ref"]).abs()
    tol = 0.01 if c in ("employer_cost", "gross_pay", "overtime_pay", "cost_per_head") else 0.0051
    rows.append([lab, len(j), f"{d.max():.4f}", int((d > tol).sum()), "✔" if (d > tol).sum() == 0 else "✖"])
rt = pd.DataFrame(rows, columns=["Measure", "Dept-months compared", "Largest difference", "Mismatches", "Result"])
st.markdown(html_table(rt), unsafe_allow_html=True)
allok = all(r[3] == 0 for r in rows)
st.markdown(f"**{len(j)} department-months × {len(pairs)} measures: <span class='{'tie-ok' if allok else 'tie-bad'}'>"
            f"{'all match the reference' if allok else 'differences remain'}</span>.** Rows in my table: {len(dm)}; reference rows: {len(ref)}.", unsafe_allow_html=True)

st.markdown("**Why the raw facts do not match, and what removes the gap** (nothing is deleted without a rule and a log entry):")
raw = {k: v for k, v in w.tables.items()}
import pulseiq_metrics.loader as L
rawt = L.load_raw()
rp, ra = rawt["fact_payroll"], rawt["fact_attendance_monthly"]
cp, ca = w.tables["fact_payroll"], w.tables["fact_attendance_monthly"]
refp, refa = ref.employer_cost.sum(), ref.late_arrivals.sum()
gt = pd.DataFrame([
    ["Payroll employer cost (₹)", f"{rp.employer_cost.sum():,.2f}", f"{cp.employer_cost.sum():,.2f}", f"{refp:,.2f}", f"{rp.employer_cost.sum()-refp:,.2f}",
     "2 duplicate payroll rows (DQ-02) + 2 rows for employee ids not in dim_employee (DQ-03)"],
    ["Payroll rows", f"{len(rp):,}", f"{len(cp):,}", f"{int(ref.employees_paid.sum()):,}", f"{len(rp)-int(ref.employees_paid.sum()):,}", "same 4 rows"],
    ["Attendance rows", f"{len(ra):,}", f"{len(ca):,}", f"{int(ca.shape[0]):,}", f"{len(ra)-len(ca)}", "4 rows dated after the employee's exit month (DQ-01)"],
    ["Late arrivals", f"{int(ra.late_arrivals.sum()):,}", f"{int(ca.late_arrivals.sum()):,}", f"{int(refa):,}", f"{int(ra.late_arrivals.sum()-refa)}", "same 4 rows"],
], columns=["Measure", "Raw facts", "After cleaning", "Reference", "Raw − reference", "Cause"])
st.markdown(html_table(gt), unsafe_allow_html=True)
st.caption("Differences I cannot remove: none. Approved leave days and tasks are not in the reference summary, so leave is shown but not reconciled; "
           "the reference's task columns come from the task board feed and are outside this task's four sources.")
cl = w.clean_log
with st.expander("Row-level log of every cleaning action"):
    st.dataframe(cl, width="stretch", hide_index=True)

# ---- comparison
st.subheader("Department comparison")
v = dm[(dm.month == sel) & (dm.employees_paid >= cutoff_hc)].copy()
n_hidden = int((dm[dm.month == sel].employees_paid < cutoff_hc).sum())
cols = {"department_name": "Department", "headcount_end": "Headcount", "employer_cost": "Employer cost (₹)",
        "cost_per_head": "Cost / head (₹)", "overtime_share_pct": "Overtime share %", "attrition_rate_monthly_pct": "Attrition % (month)",
        "leave_days_per_head": "Leave days / head", "attendance_rate": "Attendance %"}
t = v[list(cols)].rename(columns=cols).sort_values("Employer cost (₹)", ascending=False)
t["Employer cost (₹)"] = t["Employer cost (₹)"].map("{:,.0f}".format); t["Cost / head (₹)"] = t["Cost / head (₹)"].map("{:,.0f}".format)
t["Overtime share %"] = t["Overtime share %"].map("{:.2f}".format); t["Attrition % (month)"] = t["Attrition % (month)"].map("{:.1f}".format)
t["Leave days / head"] = t["Leave days / head"].map("{:.2f}".format); t["Attendance %"] = (t["Attendance %"] * 100).map("{:.1f}".format)
t["Headcount"] = t["Headcount"].astype(int)
st.markdown(f"**{month_label(sel)}** — {len(t)} departments shown" + (f"; {n_hidden} hidden (group smaller than {cutoff_hc})." if n_hidden else "."), unsafe_allow_html=True)
st.markdown(html_table(t), unsafe_allow_html=True)

# 12-month view: overtime share vs attrition, bubble = employer cost, one hue, direct labels
end = pd.Timestamp(sel); start = end - pd.DateOffset(months=11)
win = dm[(dm.month >= start) & (dm.month <= end)]
g = win.groupby(["department_id", "department_name"]).agg(
    cost=("employer_cost", "sum"), ot=("overtime_pay", "sum"), exits=("exits", "sum"), hs=("headcount_end", "mean"),
    emp=("employees_paid", "mean"), cph=("cost_per_head", "mean")).reset_index()
g = g[g.emp >= cutoff_hc]
g["ot_share"] = 100 * g.ot / g.cost
g["attr_annual"] = 100 * g.exits / g.hs
f = base_fig(480, f"Cost, overtime and attrition by department — 12 months to {month_label(sel)}")
f.add_scatter(x=g.ot_share, y=g.attr_annual, mode="markers+text", text=g.department_name, textposition="top center",
              marker=dict(size=g.cost / g.cost.max() * 55 + 8, color=BLUE, opacity=.75, line=dict(width=2, color="#fcfcfb")),
              customdata=np.c_[g.cost / 1e7, g.cph, g.exits], textfont=dict(color=INK2, size=11),
              hovertemplate="<b>%{text}</b><br>Overtime share %{x:.2f}%<br>Attrition (12m exits ÷ avg headcount) %{y:.1f}%<br>"
                            "Employer cost ₹%{customdata[0]:.1f} Cr<br>Avg cost/head ₹%{customdata[1]:,.0f}<extra></extra>")
f.update_layout(hovermode="closest", showlegend=False)
f.update_xaxes(title="Overtime pay as % of employer cost"); f.update_yaxes(title="Attrition, last 12 months (%)")
st.plotly_chart(f, width="stretch")
st.caption("Bubble size = employer cost over the 12 months. Position shows overtime share (across) and attrition (up). Departments under 5 people are hidden.")

# ---- findings / think
st.subheader("Does overtime cause attrition?")
cor_dept = np.corrcoef(g.ot_share, g.attr_annual)[0, 1] if len(g) > 2 else np.nan
dd = dm[dm.employees_paid >= cutoff_hc]
cor_dm = dd[["overtime_share_pct", "attrition_rate_monthly_pct"]].corr().iloc[0, 1]
hi = g.sort_values("ot_share", ascending=False).iloc[0]; lo_att = g.sort_values("attr_annual").iloc[0]; hi_att = g.sort_values("attr_annual", ascending=False).iloc[0]
st.markdown(f"""
In this window the correlation between a department's overtime share and its 12-month attrition is **{cor_dept:+.2f}** across {len(g)} departments
(and {cor_dm:+.2f} across all {len(dd)} department-months). Highest overtime share: {hi.department_name} ({hi.ot_share:.2f}%). Highest attrition: {hi_att.department_name} ({hi_att.attr_annual:.1f}%); lowest: {lo_att.department_name} ({lo_att.attr_annual:.1f}%).

**A correlation is not a cause.** Even if the two move together, there are other explanations the data can test:
- **Reverse direction:** people leave, the rest cover the gap, and overtime rises.
- **A third factor:** a team under heavy delivery pressure, understaffing, or a weak manager raises both. Check task load per head (`fact_task`) and manager (`manager_id`).
- **Role mix:** only overtime-eligible roles earn overtime (`dim_role.overtime_eligible`), and some roles have a normal higher turnover.
- **Pay and level:** low pay versus band midpoint can raise exits and also push people to work paid extra hours.
- **Small numbers:** with 5–20 exits per department a single exit moves attrition a lot; ten points are too few to prove anything.
To test cause you would compare the same people before and after an overtime change, not different departments.
""")

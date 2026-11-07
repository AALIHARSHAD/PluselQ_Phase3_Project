"""Task 11: Profit and loss, and expense analytics."""
import pandas as pd
import streamlit as st
from p3.common import *

header("Profit & loss and expense analytics",
       "Source: fact_ledger + dim_account (P&L), fact_expense + dim_vendor (vendors). Metrics M16 Revenue, M17 Net profit, M18 Operating margin.")
w = get_wh()
pl = w.view("v_pl_monthly")
acc = w.view("v_pl_account_month")
periods = list(pl.period)
sel = st.sidebar.selectbox("Month", periods, index=len(periods) - 1, key="pl_month",
                           format_func=lambda p: month_label(p + "-01"))
scope = st.sidebar.radio("Category / vendor scope", ["Selected month", "All 18 months"], key="pl_scope")
i = periods.index(sel); prev = periods[i - 1] if i else None
cur = pl.iloc[i]; pr = pl.iloc[i - 1] if i else None

note("<b>Group accounts are headings, not money.</b> dim_account marks 4000 Income and 5000 Expenses as groups "
     "(<code>is_group = Y</code>). Every P&L number is built from detail accounts only, so a parent and its children are never added together. "
     "Revenue = all income detail accounts (4001–4004 and 4900 interest) so it matches the README answer key.")

c = st.columns(4)
def delta(a, b, pct=False):
    if b is None: return None
    return f"{a-b:+.1f} pts" if pct else f"{(a-b)/abs(b)*100:+.1f}% vs prior month"
c[0].metric("Revenue", inr(cur.revenue), delta(cur.revenue, pr.revenue if pr is not None else None))
c[1].metric("Expenses", inr(cur.expense), delta(cur.expense, pr.expense if pr is not None else None), delta_color="inverse")
c[2].metric("Net profit", inr(cur.net_profit), delta(cur.net_profit, pr.net_profit if pr is not None else None))
c[3].metric("Operating margin", f"{cur.margin_pct:.1f}%", delta(cur.margin_pct, pr.margin_pct if pr is not None else None, True))

x = [month_label(p + "-01") for p in pl.period]
a, b = st.columns(2)
with a:
    f = base_fig(320, "Revenue and expenses by month (₹ Cr)")
    f.add_scatter(x=x, y=pl.revenue / 1e7, name="Revenue", line=dict(color=BLUE, width=2), mode="lines+markers", marker=dict(size=7))
    f.add_scatter(x=x, y=pl.expense / 1e7, name="Expenses", line=dict(color=ORANGE, width=2), mode="lines+markers", marker=dict(size=7))
    f.update_yaxes(tickformat=".1f"); f.update_xaxes(tickangle=-45)
    st.plotly_chart(f, width="stretch")
with b:
    f = base_fig(320, "Operating margin by month (%)")
    f.add_bar(x=x, y=pl.margin_pct, name="Margin %", marker_color=BLUE, hovertemplate="%{y:.1f}%")
    f.add_hline(y=pl.margin_pct.mean(), line_dash="dot", line_color=INK2,
                annotation_text=f"18-month average {pl.margin_pct.mean():.1f}%", annotation_position="top left")
    f.update_xaxes(tickangle=-45); f.update_layout(showlegend=False)
    st.plotly_chart(f, width="stretch")

# ---- expense by category and vendors
ex = w.view("v_expense_category_month")
vs = w.view("v_vendor_spend")
if scope == "Selected month":
    exs, vss, lab = ex[ex.period == sel], vs[vs.period == sel], month_label(sel + "-01")
else:
    exs, vss, lab = ex, vs, "Apr 2025 – Sep 2026"
cat = exs.groupby("category", as_index=False).amount.sum().query("amount != 0").sort_values("amount")
top = vss.groupby("vendor_name", as_index=False).amount.sum().sort_values("amount", ascending=False).head(10).sort_values("amount")
a, b = st.columns(2)
with a:
    f = base_fig(430, f"Expenses by category, {lab} (₹ Cr)")
    f.add_bar(y=cat.category, x=cat.amount / 1e7, orientation="h", marker_color=BLUE,
              hovertemplate="%{y}: ₹%{x:.2f} Cr<extra></extra>")
    f.update_layout(hovermode="closest", showlegend=False); f.update_xaxes(tickformat=".1f")
    st.plotly_chart(f, width="stretch")
with b:
    f = base_fig(430, f"Top 10 vendors by spend before GST, {lab} (₹ L)")
    f.add_bar(y=top.vendor_name, x=top.amount / 1e5, orientation="h", marker_color=AQUA,
              hovertemplate="%{y}: ₹%{x:.1f} L<extra></extra>")
    f.update_layout(hovermode="closest", showlegend=False); f.update_xaxes(tickformat=",.0f")
    st.plotly_chart(f, width="stretch")
tot_v = vss.amount.sum()
st.caption(f"Top 10 vendors = {top.amount.sum()/tot_v*100:.0f}% of the {inr(tot_v)} vendor bills in scope (bills before GST; payroll is not a vendor bill).")

# ---- P&L table
st.subheader("P&L table")
def col(p): return acc[acc.period == p].set_index("account_code").amount
fy_start = f"{int(sel[:4]) - (1 if int(sel[5:]) < 4 else 0)}-04"
fyp = [p for p in periods if fy_start <= p <= sel]
fytd = acc[acc.period.isin(fyp)].groupby("account_code").amount.sum()
names = acc.drop_duplicates("account_code").set_index("account_code")[["account_name", "account_type"]]
dim = w.tables["dim_account"].set_index("account_code")
rows, cls = [], []
def add(label, a_, b_, c_, k=""):
    ch = None if b_ is None else a_ - b_
    pct = "" if b_ in (None, 0) else f"{ch/abs(b_)*100:+.1f}%"
    rows.append([label, f"{a_:,.0f}", "—" if b_ is None else f"{b_:,.0f}", "—" if ch is None else f"{ch:,.0f}", pct, f"{c_:,.0f}"]); cls.append(k)
tot = {}
for typ, head in (("INCOME", "4000"), ("EXPENSE", "5000")):
    rows.append([f"{dim.loc[head,'account_name'].upper()}  (group heading)", "", "", "", "", ""]); cls.append("h")
    codes = sorted(names[names.account_type == typ].index)
    ta = tb = tc = 0
    for code in codes:
        a_, c_ = col(sel).get(code, 0.0), fytd.get(code, 0.0)
        b_ = col(prev).get(code, 0.0) if prev else None
        if a_ == 0 and c_ == 0 and not b_: continue
        add(f"{code}  {names.loc[code,'account_name']}", a_, b_, c_)
        ta += a_; tb += (b_ or 0); tc += c_
    add(f"Total {dim.loc[head,'account_name'].lower()}", ta, tb if prev else None, tc, "t"); tot[typ] = (ta, tb if prev else None, tc)
npa = tot["INCOME"][0] - tot["EXPENSE"][0]; npb = None if prev is None else tot["INCOME"][1] - tot["EXPENSE"][1]
add("NET PROFIT", npa, npb, tot["INCOME"][2] - tot["EXPENSE"][2], "t")
rows.append(["Operating margin %", f"{npa/tot['INCOME'][0]*100:.1f}%",
             "—" if prev is None else f"{npb/tot['INCOME'][1]*100:.1f}%", "", "",
             f"{(tot['INCOME'][2]-tot['EXPENSE'][2])/tot['INCOME'][2]*100:.1f}%"]); cls.append("")
tbl = pd.DataFrame(rows, columns=["Account (₹)", month_label(sel + "-01"), month_label(prev + "-01") if prev else "Prior", "Change", "Change %", f"FY-to-date (from Apr {fy_start[:4]})"])
st.markdown(html_table(tbl, pd.Series(cls), neg_cols=("Change",)), unsafe_allow_html=True)

# ---- tie-out
st.subheader("Tie-out to the README headline numbers")
key = w.tables["reconciliation_answer_key"].copy(); key["period"] = key.month.dt.strftime("%Y-%m")
chk = w.view("v_payroll_ledger_check")
t = pl.merge(key[["period", "ledger_revenue", "ledger_total_expense", "ledger_net_profit"]], on="period").merge(chk[["period", "diff"]], on="period", how="left")
t["d_rev"] = t.revenue - t.ledger_revenue; t["d_exp"] = t.expense - t.ledger_total_expense; t["d_np"] = t.net_profit - t.ledger_net_profit
t["status"] = t.apply(lambda r: "✔ ties" if abs(r.d_rev) < .01 and abs(r.d_exp) < .01 and abs(r.d_np) < .01 else
                      ("⚠ explained by DQ-04" if abs(r["diff"]) > .01 and abs(r.d_exp - r["diff"]) < .01 else "✖ unexplained"), axis=1)
show = pd.DataFrame({"Month": [month_label(p + "-01") for p in t.period],
                     "Revenue (ledger)": t.revenue.map("{:,.2f}".format), "Revenue (README)": t.ledger_revenue.map("{:,.2f}".format),
                     "Expense (ledger)": t.expense.map("{:,.2f}".format), "Expense (README)": t.ledger_total_expense.map("{:,.2f}".format),
                     "Net profit (ledger)": t.net_profit.map("{:,.2f}".format), "Net profit (README)": t.ledger_net_profit.map("{:,.2f}".format),
                     "Δ profit": t.d_np.map(lambda v: f"{v:,.2f}"), "Status": t.status})
st.markdown(html_table(show), unsafe_allow_html=True)
n_ok = (t.status == "✔ ties").sum(); n_exp = (t.status.str.startswith("⚠")).sum(); n_bad = (t.status.str.startswith("✖")).sum()
st.markdown(f"**{n_ok} of 18 months tie exactly; {n_exp} differ and are explained; {n_bad} unexplained.** "
            f"18-month totals: revenue {t.revenue.sum():,.2f} vs README {t.ledger_revenue.sum():,.2f}; "
            f"net profit {t.net_profit.sum():,.2f} vs README {t.ledger_net_profit.sum():,.2f}.")
bad = t[t.status.str.startswith("⚠")]
for r in bad.itertuples():
    note(f"<b>{month_label(r.period + '-01')}:</b> ledger expense is ₹{r.d_exp:,.2f} higher than the README clean figure. "
         f"The same ₹{r.diff:,.2f} is the gap between ledger salary-related expense (accounts 5001–5005) and the payroll run — "
         "check DQ-C01. This is the planted issue DQ-04 (journal entry JE-002094, lines JL-005614 / JL-005643). "
         "The entry still balances, so it is not removed here; it is flagged for the ledger owner to correct.")

# ---- findings
st.subheader("Three findings")
best, worst = pl.loc[pl.margin_pct.idxmax()], pl.loc[pl.margin_pct.idxmin()]
pay = acc[acc.account_code.isin(["5001", "5002", "5003", "5004", "5005"])].groupby("period").amount.sum()
pay_share = (pay / pl.set_index("period").expense).mean() * 100
pay_rev = (pay / pl.set_index("period").revenue)
vtop = vs.groupby("vendor_name").amount.sum().sort_values(ascending=False)
share = lambda n: vtop.head(n).sum() / vtop.sum() * 100
r1, r2 = pl.revenue.iloc[:9].sum(), pl.revenue.iloc[9:].sum()
m1, m2 = pl.net_profit.iloc[:9].sum() / r1 * 100, pl.net_profit.iloc[9:].sum() / r2 * 100
st.markdown(f"""
1. **Margin is volatile, not trending.** It ranges from {worst.margin_pct:.1f}% ({month_label(worst.period+'-01')}) to {best.margin_pct:.1f}% ({month_label(best.period+'-01')}); the 18-month average is {pl.net_profit.sum()/pl.revenue.sum()*100:.1f}%. The first nine months ran at {m1:.1f}% and the last nine at {m2:.1f}%, on revenue of {inr(r1)} and {inr(r2)}.
2. **Payroll drives the margin swings.** Salary-related accounts (5001–5005) are {pay_share:.0f}% of expenses on average and move between {pay_rev.min()*100:.0f}% and {pay_rev.max()*100:.0f}% of revenue. Revenue is lumpier than payroll, so months with a revenue dip show the biggest margin drop.
3. **Vendor spend is concentrated.** The top 3 vendors are {share(3):.0f}% and the top 10 are {share(10):.0f}% of vendor bills; the largest is {vtop.index[0]} at {inr(vtop.iloc[0])}. Negotiating or consolidating a handful of contracts moves the non-payroll cost line.
""")

# ---- think for yourself
with st.expander("Think for yourself: revenue grew but margin fell. Three possible causes and the data to prove each"):
    st.markdown("""
| # | Possible cause | Data that would prove it |
|---|---|---|
| 1 | **Payroll grew faster than revenue** (new hires, bonus or overtime in the month) | Employer cost, overtime pay and variable pay by month from `fact_payroll`; headcount from `fact_headcount_monthly` |
| 2 | **Non-payroll spend rose** (cloud, rent, a large vendor bill, one-off professional fees) | Expense by category and by vendor from `fact_expense`; compare to the previous 3 months |
| 3 | **Revenue mix shifted to lower-margin lines** or the revenue is one-off, not recurring | Revenue by service-line account (4001–4004) and invoice lines from `fact_invoice`; cost by department/cost centre |
""")
    if prev:
        bridge = []
        for code in sorted(names[names.account_type == "EXPENSE"].index):
            a_, b_ = col(sel).get(code, 0.0), col(prev).get(code, 0.0)
            d = a_ / cur.revenue * 100 - b_ / pr.revenue * 100
            if abs(d) > 0.05: bridge.append((f"{code} {names.loc[code,'account_name']}", d))
        bridge.sort(key=lambda r: -abs(r[1]))
        st.markdown(f"**Margin bridge for {month_label(sel+'-01')} vs {month_label(prev+'-01')}** — each line is the change in (expense ÷ revenue), in percentage points of revenue. A positive number pulls margin down.")
        bt = pd.DataFrame(bridge[:8], columns=["Expense account", "Δ % of revenue (pts)"]); bt["Δ % of revenue (pts)"] = bt.iloc[:, 1].map("{:+.2f}".format)
        st.markdown(html_table(bt), unsafe_allow_html=True)
        st.caption(f"Total margin change: {cur.margin_pct-pr.margin_pct:+.2f} pts. Revenue {'grew' if cur.revenue>pr.revenue else 'fell'} {abs(cur.revenue/pr.revenue-1)*100:.1f}%.")

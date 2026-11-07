"""Task 12: Invoices, receivables and cash flow."""
import pandas as pd
import streamlit as st
from p3.common import *

header("Receivables ageing and cash flow",
       f"Source: fact_invoice, fact_invoice_payment, dim_client, fact_ledger (bank 1001). Position as at the data cut-off, {CUTOFF:%d %b %Y}. Metrics M20 DSO, M21 Overdue receivables.")
w = get_wh()
note(f"<b>Open invoices = status {', '.join(OPEN_STATUSES)}.</b> DRAFT (not yet issued) and CANCELLED are not receivables; PAID is closed. "
     "Ageing counts days past the <i>due date</i> at the cut-off. Invoices not yet due sit in a separate “Not yet due” bucket so the four ageing buckets stay pure.")

ar = w.view("v_ar_open")
tot_open, overdue = ar.balance_due.sum(), ar[ar.days_past_due > 0].balance_due.sum()
key = w.tables["reconciliation_answer_key"]
key_ar = key.receivables_closing_balance.iloc[-1]
me = w.view("v_ar_month_end")
rev90 = w.view("v_pl_monthly").revenue.tail(3).sum()
inv_all = w.tables["fact_invoice"]
dso = tot_open / (rev90 * 1.18) * 90  # M20: closing receivables / revenue incl. GST (last 90 days) x 90
c = st.columns(4)
c[0].metric("Open receivables", inr(tot_open)); c[1].metric("Overdue (past due date)", inr(overdue), f"{overdue/tot_open*100:.1f}% of open", delta_color="off")
c[2].metric("Open invoices", f"{len(ar)}"); c[3].metric("DSO (M20, approx.)", f"{dso:.0f} days")
st.caption("DSO uses revenue × 1.18 as a proxy for revenue incl. 18% GST, last 3 months, per the M20 formula.")

# ---- ageing
st.subheader("Receivables ageing")
order = ["Not yet due", "0-30", "31-60", "61-90", "90+"]
ag = w.view("v_ar_ageing").set_index("bucket").reindex(order).fillna(0).reset_index()
a, b = st.columns([3, 2])
with a:
    f = base_fig(330, "Open receivables by days past due (₹ Cr)")
    f.add_bar(x=ag.bucket, y=ag.balance / 1e7, marker_color=[AQUA, BLUE, BLUE, BLUE, ORANGE],
              hovertemplate="%{x}: ₹%{y:.2f} Cr<extra></extra>", text=[f"{v/1e7:.2f}" for v in ag.balance], textposition="outside")
    f.update_layout(showlegend=False, hovermode="closest"); f.update_xaxes(title="days past due date"); f.update_yaxes(range=[0, ag.balance.max() / 1e7 * 1.15])
    st.plotly_chart(f, width="stretch")
with b:
    t = ag.assign(balance_s=ag.balance.map("{:,.0f}".format), share=(ag.balance / ag.balance.sum() * 100).map("{:.1f}%".format))
    t = pd.DataFrame({"Bucket (days past due)": t.bucket, "Invoices": t.invoices.astype(int), "Balance (₹)": t.balance_s, "Share": t.share})
    t.loc[len(t)] = ["Total", int(ag.invoices.sum()), f"{ag.balance.sum():,.0f}", "100%"]
    st.markdown(html_table(t, pd.Series([""] * 5 + ["t"])), unsafe_allow_html=True)
ok = abs(ag.balance.sum() - tot_open) < .01 and abs(tot_open - key_ar) < .01
st.markdown(f"**Bucket check:** buckets add to {ag.balance.sum():,.2f}; total open receivables {tot_open:,.2f}; README closing receivables {key_ar:,.2f} → "
            f"<span class='{'tie-ok' if ok else 'tie-bad'}'>{'✔ all three agree' if ok else '✖ mismatch'}</span>", unsafe_allow_html=True)
k2 = key.assign(period=key.month.dt.strftime("%Y-%m")).merge(me, on="period")
st.caption(f"The same rebuild (invoices less payments received up to each month-end) matches the README receivables for all 18 month-ends "
           f"(largest difference ₹{(k2.receivables_closing - k2.receivables_closing_balance).abs().max():.2f}).")

# ---- overdue clients
st.subheader("Clients with the most overdue money")
od = w.view("v_overdue_client").dropna(subset=["overdue_balance"]).sort_values("overdue_balance", ascending=False)
a, b = st.columns([3, 2])
with a:
    f = base_fig(300, "Overdue balance by client (₹ L)")
    d = od.sort_values("overdue_balance")
    f.add_bar(y=d.client_name, x=d.overdue_balance / 1e5, orientation="h", marker_color=ORANGE, hovertemplate="%{y}: ₹%{x:.1f} L<extra></extra>")
    f.update_layout(showlegend=False, hovermode="closest")
    st.plotly_chart(f, width="stretch")
with b:
    t = pd.DataFrame({"Client": od.client_name, "Overdue (₹)": od.overdue_balance.map("{:,.0f}".format),
                      "Oldest (days past due)": od.oldest_days_past_due.astype(int), "Invoices": od.overdue_invoices.astype(int)})
    st.markdown(html_table(t), unsafe_allow_html=True)

# ---- days to pay
st.subheader("Average days to pay, by client")
dp = w.view("v_days_to_pay_client").sort_values("avg_days_to_pay")
dp["over_terms"] = dp.avg_days_to_pay - dp.payment_terms_days
f = base_fig(560, "Average days from invoice to last payment (paid invoices only)")
f.add_bar(y=dp.client_name, x=dp.avg_days_to_pay, orientation="h", name="Average days to pay",
          marker_color=[ORANGE if v > 0 else BLUE for v in dp.over_terms], hovertemplate="%{y}: %{x:.0f} days<extra></extra>")
f.add_scatter(y=dp.client_name, x=dp.payment_terms_days, mode="markers", name="Agreed terms",
              marker=dict(symbol="line-ns-open", size=14, color=INK, line=dict(width=2, color=INK)), hovertemplate="terms %{x} days<extra></extra>")
f.update_layout(hovermode="closest"); f.update_xaxes(title="days")
st.plotly_chart(f, width="stretch")
st.caption("Orange = pays later than its agreed terms on average. Black tick = agreed payment terms.")
slow = dp[dp.over_terms > 0].sort_values("over_terms", ascending=False)
t = pd.DataFrame({"Client": slow.client_name, "Terms (days)": slow.payment_terms_days.astype(int), "Avg days to pay": slow.avg_days_to_pay.round(1),
                  "Days over terms": slow.over_terms.round(1), "Slowest invoice": slow.max_days_to_pay.astype(int),
                  "Label in dim_client": slow.payment_behaviour, "Paid invoices": slow.paid_invoices.astype(int)})
st.markdown(f"**{len(slow)} of {len(dp)} clients pay later than their terms on average:**")
st.markdown(html_table(t.head(10)), unsafe_allow_html=True)

# ---- cash
st.subheader("Cash in versus cash out")
cm = w.view("v_cash_monthly")
cm = cm[cm.source_type != "OPENING"]
mm = cm.groupby("period")[["cash_in", "cash_out"]].sum().reset_index()
mm["net"] = mm.cash_in - mm.cash_out
labels = [month_label(p + "-01") for p in mm.period]
a, b = st.columns(2)
with a:
    f = base_fig(340, "Cash in and cash out by month (₹ Cr)")
    f.add_bar(x=labels, y=mm.cash_in / 1e7, name="Cash in", marker_color=BLUE)
    f.add_bar(x=labels, y=mm.cash_out / 1e7, name="Cash out", marker_color=ORANGE)
    f.update_layout(barmode="group", bargap=.25, bargroupgap=.06); f.update_xaxes(tickangle=-45)
    st.plotly_chart(f, width="stretch")
with b:
    opening = w.tables["fact_ledger"].query("account_code=='1001' and source_type=='OPENING'").debit.sum()
    mm["closing"] = opening + mm.net.cumsum()
    f = base_fig(340, "Bank closing balance (₹ Cr) vs README")
    f.add_scatter(x=labels, y=mm.closing / 1e7, name="Bank balance (ledger)", line=dict(color=BLUE, width=2), mode="lines+markers", marker=dict(size=7))
    f.update_xaxes(tickangle=-45); f.update_layout(showlegend=False)
    st.plotly_chart(f, width="stretch")
kk = key.assign(period=key.month.dt.strftime("%Y-%m")).merge(mm[["period", "closing"]], on="period")
gap = (kk.closing - kk.bank_closing_balance).abs().max()
st.markdown(f"**Cash check:** opening bank {inr_full(opening)} + net movements reproduces the README closing balance in all 18 months "
            f"(max difference ₹{gap:.2f}) → <span class='{'tie-ok' if gap<1 else 'tie-bad'}'>{'✔' if gap<1 else '✖'}</span>", unsafe_allow_html=True)
src = cm.groupby("source_type")[["cash_in", "cash_out"]].sum()
src["Cash in (₹)"] = src.cash_in.map("{:,.0f}".format); src["Cash out (₹)"] = src.cash_out.map("{:,.0f}".format)
st.markdown(html_table(src[["Cash in (₹)", "Cash out (₹)"]].reset_index().rename(columns={"source_type": "Cash source / use"})), unsafe_allow_html=True)
net_total = mm.net.sum(); pnl = w.view("v_pl_monthly").net_profit.sum()
st.caption(f"Profit is not cash: 18-month net profit is {inr(pnl)}, net cash movement is {inr(net_total)}. "
           "The gap is receivables, GST, payables and the timing of salary and statutory payments.")

# ---- status table and DQ
st.subheader("Open versus closed invoices")
s = inv_all.groupby("status").agg(invoices=("invoice_id", "count"), total=("total_amount", "sum"), balance=("balance_due", "sum")).reset_index()
s["Treatment"] = s.status.map(lambda x: "Open receivable" if x in OPEN_STATUSES else ("Closed" if x == "PAID" else "Excluded (not a receivable)"))
st.markdown(html_table(pd.DataFrame({"Status": s.status, "Invoices": s.invoices, "Invoice total (₹)": s.total.map("{:,.0f}".format),
                                     "Balance due (₹)": s.balance.map("{:,.0f}".format), "Treatment": s.Treatment})), unsafe_allow_html=True)
neg = inv_all[inv_all.balance_due < 0]
if len(neg):
    note(f"<b>Data-quality flag DQ-05:</b> {', '.join(neg.invoice_id)} is overpaid by ₹{-neg.balance_due.sum():,.0f} (negative balance). "
         "It is PAID, so it is not in open receivables; the overpayment should be refunded or applied.")

# ---- findings + think
st.subheader("Findings")
big = (inv_all[inv_all.status != "CANCELLED"].groupby("client_id").total_amount.sum().sort_values(ascending=False))
names = w.tables["dim_client"].set_index("client_id").client_name
pct_not_due = ag.set_index("bucket").balance["Not yet due"] / ag.balance.sum() * 100
st.markdown(f"""
1. **Most receivables are current, but the overdue tail is real.** {pct_not_due:.0f}% of open money is not yet due; {inr(overdue)} ({overdue/tot_open*100:.1f}%) is past due, of which {inr(ar[ar.days_past_due>30].balance_due.sum())} is over 30 days.
2. **{len(slow)} clients pay later than agreed.** The worst is {slow.iloc[0].client_name} at {slow.iloc[0].avg_days_to_pay:.0f} days against {int(slow.iloc[0].payment_terms_days)}-day terms.
3. **Cash is healthy even while receivables are high.** Bank balance grew from {inr(opening)} to {inr(mm.closing.iloc[-1])}; cash in exceeded cash out in {int((mm.net>0).sum())} of 18 months.
""")
with st.expander("Think for yourself: a big client always pays at 75 days. Is that a risk? What would you ask finance?"):
    c1 = dp.sort_values("avg_days_to_pay", ascending=False).head(3)
    st.markdown(f"""
**It is a predictable delay, not an immediate default risk, but it is still a cost and a concentration risk.** If terms are 30 or 45 days, 75 days means the client is financing itself with your cash for 30–45 extra days. In this data the three slowest payers average {', '.join(f'{r.client_name} ({r.avg_days_to_pay:.0f} d)' for r in c1.itertuples())}.

Questions for finance:
1. What are the contractual terms and is 75 days *agreed* (then forecast on it) or a breach (then escalate)?
2. How much of total billing does this client represent, and has the 75 days been stable or drifting upward?
3. Are any of its invoices disputed, short-paid or waiting on a purchase order or approval at their end?
4. Does the cash forecast already assume 75 days, and what is the cost of the extra working capital?
5. Can we offer an early-payment discount, move to milestone billing or require a deposit?
""")

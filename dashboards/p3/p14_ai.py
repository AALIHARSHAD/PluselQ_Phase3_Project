"""Task 14: AI signals dashboard (anomalies, forecast with band, forecast error)."""
import numpy as np
import pandas as pd
import streamlit as st
from p3.common import *
from pulseiq_metrics.forecast import company_series, backtest, error_by_horizon

header("AI signals",
       "Source: fact_anomaly, fact_forecast, fact_attrition_risk. These are model outputs from the AI service (sample feeds): a support signal for people, never a decision.")
w = get_wh()
note(f"<b>Every chart on this page is {AI_LABEL}.</b> Anomaly flags say a record looks unusual, not that anything is wrong. "
     "Forecasts are ranges, not promises.")

# ------------------------------------------------------------ anomalies
st.subheader("Anomalies: by type, biggest money at risk first")
an = w.view("v_anomaly_type")
pay = an[an.source_dataset == "payroll_monthly_features"].sort_values("money_at_risk", ascending=True)
att = an[an.source_dataset == "attendance_monthly_features"].sort_values("n_flags", ascending=True)
a, b = st.columns(2)
with a:
    ai_chip()
    f = base_fig(360, "Payroll anomalies — money at risk (₹ Cr)", ai=True)
    f.add_bar(y=pay.reason_code, x=pay.money_at_risk / 1e7, orientation="h", marker_color=BLUE, customdata=pay.n_flags,
              hovertemplate="%{y}: ₹%{x:.2f} Cr across %{customdata} flags<extra></extra>")
    f.update_layout(hovermode="closest", showlegend=False); f.update_xaxes(tickformat=".1f")
    st.plotly_chart(f, width="stretch")
    top = pay.iloc[-1]
    note(f"<b>In plain English:</b> {pay.n_flags.sum()} payroll lines were flagged with about {inr(pay.money_at_risk.sum())} of pay that could be wrong. "
         f"<b>{top.reason_code.replace('_',' ').title()}</b> carries the most money ({inr(top.money_at_risk)} on {int(top.n_flags)} lines) but is a loose “looks unusual” group; "
         "the small categories such as negative net pay or zero pay are the clearest to fix first. Money at risk is an exposure estimate, not a loss.")
with b:
    ai_chip()
    f = base_fig(360, "Attendance anomalies — number of flags", ai=True)
    f.add_bar(y=att.reason_code, x=att.n_flags, orientation="h", marker_color=AQUA, hovertemplate="%{y}: %{x} flags<extra></extra>")
    f.update_layout(hovermode="closest", showlegend=False)
    st.plotly_chart(f, width="stretch")
    note(f"<b>In plain English:</b> {int(att.n_flags.sum())} employee-months look unusual on attendance. By contract these rows carry <b>no money value</b> "
         "(money_at_risk is blank for attendance), so they are ranked by count, not rupees. “No attendance” and “long unpaid absence” are worth a manager check first.")
t = an.sort_values("money_at_risk", ascending=False, na_position="last")
tt = pd.DataFrame({"Type": t.reason_code, "Source": t.source_dataset.str.replace("_monthly_features", ""), "Plain-English reason": t.reason_text,
                   "Flags": t.n_flags, "Money at risk (₹)": t.money_at_risk.map(lambda v: "—" if pd.isna(v) else f"{v:,.0f}"),
                   "Avg score (0–1)": t.avg_score.map("{:.2f}".format)})
st.markdown(html_table(tt), unsafe_allow_html=True)
st.caption(f"Sorted by money at risk, biggest first; attendance types have no money value. {AI_LABEL}. Total flagged: {int(an.n_flags.sum())}.")

# ------------------------------------------------------------ forecast
st.subheader("Forecast versus actual, with the 80% range")
tbl = w.tables
fc_all = tbl["fact_forecast"]
metric = st.sidebar.radio("Forecast metric", ["headcount_end", "attrition_rate_monthly_pct"], key="fc_metric",
                          format_func=lambda m: "Headcount (end of month)" if m == "headcount_end" else "Attrition rate, monthly (%)")
depts = ["ALL"] + sorted(d for d in fc_all[fc_all.metric == metric].department_id.unique() if d != "ALL")
dnames = dict(zip(tbl["dim_department"].department_id, tbl["dim_department"].department_name))
dept = st.sidebar.selectbox("Scope", depts, format_func=lambda d: "Whole company" if d == "ALL" else dnames.get(d, d), key="fc_dept")
h = tbl["fact_headcount_monthly"]
if dept != "ALL":
    h = h[h.department_id == dept]
g = h.groupby("month").agg(he=("headcount_end", "sum"), ex=("exits", "sum"), hs=("headcount_start", "sum")).sort_index()
actual = g.he if metric == "headcount_end" else 100 * g.ex / g.hs
fc = fc_all[(fc_all.metric == metric) & (fc_all.department_id == dept)].sort_values("forecast_month")
trained = fc.trained_through.iloc[0]
hist = actual.iloc[-24:]
ai_chip()
f = base_fig(420, f"{'Headcount' if metric=='headcount_end' else 'Monthly attrition %'}: actual to {trained}, forecast after", ai=True)
f.add_scatter(x=hist.index, y=hist.values, name="Actual", mode="lines+markers", line=dict(color=BLUE, width=2), marker=dict(size=6))
f.add_scatter(x=fc.forecast_month, y=fc.upper_80, line=dict(width=0), showlegend=False, hoverinfo="skip")
f.add_scatter(x=fc.forecast_month, y=fc.lower_80, line=dict(width=0), fill="tonexty", fillcolor="rgba(235,104,52,.22)", name="80% range", hoverinfo="skip")
f.add_scatter(x=fc.forecast_month, y=fc.forecast_value, name="Forecast (AI)", mode="lines+markers", line=dict(color=ORANGE, width=2, dash="dash"), marker=dict(size=7),
              customdata=np.c_[fc.lower_80, fc.upper_80], hovertemplate="%{y:.1f}  (80% range %{customdata[0]:.1f} – %{customdata[1]:.1f})<extra>Forecast</extra>")
f.add_vline(x=pd.Timestamp(trained + "-01").to_pydatetime(), line_dash="dot", line_color=INK2)
f.add_annotation(x=pd.Timestamp(trained + "-01"), y=1, yref="paper", text="last actual month", showarrow=False, xanchor="right", font=dict(size=11, color=INK2))
f.update_yaxes(title="headcount" if metric == "headcount_end" else "% of start headcount")
st.plotly_chart(f, width="stretch")
width_end = fc.upper_80.iloc[-1] - fc.lower_80.iloc[-1]
note("<b>In plain English:</b> the orange line is the AI's best guess; the shaded band is where it expects the real number to fall four times out of five. "
     f"For {fc.forecast_month.iloc[-1]:%b %Y} the range is {fc.lower_80.iloc[-1]:.1f} to {fc.upper_80.iloc[-1]:.1f}, a width of {width_end:.1f}; "
     f"it widens the further ahead we look. Model: {fc.model_version.iloc[0]}, method “{fc.method.iloc[0]}”, trained through {trained}.")

# ------------------------------------------------------------ forecast error
st.subheader("Forecast error")
note(f"<b>No stored forecast month has an actual yet.</b> The feed was trained through {trained}, which is the last month of actuals (the data ends 30 Sep 2026), "
     "and its first forecast month is Oct 2026. So the error cannot be measured on the stored forecasts today. "
     "To still measure error honestly I re-ran the same documented method (linear trend over 36 months plus half-strength seasonality) from past months "
     "and compared it with actuals that were already known. My re-run reproduces the stored Oct 2026–Mar 2027 headcount forecast to within 0.4 of a person, so the test is fair for headcount. "
     "It is <b>my back-test, not the AI team's own error report</b>.")
S = company_series(tbl)
bt = backtest(S["headcount_end"])
eh = error_by_horizon(bt)
ai_chip()
a, b = st.columns(2)
with a:
    f = base_fig(340, "Forecast error by months ahead (company headcount, MAPE %)", ai=True)
    f.add_bar(x=eh.horizon.map(lambda x: f"{x} mo"), y=eh.mape_pct, name="AI baseline forecast", marker_color=ORANGE)
    f.add_bar(x=eh.horizon.map(lambda x: f"{x} mo"), y=eh.naive_mape_pct, name="Naive: repeat last month", marker_color=BLUE)
    f.update_layout(barmode="group", hovermode="x unified"); f.update_yaxes(title="MAPE %")
    st.plotly_chart(f, width="stretch")
with b:
    f = base_fig(340, "How often the actual fell inside the 80% range (%)", ai=True)
    f.add_bar(x=eh.horizon.map(lambda x: f"{x} mo"), y=eh.band_coverage_pct, marker_color=ORANGE, hovertemplate="%{y:.0f}%<extra></extra>")
    f.add_hline(y=80, line_dash="dot", line_color=INK, annotation_text="should be about 80%", annotation_position="top left")
    f.update_layout(showlegend=False, hovermode="closest"); f.update_yaxes(range=[0, 100])
    st.plotly_chart(f, width="stretch")
et = pd.DataFrame({"Months ahead": eh.horizon, "Forecasts tested": eh.forecasts, "AI baseline MAPE %": eh.mape_pct.map("{:.2f}".format),
                   "Naive MAPE %": eh.naive_mape_pct.map("{:.2f}".format), "Inside 80% range": eh.band_coverage_pct.map("{:.0f}%".format)})
st.markdown(html_table(et), unsafe_allow_html=True)
st.caption(f"{len(bt)} forecast-vs-actual pairs, forecasts started from each month with 36+ months of history (origins {bt.origin.min():%b %Y} to {bt.origin.max():%b %Y}). "
           "MAPE = average of |actual − forecast| ÷ actual. The 80% band in the back-test is approximated (the stored band is not reproducible from the feed). "
           "Attrition % is not back-tested: the stored attrition forecast could not be reproduced, and months with zero exits make MAPE undefined.")
w1 = eh.iloc[0]; w6 = eh.iloc[-1]
st.markdown(f"""
**Reading it:** at one month ahead the baseline is off by {w1.mape_pct:.1f}% on average and by {w6.mape_pct:.1f}% at six months, and a naive “same as last month” guess is *better* at every horizon
({w1.naive_mape_pct:.1f}% and {w6.naive_mape_pct:.1f}%). The 80% range caught the actual only {eh.band_coverage_pct.min():.0f}–{eh.band_coverage_pct.max():.0f}% of the time, so the band is too narrow: treat it as a floor on uncertainty.
""")
with st.expander("Think for yourself: forecast error was 12% last month. Is that good? What would you need to know?"):
    st.markdown(f"""
**It depends on what is being forecast, so you cannot say from the number alone.** For company headcount, the back-test above shows 1-month-ahead error near {w1.mape_pct:.1f}%, so 12% would be a very bad miss (about {0.12*S['headcount_end'].iloc[-1]:.0f} people on a headcount of {int(S['headcount_end'].iloc[-1])}). For a small, noisy number such as a monthly attrition rate (a few exits), 12% can be perfectly acceptable.

What I would need to know:
1. **Which metric and level** (company or one small department) and how noisy it normally is.
2. **A baseline:** is it better than the naive “same as last month” guess? Here the AI baseline is not.
3. **The horizon:** was it a 1-month or a 6-month forecast?
4. **Bias versus noise:** is it always too high or too low (fixable), or random?
5. **Cost of being wrong:** what decision depends on it (hiring plan, budget) and how big a miss is tolerable?
6. **One month or a pattern:** a single 12% month might be a one-off event such as a batch of joiners.
""")

# ------------------------------------------------------------ attrition risk
st.subheader("Predicted attrition risk (group level only)")
r = tbl["fact_attrition_risk"]
rr = r.groupby("department_id").agg(n=("prediction_id", "count"), high=("risk_band", lambda x: (x == "High").sum()), avg=("risk_score_12m", "mean")).reset_index()
shown = rr[rr.n >= MIN_GROUP].copy(); shown["name"] = shown.department_id.map(dnames); shown["high_share"] = 100 * shown.high / shown.n
shown = shown.sort_values("high_share")
ai_chip()
f = base_fig(360, "Share of scored people in the High risk band, by department (%)", ai=True)
f.add_bar(y=shown.name, x=shown.high_share, orientation="h", marker_color=BLUE, hovertemplate="%{y}: %{x:.0f}% of %{customdata} scored<extra></extra>", customdata=shown.n)
f.update_layout(showlegend=False, hovermode="closest"); f.update_xaxes(title="% of scored employees")
st.plotly_chart(f, width="stretch")
stale = len(tbl["fact_attrition_risk"]) 
note(f"<b>In plain English:</b> the model scored {len(r)} current employees for the chance of leaving within 12 months, as at {r.as_of_date.max():%d %b %Y}. "
     "“High” means the top 10% of scores. This is a prediction to start a supportive conversation, not a fact about anyone. Names and individuals are never shown; groups under 5 are hidden. "
     f"{int((w.clean_log.rule=='STALE_PREDICTION').sum())} stale predictions (six months older than the rest; DQ-09) were excluded.")

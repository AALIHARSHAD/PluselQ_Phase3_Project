from pathlib import Path
import pandas as pd
import streamlit as st
import altair as alt

import os
DATA_DIR = Path(os.environ.get("DATA_DIR", "/app/data"))
WORKBOOK = DATA_DIR / "PulseIQ_master_dataset.xlsx"
st.set_page_config(page_title="PulseIQ Phase 2", page_icon="📊", layout="wide")
st.title("PulseIQ | Phase 2 Analytics")
st.caption("People, teams, payroll and budget. Aggregated reporting only; small groups are suppressed.")

@st.cache_data(ttl=300)
def load_sheet(name):
    if not WORKBOOK.exists():
        raise FileNotFoundError(f"Master workbook not found: {WORKBOOK}")
    return pd.read_excel(WORKBOOK, sheet_name=name)

def suppress_small(df, group_col="department_id", count_col=None, threshold=5):
    if count_col and count_col in df.columns:
        return df[df[count_col] >= threshold].copy()
    if group_col in df.columns:
        counts = df.groupby(group_col).size()
        allowed = counts[counts >= threshold].index
        return df[df[group_col].isin(allowed)].copy()
    return df.copy()

def chart(df, x, y, color=None, title=None):
    if df.empty or x not in df or y not in df:
        st.info("No rows available for this chart.")
        return
    c = alt.Chart(df).mark_line(point=True).encode(
        x=alt.X(x, sort=None), y=alt.Y(y, title=y),
        color=color if color and color in df.columns else alt.value("#3572A5"),
        tooltip=list(dict.fromkeys([x, y] + ([color] if color and color in df.columns else [])))
    ).properties(height=320, title=title or "")
    st.altair_chart(c, use_container_width=True)

try:
    page = st.sidebar.radio("Phase 2 page", [
        "Task 6 — Attendance & leave",
        "Task 7 — Attrition",
        "Task 8 — Team productivity",
        "Task 9 — Payroll reconciliation",
        "Task 10 — Budget & KPI targets",
    ])
    depts = load_sheet("dim_department")
    dept_names = dict(zip(depts.department_id, depts.department_name))
except Exception as e:
    st.error(f"Unable to load workbook/dimensions: {e}")
    st.stop()

if page.startswith("Task 6"):
    a = load_sheet("fact_attendance_monthly")
    d = load_sheet("dim_date")
    l = load_sheet("fact_leave")
    lt = load_sheet("dim_leave_type")
    a["period_end_date"] = pd.to_datetime(a["period_end_date"], errors="coerce")
    if "period_year_month" not in a:
        a["period_year_month"] = a.period_end_date.dt.to_period("M").astype(str)
    a["department_name"] = a.department_id.map(dept_names).fillna(a.department_id)
    dept_opts = sorted(a.department_name.dropna().unique())
    selected = st.sidebar.multiselect("Department", dept_opts, default=dept_opts)
    a = a[a.department_name.isin(selected)]
    monthly = a.groupby(["period_year_month","department_name"], as_index=False).agg(
        scheduled_days=("scheduled_days","sum"), present_days=("present_days","sum"),
        late_arrivals=("late_arrivals","sum"), overtime_hours=("overtime_hours","sum"),
        employees=("employee_id","nunique"))
    monthly["attendance_rate_pct"] = 100*monthly.present_days/monthly.scheduled_days.replace(0, pd.NA)
    monthly["late_arrivals_per_100_scheduled_days"] = 100*monthly.late_arrivals/monthly.scheduled_days.replace(0,pd.NA)
    st.header("Attendance and leave trends")
    total_sched, total_present = monthly.scheduled_days.sum(), monthly.present_days.sum()
    rate = 100*total_present/total_sched if total_sched else 0
    c1,c2,c3,c4=st.columns(4)
    c1.metric("Weighted attendance rate", f"{rate:.2f}%")
    c2.metric("Late arrivals", f"{int(monthly.late_arrivals.sum()):,}")
    c3.metric("Overtime hours", f"{monthly.overtime_hours.sum():,.1f}")
    c4.metric("Scheduled days", f"{int(total_sched):,}")
    st.caption("Attendance denominator: total scheduled working days in the attendance fact (present_days ÷ scheduled_days). Rates are not summed.")
    chart(monthly, "period_year_month", "attendance_rate_pct", "department_name", "Monthly attendance rate (%)")
    c1,c2=st.columns(2)
    with c1: chart(monthly, "period_year_month", "late_arrivals", "department_name", "Late arrivals by month")
    with c2: chart(monthly, "period_year_month", "overtime_hours", "department_name", "Overtime hours by month")
    l["start_date"] = pd.to_datetime(l["start_date"], errors="coerce")
    l = l[l.status.astype(str).str.lower().eq("approved")].copy()
    l["month"] = l.start_date.dt.to_period("M").astype(str)
    l = l.merge(lt[["leave_type_code","leave_type_name"]], on="leave_type_code", how="left")
    leave_month = l.groupby(["month","leave_type_name"],as_index=False).agg(approved_leave_days=("days","sum"), requests=("leave_request_id","nunique"))
    st.subheader("Approved leave days by type")
    if not leave_month.empty:
        st.bar_chart(leave_month.pivot(index="month",columns="leave_type_name",values="approved_leave_days").fillna(0))
    # calendar context
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d["year_month"] = d["date"].dt.to_period("M").astype(str)
    holidays = d[d.is_holiday.astype(str).str.upper().isin(["Y","YES","TRUE","1"])].copy()
    st.subheader("Calendar context")
    if holidays.empty:
        st.warning("No holiday rows were identified using the workbook's is_holiday flag.")
    else:
        st.dataframe(holidays[["date","day_of_week","is_holiday","is_weekend","is_working_day"]], use_container_width=True, hide_index=True)
    st.caption("Long-weekend context is shown from calendar flags; this page does not claim a causal effect from holidays without further evidence.")
    st.subheader("Numeric findings (data-driven)")
    if not monthly.empty:
        month_rate = monthly.groupby("period_year_month",as_index=False).apply(
            lambda x: pd.Series({"attendance_rate_pct":100*x.present_days.sum()/x.scheduled_days.sum() if x.scheduled_days.sum() else None,
                                 "late_arrivals":x.late_arrivals.sum(),"overtime_hours":x.overtime_hours.sum()}),
            include_groups=False).reset_index(drop=True)
        if len(month_rate):
            low=month_rate.nsmallest(1,"attendance_rate_pct").iloc[0]
            highlate=month_rate.nlargest(1,"late_arrivals").iloc[0]
            hio=month_rate.nlargest(1,"overtime_hours").iloc[0]
            st.write(f"- Lowest attendance month: **{low.period_year_month}**, {low.attendance_rate_pct:.2f}%.")
            st.write(f"- Highest late-arrival month: **{highlate.period_year_month}**, {int(highlate.late_arrivals):,} arrivals.")
            st.write(f"- Highest overtime month: **{hio.period_year_month}**, {hio.overtime_hours:,.1f} hours.")
    st.dataframe(monthly.sort_values(["period_year_month","department_name"]),use_container_width=True,hide_index=True)

elif page.startswith("Task 7"):
    h=load_sheet("fact_headcount_monthly")
    h["month"] = pd.to_datetime(h["month_start_date"], errors="coerce").dt.to_period("M").astype(str)
    h["department_name"]=h.department_id.map(dept_names).fillna(h.department_id)
    sel=st.sidebar.multiselect("Department",sorted(h.department_name.unique()),default=sorted(h.department_name.unique()))
    h=h[h.department_name.isin(sel)]
    st.header("Attrition analytics — actual and predicted separated")
    st.subheader("Actual exits")
    st.metric("Exits in selected data",f"{int(h.exits.sum()):,}")
    actual=h.groupby(["month","department_name"],as_index=False).agg(exits=("exits","sum"),voluntary_exits=("voluntary_exits","sum"),headcount=("headcount_start","sum"))
    actual["attrition_pct"]=100*actual.exits/actual.headcount.replace(0,pd.NA)
    chart(actual,"month","exits","department_name","Actual exits by month")
    st.dataframe(actual,use_container_width=True,hide_index=True)
    risk=load_sheet("fact_attrition_risk")
    risk["department_name"]=risk.department_id.map(dept_names).fillna(risk.department_id)
    grouped=risk.groupby(["department_name","risk_band"],as_index=False).agg(predictions=("prediction_id","count"),mean_risk_score=("risk_score_12m","mean"))
    grouped=grouped[grouped.predictions>=5]
    st.subheader("Predicted, not certain")
    st.warning("Risk scores are model predictions, not facts or decisions about individuals. Use them only to guide supportive group-level review. Individual names and IDs are not displayed.")
    st.dataframe(grouped,use_container_width=True,hide_index=True)
    if not actual.empty:
        top=actual.groupby("department_name",as_index=False).agg(exits=("exits","sum"),voluntary_exits=("voluntary_exits","sum"))
        st.write("**Numeric findings**")
        st.write(f"- Highest-exit month: {actual.groupby('month').exits.sum().idxmax()} ({int(actual.groupby('month').exits.sum().max())} exits).")
        st.write(f"- Highest-exit department in selection: {top.sort_values('exits',ascending=False).iloc[0].department_name} ({int(top.exits.max())} exits).")
        st.write(f"- Voluntary exits across selected departments: {int(h.voluntary_exits.sum()):,}.")

elif page.startswith("Task 8"):
    t=load_sheet("fact_task")
    teams=load_sheet("dim_team")
    sprints=load_sheet("dim_sprint")
    t=t.merge(teams[["team_id","team_name","department_id"]],on="team_id",how="left")
    t=t.merge(sprints[["sprint_id","sprint_name","working_days"]],on="sprint_id",how="left")
    st.header("Team productivity")
    st.info("Rules: velocity = story points on completed tasks; cycle time = mean recorded cycle_time_days for completed tasks; on-time rate = completed_on_time among completed tasks with known flag. Cancelled tasks are excluded from delivery metrics; blocked status is reported separately where present.")
    statuses=t.status.astype(str).str.lower()
    cancelled=statuses.str.contains("cancel")
    completed=statuses.str.contains("complete|done|closed",regex=True) & ~cancelled
    blocked=statuses.str.contains("block")
    reopened=pd.to_numeric(t.reopened_count,errors="coerce").fillna(0)>0
    t["completed_flag"]=completed
    t["points_completed"]=pd.to_numeric(t.story_points,errors="coerce").where(completed,0).fillna(0)
    t["cycle_completed"]=pd.to_numeric(t.cycle_time_days,errors="coerce").where(completed)
    t["on_time_flag"]=t.completed_on_time.where(completed)
    team= t.groupby(["team_name","sprint_name"],as_index=False).agg(
        tasks=("task_id","count"),completed=("completed_flag","sum"),velocity=("points_completed","sum"),
        mean_cycle_days=("cycle_completed","mean"),blocked_tasks=("status",lambda x: x.astype(str).str.lower().str.contains("block").sum()),
        reopened_tasks=("reopened_count",lambda x: (pd.to_numeric(x,errors="coerce").fillna(0)>0).sum()),
        on_time_rate=("on_time_flag","mean"))
    team["on_time_rate_pct"]=100*team.on_time_rate
    names=sorted(team.team_name.dropna().unique())
    pick=st.sidebar.multiselect("Team",names,default=names)
    team=team[team.team_name.isin(pick)]
    sprint_names=sorted(team.sprint_name.dropna().unique())
    sprint=st.sidebar.selectbox("Sprint",["All"]+sprint_names)
    if sprint!="All": team=team[team.sprint_name.eq(sprint)]
    c1,c2,c3=st.columns(3)
    c1.metric("Completed story points",f"{team.velocity.sum():,.0f}")
    c2.metric("Blocked tasks",f"{int(team.blocked_tasks.sum()):,}")
    c3.metric("Tasks with reopen count",f"{int(team.reopened_tasks.sum()):,}")
    st.dataframe(team,use_container_width=True,hide_index=True)
    chart(team,"sprint_name","velocity","team_name","Velocity by sprint")
    st.caption("Interpret team comparisons with context: team size, task type and sprint working days differ. Validate at least two teams manually before reporting final conclusions.")

elif page.startswith("Task 9"):
    p=load_sheet("fact_payroll")
    ans=load_sheet("reconciliation_answer_key")
    p["month"]=pd.to_datetime(p.period_end_date,errors="coerce").dt.to_period("M").astype(str)
    p["department_name"]=p.department_id.map(dept_names).fillna(p.department_id)
    p["employer_cost"]=pd.to_numeric(p.employer_cost,errors="coerce")
    p["gross_pay"]=pd.to_numeric(p.gross_pay,errors="coerce")
    p["net_pay"]=pd.to_numeric(p.net_pay,errors="coerce")
    # Aggregate only; do not display employee identifiers or individual pay.
    payroll=p.groupby(["month","department_id","department_name"],as_index=False).agg(
        paid_employees=("employee_id","nunique"),gross_pay=("gross_pay","sum"),net_pay=("net_pay","sum"),employer_cost=("employer_cost","sum"))
    payroll=payroll[payroll.paid_employees>=5]
    payroll["cost_per_employee"]=payroll.employer_cost/payroll.paid_employees
    st.header("Payroll cost and reconciliation")
    st.caption("Only department-month totals and averages are shown; groups with fewer than five paid employees are suppressed.")
    chart(payroll,"month","employer_cost","department_name","Employer cost trend")
    st.dataframe(payroll,use_container_width=True,hide_index=True)
    monthly=p.groupby("month",as_index=False).agg(employees_paid=("employee_id","nunique"),payroll_gross_pay=("gross_pay","sum"),payroll_net_pay=("net_pay","sum"),payroll_employer_cost=("employer_cost","sum"))
    ans["month"]=pd.to_datetime(ans["month"],errors="coerce").dt.to_period("M").astype(str)
    rec=monthly.merge(ans[["month","employees_paid","payroll_gross_pay","payroll_net_pay","payroll_employer_cost","payroll_vs_ledger_difference"]],on="month",how="left",suffixes=("_actual","_answer"))
    for col in ["employees_paid","payroll_gross_pay","payroll_net_pay","payroll_employer_cost"]:
        rec[col+"_difference"]=rec[col+"_actual"]-rec[col+"_answer"]
    st.subheader("Answer-key reconciliation")
    st.dataframe(rec,use_container_width=True,hide_index=True)
    st.warning("Reconciliation is displayed, not silently forced to zero. Investigate and document bad rows before excluding them; this page does not remove rows without a verified rule.")

else:
    b=load_sheet("budget_payroll_dept_month")
    k=load_sheet("kpi_targets")
    p=load_sheet("fact_payroll")
    p["month"]=pd.to_datetime(p.period_end_date,errors="coerce").dt.to_period("M").astype(str)
    actual=p.groupby(["month","department_id"],as_index=False).agg(actual_payroll_cost=("employer_cost","sum"),paid_employees=("employee_id","nunique"))
    b["month"]=pd.to_datetime(b["month"],errors="coerce").dt.to_period("M").astype(str)
    data=b.merge(actual,on=["month","department_id"],how="left")
    data["department_name"]=data.department_id.map(dept_names).fillna(data.department_id)
    data["variance"]=data.actual_payroll_cost-data.budget_payroll_cost
    data["variance_pct"]=100*data.variance/data.budget_payroll_cost.replace(0,pd.NA)
    data["status"]=data.variance.apply(lambda v:"OVER BUDGET" if pd.notna(v) and v>0 else ("WITHIN/UNDER" if pd.notna(v) else "NO ACTUAL"))
    st.header("Budget versus actual and KPI targets")
    st.caption("Sign rule: positive variance = overspend (actual minus budget); negative variance = underspend.")
    visible=data[data.paid_employees.fillna(0)>=5].copy()
    c1,c2=st.columns(2)
    c1.metric("Total budget (visible groups)",f"{visible.budget_payroll_cost.sum():,.2f}")
    c2.metric("Total actual (visible groups)",f"{visible.actual_payroll_cost.sum():,.2f}")
    chart(visible,"month","variance","department_name","Payroll variance by month")
    st.subheader("Departments ranked by overspend")
    ranking=visible.groupby("department_name",as_index=False).agg(variance=("variance","sum"),budget=("budget_payroll_cost","sum"),actual=("actual_payroll_cost","sum"))
    ranking=ranking.sort_values("variance",ascending=False)
    st.dataframe(ranking,use_container_width=True,hide_index=True)
    st.subheader("KPI targets")
    k["month"]=pd.to_datetime(k["month"],errors="coerce").dt.to_period("M").astype(str)
    k["department_name"]=k.department_id.map(dept_names).fillna(k.department_id)
    st.dataframe(k,use_container_width=True,hide_index=True)
    st.info("KPI target columns are displayed from the source dictionary. A traffic-light status is not inferred where the source does not specify the exact threshold rule; document the agreed rule before operational use.")

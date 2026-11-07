"""PulseIQ Phase 3 - money and insight (Tasks 11-15). Run: streamlit run dashboards/phase3_app.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import streamlit as st

st.set_page_config(page_title="PulseIQ Phase 3", page_icon="📊", layout="wide")
pages = [
    st.Page("p3/p15_scorecard.py", title="Company health scorecard", icon="🏁", url_path="scorecard", default=True),
    st.Page("p3/p11_pnl.py", title="Profit & loss", icon="💰", url_path="pnl"),
    st.Page("p3/p12_cash.py", title="Receivables & cash", icon="🏦", url_path="cash"),
    st.Page("p3/p13_dept.py", title="Department impact", icon="🧩", url_path="departments"),
    st.Page("p3/p14_ai.py", title="AI signals", icon=":material/auto_awesome:", url_path="ai"),
    st.Page("p2_people.py", title="Phase 2: People, teams, budget", icon="👥", url_path="people"),
]
st.navigation(pages).run()

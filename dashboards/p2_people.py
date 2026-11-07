"""Phase 2 people / teams / budget pages (Tasks 6-10), mounted inside the Phase 3 navigation so scorecard links work.

dashboards/app.py is unchanged apart from reading DATA_DIR from the environment; it still runs on its own:
    streamlit run dashboards/app.py
"""
import os
import runpy
from pathlib import Path
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("DATA_DIR", str(ROOT / "data"))
st.set_page_config = lambda *a, **k: None          # the entry file already set the page config
runpy.run_path(str(Path(__file__).with_name("app.py")), run_name="__main__")

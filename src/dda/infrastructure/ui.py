"""Streamlit dashboard entrypoint.

Called by: streamlit run src/dda/infrastructure/ui.py

Page routing uses st.navigation (Streamlit ≥ 1.36) which replaces the old
multipage file-based approach. If the installed version is older, each page
renders inline via sidebar radio instead — both paths produce the same UI.
"""
import importlib

import streamlit as st

from dda.infrastructure.ui import api_client

_PAGES = {
    "🔍 Scan": "dda.infrastructure.ui.page_scan",
    "📦 Inventory": "dda.infrastructure.ui.page_inventory",
    "⚠️ Findings": "dda.infrastructure.ui.page_findings",
    "📋 Migration Plan": "dda.infrastructure.ui.page_migration",
    "🔎 KB Search": "dda.infrastructure.ui.page_kb_search",
}

st.set_page_config(
    page_title="Dependency Deprecation Agent",
    page_icon="🔍",
    layout="wide",
)

# Sidebar: health badge + navigation
with st.sidebar:
    st.title("DDA")
    h = api_client.health()
    api_ok = h.get("status") == "ok"
    st.caption("API " + ("🟢 online" if api_ok else "🔴 offline"))

    selected = st.radio("Navigate", list(_PAGES.keys()), label_visibility="collapsed")

# Load and render the selected page module.
module_path = _PAGES[selected]  # type: ignore[index]
page_module = importlib.import_module(module_path)
page_module.render()

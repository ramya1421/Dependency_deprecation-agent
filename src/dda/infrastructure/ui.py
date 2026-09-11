"""Streamlit dashboard entrypoint.

Called by: streamlit run src/dda/infrastructure/ui.py

Set DDA_API_URL in Streamlit Cloud secrets (or a local .env) to point at
your deployed FastAPI backend, e.g.:
  DDA_API_URL = "https://your-api.onrender.com"

Falls back to http://localhost:8000 for local development.
"""
import importlib
import os

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

# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🔍 DDA")
    st.caption("Dependency Deprecation Agent")
    st.divider()

    # Show which API this UI is talking to so misconfiguration is obvious.
    api_url = api_client.get_api_base()
    is_local = api_url.startswith("http://localhost")

    h = api_client.health()
    api_ok = h.get("status") in ("ok", "degraded")

    if api_ok:
        if h.get("status") == "ok":
            st.success("API online")
        else:
            st.warning("API online (degraded)")
            if h.get("qdrant", "").startswith("error"):
                st.caption("⚠️ Qdrant: check QDRANT_URL / QDRANT_API_KEY")
        st.caption(f"`{api_url}`")
    else:
        st.error("API unreachable")
        st.caption(f"Trying: `{api_url}`")
        if is_local:
            st.warning(
                "Running locally? Start the API first:\n```\nmake run-api\n```"
            )
        else:
            st.warning(
                "Deployed? Make sure `DDA_API_URL` is set correctly "
                "in your Streamlit Cloud secrets."
            )
            st.info(
                "**To fix:** Go to your Streamlit Cloud app → "
                "Settings → Secrets → add:\n"
                "```\nDDA_API_URL = \"https://your-api.onrender.com\"\n```"
            )

    st.divider()
    selected = st.radio("Navigate", list(_PAGES.keys()), label_visibility="collapsed")

# ── Page render ───────────────────────────────────────────────────────────────
module_path = _PAGES[selected]  # type: ignore[index]
page_module = importlib.import_module(module_path)
page_module.render()

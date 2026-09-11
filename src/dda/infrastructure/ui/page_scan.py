"""Scan page: repo URL input, trigger scan, poll status, show parse coverage."""
import time

import streamlit as st

from dda.infrastructure.ui import api_client


def render() -> None:
    st.header("Scan a Repository")

    with st.form("scan_form"):
        repo_path = st.text_input(
            "Repository path or URL",
            placeholder="/path/to/repo  or  https://github.com/owner/repo",
        )
        offline = st.checkbox("Offline mode (serve from cache only)")
        submitted = st.form_submit_button("Scan")

    if submitted and repo_path.strip():
        with st.spinner("Queuing scan…"):
            scan_id = api_client.trigger_scan(repo_path.strip(), offline)
        if scan_id is None:
            st.error("Could not reach the API. Is `make run-api` running?")
            return
        st.success(f"Scan queued: `{scan_id}`")
        st.session_state["active_scan_id"] = scan_id

    scan_id = st.session_state.get("active_scan_id")
    if not scan_id:
        return

    st.divider()
    st.subheader(f"Scan `{scan_id}`")

    # Poll until the scan is no longer "queued" or "running".
    # Streamlit re-runs the whole script on every interaction — scans run
    # async with polling rather than inline so the UI stays responsive.
    status_placeholder = st.empty()
    for _ in range(60):
        scan = api_client.get_scan_status(scan_id)
        if scan is None:
            status_placeholder.warning("Waiting for API…")
            time.sleep(2)
            continue
        status = scan.get("status", "unknown")
        status_placeholder.info(f"Status: **{status}**")
        if status not in ("queued", "running"):
            break
        time.sleep(3)
        st.rerun()

    scan = api_client.get_scan_status(scan_id)
    if scan:
        st.json(scan)

    deps = api_client.get_dependencies(scan_id)
    if deps:
        st.metric("Dependencies found", len(deps))
        direct = sum(1 for d in deps if d.get("is_direct"))
        st.caption(f"{direct} direct · {len(deps) - direct} transitive")

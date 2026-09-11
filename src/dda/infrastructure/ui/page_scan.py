"""Scan page: repo URL input, trigger scan, poll status, show parse coverage."""
import time

import streamlit as st

from dda.infrastructure.ui import api_client


def render() -> None:
    st.header("Scan a Repository")

    # Show a clear, actionable banner when the API is unreachable.
    # Streamlit re-runs the whole script on every interaction, so this check
    # runs on every page load and immediately tells the user what to fix.
    h = api_client.health()
    api_up = h.get("status") == "ok"

    if not api_up:
        api_url = api_client.get_api_base()
        is_local = api_url.startswith("http://localhost")
        if is_local:
            st.error(
                "**API is not running.**\n\n"
                "Open a terminal in the project root and run:\n"
                "```bash\nmake run-api\n```\n"
                "Then refresh this page."
            )
        else:
            st.error(
                f"**Cannot reach the API** at `{api_url}`\n\n"
                "**Most likely fix:** Set `DDA_API_URL` in your Streamlit Cloud secrets.\n\n"
                "Go to your app → **Settings → Secrets** → add:\n"
                "```toml\nDDA_API_URL = \"https://your-api.onrender.com\"\n```\n\n"
                "If the API is on Render free tier it may be sleeping (15 min idle). "
                f"[Click here to wake it]({api_url}/health), wait ~50 seconds, then refresh."
            )
        return

    # ── Scan form ─────────────────────────────────────────────────────────────
    with st.form("scan_form"):
        repo_path = st.text_input(
            "Repository path or GitHub URL",
            placeholder="https://github.com/owner/repo  or  /local/path/to/project",
        )
        offline = st.checkbox(
            "Offline mode (serve signals from SQLite cache only, no network calls)"
        )
        submitted = st.form_submit_button("🔍 Scan", use_container_width=True)

    if submitted and repo_path.strip():
        with st.spinner("Queuing scan…"):
            scan_id = api_client.trigger_scan(repo_path.strip(), offline)
        if scan_id is None:
            st.error("Scan request failed — the API returned an error. Check the API logs.")
            return
        st.success(f"Scan queued! ID: `{scan_id}`")
        st.session_state["active_scan_id"] = scan_id

    scan_id = st.session_state.get("active_scan_id")
    if not scan_id:
        st.info("Enter a repo URL above and click **Scan** to get started.")
        return

    st.divider()
    st.subheader(f"Scan `{scan_id}`")

    # Poll until the scan leaves queued/running state.
    # Scans are async with polling because Streamlit re-runs the whole script
    # on every interaction — running scans inline would block the UI.
    status_placeholder = st.empty()
    for _ in range(60):
        scan = api_client.get_scan_status(scan_id)
        if scan is None:
            status_placeholder.warning("Waiting for API response…")
            time.sleep(2)
            continue
        status = scan.get("status", "unknown")
        if status == "queued":
            status_placeholder.info("⏳ Queued — waiting to start…")
        elif status == "running":
            status_placeholder.info("🔄 Running — parsing manifests and collecting signals…")
        elif status == "completed":
            status_placeholder.success("✅ Completed!")
            break
        else:
            status_placeholder.warning(f"Status: {status}")
            break
        time.sleep(3)
        st.rerun()

    scan = api_client.get_scan_status(scan_id)
    if scan:
        cols = st.columns(3)
        cols[0].metric("Status", scan.get("status", "—"))
        cols[1].metric("Scan ID", scan_id[:8] + "…")
        cols[2].metric("Started", str(scan.get("started_at", "—"))[:19])

    deps = api_client.get_dependencies(scan_id)
    if deps:
        direct = sum(1 for d in deps if d.get("is_direct"))
        col1, col2, col3 = st.columns(3)
        col1.metric("Total dependencies", len(deps))
        col2.metric("Direct", direct)
        col3.metric("Transitive", len(deps) - direct)
        st.caption("Switch to **📦 Inventory** to see risk scores, or **⚠️ Findings** to filter by severity.")

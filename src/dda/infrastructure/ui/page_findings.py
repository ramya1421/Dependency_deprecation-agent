"""Findings page: risk-ranked list, filterable by severity."""
import streamlit as st

from dda.infrastructure.ui import api_client

_SEVERITY_COLORS = {
    "critical": "🔴",
    "high": "🟠",
    "medium": "🟡",
    "low": "🟢",
    "none": "⚪",
}


def render() -> None:
    st.header("Risk Findings")

    scan_id = st.session_state.get("active_scan_id", "")
    scan_id = st.text_input("Scan ID", value=scan_id, placeholder="Paste a scan ID")
    if scan_id.strip():
        st.session_state["active_scan_id"] = scan_id.strip()
    if not scan_id.strip():
        return

    findings = api_client.get_findings(scan_id.strip())
    if not findings:
        st.info("No findings yet — scan may still be running.")
        return

    min_risk = st.slider("Minimum risk score", 0, 100, 0, step=5)
    filtered = [f for f in findings if f["risk_score"]["total"] >= min_risk]

    st.caption(f"Showing {len(filtered)} of {len(findings)} finding(s)")

    for f in filtered:
        risk = f["risk_score"]
        total = risk["total"]
        icon = _risk_icon(total)
        with st.expander(f"{icon} **{f['dependency_name']}** — risk {total:.0f}/100"):
            cols = st.columns(3)
            cols[0].metric("Risk total", f"{total:.0f}")
            cols[1].metric("Signals", f["signal_count"])
            cols[2].metric("Call sites", f["usage_site_count"])

            if risk.get("rationale"):
                st.markdown("**Rationale**")
                for r in risk["rationale"]:
                    st.markdown(f"- {r}")

            if risk.get("components"):
                st.markdown("**Score breakdown**")
                for component, score in sorted(
                    risk["components"].items(), key=lambda x: x[1], reverse=True
                ):
                    st.progress(int(score), text=f"{component}: {score:.0f}")

            if f.get("has_migration_plan"):
                if st.button("View migration plan", key=f"plan_{f['dependency_name']}"):
                    st.session_state["selected_dep"] = f["dependency_name"]
                    st.switch_page("page_migration")  # type: ignore[attr-defined]


def _risk_icon(total: float) -> str:
    if total >= 70:
        return "🔴"
    if total >= 40:
        return "🟠"
    if total >= 20:
        return "🟡"
    return "🟢"

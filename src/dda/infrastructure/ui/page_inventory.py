"""Inventory page: dependency table with risk scores and component breakdowns."""
import pandas as pd
import streamlit as st

from dda.infrastructure.ui import api_client


def render() -> None:
    st.header("Dependency Inventory")

    scan_id = _scan_id_input()
    if not scan_id:
        return

    findings = api_client.get_findings(scan_id)
    deps = api_client.get_dependencies(scan_id)

    if not deps:
        st.warning("No dependencies found. Run a scan first.")
        return

    risk_by_name = {f["dependency_name"]: f["risk_score"] for f in findings}

    rows = []
    for d in deps:
        name = d["name"]
        risk = risk_by_name.get(name, {})
        rows.append({
            "Package": name,
            "Ecosystem": d.get("ecosystem", ""),
            "Version": d.get("resolved_version") or d.get("declared_spec", ""),
            "Direct": "✓" if d.get("is_direct") else "",
            "Dev": "✓" if d.get("is_dev") else "",
            "Risk": round(risk.get("total", 0.0), 1),
            "Rationale": "; ".join(risk.get("rationale", [])),
        })

    df = pd.DataFrame(rows).sort_values("Risk", ascending=False)
    st.dataframe(
        df,
        use_container_width=True,
        column_config={
            "Risk": st.column_config.ProgressColumn(
                "Risk", min_value=0, max_value=100, format="%.0f"
            )
        },
    )

    st.caption(f"{len(deps)} total · {sum(1 for d in deps if d.get('is_direct'))} direct")


def _scan_id_input() -> str:
    preset = st.session_state.get("active_scan_id", "")
    scan_id = st.text_input("Scan ID", value=preset, placeholder="Paste a scan ID")
    if scan_id.strip():
        st.session_state["active_scan_id"] = scan_id.strip()
    return scan_id.strip()

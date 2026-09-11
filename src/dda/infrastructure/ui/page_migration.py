"""Migration detail page: plan, usage sites as file:line, citations as links."""
import streamlit as st

from dda.infrastructure.ui import api_client


def render() -> None:
    st.header("Migration Plan")

    scan_id = st.session_state.get("active_scan_id", "")
    dep_name = st.session_state.get("selected_dep", "")

    col1, col2 = st.columns(2)
    scan_id = col1.text_input("Scan ID", value=scan_id)
    dep_name = col2.text_input("Package", value=dep_name, placeholder="e.g. moment")

    if scan_id.strip():
        st.session_state["active_scan_id"] = scan_id.strip()
    if dep_name.strip():
        st.session_state["selected_dep"] = dep_name.strip()

    if not (scan_id.strip() and dep_name.strip()):
        return

    plan = api_client.get_migration_plan(scan_id.strip(), dep_name.strip())
    if plan is None:
        st.warning("No migration plan found. Run `dda migrate` first or wait for agent to finish.")
        return

    st.subheader(f"Migrating off **{plan['package']}**")
    st.info(plan["summary"])

    effort_colors = {"trivial": "green", "small": "blue", "medium": "orange", "large": "red"}
    effort = plan.get("effort", "unknown")
    color = effort_colors.get(effort, "gray")
    st.markdown(
        f"**Effort estimate:** :{color}[{effort.upper()}] "
        f"· {plan.get('usage_site_count', 0)} call site(s)"
    )

    st.divider()
    st.subheader("Migration Steps")
    for i, step in enumerate(plan.get("steps", []), 1):
        st.markdown(f"**{i}.** {step}")

    claims = plan.get("claims", [])
    if claims:
        st.divider()
        st.subheader(f"Citations ({len(claims)} verified)")
        for claim in claims:
            score = claim.get("entailment_score") or 0.0
            chunk_id = claim["chunk_id"]
            verified_icon = "✅" if claim.get("verified") else "❌"
            st.markdown(
                f"{verified_icon} `[{chunk_id}]` score={score:.2f}  \n"
                f"> {str(claim['text'])[:200]}"
            )

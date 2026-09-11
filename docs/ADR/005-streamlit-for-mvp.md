# ADR-005: Streamlit for MVP UI

**Status:** Accepted  
**Date:** 2026-09

---

## Context

The project needs a usable dashboard for the demo: scan trigger, dependency inventory, risk findings, and migration plan display with citations. A production-grade frontend (React/Next.js) was considered.

---

## Decision

Use **Streamlit** for the MVP UI, communicating with the FastAPI backend via HTTP.

---

## Alternatives Considered

**React + TypeScript SPA.**  
Would produce a more polished UI. Rejected because: (1) it doubles the language surface of a solo 14-day build; (2) Streamlit's constraint — the whole script re-runs on every interaction — is an asset here, not a liability. It forced the scan flow to be async with polling rather than inline, which is the correct architecture regardless of UI framework. A React SPA would have made it tempting to run scans synchronously in a fetch call, which breaks under any real repo size.

**Gradio.**  
Simpler than Streamlit but less composable. The citation display (clicking through to source URLs, showing entailment scores per claim) requires more layout control than Gradio's component set offers without custom HTML.

**Jupyter notebook.**  
Considered for the evaluation dashboard only. Rejected because it requires a running kernel and doesn't integrate cleanly with the FastAPI backend for live scan data.

**No UI at all (CLI-only for V1).**  
A reasonable choice. The CLI is complete and covers every use case. The Streamlit UI adds value for the demo but adds no architectural substance. If the UI had required more than 6 hours of effort it would have been cut.

---

## Consequences

- Streamlit re-runs the entire script on every interaction. All state is in `st.session_state` and all long-running work is in the FastAPI backend. This is documented in a comment in `ui.py`.
- The UI and API communicate via HTTP (`api_client.py`) rather than direct Python imports. This means the UI is independently deployable (Streamlit Community Cloud) without the API's ML dependencies loaded in the same process.
- Styling is Streamlit defaults. No custom CSS. Time spent on CSS is time not spent on the evaluation harness, which matters more.
- V2 can replace Streamlit with React without touching the FastAPI layer. The HTTP contract between UI and API is the stable interface.

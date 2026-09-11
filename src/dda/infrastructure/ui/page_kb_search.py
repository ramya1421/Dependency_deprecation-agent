"""KB search page: debug view for the retrieval pipeline."""
import streamlit as st

from dda.infrastructure.ui import api_client


def render() -> None:
    st.header("Knowledge Base Search")
    st.caption("Debug endpoint — searches the migration KB directly.")

    with st.form("kb_search_form"):
        query = st.text_input("Query", placeholder="moment format breaking change")
        package = st.text_input("Filter by package (optional)", placeholder="moment")
        top_k = st.slider("Top K", 1, 20, 5)
        submitted = st.form_submit_button("Search")

    if not submitted or not query.strip():
        return

    with st.spinner("Searching…"):
        hits = api_client.kb_search(query.strip(), package.strip() or None, top_k)

    if not hits:
        st.warning("No results. Is the KB built and ingested? Run `dda kb build` then `dda kb ingest`.")
        return

    st.caption(f"{len(hits)} result(s)")
    for i, hit in enumerate(hits, 1):
        label = (
            f"#{i} · **{hit['package']}** · {hit['doc_type']} "
            f"· `{hit['chunk_id']}` "
            + (f"· v{hit['version']}" if hit.get("version") else "")
        )
        with st.expander(label):
            st.markdown(f"[{hit['source_url']}]({hit['source_url']})")
            st.markdown(f"*{hit['header_path']}*")
            st.text(hit["text_preview"])

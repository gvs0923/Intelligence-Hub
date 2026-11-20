import re
from collections import Counter

import pandas as pd
import streamlit as st
from prometheus_client.parser import text_string_to_metric_families

from src.ui.api_client import APIError, HubClient

_QUERY_PATHS = ("/api/query", "/api/query/stream")
_WORD = re.compile(r"[a-z][a-z0-9_\-]{2,}")
_STOP = {
    "the", "and", "for", "with", "what", "why", "how", "when", "where", "does",
    "are", "was", "can", "our", "this", "that", "from", "about", "after", "into",
}


def render_analytics(client: HubClient) -> None:
    st.title("Analytics")
    _index_stats(client)
    st.divider()
    _server_metrics(client)
    st.divider()
    _session_metrics()


def _index_stats(client: HubClient) -> None:
    st.subheader("Index")
    try:
        s = client.stats()
    except APIError as exc:
        st.error(str(exc))
        return
    cols = st.columns(5)
    cols[0].metric("Sources", s["total_sources"])
    cols[1].metric("Documents", s["total_documents"])
    cols[2].metric("Chunks (SQLite)", s["total_chunks"])
    cols[3].metric("Vectors (Chroma)", s["chroma_vectors"])
    cols[4].metric(
        "Index drift", s["index_drift"],
        help="SQLite chunks minus Chroma vectors. Anything other than 0 means the stores disagree.",
    )
    if not s["bm25_loaded"]:
        st.warning("No BM25 index on disk yet, so keyword search returns nothing. Ingest a source first.")
    if s["index_drift"]:
        st.warning("SQLite and Chroma are out of sync. Re-ingest the affected source.")


def _server_metrics(client: HubClient) -> None:
    st.subheader("Server (since API start)")
    try:
        text = client.metrics_text()
    except APIError as exc:
        st.error(str(exc))
        return

    totals = {path: {"requests": 0.0, "seconds": 0.0} for path in _QUERY_PATHS}
    for family in text_string_to_metric_families(text):
        for sample in family.samples:
            path = sample.labels.get("path")
            if path not in totals:
                continue
            if sample.name == "http_request_latency_seconds_count":
                totals[path]["requests"] += sample.value
            elif sample.name == "http_request_latency_seconds_sum":
                totals[path]["seconds"] += sample.value

    for col, (path, t) in zip(st.columns(len(totals)), totals.items()):
        avg = t["seconds"] / t["requests"] if t["requests"] else 0.0
        col.metric(path, f"{int(t['requests'])} requests", f"avg {avg:.2f}s", delta_color="off")
    st.caption(
        "The middleware times `call_next`, which returns once response headers are sent, so the "
        "server latency for /api/query/stream is only time-to-first-byte. Use the session latency "
        "below for end-to-end streaming time."
    )


def _session_metrics() -> None:
    st.subheader("This browser session")
    log = st.session_state.query_log
    if not log:
        st.info("Ask something on the Chat page to populate these charts.")
        return

    df = pd.DataFrame(log)
    a, b, c, d = st.columns(4)
    a.metric("Queries", len(df))
    b.metric("Avg latency", f"{df['latency_s'].mean():.1f}s")
    c.metric("p95 latency", f"{df['latency_s'].quantile(0.95):.1f}s")
    d.metric("Refusal rate", f"{df['refused'].mean():.0%}")

    left, right = st.columns(2)
    with left:
        st.markdown("**Latency per query (s)**")
        st.line_chart(df["latency_s"])
        st.markdown("**Queries per minute**")
        st.bar_chart(df.set_index("time").resample("1min").size())
    with right:
        st.markdown("**Confidence distribution**")
        st.bar_chart(df["confidence"].value_counts())
        st.markdown("**Top query terms**")
        st.bar_chart(_top_terms(df["query"]), horizontal=True)

    with st.expander("Raw query log"):
        st.dataframe(df, hide_index=True)


def _top_terms(queries: pd.Series, n: int = 10) -> pd.Series:
    counts = Counter(w for q in queries for w in _WORD.findall(q.lower()) if w not in _STOP)
    return pd.Series(dict(counts.most_common(n)), name="count")
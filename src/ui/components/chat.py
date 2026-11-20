import itertools
import time
from datetime import UTC, datetime

import streamlit as st

from src.ui.api_client import APIError, HubClient

SOURCE_FILTERS = {"All sources": None, "Docs": "markdown", "Code": "code", "Incidents": "incident"}

_BADGES = {
    "high": ("High confidence", "green"),
    "medium": ("Medium confidence", "orange"),
    "low": ("Low confidence", "red"),
    "none": ("Not enough information", "gray"),
    "error": ("Request failed", "red"),
}


def render_filters() -> dict:
    with st.sidebar:
        st.subheader("Search filters")
        label = st.selectbox("Source type", list(SOURCE_FILTERS), key="source_filter")
    source_type = SOURCE_FILTERS[label]
    return {"source_type": source_type} if source_type else {}


def render_chat(client: HubClient, filters: dict) -> None:
    st.title("Ask the Hub")
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg["role"] == "assistant":
                _render_meta(msg)

    prompt = st.chat_input("Ask about your code, docs or incidents")
    if not prompt:
        return

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        reply = _answer(client, prompt, filters)
        _render_meta(reply)
    st.session_state.messages.append(reply)
    st.session_state.query_log.append({
        "time": datetime.now(UTC),
        "query": prompt,
        "latency_s": reply["latency"],
        "confidence": reply["confidence"],
        "sources": len(reply["sources"]),
        "refused": reply["refused"],
        "filter": filters.get("source_type", "all"),
    })


def _answer(client: HubClient, prompt: str, filters: dict) -> dict:
    payload = {"query": prompt, "session_id": st.session_state.session_id, **filters}
    start = time.perf_counter()
    try:
        reply = _stream(client, payload) if st.session_state.streaming else _blocking(client, payload)
    except APIError as exc:
        st.error(str(exc))
        reply = {"content": f"_Request failed: {exc}_", "sources": [], "confidence": "error", "refused": True}
    return {"role": "assistant", **reply, "latency": time.perf_counter() - start}


def _blocking(client: HubClient, payload: dict) -> dict:
    with st.spinner("Retrieving context and generating an answer..."):
        body = client.query(payload)
    st.markdown(body["answer"])
    return {
        "content": body["answer"],
        "sources": body["sources"],
        "confidence": body["confidence"],
        "refused": body["refused"],
    }


def _stream(client: HubClient, payload: dict) -> dict:
    meta = {"sources": [], "confidence": "none", "refused": False}
    events = client.stream_query(payload)
    with st.spinner("Retrieving context..."):
        first = next(events, None)

    def tokens():
        for event, data in itertools.chain([first] if first else [], events):
            if event == "token":
                yield data
            elif event == "sources":
                meta["sources"] = data
            elif event == "done":
                meta["confidence"] = data["confidence"]
                meta["refused"] = data["refused"]

    content = st.write_stream(tokens())
    return {"content": content, **meta}


def _render_meta(msg: dict) -> None:
    label, color = _BADGES.get(msg["confidence"], (msg["confidence"], "blue"))
    st.badge(label, color=color)
    st.caption(f"{msg['latency']:.1f}s · {len(msg['sources'])} cited source(s)")
    for src in msg["sources"]:
        with st.expander(f"[{src['index']}] {src['path']}"):
            if src.get("score") is not None:
                st.caption(f"Fused RRF score: {src['score']:.4f}")
            st.code(src["snippet"], language=None, wrap_lines=True)
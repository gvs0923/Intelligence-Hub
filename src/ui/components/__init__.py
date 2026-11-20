import os
import uuid

import streamlit as st

from src.ui.api_client import APIError, HubClient

_WIDGET_KEYS = ("api_url", "timeout", "streaming", "source_filter")


def init_state() -> None:
    defaults = {
        "session_id": uuid.uuid4().hex[:12],
        "messages": [],
        "query_log": [],
        "jobs": {},
        "api_url": os.getenv("API_URL", "http://localhost:8000"),
        "timeout": 120.0,
        "streaming": True,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)
    for key in _WIDGET_KEYS:
        if key in st.session_state:
            st.session_state[key] = st.session_state[key]


def new_conversation() -> None:
    st.session_state.messages = []
    st.session_state.session_id = uuid.uuid4().hex[:12]


@st.cache_data(ttl=15, show_spinner=False)
def cached_health(_client: HubClient, api_url: str) -> dict | None:
    try:
        return _client.health()
    except APIError:
        return None


def render_health(client: HubClient) -> None:
    health = cached_health(client, st.session_state.api_url)
    if health is None:
        st.badge("API unreachable", icon=":material/error:", color="red")
    elif health["status"] == "ok":
        st.badge("All systems ok", icon=":material/check_circle:", color="green")
    else:
        down = [name for name in ("ollama", "chroma", "sqlite", "bm25") if not health[name]]
        st.badge("Degraded", icon=":material/warning:", color="orange")
        st.caption("Down: " + ", ".join(down))


def render_settings(client: HubClient) -> None:
    st.title("Settings")

    st.subheader("Connection")
    st.text_input("API base URL", key="api_url", help="Where the FastAPI backend is running")
    st.number_input(
        "Request timeout (seconds)", min_value=10.0, max_value=600.0, step=10.0, key="timeout"
    )
    if st.button("Test connection", icon=":material/network_check:"):
        cached_health.clear()
        health = cached_health(client, st.session_state.api_url)
        if health is None:
            st.error(f"Cannot reach {st.session_state.api_url}")
        else:
            st.json(health)

    st.subheader("Conversation")
    st.toggle("Stream responses", key="streaming", help="Off = wait for the full answer from /api/query")
    st.text_input("Session ID", value=st.session_state.session_id, disabled=True)
    st.button("Start new conversation", on_click=new_conversation)

    st.subheader("Model and retrieval")
    st.info(
        "LLM model, temperature, top-k and query rewriting / re-ranking are server-side "
        "settings (`.env` → `src/config.py`). The API does not accept them per request yet, "
        "so they are not exposed here."
    )
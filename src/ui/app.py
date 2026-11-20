from pathlib import Path

import streamlit as st

from src.ui.api_client import HubClient
from src.ui.components.analytics import render_analytics
from src.ui.components.chat import render_chat, render_filters
from src.ui.components.settings import (
    init_state,
    new_conversation,
    render_health,
    render_settings,
)
from src.ui.components.source_manager import render_source_manager

_CSS = Path(__file__).parent / "styles" / "custom.css"


@st.cache_resource
def get_client(api_url: str, timeout: float) -> HubClient:
    return HubClient(api_url, timeout)


def _client() -> HubClient:
    return get_client(st.session_state.api_url, st.session_state.timeout)


def chat_page() -> None:
    filters = render_filters()
    st.sidebar.button("New conversation", on_click=new_conversation, icon=":material/add_comment:")
    render_chat(_client(), filters)


def sources_page() -> None:
    render_source_manager(_client())


def analytics_page() -> None:
    render_analytics(_client())


def settings_page() -> None:
    render_settings(_client())


def main() -> None:
    st.set_page_config(page_title="Engineering Intelligence Hub", page_icon=":material/hub:", layout="wide")
    init_state()
    st.markdown(f"<style>{_CSS.read_text()}</style>", unsafe_allow_html=True)

    with st.sidebar:
        st.markdown("### Engineering Intelligence Hub")
        render_health(_client())

    page = st.navigation([
        st.Page(chat_page, title="Chat", icon=":material/chat:", default=True),
        st.Page(sources_page, title="Sources", icon=":material/database:"),
        st.Page(analytics_page, title="Analytics", icon=":material/monitoring:"),
        st.Page(settings_page, title="Settings", icon=":material/settings:"),
    ])
    page.run()


main()
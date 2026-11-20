import pandas as pd
import streamlit as st

from src.ui.api_client import APIError, HubClient

SOURCE_TYPES = {
    "git": "Git repo URL, cloned by the worker",
    "markdown": "Folder of Markdown docs",
    "code": "Folder of source code",
    "incident": "Incident file (.json or .csv)",
}
_FINAL = {"done", "failed"}
_PROGRESS = {"pending": 5, "running": 50, "done": 100, "failed": 100}


def render_source_manager(client: HubClient) -> None:
    st.title("Data sources")
    left, right = st.columns([2, 3], gap="large")
    with left:
        _add_source_form(client)
        _job_tracker(client)
    with right:
        _source_table(client)


def _track(job_id: int, name: str) -> None:
    st.session_state.jobs[job_id] = {"name": name, "status": "pending", "error": None}


def _add_source_form(client: HubClient) -> None:
    st.subheader("Add a source")
    with st.form("add_source", clear_on_submit=True):
        name = st.text_input("Name", placeholder="kubernetes-docs")
        source_type = st.selectbox(
            "Type", list(SOURCE_TYPES), format_func=lambda t: f"{t}: {SOURCE_TYPES[t]}"
        )
        location = st.text_input(
            "Location",
            placeholder="https://github.com/nolar/kopf.git  or  ./corpus/incidents.json",
            help="Paths are resolved on the machine running the Celery worker, not in your browser.",
        )
        submitted = st.form_submit_button("Start ingestion", type="primary")

    if not submitted:
        return
    if not name.strip() or not location.strip():
        st.warning("Name and location are both required.")
        return
    try:
        job = client.ingest(name.strip(), source_type, location.strip())
    except APIError as exc:
        st.error(str(exc))
        return
    _track(job["job_id"], name.strip())
    st.toast(f"Queued ingestion job #{job['job_id']}")


@st.fragment(run_every=2)
def _job_tracker(client: HubClient) -> None:
    jobs = st.session_state.jobs
    if not jobs:
        return
    st.subheader("Ingestion jobs")
    finished_now = False
    for job_id, job in jobs.items():
        if job["status"] not in _FINAL:
            try:
                latest = client.job_status(job_id)
            except APIError as exc:
                st.error(f"Job #{job_id}: {exc}")
                continue
            finished_now |= latest["status"] in _FINAL
            job.update(status=latest["status"], error=latest["error"])
        st.progress(_PROGRESS.get(job["status"], 0), text=f"#{job_id} {job['name']}: {job['status']}")
        if job["status"] == "failed":
            st.error(job["error"] or "Ingestion failed")
    if finished_now:
        st.rerun()
    if all(j["status"] in _FINAL for j in jobs.values()):
        st.button("Clear finished jobs", on_click=jobs.clear)


def _source_table(client: HubClient) -> None:
    st.subheader("Indexed sources")
    try:
        sources = client.list_sources()
    except APIError as exc:
        st.error(str(exc))
        return
    if not sources:
        st.info("Nothing indexed yet. Add a source on the left.")
        return

    df = pd.DataFrame(sources)
    st.dataframe(
        df[["id", "name", "source_type", "document_count", "location", "created_at"]],
        hide_index=True,
    )

    names = {s["id"]: s["name"] for s in sources}
    source_id = st.selectbox("Manage source", list(names), format_func=lambda i: f"#{i} {names[i]}")
    refresh_col, delete_col = st.columns(2)

    if refresh_col.button("Re-ingest", icon=":material/refresh:"):
        try:
            job = client.refresh_source(source_id)
        except APIError as exc:
            st.error(str(exc))
        else:
            _track(job["job_id"], names[source_id])
            st.rerun()

    confirm = delete_col.checkbox("Confirm delete")
    if delete_col.button("Delete", icon=":material/delete:", disabled=not confirm):
        try:
            client.delete_source(source_id)
        except APIError as exc:
            st.error(str(exc))
        else:
            st.rerun()
import json
from collections.abc import Iterable, Iterator
from typing import Any

import httpx


class APIError(Exception):
    """Backend unreachable or returned an error status."""


def parse_sse(lines: Iterable[str]) -> Iterator[tuple[str, Any]]:
    """Turn Server-Sent Events text lines into (event, json_data) pairs."""
    event, data = "message", []
    for line in lines:
        if line.startswith("event:"):
            event = line.removeprefix("event:").strip()
        elif line.startswith("data:"):
            data.append(line.removeprefix("data:").removeprefix(" "))
        elif not line:
            if data:
                yield event, json.loads("\n".join(data))
            event, data = "message", []
    if data:
        yield event, json.loads("\n".join(data))


class HubClient:
    """HTTP client for the FastAPI backend. The UI talks to the backend only through this class."""

    def __init__(
        self,
        base_url: str,
        timeout: float = 120.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self._http = httpx.Client(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout, connect=5.0),
            transport=transport,
        )

    def health(self) -> dict:
        return self._send("GET", "/api/health").json()

    def stats(self) -> dict:
        return self._send("GET", "/api/stats").json()

    def metrics_text(self) -> str:
        return self._send("GET", "/metrics").text

    def list_sources(self) -> list[dict]:
        return self._send("GET", "/api/sources").json()

    def delete_source(self, source_id: int) -> None:
        self._send("DELETE", f"/api/sources/{source_id}")

    def ingest(self, name: str, source_type: str, location: str) -> dict:
        body = {"name": name, "source_type": source_type, "location": location}
        return self._send("POST", "/api/ingest", json=body).json()

    def refresh_source(self, source_id: int, force: bool = False) -> dict:
        return self._send(
            "POST", f"/api/ingest/sources/{source_id}/refresh", params={"force": force}
        ).json()

    def job_status(self, job_id: int) -> dict:
        return self._send("GET", f"/api/ingest/{job_id}").json()

    def query(self, payload: dict) -> dict:
        return self._send("POST", "/api/query", json=payload).json()

    def query_log(self, hours: int = 24) -> list[dict]:
        return self._send("GET", "/api/analytics/queries", params={"hours": hours}).json()

    def stream_query(self, payload: dict) -> Iterator[tuple[str, Any]]:
        try:
            with self._http.stream("POST", "/api/query/stream", json=payload) as resp:
                if resp.is_error:
                    resp.read()
                    raise APIError(_describe(resp))
                yield from parse_sse(resp.iter_lines())
        except httpx.HTTPError as exc:
            raise APIError(f"Cannot reach API at {self.base_url}: {exc}") from exc

    def _send(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            resp = self._http.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise APIError(f"Cannot reach API at {self.base_url}: {exc}") from exc
        if resp.is_error:
            raise APIError(_describe(resp))
        return resp


def _describe(resp: httpx.Response) -> str:
    try:
        body = resp.json()
        detail = body.get("detail", body) if isinstance(body, dict) else body
    except ValueError:
        detail = resp.text
    return f"{resp.status_code}: {detail}"
import httpx
import pytest

from src.ui.api_client import APIError, HubClient, parse_sse


def _client(handler) -> HubClient:
    return HubClient("http://test", transport=httpx.MockTransport(handler))


def test_parse_sse_decodes_json_and_preserves_newlines():
    lines = [
        "event: token", 'data: "line1\\nline2"', "",
        "event: done", 'data: {"confidence": "high", "refused": false}', "",
    ]
    assert list(parse_sse(lines)) == [
        ("token", "line1\nline2"),
        ("done", {"confidence": "high", "refused": False}),
    ]


def test_stream_query_yields_events_in_order():
    body = (
        'event: token\ndata: "Hi"\n\n'
        "event: sources\ndata: []\n\n"
        'event: done\ndata: {"confidence": "high", "refused": false}\n\n'
    )
    client = _client(lambda req: httpx.Response(200, text=body, headers={"content-type": "text/event-stream"}))
    assert [event for event, _ in client.stream_query({"query": "q"})] == ["token", "sources", "done"]


def test_http_error_becomes_api_error_with_detail():
    client = _client(lambda req: httpx.Response(503, json={"detail": "Ingestion queue unavailable"}))
    with pytest.raises(APIError, match="503: Ingestion queue unavailable"):
        client.ingest("n", "git", "https://example.com/repo.git")


def test_connection_error_becomes_api_error():
    def boom(req):
        raise httpx.ConnectError("refused")

    with pytest.raises(APIError, match="Cannot reach API"):
        _client(boom).health()
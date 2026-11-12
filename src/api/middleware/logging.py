import time

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from src.logging_config import get_logger

log = get_logger(__name__)

REQUEST_COUNT = Counter(
    "http_requests_total", "HTTP requests", ["method", "path", "status"]
)
REQUEST_LATENCY = Histogram(
    "http_request_latency_seconds", "HTTP latency", ["method", "path"],
    buckets=[0.05, 0.1, 0.5, 1, 2.5, 5, 10, 30],
)


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """Per request: structured log line + Prometheus counter/histogram."""

    async def dispatch(self, request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - start
        path = request.url.path
        log.info(
            "http_request",
            method=request.method,
            path=path,
            status=response.status_code,
            latency_ms=round(elapsed * 1000, 1),
        )
        REQUEST_COUNT.labels(request.method, path, response.status_code).inc()
        REQUEST_LATENCY.labels(request.method, path).observe(elapsed)
        return response


def metrics_response() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
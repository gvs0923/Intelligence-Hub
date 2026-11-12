from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.middleware.logging import ObservabilityMiddleware, metrics_response
from src.api.routes.ingest import router as ingest_router
from src.api.routes.query import router as query_router
from src.api.routes.sources import router as sources_router
from src.api.routes.stats import router as stats_router
from src.config import get_settings
from src.db.session import init_db
from src.logging_config import configure_logging, get_logger

settings = get_settings()
log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    log.info("starting_up", app_name=settings.app_name)
    init_db()
    yield
    log.info("shutting_down")


app = FastAPI(title=settings.app_name, version="0.6.0", lifespan=lifespan)

app.add_middleware(ObservabilityMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(query_router)
app.include_router(sources_router)
app.include_router(stats_router)
app.include_router(ingest_router)


@app.get("/metrics", include_in_schema=False)
def metrics():
    return metrics_response()
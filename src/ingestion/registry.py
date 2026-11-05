from src.ingestion.chunkers.code import CodeChunker
from src.ingestion.chunkers.incident import IncidentChunker
from src.ingestion.chunkers.markdown import MarkdownChunker
from src.ingestion.chunkers.mixed import MixedChunker
from src.ingestion.chunkers.text import TextChunker
from src.ingestion.code import CodeIngester
from src.ingestion.git_repo import GitRepoIngester
from src.ingestion.incident import IncidentIngester
from src.ingestion.markdown import MarkdownIngester

INGESTERS = {
    "git": GitRepoIngester,
    "markdown": MarkdownIngester,
    "code": CodeIngester,
    "incident": IncidentIngester,
}

CHUNKERS = {
    "git": MixedChunker,
    "markdown": MarkdownChunker,
    "code": CodeChunker,
    "incident": IncidentChunker,
}


def get_ingester(source_type: str):
    if source_type not in INGESTERS:
        raise ValueError(f"Unknown source_type: {source_type}")
    return INGESTERS[source_type]()


def get_chunker(source_type: str):
    return CHUNKERS.get(source_type, TextChunker)()
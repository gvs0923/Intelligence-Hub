from concurrent.futures import ThreadPoolExecutor

from src.config import get_settings
from src.indexing.bm25 import BM25Index
from src.indexing.embedders import get_embedder
from src.indexing.vector_store import VectorStore
from src.logging_config import get_logger
from src.retrieval.base import RetrievalResult
from src.retrieval.bm25_retriever import BM25Retriever
from src.retrieval.confidence import is_confident, retrieval_confidence
from src.retrieval.dense import DenseRetriever
from src.retrieval.filters import RetrievalFilters
from src.retrieval.fusion import reciprocal_rank_fusion
from src.retrieval.query_rewriter import QueryRewriter
from src.retrieval.reranker import LLMReranker

log = get_logger(__name__)


class RetrievalPipeline:
    """Query rewrite → parallel dense+BM25 → RRF → filter → rerank → top-k."""

    def __init__(
        self,
        dense: DenseRetriever,
        bm25: BM25Retriever,
        rewriter: QueryRewriter | None = None,
        reranker: LLMReranker | None = None,
    ):
        settings = get_settings()
        self.dense = dense
        self.bm25 = bm25
        self.rewriter = rewriter
        self.reranker = reranker
        self._s = settings

    @classmethod
    def from_defaults(cls) -> "RetrievalPipeline":
        embedder = get_embedder()
        bm25_index = BM25Index()
        bm25_index.load()
        return cls(
            dense=DenseRetriever(embedder, VectorStore()),
            bm25=BM25Retriever(bm25_index),
            rewriter=QueryRewriter(),
            reranker=LLMReranker(),
        )

    def retrieve(
        self, query: str, filters: RetrievalFilters | None = None
    ) -> tuple[list[RetrievalResult], float, bool]:
        filters = filters or RetrievalFilters()
        rewritten = self.rewriter.rewrite(query) if self.rewriter else query

        # Dense + BM25 are independent — run them in parallel
        with ThreadPoolExecutor(max_workers=2) as pool:
            dense_fut = pool.submit(
                self.dense.retrieve, rewritten, self._s.top_k_dense, filters.to_chroma_where()
            )
            bm25_fut = pool.submit(self.bm25.retrieve, rewritten, self._s.top_k_bm25)
            dense_results = dense_fut.result()
            bm25_results = bm25_fut.result()

        # BM25 can't filter inside the index — post-filter
        bm25_results = [r for r in bm25_results if filters.matches(r)]

        fused = reciprocal_rank_fusion(
            [dense_results, bm25_results], k=self._s.rrf_k
        )

        candidates = fused[: self._s.top_k_dense]
        if self.reranker:
            candidates = self.reranker.rerank(rewritten, candidates)

        final = candidates[: self._s.top_k_final]
        conf = retrieval_confidence(fused)
        confident = is_confident(fused, self._s.min_confidence_threshold)

        log.info(
            "retrieval_complete",
            query=query,
            rewritten=rewritten,
            dense=len(dense_results),
            bm25=len(bm25_results),
            final=len(final),
            confidence=round(conf, 3),
            confident=confident,
        )
        return final, conf, confident
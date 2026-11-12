from src.generation.guardrails import confidence_label, grounding_score
from src.generation.llm_client import LLMClient
from src.generation.memory import ConversationMemory
from src.generation.prompt_templates import build_messages
from src.generation.response_builder import GenerationResponse, build_response
from src.logging_config import get_logger
from src.retrieval.filters import RetrievalFilters
from src.retrieval.pipeline import RetrievalPipeline

log = get_logger(__name__)

_REFUSAL = "I don't have enough information in the indexed sources to answer this."


class RAGResponse(GenerationResponse):
    confidence: str
    retrieval_confidence: float


class RAGGenerator:
    """Full RAG loop: retrieve → (gate) → generate → cite → grade."""

    def __init__(
        self,
        retriever: RetrievalPipeline,
        llm: LLMClient,
        memory: ConversationMemory | None = None,
    ):
        self.retriever = retriever
        self.llm = llm
        self.memory = memory or ConversationMemory()

    def ask(
        self,
        query: str,
        session_id: str = "default",
        filters: RetrievalFilters | None = None,
    ) -> RAGResponse:
        results, conf, confident = self.retriever.retrieve(query, filters)

        # Gate 1: retrieval confidence — don't even call the LLM
        if not confident or not results:
            return RAGResponse(
                answer=_REFUSAL,
                sources=[],
                refused=True,
                confidence="none",
                retrieval_confidence=conf,
            )

        messages = build_messages(query, results, self.memory.get(session_id))
        answer = self.llm.chat(messages)
        resp = build_response(answer, results)

        # Gate 2: grounding — did the answer stay inside the chunks?
        grounding = grounding_score(answer, results)
        label = confidence_label(conf, grounding, resp.refused)

        if not resp.refused:
            self.memory.add_turn(session_id, query, answer)

        log.info(
            "rag_answer",
            query=query,
            refused=resp.refused,
            cited=len(resp.sources),
            retrieval_conf=round(conf, 3),
            grounding=round(grounding, 3),
            label=label,
        )
        return RAGResponse(
            **resp.model_dump(),
            confidence=label,
            retrieval_confidence=conf,
        )
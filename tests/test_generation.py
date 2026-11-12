from src.generation.guardrails import grounding_score
from src.generation.memory import ConversationMemory
from src.generation.prompt_templates import build_messages, format_context
from src.generation.response_builder import build_response
from src.retrieval.base import RetrievalResult


def _r(vid: str, text: str, **meta) -> RetrievalResult:
    return RetrievalResult(
        content=text, score=0.5, metadata={"vector_id": vid, **meta}
    )


RESULTS = [
    _r("doc1-chunk0", "Pods are evicted when node memory is under pressure.", source_path="docs/qos.md"),
    _r("doc2-chunk3", "Set memory requests to avoid OOM kills.", source_path="docs/memory.md"),
]


def test_format_context_numbers_chunks():
    ctx = format_context(RESULTS)
    assert '[1] {source: "docs/qos.md"}' in ctx
    assert '[2] {source: "docs/memory.md"}' in ctx
    assert "evicted" in ctx


def test_build_messages_structure():
    history = [{"role": "user", "content": "prior"}, {"role": "assistant", "content": "earlier"}]
    msgs = build_messages("why evicted?", RESULTS, history)
    assert msgs[0]["role"] == "system"
    assert msgs[1:3] == history
    assert msgs[-1]["role"] == "user"
    assert "Context:" in msgs[-1]["content"] and "why evicted?" in msgs[-1]["content"]


def test_response_maps_citations():
    resp = build_response("Pods evict under memory pressure [1]. Also see [2].", RESULTS)
    assert [s.index for s in resp.sources] == [1, 2]
    assert resp.sources[0].path == "docs/qos.md"
    assert not resp.refused


def test_response_drops_hallucinated_and_duplicate_citations():
    resp = build_response("claims [1] more [1] fake [9]", RESULTS)
    assert [s.index for s in resp.sources] == [1]  # [9] out of range, dup dropped


def test_response_detects_refusal():
    resp = build_response("I don't have enough information in the indexed sources to answer this.", RESULTS)
    assert resp.refused


def test_grounding_score():
    grounded = grounding_score("pods evicted node memory pressure", RESULTS)
    ungrounded = grounding_score("quantum blockchain synergy protocol", RESULTS)
    assert grounded > 0.7
    assert ungrounded < 0.3


def test_memory_caps_turns_and_skips_overflow():
    mem = ConversationMemory(max_turns=2)
    for i in range(4):
        mem.add_turn("s", f"q{i}", f"a{i}")
    hist = mem.get("s")
    assert len(hist) == 4                      # 2 turns * 2 msgs
    assert hist[0]["content"] == "q2"          # oldest dropped
    assert mem.get("other-session") == []      # sessions isolated
from collections import OrderedDict


class ConversationMemory:
    """In-memory per-session chat history, capped at the last N turns.

    A 'turn' = one user + one assistant message. History is injected into
    the prompt as prior messages so follow-ups like "what about the second
    one?" have context."""

    def __init__(self, max_turns: int = 5):
        self._max_turns = max_turns
        self._sessions: OrderedDict[str, list[dict]] = OrderedDict()

    def get(self, session_id: str) -> list[dict]:
        return list(self._sessions.get(session_id, []))

    def add_turn(self, session_id: str, user_query: str, assistant_answer: str) -> None:
        history = self._sessions.setdefault(session_id, [])
        history.append({"role": "user", "content": user_query})
        history.append({"role": "assistant", "content": assistant_answer})
        # cap at max_turns * 2 messages (user + assistant per turn)
        del history[: max(0, len(history) - self._max_turns * 2)]
        self._sessions.move_to_end(session_id)

    def clear(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
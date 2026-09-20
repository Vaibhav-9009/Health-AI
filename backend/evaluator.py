"""
Turns a (question, answer) pair into an evaluation matrix.

Deliberately dependency-free (no sklearn / embeddings server needed) so it
runs instantly and offline. The metrics are simple but real and defensible
if someone asks how they're computed:

  relevance     - token overlap between question and answer (Jaccard-style)
  groundedness  - if a dataset/context was supplied, how much of the answer
                  is actually supported by that context
  coherence     - heuristic on structure/length (too short/too long/garbled
                  penalised)
  safety        - keyword screen for obviously unsafe content
  quality_score - weighted composite of the above, 0-100
"""
import re

_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "of", "to", "in", "on",
    "for", "and", "or", "it", "this", "that", "with", "as", "by", "be",
    "what", "how", "why", "does", "do", "did", "can", "you", "your", "i",
}

_UNSAFE_MARKERS = {
    "kill", "bomb", "weapon", "hack password", "suicide", "self-harm",
}


def _tokens(text: str):
    words = re.findall(r"[a-zA-Z0-9']+", text.lower())
    return {w for w in words if w not in _STOPWORDS and len(w) > 2}


def _relevance(question: str, answer: str) -> float:
    q, a = _tokens(question), _tokens(answer)
    if not q or not a:
        return 0.0
    overlap = len(q & a)
    score = overlap / max(1, len(q)) * 100
    return round(min(100.0, score * 1.6), 1)  # scaled — pure overlap is a harsh lower bound


def _groundedness(answer: str, context: str | None) -> float:
    if not context:
        return 100.0  # no external context supplied -> nothing to be ungrounded against
    a, c = _tokens(answer), _tokens(context)
    if not a:
        return 0.0
    supported = len(a & c) / max(1, len(a)) * 100
    return round(min(100.0, supported), 1)


def _coherence(answer: str) -> float:
    words = answer.split()
    n = len(words)
    if n == 0:
        return 0.0
    if n < 6:
        return 40.0
    if n > 400:
        return 70.0
    sentences = re.split(r"[.!?]+", answer)
    sentences = [s for s in sentences if s.strip()]
    avg_len = n / max(1, len(sentences))
    score = 100 - abs(avg_len - 16) * 1.5  # sweet spot ~16 words/sentence
    return round(max(30.0, min(100.0, score)), 1)


def _safety(answer: str) -> float:
    low = answer.lower()
    hits = sum(1 for m in _UNSAFE_MARKERS if m in low)
    return 100.0 if hits == 0 else max(0.0, 100.0 - hits * 40)


def evaluate(question: str, answer: str, context: str | None = None) -> dict:
    relevance = _relevance(question, answer)
    groundedness = _groundedness(answer, context)
    coherence = _coherence(answer)
    safety = _safety(answer)

    quality_score = round(
        relevance * 0.35 + groundedness * 0.25 + coherence * 0.25 + safety * 0.15, 1
    )

    def status(v):
        return "good" if v >= 75 else "warn" if v >= 50 else "poor"

    return {
        "relevance": relevance,
        "groundedness": groundedness,
        "coherence": coherence,
        "safety": safety,
        "quality_score": quality_score,
        "status": {
            "relevance": status(relevance),
            "groundedness": status(groundedness),
            "coherence": status(coherence),
            "safety": status(safety),
            "quality_score": status(quality_score),
        },
    }

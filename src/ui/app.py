"""
Streamlit UI for The Librarian: a three-pane console.

    left    this session's questions (unanswered ones in amber), status, settings
    middle  the question, the cited answer, per-stage timings, feedback, input
    right   the passages the answer cites, as the model saw them, one tab per
            source, with the lines that share terms with the answer highlighted

Talks to the API over HTTP only (API_URL), never imports the pipeline, so it
stays a small image with no torch, no index and no API keys. Everything from
the model or the corpus is HTML-escaped before rendering: the cheat sheets
are full of example attack payloads.

Run locally:   API_URL=http://127.0.0.1:8000 streamlit run src/ui/app.py
In Compose:    the `ui` service, API_URL=http://api:8000
Theme:         .streamlit/config.toml
"""
from __future__ import annotations

import html
import os
import re

import httpx
import streamlit as st

API_URL = os.environ.get("API_URL", "http://127.0.0.1:8000").rstrip("/")
# First request can include reranker warm-up + upstream retries. On a sleeping
# free-tier host (render.yaml) a cold start plus a slow CPU rerank can exceed
# 2 minutes, so it's configurable there.
ASK_TIMEOUT_S = float(os.environ.get("ASK_TIMEOUT_S") or 120)
MAX_QUESTION_CHARS = 1000  # same limits as the API (src/api/app.py)
MAX_COMMENT_CHARS = 1000
MAX_TURNS = 20
EXAMPLES = [
    "How should I store passwords?",
    "How do I prevent CSRF in a single-page app?",
    "What should I check when validating a JWT?",
]
REFUSAL_REASONS = {
    "empty_query": "The question was empty.",
    "no_results": "No passage in the cheat sheets matched this question.",
    "below_vector_score_threshold": "No passage in the cheat sheets matched this question closely enough.",
    "model_declined": "The closest passages in the cheat sheets don't answer this question.",
    "no_valid_citations": "An answer was drafted but couldn't be tied to a source, so it isn't shown.",
    "invalid_model_output": "The model's reply couldn't be read. Ask again.",
}
TIMING_LABELS = [  # (key in timings_ms, label), in pipeline order
    ("retrieval_vector_ms", "vector"),
    ("retrieval_bm25_ms", "bm25"),
    ("retrieval_rerank_ms", "rerank"),
    ("generation_ms", "generation"),
    ("total_ms", "total"),
]
_STOPWORDS = set(
    "that this with from have should when what which will into your their there than then them they these those "
    "also only used uses using must more most such been being about over each other were where while does make".split()
)

_CITATION_RE = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")
_CODE_RE = re.compile(r"`([^`\n]+)`")
_BOLD_RE = re.compile(r"\*\*([^*\n]+)\*\*")
_BULLET_RE = re.compile(r"^\s*(?:[-*]|\d+\.)\s+")
_WORD_RE = re.compile(r"[a-z0-9][a-z0-9_\-]*")


# --------------------------------------------------------------------- #
# pure helpers (unit-tested in tests/test_ui.py)
# --------------------------------------------------------------------- #


def call_tag(title: str) -> str:
    """Short shelf mark for a cheat sheet: "Password Storage" -> "PS",
    "Authentication" -> "AUTH", "Cross Site Request Forgery Prevention" -> "CSRF"."""
    words = [w for w in re.split(r"[\s_-]+", title.replace("Cheat Sheet", "")) if w]
    if not words:
        return "?"
    if len(words) == 1:
        return words[0][:4].upper()
    return "".join(w[0] for w in words[:4]).upper()


def _inline(text: str, numbers: set[int]) -> str:
    """Escape one line of model text, then add the markup we allow: `code`,
    **bold**, and [n] citation markers."""
    out = html.escape(text, quote=False)
    out = _CODE_RE.sub(r"<code>\1</code>", out)
    out = _BOLD_RE.sub(r"<strong>\1</strong>", out)

    def cite(match: re.Match) -> str:
        return "".join(
            f'<span class="c">{n}</span>' if n in numbers else f'<span class="c dead">{n}</span>'
            for n in (int(x) for x in re.split(r"\s*,\s*", match.group(1)))
        )

    return _CITATION_RE.sub(cite, out)


def answer_html(answer: str, citations: list[dict]) -> str:
    """Model answer -> safe HTML: paragraphs, bullet lists, inline code, bold,
    and [n] markers (numbers with no real source are greyed out)."""
    numbers = {c["number"] for c in citations}
    blocks = []
    for para in re.split(r"\n\s*\n", answer.strip()):
        lines = [ln for ln in para.splitlines() if ln.strip()]
        if lines and all(_BULLET_RE.match(ln) for ln in lines):
            items = "".join(f"<li>{_inline(_BULLET_RE.sub('', ln), numbers)}</li>" for ln in lines)
            blocks.append(f"<ul>{items}</ul>")
        elif lines:
            blocks.append("<p>" + "<br>".join(_inline(ln, numbers) for ln in lines) + "</p>")
    return "".join(blocks)


def _terms(text: str) -> set[str]:
    """Distinctive words: 4+ letters and not a stopword, or anything with a digit."""
    return {
        w for w in _WORD_RE.findall(text.lower())
        if any(ch.isdigit() for ch in w) or (len(w) >= 4 and w not in _STOPWORDS)
    }


def support_terms(answer: str, number: int) -> set[str]:
    """Terms from the parts of the answer that cite source `number`."""
    parts = re.split(r"(?<=[.!?])\s+|\n+", answer)
    cited = [
        p for p in parts
        if number in {int(x) for m in _CITATION_RE.findall(p) for x in re.split(r"\s*,\s*", m)}
    ]
    return _terms(_CITATION_RE.sub(" ", " ".join(cited)))


def passage_html(text: str, terms: set[str] | None = None, min_overlap: int = 2) -> str:
    """The passage as numbered lines. A line is highlighted when it shares at
    least `min_overlap` distinctive terms with the answer, or one specific
    value (a number of 2+ characters, like 19 or 72): a reading aid, not a
    claim about which line the model used."""
    rows = []
    for i, line in enumerate(text.splitlines() or [""], start=1):
        shared = _terms(line) & terms if terms else set()
        hit = len(shared) >= min_overlap or any(len(w) >= 2 and any(ch.isdigit() for ch in w) for w in shared)
        rows.append(
            f'<div class="ln{" hit" if hit else ""}"><i>{i}</i><span>{html.escape(line) or "&nbsp;"}</span></div>'
        )
    return f'<div class="passage">{"".join(rows)}</div>'


def timings_html(timings: dict, cited: int | None = None, given: int | None = None) -> str:
    parts = []
    for key, label in TIMING_LABELS:
        if key in timings:
            ms = timings[key]
            value = f"{ms / 1000:.2f} s" if ms >= 1000 else f"{ms:.0f} ms"
            parts.append(f"<span>{label} {value}</span>")
    if given:
        parts.append(f"<span>{cited or 0}/{given} passages cited</span>")
    return f'<div class="metrics">{"".join(parts)}</div>' if parts else ""


def refusal_text(reason: str | None) -> str:
    return REFUSAL_REASONS.get(reason or "", "The cheat sheets don't cover this question.")


def feedback_payload(result: dict, rating: str, comment: str = "") -> dict:
    """The POST /feedback body for one answer: what was asked and answered,
    nothing about who asked."""
    return {
        "question": result["question"],
        "answer": result["answer"],
        "answerable": result["answerable"],
        "refusal_reason": result.get("refusal_reason"),
        "cited_chunk_ids": [c["chunk_id"] for c in result.get("citations", [])],
        "model": result.get("model"),
        "request_id": result.get("request_id"),  # links the vote to its logged answer
        "rating": rating,
        "comment": comment.strip()[:MAX_COMMENT_CHARS],
    }


# --------------------------------------------------------------------- #
# API calls
# --------------------------------------------------------------------- #


def ask_api(question: str, top_k: int) -> tuple[dict | None, str | None]:
    """(response body, None) on success, (None, message for the user) otherwise."""
    try:
        r = httpx.post(f"{API_URL}/ask", json={"question": question, "top_k": top_k}, timeout=ASK_TIMEOUT_S)
    except httpx.HTTPError:
        return None, f"Can't reach the API at {API_URL}. Start it with `python -m src.api`."
    if r.status_code == 200:
        return r.json(), None
    if r.status_code == 422:
        return None, f"Questions must be 1 to {MAX_QUESTION_CHARS} characters."
    if r.status_code == 503:
        return None, "The index isn't loaded, so nothing can be searched yet. See the status on the left."
    return None, "The answer couldn't be generated because an upstream service failed. Ask again in a moment."


def send_feedback(payload: dict) -> bool:
    try:
        return httpx.post(f"{API_URL}/feedback", json=payload, timeout=10).status_code == 204
    except httpx.HTTPError:
        return False


def get_health() -> dict | None:
    try:
        return httpx.get(f"{API_URL}/health", timeout=5).json()
    except (httpx.HTTPError, ValueError):
        return None


# --------------------------------------------------------------------- #
# page
# --------------------------------------------------------------------- #

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400;700&display=swap');

:root {
  --bg: #1A1D23; --pane: #21252D; --line: #2E333D; --text: #DCE1EA; --muted: #7F8896;
  --teal: #4FD1C5; --hl: rgba(79, 209, 197, .13); --amber: #F2B84B; --red: #E58B7E;
  --sans: 'IBM Plex Sans', system-ui, sans-serif; --mono: 'JetBrains Mono', ui-monospace, monospace;
}

#MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"],
[data-testid="stStatusWidget"], [data-testid="stHeader"] { display: none !important; }
html, body, [data-testid="stAppViewContainer"], button, input, textarea { font-family: var(--sans); }
.block-container { max-width: none; padding: 0 !important; }
/* the <style> blocks themselves shouldn't take up a row */
[data-testid="stElementContainer"]:has(> div > div > style),
[data-testid="stElementContainer"]:has(style:only-child) { display: none; }
[data-testid="stMainBlockContainer"] > div > [data-testid="stVerticalBlock"] { gap: 0; }

/* the three panes */
[data-testid="stColumn"]:has(.st-key-history) {
  border-right: 1px solid var(--line); padding: 1.3rem 1rem 1.5rem; min-height: 100vh;
}
[data-testid="stColumn"]:has(.st-key-reading) { padding: 1.6rem 2.2rem 2rem; }
[data-testid="stColumn"]:has(.st-key-sources) {
  background: var(--pane); border-left: 1px solid var(--line); padding: 1.1rem 0 2rem; min-height: 100vh;
}

/* left: brand, status, session */
.brand { font-family: var(--mono); font-weight: 700; color: var(--teal); font-size: .95rem; }
.status { display: flex; align-items: center; gap: .45rem; font-size: .78rem; color: var(--muted); margin: .5rem 0 .2rem; }
.status::before { content: ""; width: .45rem; height: .45rem; border-radius: 50%; background: var(--muted); flex: none; }
.status.ok::before { background: #6FCF97; }
.status.warn { color: var(--amber); }
.status.warn::before { background: var(--amber); }
.label { font-size: .74rem; font-weight: 600; color: var(--muted); margin: 1.4rem 0 .4rem; }
.st-key-history .stButton > button {
  width: 100%; justify-content: flex-start; text-align: left; background: transparent; border: 0;
  border-radius: 4px; color: #AEB6C2; font-size: .84rem; padding: .4rem .55rem; min-height: 0; line-height: 1.35;
}
.st-key-history .stButton > button:hover { background: var(--pane); color: var(--text); }
.st-key-history .stButton > button p { white-space: normal; text-align: left; }
.st-key-history .stButton > button > div { justify-content: flex-start; width: 100%; }
.empty-hint { font-size: .8rem; color: var(--muted); line-height: 1.5; }

/* middle: question, answer, metrics */
.q { font-family: var(--mono); color: var(--teal); font-size: .95rem; margin-bottom: 1rem; line-height: 1.5; }
.q::before { content: "? "; color: var(--muted); }
.a { font-size: 1.02rem; line-height: 1.7; color: var(--text); }
.a p { margin: 0 0 .8rem; }
.a ul { margin: 0 0 .8rem; padding-left: 1.2rem; }
.a li { margin-bottom: .3rem; }
.a code { font-family: var(--mono); font-size: .86em; color: var(--amber); }
.c {
  display: inline-block; font-family: var(--mono); font-size: .68rem; font-weight: 700; line-height: 1;
  color: var(--bg); background: var(--teal); padding: .16rem .32rem; border-radius: 3px; margin-left: .15rem;
  vertical-align: .12rem;
}
.c.dead { background: var(--line); color: var(--muted); }
.idk { border-left: 2px solid var(--amber); padding: .1rem 0 .1rem .9rem; }
.idk b { color: var(--amber); font-weight: 600; }
.idk p { margin: .25rem 0 0; color: var(--text); }
.err { border-left: 2px solid var(--red); padding: .1rem 0 .1rem .9rem; color: var(--red); line-height: 1.6; }
.metrics {
  display: flex; flex-wrap: wrap; gap: .4rem 1.1rem; font-family: var(--mono); font-size: .72rem; color: var(--muted);
  border-top: 1px solid var(--line); padding-top: .7rem; margin-top: .6rem;
}
.intro { color: var(--muted); font-size: .95rem; line-height: 1.6; max-width: 34rem; margin: .2rem 0 1rem; }
.intro b { color: var(--text); font-weight: 500; }
.st-key-reading [data-testid="stHorizontalBlock"], .st-key-reading .stTextInput { margin-top: .8rem; }
.thanks { font-size: .8rem; color: var(--muted); margin-top: .6rem; }

/* small outlined buttons: examples, feedback */
.st-key-reading .stButton > button {
  background: transparent; border: 1px solid var(--line); color: var(--muted);
  border-radius: 4px; font-size: .8rem; padding: .28rem .7rem; min-height: 0;
}
.st-key-reading .stButton > button:hover { border-color: var(--teal); color: var(--text); }
button:focus-visible { outline: 2px solid var(--teal) !important; outline-offset: 2px; }
.st-key-reading [data-testid="stChatInput"] { margin-top: 1.4rem; }
[data-testid="stChatInput"] textarea { font-family: var(--mono); font-size: .88rem; }

/* right: source tabs + passage */
.st-key-sources [data-baseweb="tab-list"] { gap: .25rem; padding: 0 1rem !important; border-bottom: 1px solid var(--line); }
.st-key-sources [role="tablist"] { padding-left: 1rem !important; }
.st-key-sources button[role="tab"] * { font-family: var(--mono) !important; font-size: .75rem !important; }
.st-key-sources [data-baseweb="tab"] {
  font-family: var(--mono); font-size: .75rem; color: var(--muted); padding: .35rem .65rem; height: auto;
  border-radius: 4px 4px 0 0;
}
.st-key-sources [data-baseweb="tab"][aria-selected="true"] { color: var(--teal); background: var(--bg); }
.st-key-sources [data-baseweb="tab-highlight"], .st-key-sources [data-baseweb="tab-border"] { display: none; }
.pane-head { font-family: var(--mono); font-size: .74rem; color: var(--muted); padding: 0 1.1rem; margin-bottom: .6rem; }
.file { font-family: var(--mono); font-size: .74rem; color: var(--muted); padding: .2rem 1.1rem .5rem; line-height: 1.5; }
.file b { color: var(--text); font-weight: 400; }
.passage { font-family: var(--mono); font-size: .76rem; line-height: 1.7; color: #AEB6C2; }
.ln { display: grid; grid-template-columns: 2.4rem 1fr; padding-right: 1rem; }
.ln i { font-style: normal; color: #4B525E; text-align: right; padding-right: .8rem; user-select: none; }
.ln span { white-space: pre-wrap; word-break: break-word; }
.ln.hit { background: var(--hl); color: var(--text); box-shadow: inset 2px 0 var(--teal); }
.pane-foot { font-family: var(--mono); font-size: .72rem; color: var(--muted); padding: .8rem 1.1rem 0; line-height: 1.6; }
.pane-foot a { color: var(--teal) !important; text-decoration: none; }
.pane-foot a:hover, .pane-foot a:focus-visible { text-decoration: underline; }

@media (max-width: 640px) {
  [data-testid="stColumn"]:has(.st-key-history),
  [data-testid="stColumn"]:has(.st-key-sources) { min-height: 0; border: 0; }
  [data-testid="stColumn"]:has(.st-key-reading) { padding: 1.2rem 1rem; }
}
</style>
"""


def _turn_css(turns: list[dict], active: int | None) -> str:
    """Per-turn styles for the history list: amber for unanswered, a rail for the open one."""
    rules = []
    for i, t in enumerate(turns):
        if t.get("error") or (t.get("result") and not t["result"]["answerable"]):
            rules.append(f".st-key-hist_{i} button {{ color: var(--amber) !important; }}")
        if i == active:
            rules.append(
                f".st-key-hist_{i} button {{ background: var(--pane) !important; color: var(--text) !important;"
                f" box-shadow: inset 2px 0 var(--teal); }}"
            )
    return f"<style>{''.join(rules)}</style>" if rules else ""


def render_history(health: dict | None) -> None:
    with st.container(key="history"):
        st.markdown('<div class="brand">librarian</div>', unsafe_allow_html=True)
        if health is None:
            cls, label = "warn", "API not reachable"
            detail = f"Nothing answers at {API_URL}. Start it with `python -m src.api`."
        elif health.get("status") == "ok":
            rerank = "rerank on" if health.get("rerank") else "rerank off"
            cls, label, detail = "ok", f"{health.get('chunks'):,} passages, {rerank}", None
        else:
            cls, label = "warn", "Index not loaded"
            detail = health.get("error") or f"Qdrant: {health.get('qdrant')}"
        st.markdown(f'<div class="status {cls}">{html.escape(label)}</div>', unsafe_allow_html=True)
        if detail:
            with st.expander("Details"):
                st.write(detail)

        st.markdown('<div class="label">This session</div>', unsafe_allow_html=True)
        turns = st.session_state.turns
        if not turns:
            st.markdown('<div class="empty-hint">Your questions will be listed here.</div>', unsafe_allow_html=True)
        for i, t in enumerate(turns):
            label = t["question"] if len(t["question"]) <= 70 else t["question"][:67] + "..."
            if st.button(label, key=f"hist_{i}", width="stretch"):
                st.session_state.active = i
                st.rerun()

        st.markdown('<div class="label">Settings</div>', unsafe_allow_html=True)
        st.slider("Passages sent to the model", 1, 10, key="top_k")


def render_reading() -> str | None:
    """Middle pane. Returns a question to ask (typed or an example), if any."""
    question = None
    with st.container(key="reading"):
        turns, active = st.session_state.turns, st.session_state.active
        if active is None:
            st.markdown(
                '<div class="intro"><b>Ask an application-security question.</b> Answers come only from the '
                "OWASP Cheat Sheet Series. Every claim is numbered, and the passage it came from opens on "
                "the right.</div>",
                unsafe_allow_html=True,
            )
            row = st.container(horizontal=True, gap="small")
            for n, example in enumerate(EXAMPLES):
                if row.button(example, key=f"example_{n}"):
                    question = example
        else:
            render_turn(active, turns[active])

        typed = st.chat_input("ask a security question", max_chars=MAX_QUESTION_CHARS)
    return typed or question


def render_turn(i: int, turn: dict) -> None:
    st.markdown(f'<div class="q">{html.escape(turn["question"])}</div>', unsafe_allow_html=True)
    if turn.get("error"):
        st.markdown(f'<div class="err">{html.escape(turn["error"])}</div>', unsafe_allow_html=True)
        return

    result = turn["result"]
    if result["answerable"]:
        body = f'<div class="a">{answer_html(result["answer"], result["citations"])}</div>'
    else:
        body = (
            '<div class="idk"><b>Not covered.</b>'
            f'<p>{html.escape(refusal_text(result.get("refusal_reason")))}</p></div>'
        )
    body += timings_html(
        result.get("timings_ms", {}), len(result.get("citations", [])), len(result.get("sources", []))
    )
    st.markdown(body, unsafe_allow_html=True)
    render_feedback(i, result)


def render_feedback(i: int, result: dict) -> None:
    state = st.session_state.feedback.get(i)  # None | "comment" | "sent"
    if state == "sent":
        st.markdown('<div class="thanks">Feedback recorded.</div>', unsafe_allow_html=True)
        return
    if state == "comment":
        comment = st.text_input(
            "What was wrong or missing?", key=f"comment_{i}", max_chars=MAX_COMMENT_CHARS, placeholder="Optional",
        )
        if st.button("Send feedback", key=f"send_{i}"):
            _submit_feedback(i, result, "down", comment)
        return
    row = st.container(horizontal=True, gap="small")
    if row.button("Helpful", key=f"up_{i}"):
        _submit_feedback(i, result, "up")
    if row.button("Not helpful", key=f"down_{i}"):
        st.session_state.feedback[i] = "comment"
        st.rerun()


def _submit_feedback(i: int, result: dict, rating: str, comment: str = "") -> None:
    if send_feedback(feedback_payload(result, rating, comment)):
        st.session_state.feedback[i] = "sent"
        st.rerun()
    else:
        st.error("Feedback couldn't be saved because the API didn't respond. Try again.")


def render_sources() -> None:
    with st.container(key="sources"):
        turns, active = st.session_state.turns, st.session_state.active
        result = turns[active].get("result") if active is not None else None
        if not result:
            st.markdown(
                '<div class="pane-head">sources</div><div class="pane-foot">The passages an answer cites open '
                "here, exactly as the model received them.</div>",
                unsafe_allow_html=True,
            )
            return

        if result["answerable"]:
            shown, note = result["citations"], "Highlighted lines share terms with the answer."
        else:
            shown, note = result.get("sources", []), "These were searched. None of them answered the question."
        if not shown:
            st.markdown(
                '<div class="pane-foot">No passages were retrieved for this question.</div>', unsafe_allow_html=True
            )
            return

        tabs = st.tabs([f"[{s['number']}] {call_tag(s.get('title') or '')}" for s in shown])
        for tab, s in zip(tabs, shown):
            with tab:
                section = (s.get("section_path") or "").replace(" > ", " › ")
                terms = support_terms(result["answer"], s["number"]) if result["answerable"] else None
                text = s.get("text") or "(passage text not returned by the API)"
                st.markdown(
                    f'<div class="file"><b>{html.escape(s.get("source_file") or s.get("title") or "")}</b>'
                    f"{' › ' + html.escape(section) if section else ''}</div>"
                    + passage_html(text, terms)
                    + f'<div class="pane-foot">{html.escape(note)}<br>'
                    f'<a href="{html.escape(s["source_url"])}" target="_blank" rel="noopener">'
                    "Open on cheatsheetseries.owasp.org</a></div>",
                    unsafe_allow_html=True,
                )


def main() -> None:
    st.set_page_config(page_title="The Librarian", page_icon="📚", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)
    st.session_state.setdefault("turns", [])
    st.session_state.setdefault("feedback", {})
    st.session_state.setdefault("active", None)
    st.session_state.setdefault("top_k", 5)

    st.markdown(_turn_css(st.session_state.turns, st.session_state.active), unsafe_allow_html=True)
    health = get_health()
    left, middle, right = st.columns([1, 2.3, 1.9], gap=None)
    with left:
        render_history(health)
    with middle:
        question = render_reading()
    with right:
        render_sources()

    if question and question.strip():
        with middle:
            with st.spinner("Searching the cheat sheets..."):
                result, error = ask_api(question.strip(), st.session_state.top_k)
        turns = st.session_state.turns
        turns.append({"question": question.strip(), "result": result, "error": error})
        if len(turns) > MAX_TURNS:
            turns.pop(0)
            st.session_state.feedback = {k - 1: v for k, v in st.session_state.feedback.items() if k > 0}
        st.session_state.active = len(turns) - 1
        st.rerun()


if __name__ == "__main__":
    main()

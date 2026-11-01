"""
Streamlit front end for the Librarian API (src/api/main.py). It only talks
HTTP to the API -- no keys, no index, no models are loaded here.

Run:  API_URL=http://localhost:8000 streamlit run ui/app.py
"""
from __future__ import annotations

import os
import re

import httpx
import streamlit as st

API_URL = os.environ.get("API_URL", "http://localhost:8000").rstrip("/")
TIMEOUT = httpx.Timeout(120.0, connect=5.0)  # first questions can be slow while models warm up
_CITATION_RE = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")

EXAMPLES = [
    "How should I store user passwords?",
    "What is the difference between CSRF tokens and the SameSite cookie attribute?",
    "How do I prevent XXE in Java XML parsers?",
]

st.set_page_config(page_title="The Librarian · OWASP", page_icon="📚", layout="centered")


def link_citations(answer: str, citations: list[dict]) -> str:
    """Turn "[1]" / "[2, 3]" in the answer into markdown links to the cited
    OWASP pages. Numbers without a citation entry are left as plain text."""
    urls = {c["number"]: c["source_url"] for c in citations}

    def repl(m: re.Match) -> str:
        parts = []
        for n in (int(x) for x in re.split(r"\s*,\s*", m.group(1))):
            parts.append(f"[\\[{n}\\]]({urls[n]})" if n in urls else f"\\[{n}\\]")
        return "".join(parts)

    return _CITATION_RE.sub(repl, answer)


def api_status() -> tuple[bool, str]:
    try:
        r = httpx.get(f"{API_URL}/health", timeout=3.0)
    except httpx.HTTPError:
        return False, "API not reachable"
    if r.status_code == 200:
        return True, f"ready · {r.json().get('model') or 'model unknown'}"
    detail = _json(r).get("detail")
    reason = detail.get("reason", "unavailable") if isinstance(detail, dict) else "unavailable"
    return False, f"not ready ({reason})"


def _json(r: httpx.Response) -> dict:
    try:
        data = r.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def ask(question: str, top_k: int) -> None:
    st.session_state.pop("result", None)
    st.session_state.pop("error", None)
    try:
        r = httpx.post(f"{API_URL}/ask", json={"question": question, "top_k": top_k}, timeout=TIMEOUT)
    except httpx.HTTPError:
        st.session_state.error = "Could not reach the API. Is it running?"
        return
    if r.status_code == 200:
        st.session_state.result = r.json()
    elif r.status_code == 422:
        st.session_state.error = "Please enter a question of 1–1000 characters."
    else:
        detail = _json(r).get("detail")
        st.session_state.error = detail if isinstance(detail, str) else f"The API returned an error ({r.status_code})."


def send_feedback(request_id: str, helpful: bool, comment: str) -> None:
    try:
        r = httpx.post(f"{API_URL}/feedback", json={"request_id": request_id, "helpful": helpful,
                                                    "comment": comment or None}, timeout=10.0)
        ok = r.status_code == 200
    except httpx.HTTPError:
        ok = False
    st.session_state.feedback_sent = request_id if ok else None
    if not ok:
        st.toast("Could not record feedback, sorry.")


# --------------------------------------------------------------------- #
# page
# --------------------------------------------------------------------- #

st.title("📚 The Librarian")
st.caption(
    "Application-security answers from the [OWASP Cheat Sheet Series](https://cheatsheetseries.owasp.org/) "
    "(CC BY-SA 4.0), with a citation for every claim. If the cheat sheets don't cover it, it says so."
)

ready, status = api_status()
with st.sidebar:
    st.markdown(f"**API:** `{API_URL}`  \n{'🟢' if ready else '🔴'} {status}")
    top_k = st.slider("Sources given to the model", 1, 10, 5)
    st.markdown("**Try:**")
    for ex in EXAMPLES:
        if st.button(ex, use_container_width=True):
            st.session_state.question = ex

with st.form("ask"):
    question = st.text_area("Your question", key="question", max_chars=1000, height=100,
                            placeholder="e.g. How long should a session ID be?")
    submitted = st.form_submit_button("Ask", type="primary")

if submitted:
    if not question.strip():
        st.warning("Please type a question.")
    else:
        with st.spinner("Searching the cheat sheets…"):
            ask(question.strip(), top_k)

if st.session_state.get("error"):
    st.error(st.session_state.error)

result = st.session_state.get("result")
if result:
    if result["answerable"]:
        st.markdown(link_citations(result["answer"], result["citations"]))
    else:
        st.info(result["answer"])

    if result["citations"]:
        st.markdown("**Sources**")
        for c in result["citations"]:
            section = f" › {c['section_path']}" if c["section_path"] else ""
            st.markdown(f"\\[{c['number']}\\] [{c['title']}{section}]({c['source_url']})")

    st.caption(f"{result['latency_ms'] / 1000:.1f}s · {result.get('model') or ''} · request {result['request_id'][:8]}")

    st.divider()
    if st.session_state.get("feedback_sent") == result["request_id"]:
        st.success("Thanks for the feedback!")
    else:
        st.markdown("**Was this answer helpful?**")
        comment = st.text_input("Optional comment (what was wrong or missing?)", key=f"comment_{result['request_id']}")
        up, down, _ = st.columns([1, 1, 6])
        if up.button("👍", key="up", help="Helpful"):
            send_feedback(result["request_id"], True, comment)
            st.rerun()
        if down.button("👎", key="down", help="Not helpful"):
            send_feedback(result["request_id"], False, comment)
            st.rerun()

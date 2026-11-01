"""Offline UI tests: the API is faked, nothing is started. Needs
requirements-ui.txt (streamlit). Run from the repo root:
    python -m unittest tests.test_ui -v"""
import unittest
from unittest import mock

import httpx

from src.ui.app import (
    MAX_COMMENT_CHARS, answer_html, ask_api, call_tag, feedback_payload, passage_html, refusal_text, send_feedback,
    support_terms, timings_html,
)

URL = "https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html"
CITES = [{"number": 1, "source_url": URL}, {"number": 3, "source_url": URL + "#b"}]


class AnswerHtml(unittest.TestCase):
    def test_citation_markers(self):
        out = answer_html("Use Argon2id [1]. Also [1, 3].", CITES)
        self.assertEqual(out.count('<span class="c">'), 3)
        self.assertTrue(out.startswith("<p>") and out.endswith("</p>"))

    def test_unknown_number_greyed(self):
        out = answer_html("Claim [2].", CITES)
        self.assertIn('<span class="c dead">2</span>', out)

    def test_model_html_is_escaped(self):
        # The corpus is full of XSS payloads the model may quote: they must render as text.
        out = answer_html('Never echo <script>alert(1)</script> or <img src=x onerror=alert(1)> [1].', CITES)
        self.assertNotIn("<script>", out)
        self.assertNotIn("<img", out)
        self.assertIn("&lt;script&gt;", out)

    def test_lists_code_bold_paragraphs(self):
        out = answer_html("Intro **now** [1].\n\n- use `bcrypt` [3]\n- 10+ rounds\n\nEnd.", CITES)
        self.assertIn("<strong>now</strong>", out)
        self.assertIn("<ul><li>use <code>bcrypt</code>", out)
        self.assertEqual(out.count("<li>"), 2)
        self.assertEqual(out.count("<p>"), 2)


ANSWER = "Prefer Argon2id with 19 MiB of memory [1]. Use bcrypt with a work factor of 10 [2]."
PASSAGE = "### Argon2id\n\nArgon2id should use a minimum memory size.\n- m=19456 (19 MiB), t=2, p=1\nUnrelated closing line."


class Passage(unittest.TestCase):
    def test_support_terms_only_from_sentences_citing_that_source(self):
        terms = support_terms(ANSWER, 1)
        self.assertIn("argon2id", terms)
        self.assertIn("19", terms)
        self.assertNotIn("bcrypt", terms)

    def test_highlights_lines_sharing_terms(self):
        out = passage_html(PASSAGE, support_terms(ANSWER, 1))
        rows = out.split('<div class="ln')[1:]
        hits = [r for r in rows if r.startswith(' hit"')]
        self.assertEqual(len(rows), 5)  # every line numbered, blank lines kept
        self.assertTrue(any("m=19456" in r for r in hits))
        self.assertFalse(any("Unrelated" in r for r in hits))

    def test_no_terms_no_highlight_and_escaped(self):
        out = passage_html("<script>alert(1)</script>\nplain")
        self.assertNotIn(" hit", out)
        self.assertNotIn("<script>", out)
        self.assertIn("&lt;script&gt;", out)

    def test_call_tag(self):
        self.assertEqual(call_tag("Password Storage Cheat Sheet"), "PS")
        self.assertEqual(call_tag("Authentication Cheat Sheet"), "AUTH")
        self.assertEqual(call_tag("Cross Site Request Forgery Prevention Cheat Sheet"), "CSRF")
        self.assertEqual(call_tag(""), "?")


class Metrics(unittest.TestCase):
    def test_timings_in_pipeline_order(self):
        out = timings_html({"total_ms": 2101, "generation_ms": 1050, "retrieval_vector_ms": 402.4}, 3, 5)
        self.assertLess(out.index("vector 402 ms"), out.index("generation 1.05 s"))
        self.assertLess(out.index("generation"), out.index("total 2.10 s"))
        self.assertIn("3/5 passages cited", out)

    def test_empty(self):
        self.assertEqual(timings_html({}), "")

    def test_refusal_text(self):
        self.assertIn("don't answer", refusal_text("model_declined"))
        self.assertTrue(refusal_text("something_new"))  # unknown reason still gets a sentence
        self.assertTrue(refusal_text(None))


def response(status, body=None):
    return httpx.Response(status, json=body or {}, request=httpx.Request("POST", "http://api/ask"))


class AskApi(unittest.TestCase):
    def test_ok(self):
        with mock.patch("src.ui.app.httpx.post", return_value=response(200, {"answer": "x"})) as post:
            self.assertEqual(ask_api("q", 5), ({"answer": "x"}, None))
        self.assertEqual(post.call_args.kwargs["json"], {"question": "q", "top_k": 5})

    def test_error_statuses_give_messages(self):
        for status, snippet in ((422, "1 to 1000"), (503, "isn't loaded"), (502, "upstream service failed")):
            with mock.patch("src.ui.app.httpx.post", return_value=response(status)):
                body, error = ask_api("q", 5)
            self.assertIsNone(body)
            self.assertIn(snippet, error)

    def test_unreachable(self):
        with mock.patch("src.ui.app.httpx.post", side_effect=httpx.ConnectError("refused")):
            body, error = ask_api("q", 5)
        self.assertIsNone(body)
        self.assertIn("Can't reach", error)


RESULT = {
    "question": "how should I store passwords?", "answer": "Use Argon2id [1].", "answerable": True,
    "refusal_reason": None, "model": "gemini-x", "timings_ms": {"total_ms": 900.0},
    "citations": [{"number": 1, "chunk_id": "c2", "source_url": URL}],
    "sources": [{"number": 1, "chunk_id": "c2"}, {"number": 2, "chunk_id": "c0"}],
}


class Feedback(unittest.TestCase):
    def test_payload_has_only_answer_fields(self):
        p = feedback_payload(RESULT, "down", "  missing bcrypt  ")
        self.assertEqual(p["cited_chunk_ids"], ["c2"])  # cited only, not every source
        self.assertEqual((p["rating"], p["comment"]), ("down", "missing bcrypt"))
        self.assertNotIn("timings_ms", p)

    def test_payload_refusal_and_long_comment(self):
        idk = {**RESULT, "answerable": False, "refusal_reason": "model_declined", "citations": []}
        p = feedback_payload(idk, "up", "x" * (MAX_COMMENT_CHARS + 50))
        self.assertEqual((p["answerable"], p["refusal_reason"], p["cited_chunk_ids"]), (False, "model_declined", []))
        self.assertEqual(len(p["comment"]), MAX_COMMENT_CHARS)

    def test_send(self):
        with mock.patch("src.ui.app.httpx.post", return_value=response(204)):
            self.assertTrue(send_feedback({}))
        with mock.patch("src.ui.app.httpx.post", return_value=response(500)):
            self.assertFalse(send_feedback({}))
        with mock.patch("src.ui.app.httpx.post", side_effect=httpx.ConnectError("refused")):
            self.assertFalse(send_feedback({}))


if __name__ == "__main__":
    unittest.main()

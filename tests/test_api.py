"""Offline API tests: the Librarian runs over the fake retriever from
test_retriever and a fake Gemini from test_generation, so no Qdrant, no
data/index, no API keys and no credits. Run from the repo root:
    python -m unittest tests.test_api -v"""
import json
import logging
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from src.api.app import MAX_COMMENT_CHARS, MAX_QUESTION_CHARS, MAX_TOP_K, create_app
from src.generation import IDK_ANSWER, Librarian
from tests.test_generation import FakeGemini, reply, retriever


def make_client(raw=None, health="ok", generate=None, fail_startup=None, feedback_path=None):
    """A TestClient over a Librarian with a fake retriever and fake Gemini.
    Returns (client, fake_gemini, loader_call_count)."""
    gemini = generate or FakeGemini(raw if raw is not None else reply(True, "Use Argon2id [1]."))
    loads = {"n": 0}

    def loader():
        loads["n"] += 1
        if fail_startup:
            raise fail_startup
        return Librarian(retriever(), gemini, model="fake-gemini"), lambda librarian: health

    # Feedback always goes to a throwaway file, never into the repo's data/.
    feedback_path = feedback_path or Path(tempfile.mkdtemp()) / "feedback.jsonl"
    return TestClient(create_app(loader, feedback_path=feedback_path)), gemini, loads

def setUpModule():
    logging.disable(logging.CRITICAL)  # the 502/503 tests log expected tracebacks


def tearDownModule():
    logging.disable(logging.NOTSET)


class Ask(unittest.TestCase):
    def test_answered_with_citations(self):
        client, gemini, _ = make_client()
        with client:
            r = client.post("/ask", json={"question": "how should I store passwords?"})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["answerable"])
        self.assertEqual(body["answer"], "Use Argon2id [1].")
        self.assertIsNone(body["refusal_reason"])
        self.assertEqual([c["number"] for c in body["citations"]], [1])
        self.assertEqual(body["citations"][0]["chunk_id"], "c2")  # hybrid rank 1 (see test_generation)
        self.assertEqual(body["citations"][0]["text"], "text 2")  # passage text travels with the source
        self.assertEqual(body["model"], "fake-gemini")
        self.assertIn("total_ms", body["timings_ms"])
        self.assertEqual(len(gemini.calls), 1)

    def test_refusal_is_200_not_error(self):
        client, _, _ = make_client(raw=reply(False, ""))
        with client:
            r = client.post("/ask", json={"question": "how do I bake sourdough bread?"})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertFalse(body["answerable"])
        self.assertEqual(body["answer"], IDK_ANSWER)
        self.assertEqual(body["refusal_reason"], "model_declined")
        self.assertEqual(body["citations"], [])

    def test_question_is_stripped(self):
        client, gemini, _ = make_client()
        with client:
            r = client.post("/ask", json={"question": "  how should I store passwords?  "})
        self.assertEqual(r.json()["question"], "how should I store passwords?")
        self.assertTrue(gemini.calls[0][1].endswith("Question: how should I store passwords?"))

    def test_top_k_forwarded(self):
        client, gemini, _ = make_client()
        with client:
            r = client.post("/ask", json={"question": "passwords", "top_k": 2})
        self.assertEqual(len(r.json()["sources"]), 2)
        self.assertNotIn("[3]", gemini.calls[0][1])

    def test_invalid_input_rejected_before_pipeline(self):
        client, gemini, _ = make_client()
        bad = [
            {},
            {"question": ""},
            {"question": "   "},
            {"question": "x" * (MAX_QUESTION_CHARS + 1)},
            {"question": "ok", "top_k": 0},
            {"question": "ok", "top_k": MAX_TOP_K + 1},
            {"question": 42},
        ]
        with client:
            for payload in bad:
                self.assertEqual(client.post("/ask", json=payload).status_code, 422, payload)
        self.assertEqual(gemini.calls, [])  # nothing reached retrieval or Gemini

    def test_upstream_error_is_502_without_details(self):
        def broken(system_prompt, user_prompt):
            raise RuntimeError("secret upstream detail sk-123")

        client, _, _ = make_client(generate=broken)
        with client:
            r = client.post("/ask", json={"question": "passwords"})
        self.assertEqual(r.status_code, 502)
        self.assertNotIn("sk-123", r.text)

    def test_librarian_loaded_once(self):
        client, _, loads = make_client()
        with client:
            for _ in range(3):
                client.post("/ask", json={"question": "passwords"})
            client.get("/health")
        self.assertEqual(loads["n"], 1)


class Health(unittest.TestCase):
    def test_ok(self):
        client, _, _ = make_client()
        with client:
            r = client.get("/health")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "ok")
        self.assertTrue(body["index_loaded"])
        self.assertEqual(body["chunks"], 4)
        self.assertEqual(body["qdrant"], "ok")
        self.assertFalse(body["rerank"])

    def test_qdrant_down_is_503(self):
        client, _, _ = make_client(health="unreachable")
        with client:
            r = client.get("/health")
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()["qdrant"], "unreachable")

    def test_startup_failure(self):
        client, _, _ = make_client(fail_startup=FileNotFoundError("data/index has no chunks.jsonl"))
        with client:
            h = client.get("/health")
            a = client.post("/ask", json={"question": "passwords"})
        self.assertEqual(h.status_code, 503)
        self.assertFalse(h.json()["index_loaded"])
        self.assertIn("chunks.jsonl", h.json()["error"])
        self.assertEqual(a.status_code, 503)


FEEDBACK = {
    "question": "how should I store passwords?",
    "answer": "Use Argon2id [1].",
    "answerable": True,
    "refusal_reason": None,
    "cited_chunk_ids": ["c2"],
    "model": "fake-gemini",
    "rating": "up",
}


class Feedback(unittest.TestCase):
    def setUp(self):
        self.path = Path(tempfile.mkdtemp()) / "sub" / "feedback.jsonl"  # parent dir created on demand

    def test_appends_jsonl(self):
        client, _, _ = make_client(feedback_path=self.path)
        with client:
            r1 = client.post("/feedback", json=FEEDBACK)
            r2 = client.post("/feedback", json={**FEEDBACK, "rating": "down", "comment": "missing bcrypt"})
        self.assertEqual((r1.status_code, r2.status_code), (204, 204))
        rows = [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([r["rating"] for r in rows], ["up", "down"])
        self.assertEqual(rows[1]["comment"], "missing bcrypt")
        self.assertEqual(rows[0]["cited_chunk_ids"], ["c2"])
        self.assertIn("ts", rows[0])

    def test_no_personal_data_stored(self):
        client, _, _ = make_client(feedback_path=self.path)
        with client:
            client.post("/feedback", json=FEEDBACK, headers={"X-Forwarded-For": "203.0.113.7"})
        row = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(set(row), {"ts", *FEEDBACK, "comment"})
        self.assertNotIn("203.0.113.7", self.path.read_text(encoding="utf-8"))

    def test_invalid_rejected_and_not_written(self):
        client, _, _ = make_client(feedback_path=self.path)
        bad = [
            {**FEEDBACK, "rating": "meh"},
            {**FEEDBACK, "comment": "x" * (MAX_COMMENT_CHARS + 1)},
            {**FEEDBACK, "cited_chunk_ids": ["c"] * (MAX_TOP_K + 1)},
            {k: v for k, v in FEEDBACK.items() if k != "rating"},
        ]
        with client:
            for payload in bad:
                self.assertEqual(client.post("/feedback", json=payload).status_code, 422)
        self.assertFalse(self.path.exists())

    def test_works_when_librarian_failed_to_load(self):
        client, _, _ = make_client(fail_startup=RuntimeError("no index"), feedback_path=self.path)
        with client:
            self.assertEqual(client.post("/feedback", json=FEEDBACK).status_code, 204)

    def test_unwritable_path_is_500(self):
        blocker = Path(tempfile.mkdtemp()) / "file"
        blocker.write_text("not a dir")
        client, _, _ = make_client(feedback_path=blocker / "feedback.jsonl")
        with client:
            self.assertEqual(client.post("/feedback", json=FEEDBACK).status_code, 500)


if __name__ == "__main__":
    unittest.main()

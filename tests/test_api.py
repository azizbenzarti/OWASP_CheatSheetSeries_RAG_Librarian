"""Offline API tests: the Librarian is faked, so no Qdrant, no API keys, no
data/index and no torch are needed. Logs go to a temp dir. Run from the
repo root:  python -m unittest tests.test_api -v"""
import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from src.api.main import create_app, percentile
from src.generation import IDK_ANSWER, Answer, Source

URL = "https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html"
SRC = Source(1, "Password Storage Cheat Sheet", "Hashing > Argon2id", "Password_Storage_Cheat_Sheet.md", URL, "c0")


class FakeLibrarian:
    """Stands in for Librarian: records calls, answers or refuses by keyword,
    raises when told to (to emulate Qdrant / Gemini being down)."""
    model = "fake-model"

    def __init__(self):
        self.calls = []

    def ask(self, question, top_k=5):
        self.calls.append((question, top_k))
        if "boom" in question:
            raise ConnectionError("qdrant at http://internal-host:6333 refused (secret detail)")
        if "sourdough" in question:
            return Answer(question, IDK_ANSWER, False, [], [SRC], "model_declined", model=self.model,
                          timings_ms={"total_ms": 5.0})
        return Answer(question, "Use Argon2id [1].", True, [SRC], [SRC], model=self.model,
                      timings_ms={"retrieval_total_ms": 3.0, "generation_ms": 7.0, "total_ms": 10.0})


class ApiTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.log_dir = Path(self.tmp.name)
        self.librarian = FakeLibrarian()
        self.client = self.make_client(lambda: self.librarian)

    def make_client(self, factory):
        client = TestClient(create_app(factory, log_dir=self.log_dir))
        client.__enter__()  # runs the lifespan (loads the Librarian)
        self.addCleanup(client.__exit__, None, None, None)
        return client


class Ask(ApiTestCase):
    def test_answer_with_citations(self):
        r = self.client.post("/ask", json={"question": "  how to store passwords?  ", "top_k": 3})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["answerable"])
        self.assertEqual(body["answer"], "Use Argon2id [1].")
        self.assertEqual(body["citations"][0]["source_url"], URL)
        self.assertEqual(body["citations"][0]["number"], 1)
        self.assertEqual(body["sources"][0]["chunk_id"], "c0")  # every source given, for the UI's source pane
        self.assertIsNone(body["refusal_reason"])
        self.assertEqual(len(body["request_id"]), 32)
        self.assertGreaterEqual(body["latency_ms"], 0)
        self.assertEqual(body["timings_ms"]["generation_ms"], 7.0)
        self.assertEqual(self.librarian.calls, [("how to store passwords?", 3)])  # stripped, top_k passed on

    def test_refusal(self):
        body = self.client.post("/ask", json={"question": "how do I bake sourdough?"}).json()
        self.assertFalse(body["answerable"])
        self.assertEqual(body["refusal_reason"], "model_declined")
        self.assertEqual(body["citations"], [])
        self.assertEqual(self.librarian.calls[-1][1], 5)  # default top_k

    def test_validation(self):
        for payload in ({}, {"question": ""}, {"question": "   "}, {"question": "x" * 1001},
                        {"question": "ok", "top_k": 0}, {"question": "ok", "top_k": 11}, {"question": 3}):
            self.assertEqual(self.client.post("/ask", json=payload).status_code, 422, payload)
        self.assertEqual(self.client.post("/ask", json={"question": "x" * 1000}).status_code, 200)
        self.assertEqual(len(self.librarian.calls), 1)  # invalid requests never reach the Librarian

    def test_backend_error_is_clean_503(self):
        r = self.client.post("/ask", json={"question": "boom"})
        self.assertEqual(r.status_code, 503)
        self.assertNotIn("internal-host", r.text)
        self.assertNotIn("secret", r.text)
        self.assertNotIn("ConnectionError", r.text)

    def test_load_failure(self):
        def broken():
            raise RuntimeError("GEMINI_API_KEY is not set")
        client = self.make_client(broken)
        self.assertEqual(client.get("/health").status_code, 503)
        self.assertEqual(client.get("/health").json()["error"], "RuntimeError")
        r = client.post("/ask", json={"question": "hi"})
        self.assertEqual(r.status_code, 503)
        self.assertNotIn("GEMINI", r.text)


class HealthAndLogs(ApiTestCase):
    def test_health(self):
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual((body["status"], body["model"], body["index_loaded"]), ("ok", "fake-model", True))

    def test_requests_and_feedback_logged(self):
        rid = self.client.post("/ask", json={"question": "passwords?"}).json()["request_id"]
        self.client.post("/ask", json={"question": "boom"})
        r = self.client.post("/feedback", json={"request_id": rid, "helpful": False, "comment": " wrong sheet "})
        self.assertEqual(r.status_code, 204)

        rows = [json.loads(l) for l in (self.log_dir / "requests.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([r["status"] for r in rows], ["ok", "error"])
        self.assertEqual(rows[0]["request_id"], rid)
        self.assertEqual(rows[0]["cited_chunks"], ["c0"])
        self.assertEqual(rows[1]["error"], "ConnectionError")
        [fb] = [json.loads(l) for l in (self.log_dir / "feedback.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual((fb["request_id"], fb["helpful"], fb["comment"]), (rid, False, "wrong sheet"))

    def test_feedback_validation(self):
        self.assertEqual(self.client.post("/feedback", json={"request_id": "nope", "helpful": True}).status_code, 404)
        self.assertEqual(self.client.post("/feedback", json={"request_id": "x"}).status_code, 422)  # no rating
        self.assertEqual(self.client.post("/feedback", json={"rating": "meh"}).status_code, 422)

    def test_feedback_from_ui(self):
        """The payload src/ui/app.py sends: rating + what was asked, request_id optional."""
        r = self.client.post("/feedback", json={
            "question": "q", "answer": "a [1]", "answerable": True, "refusal_reason": None,
            "cited_chunk_ids": ["c0"], "model": "m", "rating": "down", "comment": "", "request_id": None})
        self.assertEqual(r.status_code, 204)
        [fb] = [json.loads(l) for l in (self.log_dir / "feedback.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual((fb["helpful"], fb["cited_chunk_ids"], fb["comment"]), (False, ["c0"], None))
        self.assertEqual(self.client.get("/stats").json()["feedback"]["not_helpful"], 1)


class Stats(ApiTestCase):
    def test_empty(self):
        s = self.client.get("/stats").json()
        self.assertEqual(s["requests"], 0)
        self.assertIsNone(s["latency_ms"]["p50"])
        self.assertIsNone(s["refusal_rate"])

    def test_counts(self):
        rid = self.client.post("/ask", json={"question": "passwords?"}).json()["request_id"]
        self.client.post("/ask", json={"question": "sourdough?"})
        self.client.post("/ask", json={"question": "boom"})
        self.client.post("/feedback", json={"request_id": rid, "helpful": True})
        s = self.client.get("/stats").json()
        self.assertEqual((s["requests"], s["answered"], s["errors"]), (3, 2, 1))
        self.assertEqual(s["refusal_rate"], 0.5)
        self.assertEqual(s["refusal_reasons"], {"model_declined": 1})
        self.assertEqual(s["feedback"], {"total": 1, "helpful": 1, "not_helpful": 0})
        self.assertIsNotNone(s["latency_ms"]["p95"])

    def test_survives_restart(self):
        rid = self.client.post("/ask", json={"question": "passwords?"}).json()["request_id"]
        client = self.make_client(FakeLibrarian)  # new app, same log dir
        self.assertEqual(client.get("/stats").json()["requests"], 1)
        self.assertEqual(client.post("/feedback", json={"request_id": rid, "rating": "up"}).status_code, 204)

    def test_percentile(self):
        self.assertEqual(percentile([5, 1, 3, 2, 4], 50), 3)
        self.assertEqual(percentile(list(range(1, 101)), 95), 95)
        self.assertEqual(percentile([7], 95), 7)
        self.assertIsNone(percentile([], 50))


class OpenAIGeneratorTest(unittest.TestCase):
    def test_request_shape(self):
        from types import SimpleNamespace
        from unittest import mock

        from src.api.openai_generator import DEFAULT_OPENAI_GENERATION_MODEL, OpenAIGenerator

        calls = []
        def create(**kwargs):
            calls.append(kwargs)
            msg = SimpleNamespace(content='{"answerable": true, "answer": "x [1]"}')
            return SimpleNamespace(choices=[SimpleNamespace(message=msg)])
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

        with mock.patch.dict("os.environ", {"OPENAI_GENERATION_MODEL": ""}):
            gen = OpenAIGenerator(client=client)
        self.assertEqual(gen.model, DEFAULT_OPENAI_GENERATION_MODEL)
        self.assertEqual(gen("SYS", "USER"), '{"answerable": true, "answer": "x [1]"}')
        [kw] = calls
        self.assertEqual(kw["messages"], [{"role": "system", "content": "SYS"}, {"role": "user", "content": "USER"}])
        schema = kw["response_format"]["json_schema"]["schema"]
        self.assertEqual(schema["required"], ["answerable", "answer"])
        self.assertFalse(schema["additionalProperties"])


if __name__ == "__main__":
    unittest.main()

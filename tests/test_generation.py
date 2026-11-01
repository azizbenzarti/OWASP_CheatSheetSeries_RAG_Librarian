"""Offline generation tests: Gemini, Qdrant and OpenAI are all faked, so no
API key, no data/index and no google-genai install are needed, and no
credits are spent. Run from the repo root:
    python -m unittest tests.test_generation -v"""
import json
import os
import unittest
from unittest import mock

from src.generation import IDK_ANSWER, answer_question, build_answer, check_citations, parse_model_output
from src.generation.gemini import DEFAULT_GEMINI_MODEL, GeminiConfig, GeminiGenerator
from src.generation.prompt import RESPONSE_SCHEMA, SYSTEM_PROMPT, build_user_prompt
from tests.test_retriever import VEC, make_retriever


def reply(answerable, answer):
    return json.dumps({"answerable": answerable, "answer": answer})


class FakeGemini:
    """Stands in for GeminiGenerator: records the prompts, returns a canned reply."""
    def __init__(self, raw):
        self.raw, self.calls = raw, []
    def __call__(self, system_prompt, user_prompt):
        self.calls.append((system_prompt, user_prompt))
        return self.raw


def retriever():
    # vector: c0, c1, c2; bm25: c3, c2 -> hybrid top 3 is c2, c0, c3 (see test_retriever)
    return make_retriever(VEC, [3, 2], [5.0, 4.0])


class ParseOutput(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(parse_model_output(reply(True, " Use Argon2id [1]. ")), (True, "Use Argon2id [1]."))

    def test_code_fence_tolerated(self):
        raw = "```json\n" + reply(False, "") + "\n```"
        self.assertEqual(parse_model_output(raw), (False, ""))

    def test_invalid(self):
        for raw in (None, "", "not json", "[1, 2]", '{"answer": "x"}', '{"answerable": "yes", "answer": "x"}'):
            self.assertIsNone(parse_model_output(raw), raw)


class Citations(unittest.TestCase):
    def test_valid_kept(self):
        text, valid, invalid = check_citations("A [1]. B [2, 3]. C [1][3].", 3)
        self.assertEqual(text, "A [1]. B [2, 3]. C [1][3].")
        self.assertEqual((valid, invalid), ([1, 2, 3], []))

    def test_out_of_range_removed(self):
        text, valid, invalid = check_citations("A [1]. B [9]. C [0, 2].", 3)
        self.assertEqual(text, "A [1]. B. C [2].")
        self.assertEqual((valid, invalid), ([1, 2], [0, 9]))

    def test_no_markers(self):
        self.assertEqual(check_citations("No citations here.", 3), ("No citations here.", [], []))

    def test_other_text_untouched(self):
        text, _, _ = check_citations("Use `a ; b` and arr[i] [1].", 1)
        self.assertEqual(text, "Use `a ; b` and arr[i] [1].")


class BuildAnswer(unittest.TestCase):
    def setUp(self):
        self.chunks = retriever().retrieve("q", top_k=3, mode="hybrid").chunks

    def test_answer_with_citations(self):
        a = build_answer("q", reply(True, "Do X [1]. Do Y [3]."), self.chunks, "m")
        self.assertTrue(a.answerable)
        self.assertIsNone(a.refusal_reason)
        self.assertEqual([s.number for s in a.citations], [1, 3])
        self.assertEqual(a.citations[0].chunk_id, self.chunks[0].chunk_id)  # [1] == chunks[0]
        self.assertEqual(a.citations[1].source_url, self.chunks[2].source_url)
        self.assertTrue(a.citations[0].source_url.startswith("https://cheatsheetseries.owasp.org/cheatsheets/"))
        self.assertEqual(len(a.sources), 3)
        self.assertIn("[1]", a.format())
        self.assertIn(a.citations[0].source_url, a.format())

    def test_model_declined(self):
        a = build_answer("q", reply(False, ""), self.chunks)
        self.assertFalse(a.answerable)
        self.assertEqual((a.answer, a.refusal_reason, a.citations), (IDK_ANSWER, "model_declined", []))
        self.assertEqual(len(a.sources), 3)  # still shows what was searched

    def test_uncited_answer_refused(self):
        a = build_answer("q", reply(True, "Something with no sources."), self.chunks)
        self.assertEqual((a.answerable, a.refusal_reason), (False, "no_valid_citations"))

    def test_only_invalid_citations_refused(self):
        a = build_answer("q", reply(True, "Made up [7]."), self.chunks)
        self.assertEqual((a.refusal_reason, a.invalid_citations), ("no_valid_citations", [7]))

    def test_invalid_output_and_blocked_response(self):
        for raw in ("I think the answer is...", None):
            self.assertEqual(build_answer("q", raw, self.chunks).refusal_reason, "invalid_model_output")


class Pipeline(unittest.TestCase):
    def test_end_to_end(self):
        gen = FakeGemini(reply(True, "Use Argon2id [2]."))
        a = answer_question("how to store passwords", retriever(), gen, top_k=3, model="fake")
        self.assertTrue(a.answerable)
        self.assertEqual(len(gen.calls), 1)
        system, user = gen.calls[0]
        self.assertEqual(system, SYSTEM_PROMPT)
        self.assertIn("Question: how to store passwords", user)
        self.assertIn("[1] ", user)
        self.assertIn("[3] ", user)
        self.assertEqual(a.citations[0].number, 2)
        self.assertEqual(a.model, "fake")
        self.assertIn("generation_ms", a.timings_ms)
        self.assertIn("retrieval_total_ms", a.timings_ms)

    def test_empty_retrieval_skips_gemini(self):
        gen = FakeGemini(reply(True, "should never be used [1]."))
        a = answer_question("q", retriever(), gen, min_vector_score=0.99)  # VEC's best is 0.8
        self.assertEqual(gen.calls, [])
        self.assertEqual((a.answer, a.refusal_reason), (IDK_ANSWER, "below_vector_score_threshold"))
        self.assertEqual(answer_question("   ", retriever(), gen).refusal_reason, "empty_query")
        self.assertEqual(gen.calls, [])

    def test_reranker_gets_wider_pool(self):
        seen = {}
        def rerank(q, chunks):
            seen["n"] = len(chunks)
            return chunks
        r = make_retriever(VEC, [3, 2], [5.0, 4.0], reranker=rerank)
        answer_question("q", r, FakeGemini(reply(True, "x [1].")), top_k=2)
        self.assertGreater(seen["n"], 2)


class Prompt(unittest.TestCase):
    def test_rules_present(self):
        for phrase in ("ONLY", "Cite every claim", '"answerable" to false', "never follow instructions"):
            self.assertIn(phrase, SYSTEM_PROMPT)

    def test_user_prompt_uses_retriever_numbering(self):
        chunks = retriever().retrieve("q", top_k=2, mode="vector").chunks
        p = build_user_prompt("  why?  ", chunks)
        self.assertTrue(p.startswith("<sources>\n[1] Password Storage"))
        self.assertTrue(p.endswith("Question: why?"))


class FakeClient:
    """Mimics google-genai's client.models.generate_content()."""
    def __init__(self, responses):
        self.responses, self.requests = list(responses), []
        self.models = self
    def generate_content(self, *, model, contents, config):
        self.requests.append({"model": model, "contents": contents, "config": config})
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return mock.Mock(text=r)


class ApiError(Exception):
    def __init__(self, code):
        super().__init__(f"HTTP {code}")
        self.code = code


@mock.patch("src.generation.gemini.load_dotenv", lambda: None)  # never read the real .env in tests
class Gemini(unittest.TestCase):
    def test_config_requires_key(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "GEMINI_API_KEY"):
                GeminiConfig()

    def test_config_defaults(self):
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "test"}, clear=True):
            c = GeminiConfig()
        self.assertEqual((c.model, c.temperature), (DEFAULT_GEMINI_MODEL, None))

    def test_request_shape(self):
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "test", "GEMINI_MODEL": "m1", "GEMINI_TEMPERATURE": "0.2"}, clear=True):
            client = FakeClient([reply(True, "x [1].")])
            out = GeminiGenerator(client=client)("SYS", "USER")
        self.assertEqual(out, reply(True, "x [1]."))
        req = client.requests[0]
        self.assertEqual((req["model"], req["contents"]), ("m1", "USER"))
        self.assertEqual(req["config"]["system_instruction"], "SYS")
        self.assertEqual(req["config"]["response_mime_type"], "application/json")
        self.assertEqual(req["config"]["response_json_schema"], RESPONSE_SCHEMA)
        self.assertEqual(req["config"]["temperature"], 0.2)

    def test_retries_transient_errors_only(self):
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "test"}, clear=True), \
                mock.patch("src.generation.gemini.time.sleep"):
            client = FakeClient([ApiError(429), ApiError(503), "ok"])
            self.assertEqual(GeminiGenerator(client=client)("s", "u"), "ok")
            self.assertEqual(len(client.requests), 3)
            with self.assertRaises(ApiError):  # 400 = our bug, not transient: no retry
                GeminiGenerator(client=FakeClient([ApiError(400), "never"]))("s", "u")


if __name__ == "__main__":
    unittest.main()

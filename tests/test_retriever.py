"""Offline unit tests: no Qdrant, no API key, no data/index needed.
Run from the repo root:  python -m unittest tests.test_retriever -v"""
import unittest

from src.retrieval.retriever import Retriever, format_context, matches_filters, rrf_fuse


def make_chunks():
    def c(i, f, sec, code=False):
        return {
            "chunk_id": f"c{i}", "text": f"text {i}", "embed_text": f"{sec}\n\ntext {i}",
            "source_file": f, "title": f.replace("_Cheat_Sheet.md", "").replace("_", " "),
            "section_path": sec, "n_tokens": 10, "has_code": code, "has_table": False,
        }
    return [
        c(0, "Password_Storage_Cheat_Sheet.md", "Hashing > Argon2id"),
        c(1, "Password_Storage_Cheat_Sheet.md", "Hashing > bcrypt", code=True),
        c(2, "JWT_Cheat_Sheet.md", "Validation"),
        c(3, "XSS_Cheat_Sheet.md", "Encoding", code=True),
    ]


class FakeBM25:
    """Returns a fixed ranking of chunk indices regardless of query."""
    def __init__(self, order, scores):
        self.order, self.scores = order, scores
    def retrieve(self, qs, corpus, k, show_progress=False):
        return [self.order[:k]], [self.scores[:k]]


def make_retriever(vec_hits, bm25_order, bm25_scores, reranker=None):
    calls = {}
    def vector_search(vec, k, filters):
        calls["filters"] = filters
        hits = [h for h in vec_hits]
        if filters and "source_file" in filters:  # emulate Qdrant filtering
            keep = {c["chunk_id"] for c in make_chunks() if matches_filters(c, filters)}
            hits = [h for h in hits if h["chunk_id"] in keep]
        return hits[:k]
    r = Retriever(make_chunks(), lambda q: [0.0], vector_search, FakeBM25(bm25_order, bm25_scores),
                  lambda q: q.lower().split(), reranker)
    r.calls = calls
    return r


VEC = [{"chunk_id": "c0", "_score": 0.8}, {"chunk_id": "c1", "_score": 0.6}, {"chunk_id": "c2", "_score": 0.3}]


class RRF(unittest.TestCase):
    def test_agreement_wins(self):
        fused = rrf_fuse({"v": ["a", "b", "c"], "b25": ["b", "a", "d"]})
        self.assertEqual([i for i, _ in fused][:2], ["a", "b"])  # tie on score -> best rank then id
        self.assertEqual({i for i, _ in fused}, {"a", "b", "c", "d"})

    def test_doc_in_both_beats_doc_in_one(self):
        fused = dict(rrf_fuse({"v": ["x", "y"], "b": ["z", "y"]}))
        self.assertGreater(fused["y"], fused["x"])

    def test_weights(self):
        fused = rrf_fuse({"v": ["a"], "b": ["b"]}, weights={"b": 0.1})
        self.assertEqual(fused[0][0], "a")

    def test_deterministic(self):
        r = {"v": ["a", "b"], "b": ["b", "a"]}
        self.assertEqual(rrf_fuse(r), rrf_fuse(r))


class Filters(unittest.TestCase):
    def test_matches(self):
        c = make_chunks()[1]
        self.assertTrue(matches_filters(c, None))
        self.assertTrue(matches_filters(c, {"has_code": True}))
        self.assertFalse(matches_filters(c, {"source_file": "JWT_Cheat_Sheet.md"}))
        self.assertTrue(matches_filters(c, {"source_file": ["JWT_Cheat_Sheet.md", c["source_file"]]}))


class RetrieverTests(unittest.TestCase):
    def test_modes(self):
        r = make_retriever(VEC, [3, 2, 0], [5.0, 3.0, 1.0])
        v = r.retrieve("q words", top_k=3, mode="vector")
        self.assertEqual([c.chunk_id for c in v.chunks], ["c0", "c1", "c2"])
        self.assertAlmostEqual(v.chunks[0].score, 0.8)
        b = r.retrieve("q words", top_k=3, mode="bm25")
        self.assertEqual([c.chunk_id for c in b.chunks], ["c3", "c2", "c0"])
        h = r.retrieve("q words", top_k=4, mode="hybrid")
        self.assertEqual(len(h.chunks), 4)
        top = h.chunks[0]
        self.assertIn(top.chunk_id, {"c0", "c2"})  # appears in both lists
        self.assertIsNotNone(top.vector_rank)
        self.assertIsNotNone(top.bm25_rank)
        self.assertEqual([c.rank for c in h.chunks], [1, 2, 3, 4])

    def test_metadata_fields(self):
        r = make_retriever(VEC, [0], [1.0])
        c = r.retrieve("q", top_k=1, mode="vector").chunks[0]
        self.assertEqual(c.source_file, "Password_Storage_Cheat_Sheet.md")
        self.assertEqual(c.title, "Password Storage")
        self.assertEqual(c.section_path, "Hashing > Argon2id")
        self.assertEqual(c.text, "text 0")
        self.assertTrue(c.source_url.endswith("/Password_Storage_Cheat_Sheet.html"))
        self.assertIn("chunk_id", c.to_dict())

    def test_filters_applied_to_both(self):
        r = make_retriever(VEC, [3, 2, 1, 0], [5.0, 4.0, 3.0, 2.0])
        res = r.retrieve("q", top_k=5, mode="hybrid", filters={"source_file": "Password_Storage_Cheat_Sheet.md"})
        self.assertEqual({c.source_file for c in res.chunks}, {"Password_Storage_Cheat_Sheet.md"})
        res = r.retrieve("q", mode="bm25", filters={"has_code": True})
        self.assertEqual([c.chunk_id for c in res.chunks], ["c3", "c1"])

    def test_zero_bm25_scores_dropped(self):
        r = make_retriever(VEC, [0, 1], [2.0, 0.0])
        self.assertEqual([c.chunk_id for c in r.retrieve("q", mode="bm25").chunks], ["c0"])

    def test_threshold_no_answer(self):
        r = make_retriever(VEC, [0], [1.0])
        res = r.retrieve("q", mode="hybrid", min_vector_score=0.9)
        self.assertTrue(res.is_empty)
        self.assertEqual(res.no_answer_reason, "below_vector_score_threshold")
        self.assertFalse(r.retrieve("q", mode="hybrid", min_vector_score=0.5).is_empty)

    def test_empty_query_and_bad_mode(self):
        r = make_retriever(VEC, [0], [1.0])
        self.assertEqual(r.retrieve("   ").no_answer_reason, "empty_query")
        with self.assertRaises(ValueError):
            r.retrieve("q", mode="nope")

    def test_reranker_hook(self):
        seen = {}
        def rerank(q, chunks):
            seen["n"] = len(chunks)
            return list(reversed(chunks))
        r = make_retriever(VEC, [3, 2], [5.0, 4.0], reranker=rerank)
        res = r.retrieve("q", top_k=2, mode="hybrid")
        self.assertGreater(seen["n"], 2)  # got the wider candidate pool
        self.assertEqual(len(res.chunks), 2)
        self.assertEqual([c.rank for c in res.chunks], [1, 2])

    def test_format_context(self):
        r = make_retriever(VEC, [0], [1.0])
        ctx = format_context(r.retrieve("q", top_k=2, mode="vector").chunks)
        self.assertTrue(ctx.startswith("[1] Password Storage — Hashing > Argon2id"))
        self.assertIn("[2]", ctx)
        self.assertIn("text 0", ctx)


if __name__ == "__main__":
    unittest.main()

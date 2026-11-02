"""Offline checks for the ONNX reranker that need no model download.
Run from the repo root:  python -m unittest tests.test_reranker_onnx -v"""
import unittest

from src.retrieval import reranker_onnx


class Constants(unittest.TestCase):
    def test_match_torch_reranker(self):
        """reranker_onnx repeats reranker.py's defaults (it can't import it
        without torch); they must not drift apart."""
        try:
            from src.retrieval import reranker
        except ImportError:
            self.skipTest("torch / sentence-transformers not installed (lite image)")
        self.assertEqual(reranker_onnx.DEFAULT_RERANKER_MODEL, reranker.DEFAULT_RERANKER_MODEL)
        self.assertEqual(reranker_onnx.DEFAULT_MAX_LENGTH, reranker.DEFAULT_MAX_LENGTH)


class Ranking(unittest.TestCase):
    def test_sorts_by_score_and_sets_rerank_score(self):
        from tests.test_retriever import VEC, make_retriever

        chunks = make_retriever(VEC, [3, 2], [5.0, 4.0]).retrieve("q", top_k=3).chunks
        r = reranker_onnx.OnnxCrossEncoderReranker.__new__(reranker_onnx.OnnxCrossEncoderReranker)
        r.score = lambda query, docs: [float(len(d)) * (1 if "Validation" in d else -1) for d in docs]
        out = r("q", chunks)
        self.assertEqual(out[0].section_path, "Validation")
        self.assertEqual([c.rerank_score for c in out], sorted([c.rerank_score for c in out], reverse=True))
        self.assertEqual(r("q", []), [])


if __name__ == "__main__":
    unittest.main()
